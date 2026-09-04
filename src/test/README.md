# Bộ đánh giá hệ thống RAG (12 sách)

Đánh giá hệ Trợ lý ảo Khoa học tự nhiên: **chất lượng truy xuất (RAG)** bằng số liệu
IR xác định (Precision / Recall / MRR) + **chất lượng câu trả lời của Qwen 2.5** được
**một LLM thứ 2 chấm lại**.

Mỗi cuốn trong 12 PDF có **một bộ test riêng** → 12 file CSV → xếp hạng 12 sách.

## 1. Yêu cầu

```bash
pip install -r requirements.txt   # đã gồm langchain-openai, pandas, pytesseract
```

- Tesseract tiếng Việt (`TESSERACT_CMD` trong `.env`) cho bước sinh test.
- Vector DB đã build sẵn trong `database/` (collection `biology_text`, ~13.7k chunk).
- **LLM đánh giá** (sinh test + chấm) cấu hình qua `.env`, dùng endpoint
  **OpenAI-compatible** nên cắm được MiMo / Groq / OpenRouter / vLLM tự host:

  ```env
  EVAL_LLM_BASE_URL=https://api.<...>/v1   # Groq: https://api.groq.com/openai/v1
  EVAL_LLM_API_KEY=<token của bạn>
  EVAL_LLM_MODEL=<model id>                 # vd mimo-2.5-pro / llama-3.3-70b-versatile
  ```
  (Logic xây client ở `llm_client.py` — đổi tên từ `eval_llm.py` ở D-182. Nếu
  key nằm ở biến tên khác, đặt `EVAL_LLM_API_KEY_ENV=GROQ_API_KEY` chẳng hạn.)

## 2. Vì sao đo được Precision / Recall / Rank "thật"?

Mỗi câu hỏi được sinh **từ một trang cụ thể** của một sách, nên ta biết chắc
"tài liệu vàng" = `(source_book, source_page)`. Khi chạy hệ RAG, ta đối chiếu
**metadata** (`source`, `page`) của các chunk truy xuất được với tài liệu vàng:

| Số liệu | Ý nghĩa |
|---|---|
| **Precision@k (page)** | Tỷ lệ chunk truy xuất đúng trang nguồn. |
| **Recall@k (page)** = hit@k | Có tìm được trang nguồn trong top-k không (0/1, lấy trung bình). |
| **MRR (page)** | Điểm rank = 1/(thứ hạng chunk đúng đầu tiên). |
| **\*_book** | Bản book-level (chỉ cần đúng sách) → đo nhiễu chéo giữa 12 sách. |
| `recall_top10_diag` | "Trần recall" top-10 thô (bỏ qua relevance gate) để chẩn đoán. |

Số liệu này **không phụ thuộc LLM chấm** → minh bạch, lặp lại được. (Cho phép sai số
±1 trang vì chunk có thể tràn qua ranh giới trang — xem `metrics.py`.)

## 3. Các bước (D-182, 2026-09-04 — viết lại từ đầu, thay pipeline cũ)

### Bước 1 — Sinh bộ test + duyệt tay (BẮT BUỘC trước khi dùng chính thức)
`build_testset.py` lấy mẫu NGẪU NHIÊN trên toàn corpus (không ràng buộc phủ đều
quyển) — một chunk/một ảnh cụ thể cho mỗi câu `van_ban`/`hinh`, cộng câu
`ngoai_pham_vi` (môn khác hẳn, không thuộc 12 quyển KHTN) từ danh sách môn cố
định. Tỉ lệ văn bản/hình tính từ kích thước THẬT của index tại thời điểm chạy.

```bash
python -m src.test.build_testset                       # sinh nháp 240 câu, seed 42
# đọc lại src/test/testset/draft.csv bằng mắt, sửa câu/ground_truth sai nếu có
python -m src.test.build_testset --mark-reviewed        # xác nhận ĐÃ duyệt tay
```
→ Sinh `src/test/testset/draft.csv` + `meta.json`. `retrieval_benchmark.py`/
`run_eval.py` (Bước 2) **raise** nếu `meta.json` chưa `human_reviewed: true` —
không có đường vòng, trừ `--allow-draft` (chỉ để tự kiểm code, mọi output khi
đó mang hậu tố `_NHAP_CHUA_DUYET`).

### Bước 2 — Chạy đánh giá
`run_eval.py` đưa từng câu hỏi vào **đúng pipeline Qwen 2.5 thật**
(`AppServices` → `HybridRetriever` → prompt → Qwen 2.5 → parser), rồi để **LLM
thứ 2 (Groq)** chấm lại câu trả lời (correctness / faithfulness / relevancy,
1–5). `retrieval_benchmark.py` đo P/R/F1/MRR@K xác định (không gọi LLM sinh câu
trả lời) trên 4 phương pháp truy vấn (keyword/dense/truyền thống/đề xuất).

```bash
python -m src.test.retrieval_benchmark --build-cache    # bảng 4 phương pháp x P/R/F1/MRR@K
python -m src.test.run_eval                             # đánh giá đầu-cuối LLM-judge
```
Kết quả (đều trong `src/test/testset/`):
- `eval_result.csv` — chi tiết từng câu.
- `eval_report.{csv,md}` — tổng hợp theo LOẠI câu hỏi (văn bản/hình/ngoài-phạm-vi).
- `retrieval_report.{csv,md}` — bảng P/R/F1/MRR@K theo phương pháp truy vấn.

> Lần chạy đầu hơi chậm vì nạp model Qwen 2.5 + vector DB (cache lại cho các câu sau).
> Một lượt `--n 240` thật ước tính 12-14 giờ trên máy dev GPU 4GB (D-164) —
> **KHÔNG có resume/checkpoint giữa chừng** (finding I-4, PARK có chủ đích khi
> triển khai D-182) — crash giữa chừng nghĩa là chạy lại từ đầu.

## 4. Tinh chỉnh (biến môi trường tùy chọn)

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `EVAL_QUESTIONS_PER_BOOK` | 12 | Số câu hỏi mỗi sách. |
| `EVAL_LLM_BASE_URL` | — | Endpoint OpenAI-compatible (MiMo/Groq/...). |
| `EVAL_LLM_API_KEY` | — | Token của bạn. |
| `EVAL_LLM_MODEL` | — | Model id dùng để sinh test + chấm. |

## 5. File trong thư mục

**Đánh giá RAG (text + câu trả lời) — D-182:**
- `testset_common.py` — cổng người duyệt bắt buộc (`require_human_reviewed`) +
  helper đặt tên file nháp (`duong_dan_output`, hậu tố `_NHAP_CHUA_DUYET`).
- `build_testset.py` — sinh bộ test bằng lấy mẫu ngẫu nhiên trên toàn corpus
  (không ràng buộc phủ đều quyển) → `src/test/testset/draft.csv` + `meta.json`.
- `retrieval_benchmark.py` — bảng đối chiếu 4 phương pháp truy vấn
  (keyword/dense/truyền thống/đề xuất) × P/R/F1/MRR@K, **không gọi LLM**; thay
  `ablation.py` (đã xoá) — giữ nguyên logic `Cache`/`Config`/`rank_for`/
  `_gold_key`/`evaluate` và bảng "Bề rộng PRODUCTION".
- `run_eval.py` — chạy RAG thật, LLM thứ 2 (Groq) chấm lại; thay `evaluator.py`
  (đã xoá) — trục tổng hợp là LOẠI câu hỏi (văn bản/hình/ngoài-phạm-vi).
- `llm_client.py` — dựng client LLM đánh giá (endpoint OpenAI-compatible:
  Groq/MiMo/OpenRouter...), đổi tên từ `eval_llm.py` ở D-182.
- `testset/` — `draft.csv`/`meta.json`/`eval_result.csv`/`eval_report.{csv,md}`/
  `retrieval_report.{csv,md}` của lượt gần nhất. **Bị `.gitignore` loại** — chỉ
  CODE tạo ra thư mục này được commit, không phải nội dung một lượt chạy cụ thể.

**QA cho ETL ảnh (không đụng DB):**
- `test_image_extraction_full.py` — render 1 page/PDF, vẽ overlay anchor + region + xuất crop PNG
  và index HTML để soi trực quan chất lượng cắt ảnh. Đây là công cụ QA ảnh chính.
- `scan_layout_cases.py` — quét hàng loạt page snapshot, phân loại bố cục (composite, grid, info-box).
