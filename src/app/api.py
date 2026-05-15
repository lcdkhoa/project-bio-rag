"""Flask API Server for Biology RAG"""

import logging
import os
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

from src.config import DATA_DIR
from src.app.dependencies import AppServices
from src.etl.image_review import ImageReviewManager

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# In-memory status tracker for ETL polling
etl_status = {}

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
    services = AppServices.get_instance()
    
    try:
        result = services.hybrid_retriever.search(question)
        text_docs = result.text_docs
        image_docs = result.image_docs
        
        if not text_docs and not image_docs:
            return jsonify({
                "answer": "Hệ thống chưa tìm thấy tài liệu nào liên quan đến câu hỏi này.",
                "images": []
            })
            
        if text_docs:
            context_texts = [doc.page_content for doc in text_docs if hasattr(doc, "page_content")]
            context_str = "\n\n".join(context_texts)
            
            citations = set()
            for doc in text_docs:
                source = doc.metadata.get("source", "Sách Giáo Khoa") if hasattr(doc, "metadata") else "Sách Giáo Khoa"
                page = doc.metadata.get("page", "?") if hasattr(doc, "metadata") else "?"
                citations.add(f"Trang {page} - {source}")
            citations_str = " | ".join(sorted(citations))
            
            try:
                formatted_prompt = services.rag.prompt.format(context=context_str, question=question)
                llm_response = services.llm.invoke(formatted_prompt)
                parsed_answer = services.rag.answer_parser.parse(llm_response)
                answer = parsed_answer
            except Exception as e:
                logger.error(f"RAG chain failed: {e}")
                answer = "Xin lỗi, đã xảy ra lỗi khi tạo câu trả lời."
                
            if "không được đề cập" not in answer.lower() and citations_str:
                answer = f"{answer}\n\n📚 Thông tin được tham khảo từ: {citations_str}"
        else:
            answer = "Không tìm thấy thông tin dạng văn bản liên quan. Vui lòng thử câu hỏi khác."
            
        gallery_items = []
        for doc in image_docs:
            if hasattr(doc, "metadata"):
                image_path = doc.metadata.get("image_path", "")
                page = doc.metadata.get("page_number", "?")
                pdf = doc.metadata.get("pdf_filename", "Sách Giáo Khoa")
                
                caption = doc.metadata.get("caption") or ""
                figure_caption = doc.metadata.get("figure_caption") or ""
                figure_label = doc.metadata.get("figure_label") or ""
                context_text = doc.metadata.get("context_text") or ""
                fallback_text = (doc.page_content or "").splitlines()[0] if doc.page_content else ""
                label_text = figure_caption or figure_label or caption or context_text or fallback_text
                
                label = f"{label_text[:80]}... (Trang {page}, {pdf})" if label_text else f"Trang {page} - {pdf}"
                
                gallery_items.append({
                    "image_path": image_path,
                    "label": label,
                    "metadata": doc.metadata
                })
                
        return jsonify({
            "answer": answer,
            "images": gallery_items
        })
        
    except Exception as e:
        logger.error(f"Error answering question: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

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

def run_api(host='0.0.0.0', port=5000):
    logger.info("Initializing AppServices before starting Flask...")
    AppServices.get_instance()
    logger.info(f"Starting Flask API server on {host}:{port}...")
    app.run(host=host, port=port, debug=False)
