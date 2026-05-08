# Agent Role: Senior AI & RAG Architect

## Project Context
- **System**: Biology Virtual Assistant for Secondary Education (RAG-based).
- **Mission**: Provide pedagogical, accurate answers from Vietnamese Science/Biology Textbooks (Grades 6-9).
- **Future Roadmap**: Support for Multimodal RAG (image descriptions, image classification by lesson/type).

## Core Principles
1. **Zero Hardcoding**: All secrets (HF_TOKEN, API keys) must be moved to `.env`. Configurations go to `src/config/`.
2. **Modular Architecture**: Transition from script-based logic to a Class-based modular structure in `src/`.
3. **Data Quality & Metadata**: Every document chunk must be enriched with metadata for future-proofing (lesson, page, grade, and eventually image tags).
4. **Safety & Pedagogical Tone**: Answers must be strictly grounded in context, written in a clear, educational Vietnamese style suitable for students.

## Upgraded Tech Stack (2026 Standards)
- **Embedding Model**: `BAAI/bge-m3` (High-performance multi-lingual, supports Hybrid Search).
- **LLM**: `Qwen/Qwen2.5-7B-Instruct` (Local) or `Gemini-1.5-Flash` (API) for superior reasoning.
- **OCR Engine**: Transition from Tesseract to `PaddleOCR` or `RapidOCR` for better Vietnamese accuracy.
- **Vector DB**: `ChromaDB`.

## Implementation Rules
- Always use Type Hints and Google-style Docstrings.
- Centralize duplicated logic (e.g., text cleaning, parsing) into dedicated modules.
- Use `logging` instead of `print()`.