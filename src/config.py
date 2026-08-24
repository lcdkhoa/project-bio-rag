"""
Configuration module for Biology RAG project.
Loads environment variables and provides shared configuration.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _path_from_env(env_name: str, default: Path, base_dir: Path = PROJECT_ROOT) -> Path:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return default

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _database_child_path_from_env(env_name: str, default: Path) -> Path:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return default

    path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path.resolve()

    parts = path.parts
    if parts and parts[0].lower() == "database":
        path = Path(*parts[1:]) if len(parts) > 1 else Path()
    return (PERSIST_DIR / path).resolve()


DATA_DIR = _path_from_env("RAG_DATA_DIR", PROJECT_ROOT / "datasources")
PERSIST_DIR = _path_from_env("RAG_DATABASE_DIR", PROJECT_ROOT / "database")
IMAGES_DIR = PERSIST_DIR / "images"
# BookManifest. Tách khỏi PERSIST_DIR được, vì trên Colab thường DB nằm ở Google
# Drive (`RAG_DATABASE_DIR`) trong khi manifest đi theo repo — không phải copy tay.
MANIFEST_DIR = _path_from_env("RAG_MANIFEST_DIR", PERSIST_DIR / "manifests")
# Layout fingerprint M0 (D-65). Mặc định đi theo REPO chứ không theo PERSIST_DIR:
# nó là KẾT QUẢ ĐO đã commit (một lượt đo lại tốn ~70 phút OCR cho 12 quyển), cùng
# lý do như MANIFEST_DIR. Trước đây là `Path("database/fingerprints")` viết cứng
# trong `book/fingerprint.py` — đường dẫn TƯƠNG ĐỐI, nên chạy từ thư mục khác
# repo root là ghi/đọc sai chỗ mà không báo gì (D-69).
FINGERPRINT_DIR = _path_from_env("RAG_FINGERPRINT_DIR",
                                 PROJECT_ROOT / "database" / "fingerprints")
PROCESSED_FILES_LOG = PERSIST_DIR / "processed_files.txt"
PROCESSED_IMAGES_LOG = PERSIST_DIR / "processed_images.txt"

HF_TOKEN = os.getenv("HF_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

USE_GPU = os.getenv("USE_GPU", "true").lower() == "true"


def embedding_model_kwargs() -> dict:
    """model_kwargs for HuggingFaceEmbeddings, shared by every embedder.

    Puts the model on CUDA when USE_GPU is set AND a GPU is actually present
    (so a Colab GPU run embeds fast, while a Windows/CPU box silently stays on
    CPU instead of crashing on a missing CUDA device).
    """
    kwargs: dict = {}
    if HF_TOKEN:
        kwargs["token"] = HF_TOKEN
    if USE_GPU:
        try:
            import torch
            if torch.cuda.is_available():
                kwargs["device"] = "cuda"
        except Exception:
            pass
    return kwargs


TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract").strip() or "tesseract"
POPPLER_PATH = os.getenv("POPPLER_PATH", "").strip() or None

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-3B-Instruct")
CLIP_MODEL = os.getenv("CLIP_MODEL", "openai/clip-vit-base-patch16")
OWL_VIT_MODEL = os.getenv("OWL_VIT_MODEL", "google/owlvit-base-patch32")
OWL_VIT_CONFIDENCE_THRESHOLD = float(
    os.getenv("OWL_VIT_CONFIDENCE_THRESHOLD", "0.1"))
IMAGE_EXTRACTION_VERSION = os.getenv(
    "IMAGE_EXTRACTION_VERSION", "v19_pill_kernels")
# Gate re-OCR cho ĐƯỜNG TEXT. Trước đây chỉ ảnh có version gate nên đổi logic
# OCR không ép re-OCR được (spec Task 1). Bump giá trị này = ép OCR lại tất cả.
TEXT_EXTRACTION_VERSION = os.getenv(
    "TEXT_EXTRACTION_VERSION", "v2_bai_spine")
# TẮT theo mặc định vì ĐÃ ĐO, không phải vì chưa làm (D-47). Vintern-1B chạy
# được (đường InternVL đã sửa trong image_captioner.py) nhưng trên 12 crop thật:
# 4/12 caption BỊA chi tiết không có trong ảnh, 0/4 số hiệu hình do model tự nêu
# là đúng, JSON parse 6/12, và 17,6 s/crop trên CPU (~4,8 h cho ~976 crop). Phần
# duy nhất đáng tin là chữ nó OCR lại từ chính crop — thứ pipeline đã có
# deterministic (pill.py + anchor caption). Bật lại chỉ khi đo được cải thiện.
IMAGE_CAPTION_ENABLED = os.getenv(
    "IMAGE_CAPTION_ENABLED", "false").lower() == "true"
IMAGE_CAPTION_MODEL = os.getenv(
    "IMAGE_CAPTION_MODEL",
    "5CD-AI/Vintern-1B-v2",
)
IMAGE_CAPTION_MAX_NEW_TOKENS = int(
    os.getenv("IMAGE_CAPTION_MAX_NEW_TOKENS", "96"))
# Vintern-1B là InternVL: ảnh được cắt thành các ô 448x448 theo tỉ lệ khung
# (dynamic patches) + 1 thumbnail. Số ô càng nhiều càng nét nhưng chi phí tăng
# gần như tuyến tính (mỗi ô = 256 token ảnh). Trên CPU đây là tham số chi phí
# quan trọng nhất, nên để cấu hình được và ĐO trước khi đổi.
IMAGE_CAPTION_MAX_PATCHES = int(
    os.getenv("IMAGE_CAPTION_MAX_PATCHES", "6"))
IMAGE_CAPTION_CACHE_PATH = _database_child_path_from_env(
    "IMAGE_CAPTION_CACHE_PATH",
    PERSIST_DIR / "image_caption_cache.json",
)
IMAGE_REVIEW_MANIFEST_PATH = _database_child_path_from_env(
    "IMAGE_REVIEW_MANIFEST_PATH",
    PERSIST_DIR / "image_review_manifest.jsonl",
)

TEXT_COLLECTION_NAME = "biology_text"
IMAGE_COLLECTION_NAME = "biology_images"
IMAGE_METADATA_COLLECTION_NAME = "biology_image_metadata"
STATUS_COLLECTION_NAME = "processing_status"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 120

LLM_TEMPERATURE = 0.1
LLM_MAX_NEW_TOKENS = 500
LLM_TOP_P = 0.75

RETRIEVER_K = 3
# How many candidates to pull from the vector store before relevance gating.
RETRIEVER_FETCH_K = int(os.getenv("RETRIEVER_FETCH_K", "8"))
# Max chunks kept after gating (upper bound on context size).
RETRIEVER_MAX_K = int(os.getenv("RETRIEVER_MAX_K", "4"))
# Relative distance gate: keep a chunk only if its distance is within
# (1 + margin) * best_distance. Drops off-topic chunks that are far from the
# best match (e.g. unrelated pages bleeding into the answer).
RETRIEVER_DISTANCE_MARGIN = float(os.getenv("RETRIEVER_DISTANCE_MARGIN", "0.3"))
IMAGE_RETRIEVER_K = int(os.getenv("IMAGE_RETRIEVER_K", "5"))
IMAGE_RETRIEVER_FETCH_K = int(os.getenv("IMAGE_RETRIEVER_FETCH_K", "48"))
IMAGE_METADATA_FETCH_K = int(os.getenv("IMAGE_METADATA_FETCH_K", "64"))
IMAGE_RELEVANCE_THRESHOLD = float(
    os.getenv("IMAGE_RELEVANCE_THRESHOLD", "0.36"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Nhịp log tiến trình của các vòng lặp ETL dài (index text/OCR/crop hình). Log
# bắn khi TỚI ĐỦ số trang HOẶC quá số giây — cái nào đến trước — nên một pha
# chậm bất thường vẫn có dấu hiệu sống trong <= PROGRESS_LOG_EVERY_SECONDS giây.
PROGRESS_LOG_EVERY_PAGES = int(os.getenv("PROGRESS_LOG_EVERY_PAGES", "10"))
PROGRESS_LOG_EVERY_SECONDS = float(
    os.getenv("PROGRESS_LOG_EVERY_SECONDS", "30"))

# --- Layout-aware ETL (M1) ---
# Không có RENDER_DPI: nguồn là PNG một file/trang, không có bước render nào để
# tinh chỉnh (D-33). Đường PDF upload legacy dùng hằng số riêng trong
# `src/etl/page_source.py`.
# HSV saturation floor for detecting colored sidebar/info boxes (0-255).
LAYOUT_BOX_MIN_SATURATION = int(os.getenv("LAYOUT_BOX_MIN_SATURATION", "45"))
# Min area fraction of the page for a colored region to count as a box.
LAYOUT_BOX_MIN_AREA_FRAC = float(os.getenv("LAYOUT_BOX_MIN_AREA_FRAC", "0.02"))
# Kiểm tra âm tiết tiếng Việt -> CHỈ gắn cờ `needs_review` trên chunk, không
# sửa ký tự nào (D-34, thay cho DIACRITIC_FIX_ENABLED của D-09).
DIACRITIC_REVIEW_ENABLED = os.getenv(
    "DIACRITIC_REVIEW_ENABLED", "true").lower() == "true"

# --- M3: figure extraction (layout reconcile) ---
# Drop a FIGURE region only when this fraction of its area lies inside a
# segmenter colour box (sidebar/info-box). Containment (intersection / figure
# area), NOT symmetric IoU — a large box must not dilute the signal. High +
# drop-only so a radial figure with coloured icons is never eaten.
FIGURE_IN_BOX_DROP_RATIO = float(os.getenv("FIGURE_IN_BOX_DROP_RATIO", "0.80"))

# --- M2: reranker + citation ---
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
# Candidates pulled from the vector store before cross-encoder reranking.
RERANK_FETCH_K = int(os.getenv("RERANK_FETCH_K", "20"))
# Absolute safety gate on the rerank score (0..1): a chunk below this is
# dropped so an all-irrelevant fetch yields no context (LLM emits fallback).
RERANK_SCORE_MIN = float(os.getenv("RERANK_SCORE_MIN", "0.2"))
# Image side: cross-encoder is an additive term over the manual fusion score.
IMAGE_RERANK_ENABLED = os.getenv("IMAGE_RERANK_ENABLED", "true").lower() == "true"
IMAGE_RERANK_TOP_N = int(os.getenv("IMAGE_RERANK_TOP_N", "12"))
IMAGE_RERANK_WEIGHT = float(os.getenv("IMAGE_RERANK_WEIGHT", "0.25"))

# --- M2: kênh THƯA (BM25) + hợp nhất thưa/dày (D-76..) ---------------------
# Đề cương Nội dung 2 đòi "kết hợp tìm kiếm theo từ khóa (BM25) và tìm kiếm ngữ
# nghĩa dày đặc"; Nội dung 4 + bảng Kế hoạch Giai đoạn 3 đòi so BA cấu hình
# "BM25 thuần vs Vector Retrieval vs Hybrid", nhân với ablation bật/tắt
# re-ranking và cổng lọc liên quan -> 3 x 2 x 2 = 12 cấu hình.
#
# Mặc định `hybrid` — ĐỔI NGÀY 2026-08-24 SAU KHI CÓ SỐ, không phải theo đề cương
# (D-82). Đo trên **300 câu / 12 quyển** ở ĐÚNG bề rộng production (20 ứng
# viên/kênh, tức `RERANK_FETCH_K`/`BM25_FETCH_K`), rerank bật, cổng lọc tắt:
#     hybrid  R@1 0,717 · R@3 0,887 · R@5 0,923 · R@10 **0,977** · MRR **0,808**
#     bm25    R@1 0,707 · R@3 0,873 · R@5 0,920 · R@10 0,960 · MRR 0,796
#     dense   R@1 0,710 · R@3 0,860 · R@5 0,903 · R@10 0,957 · MRR 0,794
# Hybrid thắng ở MỌI cột. Quan trọng: ở bề rộng ĐO (50/kênh) biên độ chỉ +0,005
# MRR — nằm trong nhiễu — nhưng ở bề rộng THẬT (20) nó là **+0,014 MRR và +0,020
# R@10**. Cửa sổ càng hẹp thì hai kênh bù nhau càng đáng giá. Chốt mặc định dựa
# trên bảng đo ở 50 mà đem chạy ở 20 là khuyến nghị cho một cấu hình KHÁC.
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid").lower()
_RETRIEVAL_MODES = ("dense", "bm25", "hybrid")
if RETRIEVAL_MODE not in _RETRIEVAL_MODES:
    raise ValueError(
        f"RETRIEVAL_MODE={RETRIEVAL_MODE!r} không hợp lệ, phải là một trong "
        f"{_RETRIEVAL_MODES}")

# Chỉ mục thưa nằm cạnh index dày nhưng là artefact SINH RA ĐƯỢC (dựng lại bằng
# `python main.py --build-bm25`), không phải nguồn dữ liệu.
SPARSE_INDEX_DIR = _path_from_env("RAG_SPARSE_INDEX_DIR", PERSIST_DIR / "sparse")

# `k1`/`b` mặc định của Okapi/Lucene. HAI SỐ NÀY PHẢI ĐƯỢC CHỌN BẰNG PHÉP QUÉT
# (`scripts/run_ablation.ps1` / `src/test/bm25_sweep.py`), không phải bằng mặc
# định của thư viện — BM25 rất nhạy với chúng.
# ĐÃ QUÉT (100 câu, index 12 quyển, tokenizer=plain): lưới 5x5
# k1 ∈ {0.5,0.7,0.9,1.2,1.5} x b ∈ {0,0.15,0.3,0.5,0.75}, cả bảng nằm trong
# decision log. Ô thắng **k1=0.7, b=0.75** (MRR 0,820 · R@1 0,760 · R@10 0,950);
# ô tệ nhất MRR 0,764 -> mặt tối ưu KHÁ PHẲNG, k1/b đáng chọn nhưng không phải
# thứ quyết định. Lưới ban đầu {0.9,1.2,1.5}x{0.3,0.5,0.75} cho ô thắng nằm ĐÚNG
# BIÊN nên phải nới ra mới biết là đỉnh hay là tường; ô thắng cuối nằm trong lòng
# lưới. Đổi `BM25_TOKENIZER` thì PHẢI quét lại: trên "folded" ô thắng là
# k1=0.7, b=0.30 — tối ưu của một cấu hình khác.
BM25_K1 = float(os.getenv("BM25_K1", "0.7"))
BM25_B = float(os.getenv("BM25_B", "0.75"))
# "plain" = GIỮ dấu, "folded" = bỏ dấu. Mặc định "plain" vì **đã đo**, và phép
# đo BÁC BỎ giả thuyết ban đầu: ta đoán bỏ dấu sẽ thắng (OCR làm hỏng dấu, và G3
# phải so khớp trên dạng đã bỏ dấu vì thế). Số thật trên 100 câu / index 12
# quyển: giữ dấu MRR **0,799** vs bỏ dấu **0,769**, R@1 0,710 vs 0,690, R@3
# 0,870 vs 0,830 — giữ dấu thắng ở MỌI k. Dấu mang thông tin phân biệt nhiều hơn
# phần OCR làm hỏng.
BM25_TOKENIZER = os.getenv("BM25_TOKENIZER", "plain").lower()
if BM25_TOKENIZER not in ("folded", "plain"):
    raise ValueError(f"BM25_TOKENIZER={BM25_TOKENIZER!r} phải là 'folded' hoặc 'plain'")
# Số ứng viên lấy từ kênh thưa trước khi hợp nhất.
BM25_FETCH_K = int(os.getenv("BM25_FETCH_K", "20"))

# Hợp nhất: "rrf" không cần chuẩn hoá thang điểm (điểm dày là KHOẢNG CÁCH, điểm
# BM25 là ĐIỂM — hai thang khác bản chất), "norm" chuẩn hoá min-max rồi cộng có
# trọng số. Phải đo CẢ HAI rồi mới chốt.
FUSION_METHOD = os.getenv("FUSION_METHOD", "rrf").lower()
if FUSION_METHOD not in ("rrf", "norm"):
    raise ValueError(f"FUSION_METHOD={FUSION_METHOD!r} phải là 'rrf' hoặc 'norm'")
FUSION_RRF_K = int(os.getenv("FUSION_RRF_K", "60"))
FUSION_DENSE_WEIGHT = float(os.getenv("FUSION_DENSE_WEIGHT", "0.5"))

# Cổng lọc liên quan, tách RIÊNG khỏi rerank vì Nội dung 4 đòi ablation từng cái.
# TRƯỚC M2 hai thứ này bị TRỘN: `VectorDB.get_retriever` chọn MỘT trong hai —
# `RERANK_ENABLED=true` thì `RelevanceGatedRetriever` KHÔNG bao giờ chạy, nên
# `RETRIEVER_DISTANCE_MARGIN` là số chết trong cấu hình đang chạy.
# Mặc định TẮT, bằng phép đo chứ không phải bằng cảm tính (D-81, D-82). Cổng lọc
# TƯƠNG ĐỐI không mua được gì và ở bề rộng production thì nó CÓ HẠI: trên 300 câu,
# hybrid MRR **0,808 -> 0,781** và R@10 **0,977 -> 0,930** khi bật. Với `bm25` và
# `dense` ở bề rộng 20 nó không cắt gì (danh sách quá ngắn) nên vô hại mà cũng vô
# dụng. Cổng lọc liên quan THỰC SỰ đang hoạt động là sàn tuyệt đối
# `RERANK_SCORE_MIN` — đó mới là thành phần để bật/tắt trong ablation của đề cương.
RELEVANCE_GATE_ENABLED = os.getenv(
    "RELEVANCE_GATE_ENABLED", "false").lower() == "true"
