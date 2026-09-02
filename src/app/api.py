"""Flask API Server for Biology RAG"""

import json
import logging
import os
import threading
from pathlib import Path

import torch
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from transformers import TextIteratorStreamer
from werkzeug.utils import secure_filename

from src.config import (DATA_DIR, IMAGES_DIR, LLM_MAX_NEW_TOKENS, LLM_TEMPERATURE,
                        LLM_TOP_P, MULTIMODAL_CONTEXT_ENABLED)
from src.app.dependencies import AppServices
from src.etl.image_review import ImageReviewManager
from src.rag.citations import (build_citations, format_book_name,
                               format_citations_block, is_fallback_answer)
from src.rag.multimodal_context import build_context

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# In-memory status tracker for ETL polling
etl_status = {}


def sse_event(event, payload):
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def image_url_for(stored_path):
    """Đường dẫn ẢNH mà trình duyệt gọi được, suy từ đường dẫn đã lưu trong chỉ mục.

    ETL lưu `image_path` là đường dẫn TUYỆT ĐỐI trên máy đã chạy ETL
    (`D:\\personal_repo\\...\\database\\images\\SGK_KHTN_7_CTST\\page_108_img_0.png`).
    Trả nguyên nó ra API là vô dụng với mọi máy khác — và còn lộ bố cục ổ đĩa của
    máy phát triển. Hàm này quy nó về đường dẫn TƯƠNG ĐỐI dưới `IMAGES_DIR`, khớp
    đúng route `/images/<path:filename>` mà chính server này đã phục vụ sẵn.

    Nhờ vậy **không cần chép 4,6 GB ảnh sang frontend**: frontend chỉ việc nối
    địa chỉ máy chủ vào trước. Chép ảnh sang frontend là cách sai — mỗi lần ETL
    dựng lại kho ảnh (đã xảy ra 3 lần trong tháng 8) là một lần bản sao lệch đi,
    và ảnh thiếu thì không có gì báo.

    Trả về chuỗi rỗng khi không quy được, KHÔNG đoán — một `<img>` hỏng còn hơn
    một đường dẫn trỏ nhầm sang ảnh của bài khác.
    """
    raw = str(stored_path or "").strip()
    if not raw:
        return ""
    # Đường dẫn có thể mang dấu phân cách của HĐH khác (chỉ mục dựng trên Windows,
    # server có thể chạy trên Linux/Colab), nên chuẩn hoá trước khi so.
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/images/"):
        return normalized                      # đã là URL rồi

    marker = "/database/images/"
    if marker in normalized:
        return "/images/" + normalized.split(marker, 1)[1].lstrip("/")

    try:
        relative = Path(raw).resolve().relative_to(Path(IMAGES_DIR).resolve())
    except (ValueError, OSError):
        return ""
    return "/images/" + relative.as_posix()


def build_gallery_items(image_docs):
    gallery_items = []
    for doc in image_docs:
        if hasattr(doc, "metadata"):
            metadata = doc.metadata or {}
            page = metadata.get("page_number", "?")
            pdf = metadata.get("pdf_filename", "Sách Giáo Khoa")
            book = format_book_name(pdf)

            caption = metadata.get("caption") or ""
            figure_caption = metadata.get("figure_caption") or ""
            figure_label = metadata.get("figure_label") or ""
            context_text = metadata.get("context_text") or ""
            fallback_text = (doc.page_content or "").splitlines()[0] if doc.page_content else ""
            label_text = figure_caption or figure_label or caption or context_text or fallback_text

            label = f"{label_text[:80]}... (Trang {page}, {pdf})" if label_text else f"Trang {page} - {pdf}"

            url = image_url_for(metadata.get("image_path", ""))
            gallery_items.append({
                # `image_path` GIỮ TÊN CŨ nhưng nay mang giá trị tương đối, nên
                # frontend cũ (vốn tự cắt chuỗi ở "/database/images/") vẫn chạy.
                "image_path": url,
                "image_url": url,
                "label": label,
                # Ba trường dưới đây đều ĐỌC LẠI TỪ ĐIỂM ẢNH của trang gốc, không
                # do mô hình sinh (D-47) — nên frontend hiển thị được chú thích
                # thật thay vì phải tự cắt chuỗi `label`.
                "figure_label": figure_label,
                "figure_caption": figure_caption,
                "page": page,
                "book": book,
                "metadata": metadata,
            })
    return gallery_items


def prepare_chat_payload(question):
    services = AppServices.get_instance()
    result = services.hybrid_retriever.search(question)
    text_docs = result.text_docs
    image_docs = result.image_docs
    image_only_query = result.image_only_query
    gallery_items = build_gallery_items(image_docs)

    if not text_docs and not image_docs:
        if image_only_query:
            return {
                "mode": "static",
                "answer": "Không tìm thấy hình ảnh liên quan trong cơ sở dữ liệu ảnh.",
                "images": gallery_items,
                "citations": [],
                "services": services,
            }
        return {
            "mode": "static",
            "answer": "Hệ thống chưa tìm thấy tài liệu nào liên quan đến câu hỏi này.",
            "images": gallery_items,
            "citations": [],
            "services": services,
        }

    if image_only_query:
        return {
            "mode": "static",
            "answer": f"Mình tìm thấy {len(image_docs)} hình ảnh liên quan trong cơ sở dữ liệu ảnh.",
            "images": gallery_items,
            "citations": [],
            "services": services,
        }

    if not text_docs:
        return {
            "mode": "static",
            "answer": "Không tìm thấy thông tin dạng văn bản liên quan. Vui lòng thử câu hỏi khác.",
            "images": gallery_items,
            "citations": [],
            "services": services,
        }

    # Ngữ cảnh ĐA PHƯƠNG THỨC (Mục tiêu 4, cấu hình 2). Cờ TẮT -> chuỗi y hệt
    # hành vi cũ; cờ BẬT -> nối thêm nhãn + chú thích hình đọc DETERMINISTIC từ
    # pill/OCR. Kho ảnh rỗng thì hai nhánh cho ra cùng một chuỗi (test khoá lại),
    # nên bảng ablation không đo lẫn một nhánh ẩn.
    context_str = build_context(
        [doc for doc in text_docs if hasattr(doc, "page_content")],
        image_docs,
        multimodal=MULTIMODAL_CONTEXT_ENABLED)

    return {
        "mode": "llm",
        "formatted_prompt": services.rag.prompt.format(context=context_str, question=question),
        "citations": build_citations(text_docs),
        "images": gallery_items,
        "services": services,
    }


def append_citations(answer, citations):
    if is_fallback_answer(answer) or not citations:
        return answer
    block = format_citations_block(citations)
    return f"{answer}\n\n{block}" if block else answer


def chat_response_body(answer_text, citations, images):
    """Thân phản hồi dùng chung cho `/api/chat` và sự kiện `done` của SSE.

    Ba trường, cố ý dư một chút để không bắt phía gọi phải tự tách chuỗi:

    - `answer`      — nguyên như trước: câu trả lời KÈM khối "📚 Nguồn:" dạng chữ.
                      Giữ lại để không phá bất kỳ phía gọi cũ nào.
    - `answer_text` — câu trả lời KHÔNG có khối nguồn.
    - `citations`   — danh sách nguồn có CẤU TRÚC (`book` / `page` / `section` /
                      `display`).

    Vì sao phải có `citations` riêng: trích dẫn ở hệ này là **xác định**, dựng từ
    metadata của chính đoạn văn bản được truy xuất chứ không do mô hình sinh
    (nguyên tắc 1). Nhưng trước hôm nay API chỉ **chèn nó vào giữa câu trả lời**,
    nên phía giao diện muốn hiển thị tử tế thì phải đi cắt chuỗi tiếng Việt —
    và trên thực tế đã không làm, tức bảo đảm quan trọng nhất của hệ thống không
    tới được mắt học sinh.
    """
    # `append_citations` đã ẩn khối trích dẫn dạng chữ khi câu trả lời là
    # fallback ("...không được đề cập..."), nhưng trường `citations` có cấu
    # trúc — thứ FE thực sự render thành chip — trước bản vá này KHÔNG được lọc
    # theo cùng điều kiện. Đo thật 2026-09-02: câu "bài 8 sgk 9 cánh diều dạy
    # bài gì" trả lời fallback đúng nhưng vẫn hiện 3 chip nguồn sai (CD7 tr.2,
    # KNTT7 tr.8, CD8 tr.179) — học sinh đọc chip trước khi đọc câu trả lời.
    effective_citations = [] if is_fallback_answer(answer_text) else (citations or [])
    return {
        "answer": append_citations(answer_text, citations),
        "answer_text": answer_text,
        "citations": effective_citations,
        "images": images,
    }


def stream_static_answer(answer):
    for word in answer.split(" "):
        yield f"{word} "


def stream_llm_text(services, formatted_prompt):
    model_pipeline = getattr(services.llm, "pipeline", None)
    if model_pipeline is None:
        yield str(services.llm.invoke(formatted_prompt))
        return

    tokenizer = model_pipeline.tokenizer
    model = model_pipeline.model
    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
    )
    inputs = tokenizer(formatted_prompt, return_tensors="pt")
    device = getattr(model, "device", None)
    if device is not None:
        inputs = {key: value.to(device) for key, value in inputs.items()}

    eos_token_id = tokenizer.eos_token_id
    pad_token_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos_token_id
    generation_kwargs = {
        **inputs,
        "streamer": streamer,
        "max_new_tokens": LLM_MAX_NEW_TOKENS,
        "do_sample": True,
        "temperature": LLM_TEMPERATURE,
        "top_p": LLM_TOP_P,
        "pad_token_id": pad_token_id,
        "eos_token_id": eos_token_id,
    }
    generation_error = {}

    def generate():
        try:
            with torch.inference_mode():
                model.generate(**generation_kwargs)
        except Exception as exc:
            generation_error["error"] = exc
            if hasattr(streamer, "on_finalized_text"):
                streamer.on_finalized_text("", stream_end=True)

    thread = threading.Thread(target=generate)
    thread.start()
    for text in streamer:
        if text:
            yield text
    thread.join()

    if generation_error:
        raise generation_error["error"]


def create_chat_stream_response(question):
    def generate_events():
        try:
            yield sse_event("status", {"type": "status", "stage": "retrieving"})
            payload = prepare_chat_payload(question)

            if payload["mode"] == "static":
                answer = payload["answer"]
                yield sse_event("status", {"type": "status", "stage": "answering"})
                for chunk in stream_static_answer(answer):
                    yield sse_event("answer_delta", {"type": "answer_delta", "delta": chunk})
                yield sse_event("done", {
                    "type": "done",
                    **chat_response_body(answer, payload["citations"], payload["images"]),
                })
                return

            yield sse_event("status", {"type": "status", "stage": "answering"})
            chunks = []
            for chunk in stream_llm_text(payload["services"], payload["formatted_prompt"]):
                chunks.append(chunk)
                yield sse_event("answer_delta", {"type": "answer_delta", "delta": chunk})

            parsed_answer = payload["services"].rag.answer_parser.parse("".join(chunks))
            yield sse_event("done", {
                "type": "done",
                **chat_response_body(parsed_answer, payload["citations"], payload["images"]),
            })
        except Exception as e:
            logger.error(f"Error streaming answer: {e}", exc_info=True)
            yield sse_event("error", {"type": "error", "error": str(e)})

    return Response(
        stream_with_context(generate_events()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

def run_etl_background(filename):
    from main import run_etl  # Import locally to avoid circular dependency
    etl_status[filename] = {"status": "processing", "message": "ETL pipeline is running"}
    try:
        run_etl()
        etl_status[filename] = {"status": "completed", "message": "ETL completed successfully"}
    except Exception as e:
        logger.error(f"ETL failed for {filename}: {e}")
        etl_status[filename] = {"status": "error", "message": str(e)}

@app.route('/api/etl', methods=['POST'])
def upload_and_etl():
    """Upload a PDF and trigger ETL process."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)
        os.makedirs(DATA_DIR, exist_ok=True)
        filepath = os.path.join(DATA_DIR, filename)
        file.save(filepath)
        
        # Start ETL in background
        thread = threading.Thread(target=run_etl_background, args=(filename,))
        thread.start()
        
        return jsonify({"message": f"File {filename} uploaded successfully. ETL started in background.", "filename": filename}), 202
    return jsonify({"error": "Only PDF files are allowed"}), 400

@app.route('/api/etl/status', methods=['GET'])
def get_etl_status():
    """Check ETL status for a given PDF filename."""
    filename = request.args.get('filename')
    if not filename:
        return jsonify({"error": "Filename parameter is required"}), 400
    
    status_info = etl_status.get(filename)
    if not status_info:
        # Check if it was already processed before server start
        try:
            from main import get_processed_files, get_processed_images
            text_done = filename in get_processed_files()
            image_done = filename in get_processed_images()
            if text_done and image_done:
                return jsonify({"status": "completed", "message": "File was already processed."}), 200
        except Exception as e:
            logger.warning(f"Failed to check processed files: {e}")
            
        return jsonify({"status": "not_found", "message": "No ETL task found for this file."}), 404
        
    return jsonify(status_info), 200

@app.route('/api/chat', methods=['POST'])
def chat():
    """Chat endpoint for RAG retrieval."""
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({"error": "Question is required"}), 400
    
    question = data['question']
    if data.get("stream") is True:
        return create_chat_stream_response(question)
    
    try:
        payload = prepare_chat_payload(question)
        citations = payload["citations"]
        if payload["mode"] == "static":
            answer = payload["answer"]
        else:
            try:
                llm_response = payload["services"].llm.invoke(payload["formatted_prompt"])
                answer = payload["services"].rag.answer_parser.parse(llm_response)
            except Exception as e:
                logger.error(f"RAG chain failed: {e}")
                answer = "Xin lỗi, đã xảy ra lỗi khi tạo câu trả lời."
                citations = []

        return jsonify(chat_response_body(answer, citations, payload["images"]))
        
    except Exception as e:
        logger.error(f"Error answering question: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """Stream chat answer chunks through Server-Sent Events."""
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({"error": "Question is required"}), 400

    return create_chat_stream_response(data['question'])

@app.route('/api/images', methods=['GET'])
def get_images():
    """Retrieve full image database snapshot."""
    pdf_filename = request.args.get('pdf_filename')
    manager = ImageReviewManager()
    try:
        snapshot = manager.get_db_snapshot(pdf_filename=pdf_filename)
        return jsonify(snapshot), 200
    except Exception as e:
        logger.error(f"Error fetching images: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/images', methods=['PUT', 'POST'])
def update_images():
    """Replace image database from a JSON array payload."""
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "Payload must be a JSON array"}), 400
        
    reviewed_by = request.args.get('reviewed_by', 'react-frontend')
    manager = ImageReviewManager()
    
    try:
        summary = manager.replace_image_db_from_payload(payload=data, reviewed_by=reviewed_by)
        return jsonify(summary), 200
    except Exception as e:
        logger.error(f"Error replacing image db: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve static images from the database."""
    return send_from_directory(str(IMAGES_DIR), filename)


@app.route('/api/health', methods=['GET'])
def health():
    """Cho biết server đã nạp xong mô hình CHƯA, và kho có bao nhiêu vector.

    Cần thiết vì lượt khởi động nạp bge-m3 + CLIP + Qwen2.5 mất khoảng nửa phút
    trên CPU: cổng 5000 mở trước khi mô hình sẵn sàng thì một `curl` sớm sẽ báo
    "chạy rồi" trong khi câu hỏi đầu tiên vẫn lỗi. Endpoint này chỉ trả 200 sau
    khi `AppServices` dựng xong, nên script khởi động chờ đúng thứ cần chờ.
    """
    services = AppServices.get_instance()
    try:
        so_chunk = services.hybrid_retriever.text_db.db._collection.count()
    except Exception:                                    # pragma: no cover
        so_chunk = None
    try:
        so_anh = services.hybrid_retriever.image_db._chroma._collection.count()
    except Exception:                                    # pragma: no cover
        so_anh = None
    return jsonify({
        "status": "ok",
        "text_chunks": so_chunk,
        "image_docs": so_anh,
        "images_dir": str(IMAGES_DIR),
        "retrieval_mode": os.getenv("RETRIEVAL_MODE", "hybrid"),
    }), 200

def run_api(host='0.0.0.0', port=5000):
    logger.info("Initializing AppServices before starting Flask...")
    AppServices.get_instance()
    logger.info(f"Starting Flask API server on {host}:{port}...")
    app.run(host=host, port=port, debug=False)
