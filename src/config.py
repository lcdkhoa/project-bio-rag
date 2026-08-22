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
