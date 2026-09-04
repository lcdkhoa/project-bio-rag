# Viết lại pipeline sinh bộ test + đánh giá LLM-as-Judge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **NGOẠI LỆ BẮT BUỘC so với luồng chuẩn của hai skill trên**: Task 2 và Task 3
> dưới đây PHẢI được giao cho **hai subagent Sonnet 5 chạy SONG SONG trong CÙNG
> một lượt gọi** (không phải tuần tự từng task một như mặc định của
> `subagent-driven-development`), rồi Task 4 PHẢI là **một subagent Opus 5
> phản biện cả hai** trước khi coi Task 2/3 là xong. Đây là yêu cầu đứng của
> `CLAUDE.md` mục "Quy tắc làm việc" (đã chốt 2026-09-03), áp dụng vì
> `build_testset.py` (Task 2) và `testset_common.py`+`retrieval_benchmark.py`+
> `run_eval.py` (Task 3) là hai phần tách file hoàn toàn, không đụng chung file
> nào. Người điều phối (coordinator) phải tự dispatch Task 2 + Task 3 bằng hai
> lời gọi Agent trong CÙNG một message, không dùng vòng lặp "một subagent mỗi
> task" mặc định của skill.

**Goal:** Xóa sạch pipeline sinh bộ test + đánh giá LLM-as-Judge cũ (D-181 và
mọi thứ trước đó), viết lại 3 script mới lấy mẫu ngẫu nhiên trên toàn corpus
(không ràng buộc phủ đều 12 quyển), với cổng người duyệt bắt buộc trước khi một
bộ test được coi là chính thức.

**Architecture:** Một bước dọn dẹp tuần tự (đổi tên + xóa file, đưa repo về
trạng thái sạch, `pytest tests/` xanh) → hai nhánh độc lập theo file chạy song
song (sinh bộ test | truy xuất + đánh giá) → một lượt phản biện đối kháng → xác
minh bằng lượt chạy nhỏ → dọn dẹp tài liệu/memory/notebook → commit cuối.

**Tech Stack:** Python 3.x, ChromaDB (đọc trực tiếp qua `chromadb.PersistentClient`),
`langchain_openai.ChatOpenAI` (qua `llm_client.JudgePool`), pandas (đọc/ghi CSV),
pytest.

**Spec:** `document/specs/2026-09-03-eval-rebuild-design.md` (commit `2e3e1b58`)
— plan này lập luận trực tiếp từ spec đó, đã qua 4 lượt phản biện (2 tự-phản-biện
+ 2 subagent độc lập). Đọc cả spec lẫn plan này trước khi thực thi bất kỳ task
nào; spec giải thích PHẢI làm gì và TẠI SAO (bao gồm 4 lượt phản biện), plan này
chỉ giải thích LÀM NHƯ THẾ NÀO.

## Global Constraints

- **Không đổi hành vi RAG sản xuất**: không sửa bất kỳ dòng nào trong `src/rag/`,
  `src/etl/`, `src/app/`, `src/config.py`. Mọi thay đổi chỉ nằm trong `src/test/`,
  `tests/`, `scripts/*.ps1` (xóa 3 file), `document/`, memory, và
  `docs/superpowers/plans/` (chính file này).
- **`RERANK_SCORE_MIN=0.59`** (D-180) là giá trị mặc định hiện tại trong
  `src/config.py:208` — 4 cấu hình báo cáo (`keyword`/`dense`/`truyen_thong`/
  `de_xuat`) phải đọc giá trị này qua `src.config`, không hardcode `0.59` trong
  script mới.
- **Không bao giờ dùng `git add -A`/`git add .`** khi commit các task dưới đây —
  liệt kê tường minh từng file (nhiều thao tác xóa hàng loạt, dễ lẫn file không
  liên quan).
- **Message commit thuần, không có dòng `Co-Authored-By`** (quy tắc repo, khác
  với hướng dẫn attribution mặc định của hệ thống ở NGOÀI phạm vi các task viết
  code trong plan này — chỉ áp dụng khi commit thay đổi trong `src/`/`tests/`/
  `scripts/`; commit tài liệu/spec/plan theo hướng dẫn attribution hiện hành của
  phiên làm việc).
- **`python -m src.test.<module>` là cách gọi chuẩn** cho cả 3 script mới (khớp
  `sys.path` mà `ablation.py`/`evaluator.py` đã dùng qua
  `sys.path.insert(0, ...)`).
- **Không viết test end-to-end gọi Groq/Qwen thật** trong bất kỳ Task nào dưới
  đây — mọi test mới dùng mock/fixture. Xác minh bằng gọi thật chỉ ở Task 5
  (`--n 6`).
- **File draft/nháp luôn có hậu tố `_NHAP_CHUA_DUYET`** trong tên khi sinh từ
  `--allow-draft` — áp dụng cho MỌI file output của `run_eval.py` và
  `retrieval_benchmark.py`.

---

## File Structure

```
src/test/
  llm_client.py              (MODIFY: đổi tên từ eval_llm.py, nội dung giữ nguyên)
  testset_common.py          (CREATE, Task 3) — require_human_reviewed(), hằng số dùng chung
  build_testset.py           (CREATE, Task 2) — sinh src/test/testset/draft.csv + meta.json
  retrieval_benchmark.py     (CREATE, Task 3) — bảng 4 phương pháp × P/R/F1/MRR@K
  run_eval.py                (CREATE, Task 3) — đánh giá đầu-cuối LLM-judge
  README.md                  (MODIFY, Task 8)
  testset/                   (thư mục output, KHÔNG commit nội dung .csv/.json sinh
                              ra — chỉ code tạo ra nó được commit)

  # XÓA (Task 1):
  generate_testsets.py, build_testset_240.py, build_image_questions.py,
  evaluator.py, metrics.py, ablation.py, ablation_multimodal.py, bm25_sweep.py,
  review_testset.py, prompt_scope_probe.py, qa_citation_page.py,
  testsets/, testsets_240/, eval_240_results/

scripts/
  # XÓA (Task 1): run_ablation.ps1, run_testsets.ps1, sau_etl_anh.ps1

tests/
  test_build_testset_sampling.py   (CREATE, Task 2)
  test_review_gate.py               (CREATE, Task 3)
  test_retrieval_benchmark_metrics.py  (CREATE, Task 3)
  test_mrr_metric.py                (MODIFY, Task 3 — sửa import)
  rag/test_ablation_cache.py        (MODIFY, Task 3 — sửa import + 4 tên thêm)
  # XÓA (Task 1): test_g3_matcher.py, test_eval_gold_keys.py,
  #   test_evaluator_cli.py, test_build_testset_240.py,
  #   test_build_image_questions.py, test_generate_testsets_resume.py,
  #   rag/test_ablation_multimodal_score.py

document/
  decision_log.html          (MODIFY, Task 6 — thêm D-182)
  colab_runtime_eval.ipynb   (MODIFY, Task 8)

CLAUDE.md                     (MODIFY, Task 6)
```

**Ranh giới rõ ràng cho song song hóa (Task 2 vs Task 3):** `build_testset.py`
(Task 2) chỉ ĐỌC ChromaDB và GHI hai file (`draft.csv`, `meta.json`) theo schema
cố định dưới đây — nó không import gì từ `testset_common.py`/
`retrieval_benchmark.py`/`run_eval.py`. `retrieval_benchmark.py`/`run_eval.py`
(Task 3) chỉ ĐỌC hai file đó theo ĐÚNG schema đó — không import gì từ
`build_testset.py`. Hai agent thực thi Task 2/Task 3 không cần biết về nhau
ngoài schema này.

### Schema dùng chung giữa Task 2 và Task 3 (BẮT BUỘC khớp chính xác)

**`src/test/testset/draft.csv`** — cột theo đúng thứ tự:
```
question,loai,source_book,source_page,figure_label,ground_truth
```
- `question`: str, câu hỏi tiếng Việt.
- `loai`: str, một trong `van_ban` / `hinh` / `ngoai_pham_vi` (chữ thường, không dấu, đúng 3 giá trị này).
- `source_book`: str (vd `SGK_KHTN_6_CD`) hoặc **chuỗi rỗng** (câu `ngoai_pham_vi`) — KHÔNG ghi `"None"`/`"nan"`.
- `source_page`: chuỗi số nguyên (vd `"37"`) hoặc **chuỗi rỗng** — KHÔNG ép kiểu int khi rỗng.
- `figure_label`: str (vd `"Hình 1.1"`) hoặc chuỗi rỗng (chỉ có giá trị ở `loai=hinh`).
- `ground_truth`: str, đáp án chuẩn.

Ghi bằng `pandas.DataFrame.to_csv(path, index=False, encoding="utf-8-sig")` —
đúng encoding mọi CSV khác trong `src/test/` đang dùng (xác nhận: `evaluator.py`
dòng 289 `encoding="utf-8-sig"`).

**`src/test/testset/meta.json`**:
```json
{
  "seed": 42,
  "n_total": 240,
  "n_van_ban": 170,
  "n_hinh": 40,
  "n_ngoai_pham_vi": 30,
  "p_hinh_do_duoc": 0.19,
  "n_chunk_do_duoc": 16515,
  "n_anh_do_duoc": 3881,
  "tao_luc": "2026-09-04T10:00:00+07:00",
  "human_reviewed": false,
  "reviewed_at": null
}
```
`reviewed_at` chỉ có giá trị (ISO timestamp) sau khi chạy `--mark-reviewed`.

**Hậu tố file nháp** (`--allow-draft` ở `run_eval.py`/`retrieval_benchmark.py`):
mọi file output đổi tên theo mẫu `<basename>_NHAP_CHUA_DUYET.<ext>`, ví dụ
`eval_result_NHAP_CHUA_DUYET.csv`, `retrieval_report_NHAP_CHUA_DUYET.md`.

---

### Task 1: Dọn dẹp tuần tự — đổi tên `eval_llm.py`, xóa toàn bộ code cũ

**PHẢI hoàn thành và `pytest tests/` XANH trước khi dispatch Task 2/Task 3.**
Đây là bước dùng-chung duy nhất — làm một mình, không giao subagent.

**Files:**
- Modify (rename): `src/test/eval_llm.py` → `src/test/llm_client.py`
- Delete: `src/test/generate_testsets.py`, `src/test/build_testset_240.py`,
  `src/test/build_image_questions.py`, `src/test/evaluator.py`,
  `src/test/metrics.py`, `src/test/ablation.py`,
  `src/test/ablation_multimodal.py`, `src/test/bm25_sweep.py`,
  `src/test/review_testset.py`, `src/test/prompt_scope_probe.py`,
  `src/test/qa_citation_page.py`
- Delete (dir, recursive): `src/test/testsets/`, `src/test/testsets_240/`,
  `src/test/eval_240_results/`
- Delete: `scripts/run_ablation.ps1`, `scripts/run_testsets.ps1`,
  `scripts/sau_etl_anh.ps1`
- Delete: `tests/test_g3_matcher.py`, `tests/test_eval_gold_keys.py`,
  `tests/test_evaluator_cli.py`, `tests/test_build_testset_240.py`,
  `tests/test_build_image_questions.py`,
  `tests/test_generate_testsets_resume.py`,
  `tests/rag/test_ablation_multimodal_score.py`
- Delete: `tests/test_mrr_metric.py`, `tests/rag/test_ablation_cache.py` (sẽ
  được TÁI TẠO trong Task 3 cùng lúc với `retrieval_benchmark.py` — xóa ở đây
  để Task 1 kết thúc với cây sạch, không còn import nào trỏ vào module đã xóa)

**Interfaces:**
- Consumes: không có (task đầu tiên).
- Produces: `src/test/llm_client.py` tồn tại với nội dung giống hệt
  `eval_llm.py` cũ (đổi tên file, không đổi một dòng code nào bên trong —
  `JudgePool`, `get_eval_llm`, `is_configured`, `config_help`,
  `_resolve_api_key`, `_is_rate_limited` giữ nguyên chữ ký). Task 2 và Task 3
  import `from src.test.llm_client import get_eval_llm, is_configured, config_help`
  (Task 3 dùng thêm `JudgePool` gián tiếp qua `get_eval_llm`, không cần import
  trực tiếp `JudgePool`).

- [ ] **Step 1: Kiểm tra git status sạch trước khi xóa hàng loạt**

Run: `git status --short`
Expected: chỉ thấy các file/thư mục liệt kê ở trên (nếu có gì khác lạ, DỪNG và hỏi
người dùng trước khi xóa).

- [ ] **Step 2: Đổi tên `eval_llm.py` bằng `git mv` (giữ lịch sử)**

```bash
git mv src/test/eval_llm.py src/test/llm_client.py
```

- [ ] **Step 3: Grep xác nhận không còn tham chiếu `eval_llm` nào TRƯỚC KHI xóa các file import nó**

Run: `grep -rn "eval_llm" --include="*.py" src/ tests/ scripts/`
Expected: chỉ còn các dòng trong chính các file SẮP BỊ XÓA ở Step 4 (ví dụ
`evaluator.py` có `from src.test.eval_llm import ...`). Nếu thấy tham chiếu ở
một file KHÔNG nằm trong danh sách xóa, DỪNG lại và điều tra trước khi tiếp tục
— đây là dấu hiệu một phụ thuộc chưa được liệt kê trong spec.

- [ ] **Step 4: Xóa toàn bộ file/thư mục cũ**

```bash
git rm src/test/generate_testsets.py src/test/build_testset_240.py \
  src/test/build_image_questions.py src/test/evaluator.py \
  src/test/metrics.py src/test/ablation.py \
  src/test/ablation_multimodal.py src/test/bm25_sweep.py \
  src/test/review_testset.py src/test/prompt_scope_probe.py \
  src/test/qa_citation_page.py
git rm -r src/test/testsets src/test/testsets_240 src/test/eval_240_results
git rm scripts/run_ablation.ps1 scripts/run_testsets.ps1 scripts/sau_etl_anh.ps1
git rm tests/test_g3_matcher.py tests/test_eval_gold_keys.py \
  tests/test_evaluator_cli.py tests/test_build_testset_240.py \
  tests/test_build_image_questions.py tests/test_generate_testsets_resume.py \
  tests/rag/test_ablation_multimodal_score.py \
  tests/test_mrr_metric.py tests/rag/test_ablation_cache.py
```

- [ ] **Step 5: Grep lại lần cuối — không còn tham chiếu module đã xóa ở bất kỳ đâu trong repo**

Run:
```bash
grep -rln "from src\.test\.\(ablation\|ablation_multimodal\|qa_citation_page\|metrics\|generate_testsets\|evaluator\|build_testset_240\|build_image_questions\|eval_llm\)\b\|from src\.test import \(ablation\|evaluator\|generate_testsets\|build_testset_240\|build_image_questions\)\b" \
  --include="*.py" . 2>/dev/null
grep -rn "src\.test\.\(ablation\|bm25_sweep\|generate_testsets\|build_image_questions\)\b" scripts/*.ps1 document/*.ipynb 2>/dev/null
```
Expected: cả hai lệnh trả về RỖNG. Nếu không rỗng, tìm và xử lý file đó trước
khi đi tiếp (đây chính là loại lỗi mà phản biện lần 3/4 của spec đã bắt được ở
`tests/`/`scripts/*.ps1` — đừng để sót một chỗ thứ ba).

- [ ] **Step 6: Chạy toàn bộ test suite, xác nhận xanh**

Run: `pytest tests/ -q`
Expected: PASS, không có FAILED/ERROR nào (số lượng pass sẽ giảm so với 781 vì
đã xóa 9 file test — đây là dự kiến, không phải bug). Không được có bất kỳ dòng
`ImportError`/`ModuleNotFoundError` nào trong output.

- [ ] **Step 7: Commit**

```bash
git add -u
git status --short   # xác nhận CHỈ có các thay đổi đã liệt kê, không có gì lạ
git commit -m "$(cat <<'EOF'
refactor(test): xoa toan bo pipeline sinh test + danh gia cu (D-182)

Doi ten eval_llm.py -> llm_client.py (giu nguyen logic JudgePool). Xoa
generate_testsets.py, build_testset_240.py, build_image_questions.py,
evaluator.py, metrics.py, ablation.py, ablation_multimodal.py,
bm25_sweep.py, review_testset.py, prompt_scope_probe.py,
qa_citation_page.py, testsets/, testsets_240/, eval_240_results/, 3
script scripts/*.ps1 goi cac module tren, va 9 file tests/ phu thuoc
truc tiep. Chuan bi cho 3 script moi (build_testset.py,
retrieval_benchmark.py, run_eval.py) theo
document/specs/2026-09-03-eval-rebuild-design.md.
EOF
)"
```

---

### Task 2: `build_testset.py` — sinh bộ test 240 câu (chạy SONG SONG với Task 3)

**Files:**
- Create: `src/test/build_testset.py`
- Create: `tests/test_build_testset_sampling.py`

**Interfaces:**
- Consumes: `chromadb` (đọc trực tiếp `PERSIST_DIR` từ `src.config`),
  `src.test.llm_client.get_eval_llm/is_configured/config_help` (đã tồn tại sau
  Task 1). KHÔNG import `src.test.testset_common` — không tồn tại cho tới khi
  Task 3 xong, và schema CSV/json ở trên đã đủ để Task 2 tự viết `meta.json`
  không cần hàm dùng chung.
- Produces: file `src/test/testset/draft.csv` + `src/test/testset/meta.json`
  đúng schema ở phần "File Structure" — Task 3 (`run_eval.py`/
  `retrieval_benchmark.py`) đọc đúng hai file này.

**Bối cảnh bắt buộc đọc trước khi viết code** (không suy đoán từ tóm tắt):
`document/specs/2026-09-03-eval-rebuild-design.md` mục 3.1 toàn bộ (đã qua 4
lượt phản biện, mọi con số/tên trường/luật chặn input đã verify với DB thật).
Đặc biệt các điểm SAU ĐÂY hay bị bỏ sót nếu chỉ đọc lướt:

1. **Ánh xạ trường ảnh KHÁC bên text** — `biology_image_metadata` dùng
   `pdf_filename`/`page_number`, KHÔNG PHẢI `source`/`page`. Cột CSV
   `source_book`/`source_page` của một dòng `hinh` lấy từ
   `metadata["pdf_filename"]`/`metadata["page_number"]`.
2. **`Collection.count()` không nhận filter** — đếm bằng
   `len(collection.get(include=[])["ids"])` sau khi áp ĐÚNG CÙNG bộ lọc sẽ dùng
   ở bước lấy mẫu (không phải bộ lọc khác).
3. Hai chỗ chặn input bắt buộc: `n_ngoai_pham_vi >= n` và pool không đủ.
4. Trần circuit-breaker: tỉ lệ lỗi LLM > 30% trên 20 lệnh gọi gần nhất → dừng
   hẳn script.

- [ ] **Step 1: Viết test lấy mẫu (mock ChromaDB, không cần DB thật)**

Tạo `tests/test_build_testset_sampling.py`:

```python
import random

import pytest

from src.test.build_testset import (
    _anh_xa_hinh_sang_cot,
    _dem_pool_hinh_hop_le,
    _kiem_tra_input,
    _tinh_n_moi_nhom,
)


def test_tinh_n_moi_nhom_tong_bang_n_total():
    n = _tinh_n_moi_nhom(n_total=240, n_ngoai_pham_vi=30,
                          n_chunk=16515, n_anh=3881)
    assert n["n_van_ban"] + n["n_hinh"] + n["n_ngoai_pham_vi"] == 240
    assert n["n_ngoai_pham_vi"] == 30


def test_tinh_n_moi_nhom_ti_le_hinh_dung_cong_thuc():
    n = _tinh_n_moi_nhom(n_total=210, n_ngoai_pham_vi=0,
                          n_chunk=8000, n_anh=2000)
    # p_hinh = 2000 / 10000 = 0.2 -> n_hinh = round(210 * 0.2) = 42
    assert n["n_hinh"] == 42
    assert n["n_van_ban"] == 168


def test_kiem_tra_input_chan_ngoai_pham_vi_qua_lon():
    with pytest.raises(SystemExit, match="n-ngoai-pham-vi"):
        _kiem_tra_input(n_total=100, n_ngoai_pham_vi=100)
    with pytest.raises(SystemExit, match="n-ngoai-pham-vi"):
        _kiem_tra_input(n_total=100, n_ngoai_pham_vi=150)


def test_kiem_tra_input_hop_le_khong_raise():
    _kiem_tra_input(n_total=240, n_ngoai_pham_vi=30)  # không raise


def test_dem_pool_hinh_hop_le_chan_pool_thieu():
    with pytest.raises(SystemExit, match="pool"):
        _dem_pool_hinh_hop_le(pool_size=10, n_can=40)


def test_anh_xa_hinh_sang_cot_dung_pdf_filename_page_number():
    meta = {
        "pdf_filename": "SGK_KHTN_6_CD",
        "page_number": 5,
        "figure_label": "Hình 1.1",
    }
    row = _anh_xa_hinh_sang_cot(meta)
    assert row["source_book"] == "SGK_KHTN_6_CD"
    assert row["source_page"] == "5"
    assert row["figure_label"] == "Hình 1.1"


def test_anh_xa_hinh_sang_cot_khong_bao_gio_doc_truong_source():
    # Nếu code lỡ đọc metadata.get("source")/metadata.get("page") (tên trường
    # bên TEXT, không tồn tại bên ẢNH) sẽ ra None -> rỗng. Test này chặn hồi quy
    # đúng lỗi nghiêm trọng nhất tìm được ở phản biện lần 4 của spec.
    meta = {"pdf_filename": "SGK_KHTN_7_CTST", "page_number": 12,
            "figure_label": "Hình 2.3", "source": None, "page": None}
    row = _anh_xa_hinh_sang_cot(meta)
    assert row["source_book"] == "SGK_KHTN_7_CTST"
    assert row["source_page"] == "12"


def test_seed_tai_lap_duoc():
    ids = [f"c{i}" for i in range(1000)]
    a = random.Random(42).sample(ids, 50)
    b = random.Random(42).sample(ids, 50)
    c = random.Random(43).sample(ids, 50)
    assert a == b
    assert a != c
```

- [ ] **Step 2: Chạy test, xác nhận FAIL (module chưa tồn tại)**

Run: `pytest tests/test_build_testset_sampling.py -v`
Expected: FAIL với `ModuleNotFoundError: No module named 'src.test.build_testset'`

- [ ] **Step 3: Viết `src/test/build_testset.py`**

```python
# -*- coding: utf-8 -*-
"""Sinh bộ test 240 câu bằng lấy mẫu ngẫu nhiên trên toàn corpus (D-182).

Thay thế toàn bộ pipeline cũ (generate_testsets.py -> build_testset_240.py ->
build_image_questions.py, D-181 và trước đó): KHÔNG còn ràng buộc "đều theo
quyển" — mỗi câu văn bản/hình được rút ngẫu nhiên từ MỘT chunk/MỘT ảnh cụ thể
trong index, không quan tâm chunk/ảnh đó thuộc quyển nào. Xem thiết kế đầy đủ
(đã qua 4 lượt phản biện) ở
`document/specs/2026-09-03-eval-rebuild-design.md` mục 3.1.

Ba nhóm câu, tỉ lệ KHÔNG cố định (tính từ kích thước thật của index tại thời
điểm chạy, xem `_tinh_n_moi_nhom`):
    - van_ban: rút 1 chunk `biology_text`, LLM soạn câu hỏi bám sát nội dung.
    - hinh: rút 1 doc `biology_image_metadata`, LLM soạn câu hỏi về hình.
    - ngoai_pham_vi: chọn ngẫu nhiên 1 môn học KHÁC (Sử/Địa/...), LLM soạn câu
      hỏi kiến thức phổ thông của môn đó — hệ thống PHẢI trả lời "không biết"
      thay vì bịa (nguyên tắc 1).

Bắt buộc người duyệt tay trước khi coi bộ test là chính thức — `run_eval.py`/
`retrieval_benchmark.py` raise nếu `meta.json` chưa `human_reviewed: true`
(xem `src/test/testset_common.py::require_human_reviewed`).

Chạy:
    python -m src.test.build_testset                       # sinh nháp, seed 42
    python -m src.test.build_testset --n 240 --n-ngoai-pham-vi 30 --seed 42
    python -m src.test.build_testset --mark-reviewed        # xác nhận ĐÃ duyệt tay
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd
from dotenv import load_dotenv

from src.config import PERSIST_DIR, TEXT_COLLECTION_NAME, IMAGE_METADATA_COLLECTION_NAME
from src.test.llm_client import get_eval_llm, is_configured, config_help

load_dotenv()
logger = logging.getLogger(__name__)

OUT_DIR = Path(__file__).resolve().parent / "testset"
DRAFT_CSV = OUT_DIR / "draft.csv"
META_JSON = OUT_DIR / "meta.json"

MIN_CHUNK_CHARS = 200  # tham khảo CHUNK_SIZE=400, không phải số đo mới
CIRCUIT_BREAKER_WINDOW = 20
CIRCUIT_BREAKER_MAX_ERROR_RATE = 0.30

MON_NGOAI_PHAM_VI = [
    "Lịch sử", "Địa lý", "Giáo dục công dân", "Toán", "Ngữ văn",
    "Tiếng Anh", "Tin học", "Thể dục", "Âm nhạc", "Mỹ thuật",
]

GEN_PROMPT_VAN_BAN = """Bạn đang soạn MỘT câu hỏi kiểm tra cho học sinh THCS dựa
trên đúng đoạn văn bản dưới đây (trích từ sách giáo khoa Khoa học tự nhiên).

[ĐOẠN VĂN BẢN]:
{doan}

Yêu cầu:
- Soạn ĐÚNG MỘT câu hỏi tiếng Việt tự nhiên mà câu trả lời nằm TRỌN trong đoạn
  văn bản trên (không cần kiến thức ngoài đoạn này).
- `ground_truth` là câu trả lời chuẩn, DIỄN GIẢI LẠI bằng lời của bạn (không
  chép nguyên văn từng chữ của đoạn).

CHỈ trả JSON thuần (không markdown, không giải thích thêm):
{{"question": "<câu hỏi>", "ground_truth": "<đáp án chuẩn>"}}
"""

GEN_PROMPT_HINH = """Bạn đang soạn MỘT câu hỏi kiểm tra cho học sinh THCS về một
HÌNH trong sách giáo khoa Khoa học tự nhiên. Thông tin bạn có về hình này:

Nhãn hình: {nhan}
Chú thích: {chu_thich}
Chữ trong hình (OCR): {chu_trong_hinh}
Ngữ cảnh quanh hình: {ngu_canh}

Yêu cầu:
- Soạn ĐÚNG MỘT câu hỏi tiếng Việt yêu cầu quan sát/hiểu nội dung hình này
  (ví dụ "Quan sát Hình X.Y, cho biết...").
- `ground_truth` là câu trả lời chuẩn dựa trên thông tin trên.

CHỈ trả JSON thuần (không markdown, không giải thích thêm):
{{"question": "<câu hỏi>", "ground_truth": "<đáp án chuẩn>"}}
"""

GEN_PROMPT_NGOAI_PHAM_VI = """Soạn ĐÚNG MỘT câu hỏi kiến thức phổ thông bậc
THCS thuộc môn {mon} (KHÔNG phải môn Khoa học tự nhiên — Lý/Hoá/Sinh).

CHỈ trả JSON thuần (không markdown, không giải thích thêm):
{{"question": "<câu hỏi>", "ground_truth": "Câu hỏi thuộc môn {mon}, KHÔNG nằm trong 12 quyển SGK Khoa học tự nhiên (Lý-Hoá-Sinh). Hệ thống nên trả lời không tìm thấy thông tin trong sách / không thuộc phạm vi kiến thức, KHÔNG được tự trả lời bằng kiến thức ngoài sách hay bịa đáp án."}}
"""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _kiem_tra_input(n_total: int, n_ngoai_pham_vi: int) -> None:
    """Chặn input vô lý TRƯỚC khi tính n_con_lai/gọi random.sample.

    Tìm ra ở phản biện lần 2 của spec: để `n_con_lai` âm rồi `random.sample`
    ném `ValueError` khó hiểu tệ hơn một thông báo rõ ràng ở đây.
    """
    if n_ngoai_pham_vi >= n_total or n_ngoai_pham_vi < 0:
        raise SystemExit(
            f"--n-ngoai-pham-vi ({n_ngoai_pham_vi}) phải nhỏ hơn --n ({n_total}) "
            "và không âm.")


def _dem_pool_hinh_hop_le(pool_size: int, n_can: int) -> None:
    """Chặn khi pool đủ điều kiện nhỏ hơn số cần rút — KHÔNG âm thầm hạ n_can.

    Tìm ra ở phản biện lần 2 của spec: hạ n_can rồi dồn phần thiếu sang nhóm
    khác sẽ âm thầm đổi tỉ lệ đã in ở bước tính N.
    """
    if pool_size < n_can:
        raise SystemExit(
            f"Pool đủ điều kiện chỉ có {pool_size} phần tử, cần rút {n_can} — "
            "không đủ. KHÔNG tự hạ số cần rút; hoặc mở rộng bộ lọc, hoặc giảm "
            "--n.")


def _tinh_n_moi_nhom(n_total: int, n_ngoai_pham_vi: int,
                      n_chunk: int, n_anh: int) -> Dict[str, int]:
    """N cho từng nhóm, tính TẠI THỜI ĐIỂM CHẠY từ kích thước thật của index.

    p_hinh = n_anh / (n_chunk + n_anh); n_hinh = round(n_con_lai * p_hinh).
    """
    n_con_lai = n_total - n_ngoai_pham_vi
    p_hinh = n_anh / (n_chunk + n_anh) if (n_chunk + n_anh) > 0 else 0.0
    n_hinh = round(n_con_lai * p_hinh)
    n_van_ban = n_con_lai - n_hinh
    return {
        "n_van_ban": n_van_ban,
        "n_hinh": n_hinh,
        "n_ngoai_pham_vi": n_ngoai_pham_vi,
        "p_hinh_do_duoc": round(p_hinh, 4),
    }


def _anh_xa_hinh_sang_cot(meta: dict) -> dict:
    """Ánh xạ metadata `biology_image_metadata` sang cột CSV chuẩn.

    QUAN TRỌNG (phản biện lần 4 của spec): collection ảnh dùng khoá
    `pdf_filename`/`page_number`, KHÔNG PHẢI `source`/`page` như bên text. Đọc
    nhầm `metadata.get("source")` sẽ luôn ra None -> cả nhóm hinh bị gán nhầm
    ngoai_pham_vi ở retrieval_benchmark.py. KHÔNG BAO GIỜ đọc `source`/`page`
    ở hàm này.
    """
    return {
        "source_book": str(meta.get("pdf_filename") or ""),
        "source_page": str(meta.get("page_number")) if meta.get("page_number") is not None else "",
        "figure_label": str(meta.get("figure_label") or ""),
    }


def _dem_anh_hop_le(client) -> Dict[str, list]:
    """Đếm/lấy ids ảnh hợp lệ với ĐÚNG MỘT bộ lọc, dùng cho CẢ đếm lẫn lấy mẫu.

    Bộ lọc: is_active=True, review_status not in (rejected, deleted), và có
    figure_label HOẶC crop_text không rỗng. Trước phản biện lần 4, bản nháp
    dùng bộ lọc KHÁC nhau ở bước đếm và bước lấy mẫu (lệch 2,6% trên corpus
    hôm nay) — nay dùng chung một hàm để không thể lệch nữa.
    """
    col = client.get_collection(IMAGE_METADATA_COLLECTION_NAME)
    got = col.get(include=["metadatas"], limit=1_000_000)  # cùng safety cap ablation.py đã dùng
    ids_hop_le = []
    metas_hop_le = {}
    for cid, meta in zip(got["ids"], got["metadatas"]):
        if meta.get("is_active") is False:
            continue
        if str(meta.get("review_status") or "").lower() in {"rejected", "deleted"}:
            continue
        if not (meta.get("figure_label") or meta.get("crop_text")):
            continue
        ids_hop_le.append(cid)
        metas_hop_le[cid] = meta
    return {"ids": ids_hop_le, "metas": metas_hop_le}


def _dem_van_ban_hop_le(client) -> Dict[str, list]:
    col = client.get_collection(TEXT_COLLECTION_NAME)
    got = col.get(include=["documents", "metadatas"], limit=1_000_000)
    ids_hop_le = []
    docs_hop_le = {}
    metas_hop_le = {}
    for cid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
        if doc and len(doc) >= MIN_CHUNK_CHARS:
            ids_hop_le.append(cid)
            docs_hop_le[cid] = doc
            metas_hop_le[cid] = meta
    return {"ids": ids_hop_le, "docs": docs_hop_le, "metas": metas_hop_le}


class _CauTron:
    """Cửa sổ trượt theo dõi tỉ lệ lỗi LLM — dừng hẳn script nếu vượt ngưỡng.

    Tìm ra ở phản biện lần 4 của spec: không có trần tổng cho cơ chế rút thay
    thế, nếu Groq lỗi hệ thống (đã xảy ra thật, D-173) script có thể đốt rất
    nhiều lệnh gọi trước khi ai đó nhận ra.
    """

    def __init__(self, window: int = CIRCUIT_BREAKER_WINDOW,
                 max_rate: float = CIRCUIT_BREAKER_MAX_ERROR_RATE):
        self._window = window
        self._max_rate = max_rate
        self._ket_qua: deque = deque(maxlen=window)

    def ghi_nhan(self, thanh_cong: bool) -> None:
        self._ket_qua.append(thanh_cong)
        if len(self._ket_qua) == self._window:
            ti_le_loi = 1 - (sum(self._ket_qua) / self._window)
            if ti_le_loi > self._max_rate:
                raise SystemExit(
                    f"Tỉ lệ lỗi LLM {ti_le_loi:.0%} vượt ngưỡng "
                    f"{self._max_rate:.0%} trên {self._window} lệnh gọi gần "
                    "nhất -> DỪNG HẲN (fail loudly thay vì âm thầm đốt quota). "
                    "Kiểm tra EVAL_LLM_* trong .env / hạn mức Groq trước khi "
                    "chạy lại.")


def _sinh_mot_cau(llm, prompt: str, cau_tron: _CauTron) -> Optional[dict]:
    """Gọi LLM 1 lần (tối đa 2 thử lại), trả None nếu thất bại cả 3 lần."""
    for lan in range(3):
        try:
            resp = llm.invoke(prompt)
            data = _parse_json(resp.content if hasattr(resp, "content") else str(resp))
            q = str(data.get("question", "")).strip()
            gt = str(data.get("ground_truth", "")).strip()
            if not q or not gt:
                raise ValueError("question/ground_truth rỗng")
            cau_tron.ghi_nhan(True)
            return {"question": q, "ground_truth": gt}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sinh câu lỗi (lần %d/3): %s", lan + 1, exc)
            if lan == 2:
                cau_tron.ghi_nhan(False)
                return None
            time.sleep(2)


def _sinh_van_ban(llm, ids: List[str], docs: Dict[str, str],
                   metas: Dict[str, dict], n_can: int,
                   da_dung: set, cau_tron: _CauTron) -> List[dict]:
    rows = []
    pool = [i for i in ids if i not in da_dung]
    random.shuffle(pool)
    idx = 0
    so_lan_thay = 0
    while len(rows) < n_can:
        if idx >= len(pool):
            raise SystemExit(
                f"Hết pool văn bản (cần {n_can}, đã hết {len(pool)} ứng viên) "
                "trước khi đủ số câu — tỉ lệ lỗi LLM quá cao hoặc pool quá nhỏ.")
        cid = pool[idx]
        idx += 1
        da_dung.add(cid)
        ket_qua = _sinh_mot_cau(llm, GEN_PROMPT_VAN_BAN.format(doan=docs[cid]), cau_tron)
        if ket_qua is None:
            so_lan_thay += 1
            continue
        m = metas[cid]
        rows.append({
            "question": ket_qua["question"], "loai": "van_ban",
            "source_book": str(m.get("source") or ""),
            "source_page": str(m.get("page")) if m.get("page") is not None else "",
            "figure_label": "", "ground_truth": ket_qua["ground_truth"],
        })
    if so_lan_thay:
        print(f"[build_testset] văn bản: đã thay {so_lan_thay} item lỗi LLM")
    return rows


def _sinh_hinh(llm, ids: List[str], metas: Dict[str, dict], n_can: int,
               da_dung: set, cau_tron: _CauTron) -> List[dict]:
    rows = []
    pool = [i for i in ids if i not in da_dung]
    random.shuffle(pool)
    idx = 0
    so_lan_thay = 0
    while len(rows) < n_can:
        if idx >= len(pool):
            raise SystemExit(
                f"Hết pool hình (cần {n_can}, đã hết {len(pool)} ứng viên) "
                "trước khi đủ số câu.")
        cid = pool[idx]
        idx += 1
        da_dung.add(cid)
        m = metas[cid]
        prompt = GEN_PROMPT_HINH.format(
            nhan=m.get("figure_label") or "(không có)",
            chu_thich=m.get("figure_caption") or "(không có)",
            chu_trong_hinh=m.get("crop_text") or "(không có)",
            ngu_canh=(m.get("context_text") or "")[:500] or "(không có)",
        )
        ket_qua = _sinh_mot_cau(llm, prompt, cau_tron)
        if ket_qua is None:
            so_lan_thay += 1
            continue
        cot = _anh_xa_hinh_sang_cot(m)
        rows.append({
            "question": ket_qua["question"], "loai": "hinh",
            **cot, "ground_truth": ket_qua["ground_truth"],
        })
    if so_lan_thay:
        print(f"[build_testset] hình: đã thay {so_lan_thay} item lỗi LLM")
    return rows


def _sinh_ngoai_pham_vi(llm, n_can: int, cau_tron: _CauTron) -> List[dict]:
    rows = []
    while len(rows) < n_can:
        mon = random.choice(MON_NGOAI_PHAM_VI)
        ket_qua = _sinh_mot_cau(llm, GEN_PROMPT_NGOAI_PHAM_VI.format(mon=mon), cau_tron)
        if ket_qua is None:
            continue
        rows.append({
            "question": ket_qua["question"], "loai": "ngoai_pham_vi",
            "source_book": "", "source_page": "", "figure_label": "",
            "ground_truth": ket_qua["ground_truth"],
        })
    return rows


def build(n_total: int, n_ngoai_pham_vi: int, seed: int) -> None:
    import chromadb

    _kiem_tra_input(n_total, n_ngoai_pham_vi)
    random.seed(seed)

    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    van_ban_pool = _dem_van_ban_hop_le(client)
    hinh_pool = _dem_anh_hop_le(client)
    n_chunk = len(van_ban_pool["ids"])
    n_anh = len(hinh_pool["ids"])

    n = _tinh_n_moi_nhom(n_total, n_ngoai_pham_vi, n_chunk, n_anh)
    print(f"[build_testset] index: {n_chunk} chunk hợp lệ, {n_anh} ảnh hợp lệ "
          f"-> p_hinh={n['p_hinh_do_duoc']}")
    print(f"[build_testset] N mục tiêu: van_ban={n['n_van_ban']} "
          f"hinh={n['n_hinh']} ngoai_pham_vi={n['n_ngoai_pham_vi']} "
          f"(tổng {n['n_van_ban'] + n['n_hinh'] + n['n_ngoai_pham_vi']})")

    _dem_pool_hinh_hop_le(n_chunk, n["n_van_ban"])
    _dem_pool_hinh_hop_le(n_anh, n["n_hinh"])

    if not is_configured():
        raise SystemExit(config_help())
    llm = get_eval_llm(temperature=0.7)
    cau_tron = _CauTron()
    da_dung: set = set()

    rows = []
    rows += _sinh_van_ban(llm, van_ban_pool["ids"], van_ban_pool["docs"],
                           van_ban_pool["metas"], n["n_van_ban"], da_dung, cau_tron)
    rows += _sinh_hinh(llm, hinh_pool["ids"], hinh_pool["metas"],
                        n["n_hinh"], da_dung, cau_tron)
    rows += _sinh_ngoai_pham_vi(llm, n["n_ngoai_pham_vi"], cau_tron)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=[
        "question", "loai", "source_book", "source_page",
        "figure_label", "ground_truth"])
    df.to_csv(DRAFT_CSV, index=False, encoding="utf-8-sig")

    meta = {
        "seed": seed, "n_total": n_total,
        "n_van_ban": n["n_van_ban"], "n_hinh": n["n_hinh"],
        "n_ngoai_pham_vi": n["n_ngoai_pham_vi"],
        "p_hinh_do_duoc": n["p_hinh_do_duoc"],
        "n_chunk_do_duoc": n_chunk, "n_anh_do_duoc": n_anh,
        "tao_luc": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "human_reviewed": False, "reviewed_at": None,
    }
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"[build_testset] đã ghi {DRAFT_CSV} ({len(df)} câu) + {META_JSON}")
    print("[build_testset] BẮT BUỘC duyệt tay trước khi dùng chính thức: "
          "đọc lại draft.csv, sửa câu/ground_truth sai, rồi chạy "
          "`python -m src.test.build_testset --mark-reviewed`")


def mark_reviewed() -> None:
    if not META_JSON.exists():
        raise SystemExit(f"Chưa có {META_JSON} — chạy sinh bộ test trước.")
    meta = json.loads(META_JSON.read_text(encoding="utf-8"))
    print(f"Xác nhận đã đọc và duyệt tay TOÀN BỘ {DRAFT_CSV} "
          f"({meta.get('n_total')} câu)?")
    xac_nhan = input("Gõ 'xac-nhan-da-doc' để tiếp tục: ").strip()
    if xac_nhan != "xac-nhan-da-doc":
        raise SystemExit("Chưa xác nhận — không đổi human_reviewed.")
    meta["human_reviewed"] = True
    meta["reviewed_at"] = datetime.now(timezone(timedelta(hours=7))).isoformat()
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"Đã đánh dấu human_reviewed=true trong {META_JSON}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=240)
    ap.add_argument("--n-ngoai-pham-vi", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mark-reviewed", action="store_true")
    args = ap.parse_args()

    if args.mark_reviewed:
        mark_reviewed()
        return 0
    build(args.n, args.n_ngoai_pham_vi, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Chạy lại test, xác nhận PASS**

Run: `pytest tests/test_build_testset_sampling.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Chạy `pytest tests/ -q` để chắc chắn không phá gì khác**

Run: `pytest tests/ -q`
Expected: PASS, 0 FAILED.

- [ ] **Step 6: Commit**

```bash
git add src/test/build_testset.py tests/test_build_testset_sampling.py
git commit -m "$(cat <<'EOF'
feat(test): them build_testset.py sinh bo test 240 cau ngau nhien (D-182)

Lay mau ngau nhien tren toan index (khong rang buoc phu deu quyen):
van_ban tu bien text, hinh tu bien anh (anh xa dung pdf_filename/
page_number, KHONG phai source/page), ngoai_pham_vi tu danh sach mon
co dinh. Co circuit-breaker khi ti le loi LLM > 30%, chan input vo ly,
va co cong nguoi duyet bat buoc (--mark-reviewed) truoc khi coi bo test
la chinh thuc.
EOF
)"
```

---

### Task 3: `testset_common.py` + `retrieval_benchmark.py` + `run_eval.py` (chạy SONG SONG với Task 2)

**Files:**
- Create: `src/test/testset_common.py`
- Create: `src/test/retrieval_benchmark.py`
- Create: `src/test/run_eval.py`
- Create: `tests/test_review_gate.py`
- Create: `tests/test_retrieval_benchmark_metrics.py`
- Create (tái tạo): `tests/test_mrr_metric.py`
- Create (tái tạo): `tests/rag/test_ablation_cache.py`

**Interfaces:**
- Consumes: `src.test.llm_client.get_eval_llm/is_configured/config_help`
  (tồn tại sau Task 1). File `src/test/testset/draft.csv` +
  `src/test/testset/meta.json` theo ĐÚNG schema ở mục "File Structure" — Task 2
  tạo ra, nhưng KHÔNG cần Task 2 xong trước để viết code (test dùng fixture
  CSV/json tự tạo, không phụ thuộc `build_testset.py` chạy thật).
- Produces:
  - `testset_common.require_human_reviewed(meta_path: Path, allow_draft: bool = False) -> None`
    — raise `SystemExit` nếu chưa duyệt và không `allow_draft`.
  - `testset_common.duong_dan_output(ten_file: str, allow_draft: bool) -> Path`
    — helper thêm hậu tố `_NHAP_CHUA_DUYET` khi `allow_draft=True`.
  - `retrieval_benchmark.py` export cấp module: `Cache`, `load_cache`, `Config`,
    `rank_for`, `chunk_ids_digest` (re-export từ `src.rag.bm25`),
    `TEXT_EXTRACTION_VERSION` (re-export từ `src.config`), `reciprocal_rank`,
    `KS`, `evaluate`, `build_cache`, `_gold_key`.

**Bối cảnh bắt buộc đọc trước khi viết code**: `src/test/ablation.py` HIỆN TẠI
(trước khi Task 1 xóa nó — đọc từ `git show <commit-trước-Task-1>:src/test/ablation.py`
hoặc từ bản đã trích dẫn đầy đủ trong lịch sử phiên làm việc/spec) chứa TOÀN BỘ
logic đúng cần giữ nguyên: `Cache`/`build_cache`/`topup_cache`/`load_cache`
(dòng 154-370), `Config`/`METHOD_LABELS`/`rank_for` (dòng 375-463), `_gold_key`/
`reciprocal_rank`/`evaluate` (dòng 468-588, gồm cả logic 3 nhóm `_gold_key is
None` / `suy_bien` / bình thường). **Copy các phần này GẦN NHƯ NGUYÊN VĂN** —
chỉ đổi phần I/O (đọc MỘT file `draft.csv` thay vì glob nhiều `*_testset.csv`)
và thêm luật "chỉ tính `ngoai_pham_vi_ti_le_tu_choi_dung` cho cấu hình `de_xuat`"
(mới, theo mục 3.3 của spec).

- [ ] **Step 1: Viết test cổng người duyệt**

Tạo `tests/test_review_gate.py`:

```python
import json

import pytest

from src.test.testset_common import duong_dan_output, require_human_reviewed


def test_raise_khi_chua_duyet(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"human_reviewed": False}), encoding="utf-8")
    with pytest.raises(SystemExit, match="chưa được duyệt tay"):
        require_human_reviewed(meta)


def test_khong_raise_khi_da_duyet(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"human_reviewed": True}), encoding="utf-8")
    require_human_reviewed(meta)  # không raise


def test_allow_draft_bo_qua_nhung_in_canh_bao(tmp_path, capsys):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"human_reviewed": False}), encoding="utf-8")
    require_human_reviewed(meta, allow_draft=True)  # không raise
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "NHÁP" in out or "nháp" in out or "draft" in out.lower()


def test_duong_dan_output_them_hau_to_khi_draft():
    p = duong_dan_output("eval_result.csv", allow_draft=True)
    assert p.name == "eval_result_NHAP_CHUA_DUYET.csv"


def test_duong_dan_output_khong_doi_khi_khong_draft():
    p = duong_dan_output("eval_result.csv", allow_draft=False)
    assert p.name == "eval_result.csv"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_review_gate.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'src.test.testset_common'`

- [ ] **Step 3: Viết `src/test/testset_common.py`**

```python
# -*- coding: utf-8 -*-
"""Tiện ích dùng chung cho `run_eval.py` và `retrieval_benchmark.py` (D-182).

CHỈ chứa cổng người duyệt tay + helper đặt tên file nháp — KHÔNG chứa logic
sinh câu hỏi (đó là việc riêng của `build_testset.py`, cố ý không import module
này để hai script không phụ thuộc chéo nhau).
"""
from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "testset"
DRAFT_CSV = OUT_DIR / "draft.csv"
META_JSON = OUT_DIR / "meta.json"


def require_human_reviewed(meta_path: Path, allow_draft: bool = False) -> None:
    """Chặn dùng một bộ test CHƯA được người duyệt tay, trừ khi `--allow-draft`.

    `--allow-draft` chỉ để tự kiểm code của chính người chạy — KHÔNG dùng số ra
    từ đó cho báo cáo (xem cảnh báo in ra + hậu tố `_NHAP_CHUA_DUYET` mà
    `duong_dan_output` thêm vào MỌI file output khi cờ này bật).
    """
    meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    if not meta.get("human_reviewed") and not allow_draft:
        raise SystemExit(
            f"{meta_path} chưa được duyệt tay (human_reviewed=false).\n"
            f"Đọc lại {DRAFT_CSV}, sửa câu/ground_truth sai, rồi chạy:\n"
            f"  python -m src.test.build_testset --mark-reviewed\n"
            f"(Chỉ dùng --allow-draft để tự kiểm code của CHÍNH BẠN, không dùng "
            f"số ra từ --allow-draft cho báo cáo.)")
    if allow_draft and not meta.get("human_reviewed"):
        print("!! CẢNH BÁO: đang chạy trên bộ test NHÁP, CHƯA người duyệt tay. "
              "Mọi file output sẽ mang hậu tố _NHAP_CHUA_DUYET — KHÔNG dùng số "
              "này cho báo cáo tốt nghiệp.")


def duong_dan_output(ten_file: str, allow_draft: bool) -> Path:
    """Thêm hậu tố `_NHAP_CHUA_DUYET` vào tên file khi `allow_draft=True`.

    Cảnh báo console không đủ (D-182, phản biện lần 4 của spec): nếu output bị
    redirect vào log hoặc file được mở lại nhiều ngày sau, phải phân biệt được
    nháp với chính thức chỉ bằng NHÌN TÊN FILE.
    """
    p = OUT_DIR / ten_file
    if not allow_draft:
        return p
    return p.with_name(f"{p.stem}_NHAP_CHUA_DUYET{p.suffix}")
```

- [ ] **Step 4: Chạy lại test cổng người duyệt, xác nhận PASS**

Run: `pytest tests/test_review_gate.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Viết test cho `retrieval_benchmark.py` (metrics thuần, không cần ChromaDB)**

Tạo `tests/test_retrieval_benchmark_metrics.py`:

```python
import pytest

from src.test.retrieval_benchmark import KS, _gold_key, evaluate, reciprocal_rank


def test_reciprocal_rank_giu_nguyen_hanh_vi():
    assert reciprocal_rank([False, True, False]) == 0.5
    assert reciprocal_rank([True, False]) == 1.0
    assert reciprocal_rank([False, False]) == 0.0


def test_gold_key_rong_khi_thieu_source_book_hoac_page():
    assert _gold_key({"source_book": "", "source_page": "5"}) is None
    assert _gold_key({"source_book": "SGK_KHTN_6_CD", "source_page": ""}) is None
    assert _gold_key({}) is None


def test_gold_key_hop_le():
    assert _gold_key({"source_book": "SGK_KHTN_6_CD", "source_page": "5"}) \
        == ("SGK_KHTN_6_CD", 5)


class _FakeConfig:
    label = "fake"
    mode = "dense"
    rerank = False
    gate = False


def _fake_rank_for(*args, **kwargs):
    return ["c1", "c2", "c3", "c4", "c5"]


def test_evaluate_phan_biet_3_nhom(monkeypatch):
    monkeypatch.setattr(
        "src.test.retrieval_benchmark.rank_for",
        lambda cfg, q, cache, sparse, top_n, gate_stats=None: _fake_rank_for())
    monkeypatch.setattr(
        "src.test.retrieval_benchmark.method_label", lambda cfg: "")

    rows = [
        # nhóm 1: không có trang vàng -> ngoai_pham_vi
        {"question": "q_opv", "source_book": "", "source_page": "",
         "_n_gold_chunks": 0},
        # nhóm 2: có trang vàng, 0 chunk -> suy_bien
        {"question": "q_sb", "source_book": "SGK_KHTN_6_CD",
         "source_page": "999", "_n_gold_chunks": 0},
        # nhóm 3: có trang vàng, có chunk -> tính bình thường
        {"question": "q_ok", "source_book": "SGK_KHTN_6_CD",
         "source_page": "5", "_n_gold_chunks": 5},
    ]
    page_of = {f"c{i}": ("SGK_KHTN_6_CD", 5) for i in range(1, 6)}
    out = evaluate(_FakeConfig(), rows, cache=None, sparse=None, page_of=page_of)

    assert out["so_cau"] == 1          # chỉ nhóm 3 vào mẫu P/R/F1/MRR
    assert out["suy_bien_gold_0_chunk"] == 1
    assert out["ngoai_pham_vi_so_cau"] == 1
    for k in KS:
        assert out[f"P@{k}"] > 0       # nhóm 3 khớp hết -> P/R > 0
```

- [ ] **Step 6: Chạy test, xác nhận FAIL**

Run: `pytest tests/test_retrieval_benchmark_metrics.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 7: Viết `src/test/retrieval_benchmark.py`**

Cấu trúc: copy TOÀN BỘ nội dung `ablation.py` (phần import, `Cache`,
`build_cache`, `topup_cache`, `load_cache`, `Config`, `METHOD_LABELS`,
`method_label`, `rank_for`, `_gold_key`, `reciprocal_rank`, `KS`, `evaluate`,
`build_page_lookup`, `ALL_CONFIGS`, `REPORT_CONFIGS`, `FUSION_CONFIGS`) GIỮ
NGUYÊN — chỉ đổi 3 chỗ:

1. **`load_testset`**: đổi từ glob nhiều `*_testset.csv` trong một thư mục
   sang đọc MỘT file `draft.csv`:

```python
def load_testset(csv_path: Path) -> List[dict]:
    rows: List[dict] = []
    with io.open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    return rows
```

2. **`evaluate()`**: thêm luật "chỉ tính tỉ lệ từ chối đúng cho cấu hình
   `de_xuat`" (mới theo mục 3.3 spec, câu hỏi để mở đã chốt ở phần "Đề xuất
   tạm" của spec) — sửa đoạn cuối hàm `evaluate()`:

```python
    # (giữ nguyên đoạn tính out_scope/tu_choi_dung phía trên KHÔNG đổi)
    #
    # CHỈ tính tỉ lệ từ chối đúng cho cấu hình "de_xuat" (production, có
    # RERANK_SCORE_MIN làm mốc rõ ràng) — 3 cấu hình còn lại ghi None (in ra
    # "n/a") vì RERANK_SCORE_MIN vô nghĩa khi rerank=off, và không có ngưỡng
    # tương đương đã đo cho BM25/dense thô (spec mục 3.3, "còn mở, đã chốt").
    if method_label(cfg) != "de_xuat":
        out["ngoai_pham_vi_ti_le_tu_choi_dung"] = None
```

   (Đặt đoạn này NGAY SAU dòng `out["ngoai_pham_vi_ti_le_tu_choi_dung"] = tu_choi_dung`
   hiện có trong `ablation.py`, ghi đè lại thành `None` khi không phải
   `de_xuat` — không xóa phần tính `tu_choi_dung` phía trên, vì các cấu hình
   khác vẫn cần `out_scope`/`suy_bien` tính đúng.)

3. **`main()`**: đổi `--testset-dir` (thư mục) thành `--testset-csv` (một
   file, mặc định `src/test/testset/draft.csv`), thêm cổng người duyệt, thêm
   `--allow-draft`, đổi output path qua `testset_common.duong_dan_output`, bỏ
   `--group-by` (không còn ý nghĩa — không còn nhãn theo quyển/`do_kho`/
   `phan_mon` trong CSV mới, và CBHD đã nói rõ không tách theo quyển/môn):

```python
def main() -> int:
    from src.test.testset_common import (DRAFT_CSV, META_JSON,
                                          duong_dan_output,
                                          require_human_reviewed)

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--testset-csv", default=str(DRAFT_CSV))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--build-cache", action="store_true")
    ap.add_argument("--topup-cache", action="store_true")
    ap.add_argument("--allow-draft", action="store_true")
    ap.add_argument(
        "--chi-4-phuong-phap", action="store_true",
        help="Chỉ chạy 4 cấu hình CBHD yêu cầu (keyword/dense/truyền thống/"
             "đề xuất, D-181 #3) — dùng cho báo cáo chương 4/5.")
    args = ap.parse_args()

    require_human_reviewed(META_JSON, allow_draft=args.allow_draft)

    rows = load_testset(Path(args.testset_csv))
    if not rows:
        print(f"Không có dữ liệu trong {args.testset_csv}")
        return 1
    collection = open_text_collection()
    sparse = get_sparse_index(collection=collection)
    page_of, per_page = build_page_lookup(collection)
    for row in rows:
        gold = _gold_key(row)
        row["_n_gold_chunks"] = per_page.get(gold, 0) if gold else 0

    _suy_bien = [r for r in rows
                 if _gold_key(r) is not None and r["_n_gold_chunks"] == 0]
    if _suy_bien:
        print(f"\n!! {len(_suy_bien)}/{len(rows)} câu CÓ trang vàng nhưng "
              "trang đó KHÔNG có chunk nào trong index -> bị loại khỏi "
              "P/R/F1@K, và KHÔNG được tính là câu ngoài phạm vi:")
        for r in _suy_bien[:10]:
            print(f"   {_gold_key(r)}  {str(r['question'])[:60]!r}")

    cache_path = Path(args.cache)
    if args.build_cache:
        cache = build_cache(rows, collection, sparse, cache_path)
    elif args.topup_cache:
        cache = topup_cache(load_cache(cache_path, collection,
                                       check_sparse_params=False),
                            rows, collection, sparse, cache_path)
    else:
        cache = load_cache(cache_path, collection)

    def table(title, configs):
        rows_out = [evaluate(c, rows, cache, sparse, page_of) for c in configs]
        head = (f"{'cấu hình':38s} "
                + " ".join(f"{'R@' + str(k):>7s}" for k in KS)
                + f" {'MRR':>7s} {'P@5':>7s} {'F1@10':>7s}")
        print(f"\n### {title}")
        print(head)
        for r in rows_out:
            print(f"{r['cau_hinh']:38s} "
                  + " ".join(f"{r['R@' + str(k)]:7.3f}" for k in KS)
                  + f" {r['MRR']:7.3f} {r['P@5']:7.3f} {r['F1@10']:7.3f}")
        return rows_out

    if args.chi_4_phuong_phap:
        results = table("4 phương pháp báo cáo (keyword/dense/truyền thống/"
                        "đề xuất)", REPORT_CONFIGS)
    else:
        results = table("12 cấu hình hợp đồng", ALL_CONFIGS)

    out_csv = duong_dan_output("retrieval_report.csv", args.allow_draft)
    out_md = duong_dan_output("retrieval_report.md", args.allow_draft)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for r in results:
        for k in r:
            if k not in fields:
                fields.append(k)
    with io.open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(results)
    with io.open(out_md, "w", encoding="utf-8") as fh:
        fh.write(f"# Bảng đối chiếu truy xuất\n\n{len(results)} cấu hình.\n")
    print(f"\nĐã lưu: {out_csv}")
    return 0
```

Đầu file, giữ nguyên toàn bộ khối import của `ablation.py` (bao gồm
`from src.rag.bm25 import chunk_ids_digest` và
`from src.config import (..., TEXT_EXTRACTION_VERSION, ...)` ở CẤP MODULE —
đây chính là điều kiện để monkeypatch của `tests/rag/test_ablation_cache.py`
hoạt động đúng, KHÔNG được đổi thành gọi qua `config.TEXT_EXTRACTION_VERSION`
mỗi lần dùng).

- [ ] **Step 8: Chạy lại test retrieval_benchmark, xác nhận PASS**

Run: `pytest tests/test_retrieval_benchmark_metrics.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 9: Tái tạo `tests/test_mrr_metric.py` với import mới**

```python
from src.test.retrieval_benchmark import reciprocal_rank


def test_reciprocal_rank_first_hit():
    assert reciprocal_rank([False, True, False]) == 0.5
    assert reciprocal_rank([True, False]) == 1.0
    assert reciprocal_rank([False, False]) == 0.0
```

- [ ] **Step 10: Tái tạo `tests/rag/test_ablation_cache.py` với import mới (nội dung giữ NGUYÊN, chỉ đổi import)**

```python
# -*- coding: utf-8 -*-
"""Bộ nhớ đệm của bảng đối chiếu: đắt, nên không được huỷ nhầm và phải resume."""

import json

import pytest

from src.test import retrieval_benchmark
from src.test.retrieval_benchmark import Cache, load_cache


def _cache(n=3, digest="dig", version="vTEST", params="k1=0.7 b=0.75 tok=plain n=50"):
    return Cache(
        index_digest=digest,
        text_version=version,
        sparse_params=params,
        dense={f"câu {i}": [(f"c{i}", 0.1 * i)] for i in range(n)},
        rerank={f"câu {i}": {f"c{i}": 0.9} for i in range(n)},
    )


class FakeCollection:
    def get(self, include=None, limit=None):
        return {"ids": ["a", "b"]}


def test_json_di_ve_khong_mat_gi(tmp_path):
    c = _cache()
    p = tmp_path / "ab.json"
    p.write_text(json.dumps(c.to_json(), ensure_ascii=False), encoding="utf-8")
    back = Cache.from_json(json.loads(p.read_text(encoding="utf-8")))
    assert back.dense == c.dense and back.rerank == c.rerank
    assert back.sparse_params == c.sparse_params


def test_dem_thuoc_index_KHAC_thi_raise(tmp_path, monkeypatch):
    p = tmp_path / "ab.json"
    p.write_text(json.dumps(_cache(digest="cu").to_json(), ensure_ascii=False),
                 encoding="utf-8")
    monkeypatch.setattr(retrieval_benchmark, "chunk_ids_digest", lambda ids: "moi")
    with pytest.raises(RuntimeError, match="digest"):
        load_cache(p, FakeCollection())


def test_doi_tham_so_kenh_thua_thi_raise_TRU_KHI_sap_topup(tmp_path, monkeypatch):
    p = tmp_path / "ab.json"
    p.write_text(json.dumps(_cache(params="k1=1.2 b=0.75 tok=folded n=50").to_json(),
                            ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(retrieval_benchmark, "chunk_ids_digest", lambda ids: "dig")
    monkeypatch.setattr(retrieval_benchmark, "TEXT_EXTRACTION_VERSION", "vTEST")

    with pytest.raises(RuntimeError, match="tham số thưa"):
        load_cache(p, FakeCollection())
    got = load_cache(p, FakeCollection(), check_sparse_params=False)
    assert len(got.dense) == 3


def test_thieu_dem_thi_raise_chu_khong_cham_tren_phan_da_co(tmp_path):
    cache = _cache(n=2)
    cfg = retrieval_benchmark.Config(mode="dense", rerank=False, gate=False)
    with pytest.raises(RuntimeError, match="thiếu câu hỏi"):
        retrieval_benchmark.rank_for(cfg, "câu 99", cache, sparse=None, top_n=5)
```

- [ ] **Step 11: Chạy 2 test vừa tái tạo, xác nhận PASS**

Run: `pytest tests/test_mrr_metric.py tests/rag/test_ablation_cache.py -v`
Expected: PASS toàn bộ 5 test (1 + 4).

- [ ] **Step 12: Viết `src/test/run_eval.py`**

Copy logic từ `evaluator.py` HIỆN TẠI (đã trích đầy đủ ở trên trong lịch sử
phiên) GIỮ NGUYÊN gần như toàn bộ: `JUDGE_PROMPT`, `_parse_json`,
`get_answer_and_context`, `JUDGE_RETRIES`/`JUDGE_BACKOFF_SECONDS`,
`_la_loi_tam_thoi`, `judge_answer`, `NUM_COLS`, `_loai_cau_hoi`,
`aggregate_by_loai`, `TEN_LOAI_HIEN_THI`. Đổi:

1. Import `from src.test.llm_client import get_eval_llm, is_configured, config_help`
   (thay `eval_llm`).
2. **Bỏ hẳn** `chon_testsets`/`book_of`/`result_path_for`/`_doc_ket_qua_cu` —
   không còn nhiều file theo quyển, chỉ MỘT file `draft.csv`.
3. `evaluate_book` đổi tên thành `evaluate_all` — chạy trên MỘT DataFrame
   duy nhất (đọc từ `testset_common.DRAFT_CSV`), không lặp theo file:

```python
def evaluate_all(csv_path: str, judge_llm) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    print(f"\n=== Đánh giá: {len(df)} câu ===")

    records = []
    for i, row in df.iterrows():
        q = str(row["question"])
        gt = str(row.get("ground_truth", ""))
        src_book = row.get("source_book")
        src_book = None if pd.isna(src_book) else str(src_book)
        src_page_raw = row.get("source_page")
        try:
            src_page = None if pd.isna(src_page_raw) else int(src_page_raw)
        except (TypeError, ValueError):
            src_page = None
        loai = _loai_cau_hoi(row.get("loai"))

        rag = get_answer_and_context(q)
        verdict = judge_answer(judge_llm, q, gt, "\n\n".join(rag["contexts"]), rag["answer"])

        retrieved_sources = "; ".join(
            f"{(m.get('source') or '?')}:p{m.get('page')}" for m in rag["metas"]
        )
        records.append({
            "question": q, "loai": loai, "source_book": src_book,
            "source_page": src_page, "retrieved": retrieved_sources,
            "rag_answer": rag["answer"], "ground_truth": gt, **verdict,
        })
        print(f"  [{i + 1:>3}/{len(df)}] loai={loai:<13} "
              f"correct={verdict['judge_correctness']:.0f}/5 "
              f"faithful={verdict['judge_faithfulness']:.0f}/5 "
              f"relevancy={verdict['judge_relevancy']:.0f}/5")

    return pd.DataFrame(records)
```

   (Cột nguồn dữ liệu là `loai`, KHÔNG phải `nguon_cau_hoi` — khớp schema mới
   của `draft.csv` do `build_testset.py` ghi ra. Sửa `_loai_cau_hoi`/
   `aggregate_by_loai` copy từ `evaluator.py` để đọc đúng tên cột `loai` thay
   vì `nguon_cau_hoi` ở MỌI chỗ.)

4. `main()` gọn lại — không còn `--book`/`--bo-qua-da-co`/`--hau-to` (một file
   duy nhất, không cần các cờ đó), thêm `--allow-draft`:

```python
if __name__ == "__main__":
    import argparse
    from src.test.testset_common import (DRAFT_CSV, META_JSON,
                                          duong_dan_output,
                                          require_human_reviewed)

    _ap = argparse.ArgumentParser(description="Đánh giá đầu-cuối, CÓ gọi LLM")
    _ap.add_argument("--testset-csv", default=str(DRAFT_CSV))
    _ap.add_argument("--allow-draft", action="store_true")
    _a = _ap.parse_args()

    require_human_reviewed(META_JSON, allow_draft=_a.allow_draft)

    if not is_configured():
        print(config_help())
        raise SystemExit(1)

    judge_llm = get_eval_llm(temperature=0.0)
    all_records = evaluate_all(_a.testset_csv, judge_llm)

    result_csv = duong_dan_output("eval_result.csv", _a.allow_draft)
    all_records.to_csv(result_csv, index=False, encoding="utf-8-sig")

    report = aggregate_by_loai(all_records)
    report_csv = duong_dan_output("eval_report.csv", _a.allow_draft)
    report_md = duong_dan_output("eval_report.md", _a.allow_draft)
    report.to_csv(report_csv, index=False, encoding="utf-8-sig")

    lines = ["# Báo cáo đánh giá RAG theo LOẠI câu hỏi\n",
             f"Tổng số câu: {len(all_records)} | "
             f"Judge: {os.getenv('EVAL_LLM_MODEL', '?')}\n",
             "## Tổng hợp theo loại câu hỏi\n",
             "| Loại | Số câu | Correct/5 | Faithful/5 | Relevancy/5 |",
             "|---|---|---|---|---|"]
    for _, r in report.iterrows():
        ten_hien_thi = TEN_LOAI_HIEN_THI.get(r["loai_cau_hoi"], r["loai_cau_hoi"])
        lines.append(
            f"| {ten_hien_thi} | {int(r['num_questions'])} | "
            f"{r['judge_correctness']:.2f} | {r['judge_faithfulness']:.2f} | "
            f"{r['judge_relevancy']:.2f} |")
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nĐã lưu: {result_csv}, {report_csv}, {report_md}")
    print("\n" + report.to_string(index=False))
```

- [ ] **Step 13: Chạy toàn bộ test suite của Task 3**

Run: `pytest tests/test_review_gate.py tests/test_retrieval_benchmark_metrics.py tests/test_mrr_metric.py tests/rag/test_ablation_cache.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 14: Chạy `pytest tests/ -q` để chắc chắn không phá gì khác**

Run: `pytest tests/ -q`
Expected: PASS, 0 FAILED.

- [ ] **Step 15: Commit**

```bash
git add src/test/testset_common.py src/test/retrieval_benchmark.py \
  src/test/run_eval.py tests/test_review_gate.py \
  tests/test_retrieval_benchmark_metrics.py tests/test_mrr_metric.py \
  tests/rag/test_ablation_cache.py
git commit -m "$(cat <<'EOF'
feat(test): them retrieval_benchmark.py + run_eval.py + testset_common.py (D-182)

retrieval_benchmark.py thay ablation.py: giu nguyen logic Cache/Config/
rank_for/_gold_key/reciprocal_rank/evaluate (3 nhom van_ban+hinh/
suy_bien/ngoai_pham_vi), doc MOT file draft.csv thay vi glob nhieu
*_testset.csv, gioi han ti le tu choi dung chi tinh cho cau hinh
de_xuat. run_eval.py thay evaluator.py: bo logic nhieu-file-theo-quyen
(chon_testsets/book_of), giu nguyen judge_answer/JudgePool/
aggregate_by_loai. testset_common.py: cong nguoi duyet bat buoc +
danh dau file nhap qua hau to _NHAP_CHUA_DUYET.
EOF
)"
```

---

### Task 4: Phản biện đối kháng (Opus 5) — TRƯỚC KHI báo Task 2/3 là xong

**Không phải một task viết code** — dispatch MỘT subagent Opus 5 sau khi Task 2
và Task 3 đều đã commit, với prompt yêu cầu:

1. Đọc `document/specs/2026-09-03-eval-rebuild-design.md` toàn bộ.
2. Đọc `src/test/build_testset.py`, `src/test/testset_common.py`,
   `src/test/retrieval_benchmark.py`, `src/test/run_eval.py` toàn bộ.
3. Đối chiếu TỪNG điểm trong spec (đặc biệt 4 lượt phản biện đã liệt kê ở
   cuối spec, mục 8) với code thật vừa viết — code có làm ĐÚNG những gì spec
   yêu cầu sau khi sửa không, có sót gì mới không.
4. Chạy `pytest tests/ -q` và xác nhận xanh.
5. Chạy thử `python -m src.test.build_testset --n 6 --n-ngoai-pham-vi 1 --seed 1`
   (cần `.env` có `EVAL_LLM_*` cấu hình — nếu môi trường subagent không có
   quyền gọi Groq thật, BỎ QUA bước này và nêu rõ trong báo cáo, không giả vờ
   đã chạy).
6. Báo cáo mọi finding theo mức độ nghiêm trọng, như 4 lượt phản biện trước đã
   làm với chính spec.

Nếu subagent tìm thấy vấn đề nghiêm trọng: **quay lại Task 2/3 sửa trực tiếp**
(không tạo Task 4b/4c — sửa tại chỗ, chạy lại `pytest tests/ -q`, commit fixup
riêng biệt với message rõ "sửa sau phản biện Task 4"), rồi mới đi tiếp Task 5.

- [ ] **Step 1: Dispatch subagent Opus 5 phản biện, đợi kết quả**
- [ ] **Step 2: Sửa mọi finding nghiêm trọng/trung bình được xác nhận đúng (verify lại bằng tay trước khi sửa, đừng tin mù)**
- [ ] **Step 3: `pytest tests/ -q` xanh sau khi sửa**
- [ ] **Step 4: Commit fixup (nếu có sửa)**

---

### Task 5: Chạy thử `--n 6`, xác nhận bằng mắt

**Không phải task viết code thường trực** — chạy thật với quota LLM thấp để
xác nhận toàn bộ pipeline hoạt động trước khi người dùng tự chạy `--n 240`.

- [ ] **Step 1: Đảm bảo `.env` có `EVAL_LLM_MODEL`/`EVAL_LLM_MODELS` + key hợp lệ**

Run: `python -c "from src.test.llm_client import is_configured; print(is_configured())"`
Expected: `True`. Nếu `False`, DỪNG và báo người dùng — không tự đoán cấu hình.

- [ ] **Step 2: Sinh thử 6 câu**

Run: `python -m src.test.build_testset --n 6 --n-ngoai-pham-vi 1 --seed 1`
Expected: exit 0, in ra 4 số N (`van_ban`/`hinh`/`ngoai_pham_vi`/tổng), tạo
`src/test/testset/draft.csv` (6 dòng) + `meta.json` (`human_reviewed: false`).

- [ ] **Step 3: Đọc bằng mắt `draft.csv`**

Mở file, kiểm tra: câu hỏi có nghĩa, `ground_truth` khớp nội dung, cột
`source_book`/`source_page` của dòng `hinh` KHÔNG rỗng (đây chính là ca lỗi
nghiêm trọng nhất tìm được ở phản biện lần 4 — nếu rỗng, DỪNG và điều tra
`_anh_xa_hinh_sang_cot` ngay, đừng đi tiếp).

- [ ] **Step 4: Duyệt tay (giả lập — chấp nhận nháp này vì chỉ để tự kiểm code)**

Run: `python -m src.test.build_testset --mark-reviewed` (gõ `xac-nhan-da-doc`
khi được hỏi).
Expected: `meta.json` có `human_reviewed: true`.

- [ ] **Step 5: Chạy bảng đối chiếu truy xuất**

Run: `python -m src.test.retrieval_benchmark --build-cache --chi-4-phuong-phap`
Expected: exit 0, in ra bảng 4 cấu hình, tạo `retrieval_report.csv`/`.md` (không
có hậu tố `_NHAP_CHUA_DUYET` vì không dùng `--allow-draft` và `meta.json` đã
`human_reviewed: true`).

- [ ] **Step 6: Chạy đánh giá đầu-cuối**

Run: `python -m src.test.run_eval`
Expected: exit 0, in ra 6 dòng tiến trình + bảng tổng hợp theo loại, tạo
`eval_result.csv`/`eval_report.csv`/`.md`.

- [ ] **Step 7: Đọc `eval_result.csv` bằng mắt, xác nhận không có lỗi rõ ràng**

Kiểm câu ngoài phạm vi có bị hệ thống trả lời bịa không (phải từ chối đúng);
kiểm câu hình có đúng chủ đề không.

- [ ] **Step 8: Báo cáo kết quả cho người dùng, KHÔNG tự ý chạy `--n 240`**

`--n 240` là quyết định và hành động của người dùng (tốn nhiều giờ + quota
Groq) — chỉ báo cáo pipeline đã sẵn sàng, không tự chạy.

---

### Task 6: `document/decision_log.html` (D-182) + `CLAUDE.md`

**Files:**
- Modify: `document/decision_log.html`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Thêm entry D-182 vào `document/decision_log.html`**

Thêm NGAY TRƯỚC dòng `];` đóng mảng `DECISIONS` (sau entry D-181, dòng ~1183).
**QUAN TRỌNG (bài học D-136/D-117)**: viết `notes` là MỘT chuỗi liên tục trên
MỘT dòng logic, dùng `<br><br>` để xuống đoạn, KHÔNG dùng xuống dòng vật lý
trong chuỗi JS — chạy `pytest tests/test_decision_log.py` ngay sau khi sửa.

```javascript
    {
      id: "D-182", date: "2026-09-04",
      decision: "Hủy cấu trúc 240-câu-cố-định-theo-quyển của D-181 (192 văn bản 16/quyển + 48 hình 4/quyển), chuyển sang lấy mẫu HOÀN TOÀN NGẪU NHIÊN trên toàn corpus (không ràng buộc phủ đều quyển) — quyết định của người dùng sau khi soát kết quả D-181 (nhóm Hình chấm Correct chỉ 2,06/5 so với Văn bản 4,36/5, mẫu 4 câu/quyển quá nhỏ để chẩn đoán). Viết lại TOÀN BỘ pipeline sinh test + đánh giá từ 0, xóa hết code cũ (kể cả ablation.py vừa viết theo D-181 sáng cùng ngày).",
      notes: "Thiết kế đầy đủ ở `document/specs/2026-09-03-eval-rebuild-design.md` (commit `2e3e1b58`), qua ĐÚNG 4 lượt phản biện đối kháng trước khi code (2 tự-phản-biện + 2 subagent độc lập) — tìm và sửa hơn 15 vấn đề, 2 trong số đó nghiêm trọng nhất: (1) `_gold_key()`/nhóm `suy_bien` của `ablation.py` cũ (3 trường hợp: không-có-trang-vàng / có-trang-vàng-0-chunk / bình-thường, KHÔNG raise ở đâu) suýt bị thoái lui thành 'raise khi gold rỗng' ở một bản nháp giữa chừng; (2) `biology_image_metadata` dùng khoá `pdf_filename`/`page_number`, KHÔNG PHẢI `source`/`page` như `biology_text` — nếu bỏ sót ánh xạ này, cả nhóm câu Hình sẽ bị gán nhầm `ngoai_pham_vi` một cách âm thầm (phát hiện bằng truy vấn DB thật, không phải suy đoán schema). <br><br> **Xóa hoàn toàn**: `generate_testsets.py`, `build_testset_240.py`, `build_image_questions.py`, `evaluator.py`, `metrics.py`, `ablation.py`, `ablation_multimodal.py`, `bm25_sweep.py`, `review_testset.py`, `prompt_scope_probe.py`, `qa_citation_page.py`, `testsets/`, `testsets_240/`, `eval_240_results/`, 3 script `scripts/{run_ablation,run_testsets,sau_etl_anh}.ps1` (gọi trực tiếp các module trên qua dòng lệnh PowerShell — lớp phụ thuộc mà grep `import` Python ban đầu bỏ sót), và 9 file `tests/` phụ thuộc trực tiếp các module đó. <br><br> **Ba script mới**: `build_testset.py` (sinh 240 câu ngẫu nhiên — mục tiêu/khoảng cho từng nhóm văn_bản/hình/ngoài_phạm_vi, KHÔNG random cả tỉ lệ 3 nhóm; tỉ lệ văn_bản/hình tính từ kích thước thật của index tại thời điểm chạy, không hardcode), `retrieval_benchmark.py` (thay `ablation.py`, giữ nguyên MRR + K∈{1,3,5,10,20} theo đúng yêu cầu MRR của `goal.docx` mà một bản nháp giữa chừng suýt làm mất), `run_eval.py` (thay `evaluator.py`, đơn giản hóa vì chỉ còn MỘT file testset thay vì 12 file theo quyển). Đổi tên `eval_llm.py` -> `llm_client.py` (giữ nguyên `JudgePool`, không viết lại — tránh debug lại rate-limit đã mất 3 vòng ở D-163/D-168/D-173). <br><br> **Cổng người duyệt bắt buộc MỚI**: `require_human_reviewed()` trong `testset_common.py` raise nếu `meta.json` chưa `human_reviewed: true` — `--allow-draft` chỉ để tự kiểm code, mọi file output khi đó mang hậu tố `_NHAP_CHUA_DUYET` (không chỉ cảnh báo console, để không ai nhầm nháp với số chính thức khi mở file nhiều ngày sau). <br><br> **Đánh đổi đã CHẤP NHẬN, không phải bỏ sót**: xóa `qa_citation_page.py` làm mất hẳn cổng đo G3 (deterministic, không cần LLM, đo trang trích dẫn có chứa câu trả lời không) — không có gì thay thế trong 3 script mới, LLM-judge của `run_eval.py` đo chiều khác. <br><br> **Việc còn lại sau khi entry này được ghi**: chạy `--n 6` xác nhận bằng mắt (Task 5 của plan triển khai), rồi người dùng tự chạy `--n 240` + duyệt tay, rồi mới cập nhật `report/tex_source/` (số 240/270 câu cũ trong đó, từ D-173..D-175, đã lỗi thời hoàn toàn).",
      tags: ["Evaluation", "Testing", "LLM-Judge", "Planning", "Breaking-Change"],
    },
```

- [ ] **Step 2: Chạy test lint decision log**

Run: `pytest tests/test_decision_log.py -v`
Expected: PASS.

- [ ] **Step 3: Sửa `CLAUDE.md` — thay thế toàn bộ mục "Cấu trúc đánh giá mới theo yêu cầu CBHD (2026-09-03, D-181)"**

Đọc mục hiện tại (từ `## Cấu trúc đánh giá mới theo yêu cầu CBHD` tới ngay
trước `## Quy tắc làm việc`) và thay bằng một mục mới mô tả D-182: tóm tắt
quyết định (lấy mẫu ngẫu nhiên, không ràng buộc quyển), tên 3 script mới, cổng
người duyệt bắt buộc, và trạng thái hiện tại (đã code xong, đã chạy `--n 6`
xác nhận — Task 5 hoàn tất; `--n 240` CHƯA chạy, chờ người dùng).

- [ ] **Step 4: Sửa mục "Lệnh" — `## Đánh giá (trong src/test/)`**

Thay các dòng lệnh cũ:
```
python src/test/generate_testsets.py ...
python src/test/evaluator.py ...
python -m src.test.ablation ...
python -m src.test.recall_at_k ...
python -m src.test.build_testset_240 ...
python -m src.test.build_image_questions ...
```
bằng:
```bash
python -m src.test.build_testset                       # sinh nháp 240 câu, seed 42
python -m src.test.build_testset --mark-reviewed        # xác nhận đã duyệt tay
python -m src.test.retrieval_benchmark --build-cache    # bảng 4 phương pháp x P/R/F1/MRR@K
python -m src.test.run_eval                             # đánh giá đầu-cuối LLM-judge
```

Xóa các dòng nhắc tới `ablation_multimodal.py`, `bm25_sweep.py`,
`review_testset.py`, `prompt_scope_probe.py`, `qa_citation_page.py` ở bất kỳ
đâu trong file.

- [ ] **Step 5: Cập nhật bảng "Trạng thái tiến độ"**

Dòng "Bộ test câu hỏi" và "Đánh giá đầu-cuối" — ghi rõ số 240/270 câu cũ
(D-173..D-181) đã lỗi thời hoàn toàn, đang chờ lượt `--n 240` mới theo D-182.

- [ ] **Step 6: Commit**

```bash
git add document/decision_log.html CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude,decision-log): ghi D-182, cap nhat CLAUDE.md theo pipeline moi

Ghi lai quyet dinh huy cau truc 240-cau-co-dinh-theo-quyen cua D-181,
chuyen sang lay mau ngau nhien toan corpus. Cap nhat CLAUDE.md: muc
"Cau truc danh gia", lenh trong src/test/, bang trang thai tien do.
EOF
)"
```

---

### Task 7: Memory (6 file + `MEMORY.md`)

**Files** (đường dẫn tuyệt đối,
`C:\Users\lcdkhoa\.claude\projects\D--personal-repo-project-rag\memory\`):

- [ ] **Step 1: Viết lại `eval_structure_revision_2026_09.md`**

Nội dung hiện tại mô tả TOÀN BỘ D-181 (240 câu cố định theo quyển) — thay bằng
mô tả D-182: lấy mẫu ngẫu nhiên, 3 script mới, cổng người duyệt bắt buộc, trạng
thái (code xong, `--n 6` xác nhận, `--n 240` chờ người dùng). Giữ nguyên
`name`/frontmatter, cập nhật `description`.

- [ ] **Step 2: Sửa `rag_eval_harness.md`**

Đánh dấu `HISTORICAL:` phần mô tả `evaluator.py --book/--bo-qua-da-co` và bảng
231 câu. Thêm dòng trỏ tới `[[eval_structure_revision_2026_09]]` cho pipeline
hiện hành. Giữ nguyên phần G1-G5 (gates ETL, không liên quan LLM-judge).

- [ ] **Step 3: Sửa `demo_and_eval_constraints.md`**

Đổi mọi chỗ nhắc `eval_llm.py` thành `llm_client.py`. Constraint TPM/TPD Groq
giữ nguyên (không đổi hạ tầng).

- [ ] **Step 4: Sửa `multimodal_ablation_m2c.md`**

Đánh dấu `HISTORICAL:` toàn file (dùng `ablation_multimodal.py`, đã xóa).

- [ ] **Step 5: Sửa `m2_plan_two_tracks.md`**

Đánh dấu `HISTORICAL:` đoạn nhắc `ablation.py`/bộ 300 câu cũ; giữ nguyên phần
quyết định hybrid mặc định (D-82, không đổi).

- [ ] **Step 6: Sửa `thesis_report_and_goals.md`**

Thêm một dòng: số liệu 240/270 câu (D-173..D-175) đã lỗi thời do D-182, chờ
lượt đo mới trước khi viết lại báo cáo.

- [ ] **Step 7: Sửa `colab_runbook_and_env.md`**

Giữ nguyên các bài học TPM/TPD/mtime-drift (vẫn đúng); cập nhật mô tả
cell/script cụ thể theo notebook đã vá ở Task 8.

- [ ] **Step 8: Cập nhật `MEMORY.md` (index)**

Sửa dòng trỏ tới `eval_structure_revision_2026_09.md` cho khớp mô tả mới; thêm
`HISTORICAL` vào mô tả ngắn của `multimodal_ablation_m2c.md` nếu index có ghi
trạng thái.

- [ ] **Step 9: Không cần chạy pytest cho bước này (memory không phải code) — chỉ đọc lại từng file đã sửa để tự kiểm chính tả/nhất quán.**

---

### Task 8: `document/colab_runtime_eval.ipynb` + `src/test/README.md`

**Files:**
- Modify: `document/colab_runtime_eval.ipynb`
- Modify: `src/test/README.md`

- [ ] **Step 1: Sửa notebook — bỏ vòng lặp 13-mục (12 quyển + NGOAI_PHAM_VI)**

Cell hiện có biến `BOOKS = [...]` (13 phần tử) và vòng lặp gọi `evaluator.py
--book <tên>` cho từng phần tử — XÓA toàn bộ vòng lặp này, thay bằng một lần
gọi `python -m src.test.run_eval` (một file `draft.csv` duy nhất, không còn
khái niệm "theo quyển").

- [ ] **Step 2: Sửa cell "recall_at_k.py đã gộp vào ablation.py"**

Đổi thành: "ablation.py đã bị xóa hoàn toàn (D-182) — thay bằng
`retrieval_benchmark.py`, xem mục dưới."

- [ ] **Step 3: Sửa cell gọi `ablation.py --build-cache`**

Đổi:
```python
r = subprocess.run([sys.executable, "-u", "-m", "src.test.ablation",
                    "--testset-dir", "src/test/testsets_240", "--build-cache",
                    "--out", "src/test/ablation_report_240"])
```
thành:
```python
r = subprocess.run([sys.executable, "-u", "-m", "src.test.retrieval_benchmark",
                    "--build-cache"])
```

- [ ] **Step 4: Thêm ghi chú đầu notebook**

Sửa markdown cell đầu tiên, nói rõ notebook này chạy trên bộ test SINH BỞI
`build_testset.py` (đã người duyệt tay TRÊN MÁY LOCAL trước khi upload lên
Drive/Colab — `--mark-reviewed` cần input tương tác, không chạy được trên Colab
không giám sát).

- [ ] **Step 5: Viết lại `src/test/README.md`**

Thay mục 3 ("Các bước") — Bước 1 giờ là `build_testset.py` (sinh + duyệt tay),
Bước 2 là `run_eval.py` (đánh giá) + `retrieval_benchmark.py` (bảng đối chiếu).
Thay mục 5 ("File trong thư mục") — xóa mô tả `metrics.py`/`generate_testsets.py`/
`ablation.py`/`eval_llm.py`, thêm mô tả `testset_common.py`/`build_testset.py`/
`retrieval_benchmark.py`/`run_eval.py`/`llm_client.py`.

- [ ] **Step 6: Commit**

```bash
git add document/colab_runtime_eval.ipynb src/test/README.md
git commit -m "$(cat <<'EOF'
docs(colab,readme): cap nhat runbook + README theo pipeline test moi (D-182)

colab_runtime_eval.ipynb: bo vong lap 13-muc theo quyen, thay bang mot
lan goi run_eval.py tren mot file draft.csv. Doi ablation.py ->
retrieval_benchmark.py. src/test/README.md viet lai muc 3 va 5 theo 3
script moi.
EOF
)"
```

---

### Task 9: Commit cuối — xác nhận toàn bộ

- [ ] **Step 1: `git status --short` — xác nhận sạch (không còn gì chưa commit)**
- [ ] **Step 2: `pytest tests/ -q` — xanh toàn bộ lần cuối**
- [ ] **Step 3: `grep -rn "ablation\.py\|evaluator\.py\|generate_testsets\.py\|build_testset_240\|build_image_questions\|eval_llm\.py" --include="*.py" --include="*.ps1" --include="*.md" --include="*.ipynb" .`**

Expected: 0 kết quả sống (mọi match còn lại chỉ nằm trong lịch sử/ghi chú giải
thích quyết định, ví dụ trong `CLAUDE.md`/decision log mô tả "đã xóa X" — đọc
từng dòng để chắc chắn không phải một lệnh gọi thật còn sót).

- [ ] **Step 4: Báo cáo người dùng: pipeline đã sẵn sàng, chờ người dùng chạy `--n 240` thật + duyệt tay.**

---

## Self-Review (đã chạy khi viết plan này)

1. **Spec coverage**: mục 1 (lý do) → ghi trong header/Task 6; mục 2 (xóa/giữ)
   → Task 1; mục 3.1 → Task 2; mục 3.2/3.3 → Task 3; mục 4 (cổng duyệt) →
   Task 3 Step 3; mục 5 (test) → Task 2 Step 1 + Task 3 Step 1/5; mục 6 (dọn
   dẹp) → Task 6/7/8; mục 7 (rủi ro) → đã phản ánh vào code (circuit breaker,
   hậu tố nháp, ánh xạ trường ảnh); mục 8 (thứ tự bàn giao) → toàn bộ cấu trúc
   Task 1→9 của plan này bám đúng thứ tự đó.
2. **Placeholder scan**: đã rà toàn bộ — không còn "TODO"/"tương tự Task N"
   nào; mọi step code có nội dung đầy đủ chạy được.
3. **Type/tên nhất quán**: `draft.csv` cột `loai` (không phải `nguon_cau_hoi`
   như bản D-181 cũ) dùng xuyên suốt Task 2 (ghi) và Task 3 (đọc,
   `run_eval.py::evaluate_all`/`_loai_cau_hoi`) — đã kiểm khớp. `Cache`/
   `Config`/`rank_for`/`chunk_ids_digest`/`TEXT_EXTRACTION_VERSION`/
   `reciprocal_rank` dùng đúng 1 tên xuyên suốt Task 3 và 2 test file tái tạo.
