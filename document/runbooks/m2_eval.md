# Runbook — M2: measure retrieval rerank + citations on the bge-m3 DB

Measures the M2 retrieval-rerank + deterministic-citation work
(`document/specs/2026-08-19-m2-retrieval-rerank-citation-design.md`, D-19) once
a **bge-m3** text index exists. M2 code is complete and unit-tested against
synthetic fixtures (`tests/rag/`, `tests/app/`, `tests/test_mrr_metric.py`);
this runbook is the real-data pass that turns those fixtures into trusted
numbers.

## 0. Prerequisite — bge-m3 DB from the M1 Colab rebuild
M2's config default (`EMBEDDING_MODEL=BAAI/bge-m3`) only matters once the
index itself was built with bge-m3. Follow
[`document/runbooks/m1_rebuild_text.md`](./m1_rebuild_text.md) first: run
`python main.py --text-only` on Colab Pro (D-18 — image ETL stays on the old
pipeline until M3) and confirm `biology_text` is populated before doing any
of the steps below. Running this runbook against a MiniLM-era DB will give
meaningless recall numbers (dimension/model mismatch).

## 1. Sanity: real cross-encoder loads and orders correctly
Before trusting any eval number, confirm the reranker is oriented the right
way on a real Vietnamese pair (not just the synthetic-predictor unit tests):
```bash
RUN_RERANK_INTEGRATION=1 python -m pytest tests/rag/test_reranker_integration.py -v
```
Expect `PASS` — a clearly-relevant passage scores above an irrelevant one.
This downloads/loads `BAAI/bge-reranker-v2-m3`, so it is opt-in and skipped
by default in normal test runs.

## 2. Recall@k + MRR, baseline vs. rerank
```bash
python src/test/recall_at_k.py
```
Reads the golden testsets in `src/test/testsets/`, reports Recall@{3,5,10}
and MRR for the `base` (no rerank) and `rer` (`RerankedRetriever`) retrieval
paths side by side, and writes `testsets/../recall_at_k_report.csv` (+ `.md`).
Compare the two columns — rerank should not regress recall, and should raise
MRR (relevant chunk surfaces earlier) since it re-orders a wider `RERANK_FETCH_K`
candidate set rather than changing what is fetched.

## 3. Tune `RERANK_SCORE_MIN` if answers fall back too often
The chat prompt (`src/rag/chain.py`) instructs the LLM to answer exactly
`"Thông tin này không được đề cập trong sách giáo khoa."` when the retrieved
context doesn't contain the answer. `RerankedRetriever` drops any chunk
scoring below the absolute floor `RERANK_SCORE_MIN` (`.env`, default `0.2`)
after rerank. If step 2's recall look right but real queries hit the
fallback message too often, the floor is likely too strict for bge-m3's
score distribution — lower `RERANK_SCORE_MIN` in small steps (e.g. `0.15`),
re-run step 2, and check that recall recovers without pulling in
off-topic chunks.

## 4. Image QA — confirm the cross-encoder term doesn't overturn exact matches
Image reranking (`IMAGE_RERANK_ENABLED`, `src/rag/image_vectorstore.py`) is
an **additive** scoring term, not a replacement for the existing CLIP +
metadata + lexical-phrase fusion — verify that holds on real images:
```bash
python src/test/test_image_extraction_full.py
```
Then run a handful of `"cho tôi hình con X"`-style queries (the lexical
phrase channel's target case) through the API/CLI and confirm the top image
result is still the exact match — the cross-encoder term (`IMAGE_RERANK_WEIGHT`,
default `0.25`) should not outrank an exact lexical/CLIP hit with a
tangentially-related image.

## 5. Record the final numbers
Once steps 2–4 look right on the real bge-m3 + reranker DB, log the actual
Recall@k / MRR (base vs. rerank) and any `RERANK_SCORE_MIN` /
`IMAGE_RERANK_WEIGHT` changes in `document/decision_log.html` as a follow-up
to D-19 / D-20, so the tuned values and the evidence behind them stay
traceable.
