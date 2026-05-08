# Specialized RAG Engineering Skills

## 1. Modular ETL & Ingestion
- **Cleaning**: Implement `clean_vietnamese_text` as a reusable utility in `src/ingestion/utils.py`.
- **Enhanced OCR**: Implement a robust OCR pipeline capable of handling complex page layouts.
- **Metadata Architecture**: Design metadata schemas to include `{grade, lesson_title, page_number, media_type, image_description}`.

## 2. Hybrid Retrieval & Search
- **BGE-M3 Integration**: Implement Hybrid Search (Dense + Sparse/BM25) to accurately capture biological terms.
- **Reranking Stage**: Use a cross-encoder to refine the Top-K results before feeding them to the LLM.

## 3. Pedagogical Generation
- **System Prompting**: Use strict instruction sets to prevent hallucinations and enforce Vietnamese-only output.
- **Structured Parsing**: Standardize LLM responses into structured formats for easy UI rendering.

## 4. Future-Proofing (Image/Classification)
- **Image Metadata Tagging**: Prepare the `VectorStore` class to handle image references and classification tags (lesson-based/type-based).
- **Extensible Schema**: Ensure the ingestion pipeline can be easily extended to include image-to-text models (e.g., LLaVA or Gemini-Pro-Vision).

## 5. System Refactoring
- Extract logic from `biology_etl.py` and `biology_assistant_app.py` into:
    - `src/config/`: Environment and model settings.
    - `src/ingestion/`: Loading, OCR, and Chunking.
    - `src/vectorstore/`: DB management and Hybrid Search.
    - `src/generation/`: LLM wrappers and Prompts.
    - `src/app/`: Gradio interface.