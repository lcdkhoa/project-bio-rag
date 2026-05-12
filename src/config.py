"""
Configuration module for Biology RAG project.
Loads environment variables and provides shared configuration.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

DATA_DIR = PROJECT_ROOT / "data"
PERSIST_DIR = PROJECT_ROOT / "database"
IMAGES_DIR = PERSIST_DIR / "images"
PROCESSED_FILES_LOG = PERSIST_DIR / "processed_files.txt"

HF_TOKEN = os.getenv("HF_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

GRADIO_SERVER_NAME = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
GRADIO_SERVER_PORT = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
USE_GPU = os.getenv("USE_GPU", "true").lower() == "true"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
LLM_MODEL = "Qwen/Qwen2.5-3B-Instruct"
CLIP_MODEL = "openai/clip-vit-base-patch16"
BLIP_MODEL = "Salesforce/blip-image-captioning-base"

TEXT_COLLECTION_NAME = "biology_text"
IMAGE_COLLECTION_NAME = "biology_images"
STATUS_COLLECTION_NAME = "processing_status"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 120

LLM_TEMPERATURE = 0.1
LLM_MAX_NEW_TOKENS = 500
LLM_TOP_P = 0.75

RETRIEVER_K = 3
IMAGE_RETRIEVER_K = 3
IMAGE_RETRIEVER_FETCH_K = int(os.getenv("IMAGE_RETRIEVER_FETCH_K", "24"))
IMAGE_RELEVANCE_THRESHOLD = float(os.getenv("IMAGE_RELEVANCE_THRESHOLD", "0.28"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
