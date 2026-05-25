# Metadata-aware image captioning plan

## Goal

Improve image captioning so `IMAGE_CAPTION_MODEL` sees both the crop image and useful page metadata/OCR context. This should help cases where the visual crop shows fish/coral and nearby text says "Dai duong", so queries such as "hinh anh ca o dai duong" can retrieve the right image.

## Checklist

- [x] Verify current flow: captioner only receives the crop image and image hash.
- [x] Add a context-aware caption prompt that includes page title, figure caption, local OCR, nearby page text, and page/file identifiers.
- [x] Include context in the caption cache key so old image-only captions are not reused for context-aware captions.
- [x] Reorder PDF image ETL so context is built before captioning.
- [x] Keep local image import compatible when no PDF context exists.
- [x] Bump `IMAGE_EXTRACTION_VERSION` default so processed pages can be recaptioned with context-aware metadata.
- [x] Validate with a small syntax/prompt check.
- [ ] Run a focused ETL smoke test when local model/runtime dependencies are available.

## Design Notes

- Visual captioning should still avoid hallucination: use context to name textbook concepts and scene terms, but keep the visible-object description grounded in the image.
- Search quality comes from both generated caption fields and the existing metadata fields in `search_text`.
- The cache key must include a context version and context fingerprint; otherwise an old image-only caption can hide the improved flow.
