# Prompt: từ index đã dựng → số liệu eval (G3/G5) → ablation → báo cáo

> Prompt cho session Claude Code kế tiếp, **dùng sau khi người dùng đã chạy xong ETL
> trên máy bàn**. Đọc hết §0 trước khi viết dòng code đầu tiên.
>
> **Bắt buộc đọc kèm:** `CLAUDE.md` (mục "Philosophy — 7 nguyên tắc" và "Working
> rules"), `document/decision_log.html` (D-01…D-52), và
> `document/specs/2026-08-21-pending-to-report-prompt.md` (Task 4–7 của lượt trước —
> phần lớn đã xong, xem §0.2 để biết cái gì còn lại).
>
> **Nhánh:** đã merge hết về `master` (fast-forward). `master` đang **ahead
> origin/master 12 commit, CHƯA push** — người dùng chưa yêu cầu push.

---

## 0. Trạng thái — ĐÃ ĐO, DÙNG LUÔN, KHÔNG ĐO LẠI

### 0.1 Những con số đã chốt (đừng đo lại, đừng "kiểm tra cho chắc")

| hạng mục | số đo | nguồn |
|---|---|---|
| Định danh trang `ocr_confirmed` | **793/793 = 100,0%** | D-33 |
| Spine Bài | **195/195 liền mạch** (55/42/47/51), G1 **PASS** cả 4 quyển | D-43 |
| Huy hiệu Bài xác nhận | sách 6: **43/55**; sách 7/8/9: **0/k** (số THẬT, đã thử 3 cách) | D-44 |
| Cổng G4 — phủ nhãn hình | **72/72 = 100,0%** | D-51 |
| Cổng G4 — gán sai Bài | **0** | D-45, D-46, D-51 |
| Caption ảnh Vintern-1B | **TẮT**, đã đo: 17,6 s/crop, JSON 6/12, bịa 4/12, **0/4** số hiệu hình đúng | D-47 |
| Test suite | **252 passed, 3 skipped** | lượt 2026-08-21 |

Version gate hiện hành (`.env` KHÔNG đặt hai biến này → dùng default trong code):
`TEXT_EXTRACTION_VERSION = v2_bai_spine`, `IMAGE_EXTRACTION_VERSION = v19_pill_kernels`.

### 0.2 Task 3–7 của lượt trước: đã xong đến đâu

- **Task 3 (caption)** — XONG, kết luận **route B**: tắt theo mặc định. `_load_model`
  **raise** thay vì tự tắt; `caption()` không còn `except` nuốt lỗi. Đường InternVL
  đã sửa đúng và còn nguyên, bật lại chỉ là một cờ — **nhưng đòi phép đo mới**.
- **Task 4 (bộ test)** — công cụ XONG, **chưa sinh dữ liệu** (cần key LLM).
  `generate_testsets.py` đọc trang qua `PageSource`, khoá vàng lấy **thẳng từ
  metadata chunk thật**. `metrics.PAGE_TOLERANCE` đã về **0**. Bộ test 12 quyển cũ
  dọn vào `src/test/testsets/_archive_12books_2026_07/`.
- **Task 5 (G3)** — cổng XONG (`src/test/qa_citation_page.py`), đã chạy thật
  end-to-end trên index 16 trang: 6/6, exit 0. **Số G3 thật thì chưa có** (cần index
  đầy đủ + bộ test).
- **Task 6 (dọn nợ)** — XONG: xoá `CtsstImageProcessor` (335 dòng) + dispatch theo
  tên file (G4 đo trước/sau y hệt, không hồi quy); nhãn trích dẫn thành
  `"Khoa học tự nhiên 6 (Kết nối tri thức)"`; `Hình 2.3` đã lấy được → G4 100%.
- **Task 7 (notebook)** — XONG, đã **chạy thử thật** 12 trang / DB riêng (log dán ở
  ô 9c của `document/colab_runtime_etl.ipynb`). Lượt chạy thử này tìm ra **D-52**.

### 0.3 Hai cái bẫy vừa được sửa — đừng để chúng quay lại

1. **D-52 — doc ảnh mồ côi.** `image_id` là hash của CROP, nên crop đổi thì id đổi và
   doc cũ **không** bị upsert đè. Đã thêm `ImageVectorDB.delete_page_documents`, gọi
   trong `run_etl` + `run_etl_image_only` **sau** khi extraction thành công và **kể
   cả khi trang không còn hình**. Nếu bạn thấy số doc ảnh > số crop thật, nghi ngay
   chỗ này.
2. **Rerank tắt âm thầm.** `HF_HUB_OFFLINE=1` + `RERANK_MODEL=BAAI/bge-reranker-v2-m3`
   thì **không nạp được** (bản tải bằng `download_models.py` nằm ở `./models`, không
   nằm trong cache hub). `RerankedRetriever` chỉ log một `warning` mỗi truy vấn rồi
   rơi về xếp theo khoảng cách. `.env` nay đặt `RERANK_MODEL=./models/bge-reranker-v2-m3`.
   **Cổng G3 in dòng `rerank: ...` — đọc nó trước khi tin bất kỳ số nào.**

---

## 1. VIỆC ĐẦU TIÊN — xác minh index người dùng vừa dựng (đừng tin, hãy đo)

Chạy trước khi làm bất cứ gì khác. Nếu một trong các phép kiểm dưới đây lệch, **dừng
lại và báo người dùng**, đừng đo tiếp trên một index sai.

```bash
python - <<'PY'
import sys; sys.path.insert(0, ".")
from src.config import PERSIST_DIR
import chromadb
from collections import Counter
c = chromadb.PersistentClient(path=str(PERSIST_DIR))
for col in c.list_collections():
    print(col.name, c.get_collection(col.name).count())
g = c.get_collection("biology_text").get(include=["metadatas"], limit=1_000_000)
m = g["metadatas"]
print("sach:", sorted(Counter(x["source"] for x in m).items()))
print("so trang co chunk:", len({(x["source"], x["page"]) for x in m}))
print("chunk co bai_so:", sum(1 for x in m if x.get("bai_so")), "/", len(m))
print("chunk needs_review:", sum(1 for x in m if x.get("needs_review")), "/", len(m))
PY
```

Kỳ vọng, và ý nghĩa nếu lệch:

- **4 quyển** trong `source`, tên đúng dạng `SGK_KHTN_{6,7,8,9}_KNTT`.
- **Số trang có chunk ≈ 801 − (số trang `role="cover"`)**. Cover bị bỏ ở bước chunk là
  ĐÚNG; thiếu nhiều hơn thế = có trang raise và bị để lại chưa xử lý → xem log.
- `bai_so` phải có trên **gần hết** chunk (spine liền mạch cả 4 quyển). Nếu = 0 thì
  manifest đang bị cờ `spine_out_of_order`/`bai_numbers_not_contiguous` → điều tra,
  đừng bỏ qua.
- `processing_status` phải ≈ số trang đã xử lý × (text + ảnh).

Rồi kiểm còn sót không:

```bash
python - <<'PY'
import os, sys; sys.path.insert(0, ".")
from src.etl import ProcessingStatus
from src.etl.page_source import discover_page_sources
from src.config import DATA_DIR
s = ProcessingStatus()
for src in discover_page_sources(DATA_DIR):
    print(src.name, "| text con thieu:", len(s.pages_needing_text(src)),
          "| anh con thieu:", len(s.pages_needing_images(src)))
PY
```

Còn sót > 0 → **báo người dùng chạy lại đúng lệnh đó** (resume theo trang), đừng tự
"vá" bằng cách bỏ qua.

---

## 2. Task 4 hoàn tất — sinh bộ test (cần key LLM)

```bash
python src/test/generate_testsets.py --dry-run --per-book 25   # xem chọn trang, khong goi LLM
python src/test/generate_testsets.py --per-book 25             # 4 quyen -> ~100 cau
```

**Nghiệm thu:**

1. Mỗi quyển có file `src/test/testsets/SGK_KHTN_{n}_KNTT_testset.csv`. **Thiếu chỉ
   tiêu thì báo con số THẬT** — script đã in `!! CHỈ được k/25 câu`, đừng làm tròn lên.
2. Chạy `python -m pytest tests/test_eval_gold_keys.py -q` (5 test) để chứng minh khoá
   vàng khớp metadata chunk thật.
3. Kiểm khoá vàng khớp **index vừa dựng** (khác với test trên: test dùng OCR trực
   tiếp, đây dùng DB):

```bash
python - <<'PY'
import csv, glob, sys; sys.path.insert(0, ".")
from src.config import PERSIST_DIR
from src.test.metrics import make_page_relevance
import chromadb
c = chromadb.PersistentClient(path=str(PERSIST_DIR)).get_collection("biology_text")
bad = 0
for path in glob.glob("src/test/testsets/*_testset.csv"):
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        got = c.get(where={"$and": [{"source": {"$eq": row["source_book"]}},
                                    {"page": {"$eq": int(row["source_page"])}}]})
        if not got["ids"]:
            bad += 1
            print("KHONG CO CHUNK NAO cho khoa vang:", row["source_book"], row["source_page"])
print("so cau co khoa vang khong ton tai trong index:", bad, "(phai la 0)")
PY
```

`bad > 0` là **lỗi thật**, không phải nhiễu: một câu hỏi trỏ tới trang không có chunk
nào thì mọi metric của nó vô nghĩa. Điều tra rồi mới đi tiếp.

4. `_generation_meta.json` phải ghi `human_reviewed: false`. **Mọi báo cáo dùng số từ
   đây phải nói rõ bộ test do LLM sinh, chưa qua kiểm tra người.**

---

## 3. Task 5 hoàn tất — số G3 THẬT + hiệu chỉnh ngưỡng

```bash
python -m src.test.qa_citation_page --out scripts/_out_g3/g3_det.json          # deterministic
python -m src.test.qa_citation_page --judge --out scripts/_out_g3/g3_judge.json # + LLM cuu
```

**Đọc kết quả cho đúng — script đã in sẵn mọi thứ cần để không nói quá:**

- `G3 = ok / (ok + cited_wrong)`. **`no_citation` nằm NGOÀI phân số** vì đó là lỗi
  recall, không phải lỗi citation. Báo cáo phải in cả ba con số cạnh nhau.
- Dòng `rerank: ...` — nếu nó nói `BẬT nhưng KHÔNG NẠP ĐƯỢC` thì **số bạn vừa đo
  không phải cấu hình bạn nghĩ**. Sửa rồi đo lại.
- Dòng `trong đó k/n câu có đáp án chỉ <= 3 token nội dung` — đó là **bằng chứng
  YẾU**. Nếu k lớn so với n thì phải nói ra trong báo cáo.
- **`--coverage-min 0,6` là con số CHƯA HIỆU CHỈNH.** Việc của bạn ở lượt này là hiệu
  chỉnh nó bằng số: chạy `--judge`, đọc bảng "đồng thuận deterministic-vs-judge", và
  quét ngưỡng (ví dụ 0,4 / 0,5 / 0,6 / 0,7) rồi chọn giá trị mà hai bên lệch nhau ít
  nhất. **Ghi phép quét đó vào decision log** — đổi ngưỡng mà không có phép đo
  trước/sau là hồi quy chờ xảy ra (nguyên tắc 3).

**Nghiệm thu:** con số G3 thật + **liệt kê từng ca fail** (câu hỏi, trang được trích,
trang vàng) + ngưỡng đã hiệu chỉnh có bằng chứng. Ngưỡng thiết kế ≥ 95%; **chưa đạt
thì báo con số thật**, và mở từng ca fail ra xem nguyên nhân (đây là cách mọi lỗi ở
Task 1–2 được tìm ra).

---

## 4. G5 + bảng ablation

```bash
python src/test/recall_at_k.py     # recall@3/5/10 + MRR, base vs rerank
python src/test/evaluator.py       # P/R/MRR + LLM judge 1-5 (can key)
```

Ba cấu hình của §5.2 báo cáo, **trên CÙNG corpus 4 quyển và CÙNG bộ test**:

| cấu hình | ý nghĩa | chi phí |
|---|---|---|
| (a) MiniLM, không rerank, không gate | tái lập cấu hình báo cáo cũ | **cần index THỨ HAI** |
| (b) bge-m3, không rerank | tách riêng đóng góp của embedding | đổi cờ, dùng index có sẵn |
| (c) bge-m3 + cross-encoder + gate | cấu hình hiện tại | index có sẵn |

**Chi phí ẩn của (a), phải nói với người dùng TRƯỚC khi bắt tay:** collection Chroma
có số chiều CỐ ĐỊNH, nên MiniLM (384) **không dùng chung** `biology_text` với bge-m3
(1024). Muốn có (a) thì phải dựng một collection riêng bằng MiniLM — tức thêm một
lượt ETL text đầy đủ (~45 phút trên máy bàn). Hiện `recall_at_k.py` /
`VectorDB` **chưa có cờ** chọn model + collection; phải thêm (nhỏ) rồi mới chạy được
(a). **Hỏi người dùng có muốn trả cái giá đó không** — nếu không, báo cáo phải nói rõ
là **không có** cấu hình (a) và vì sao, chứ không được để trống rồi ngầm so với 0,63 cũ.

---

## 5. Báo cáo — ràng buộc trung thực

### 5.1 Ràng buộc quan trọng nhất

Corpus đã đổi **12 quyển → 4 quyển**. **Không được** viết "recall tăng từ 0,63 lên X".
Số 0,63 nêu như **mốc lịch sử trên corpus khác**, nói rõ không so trực tiếp được.
Thêm một lý do nữa mới có: `PAGE_TOLERANCE` đã từ 1 về **0**, nên ngay cả cùng corpus
thì hai con số cũng là hai thước đo khác nhau.

### 5.2 Báo cáo mới PHẢI có

1. **G3** — độ đúng trang trích dẫn, kèm ba nhóm `ok`/`cited_wrong`/`no_citation` và
   ghi chú về ngưỡng đã hiệu chỉnh + số ca "bằng chứng yếu".
2. **G4** — **72/72 = 100% phủ nhãn hình, 0 hình gán sai Bài**, kèm hai cảnh báo:
   số thiếu là **cận dưới** (dẫn ca `Hình 2.5` sách 8 làm ví dụ cụ thể), và crop to
   không đồng nghĩa crop sai.
3. **G1** — 793/793 = 100% `ocr_confirmed`, cơ chế `ocr_confirmed` vs
   `model_inferred`, spine Bài 195/195, và **huy hiệu 0/k ở 3 quyển** nói thẳng.
4. **Sửa lệch mô tả–code.** Báo cáo cũ viết cắt hình bằng OWL-ViT detect-then-crop;
   code thật là **anchor-first deterministic**. Kiến trúc phải viết đúng: `PageSource`
   → segmenter theo vùng + tách hue → pill anchor → MỤC LỤC-dạng-bảng → checkpoint
   theo hash trang → citation deterministic.
5. **Nói ra giới hạn còn lại:** caption ảnh tắt (kèm số đo); 3 nhãn ô so sánh chưa
   đọc được (lớp D-40); huy hiệu Bài 0/k ở 3 quyển; bộ test do LLM sinh chưa qua
   người; **G2 chưa có** (xem §7).

### 5.3 Demo

FE nằm **repo khác** — đừng dựng FE mới trong repo này, hỏi người dùng repo/URL.
Trên máy bàn **không có CUDA**, nên `serve` Qwen2.5-3B sẽ rất chậm: **đo tốc độ
sinh token trước khi hứa demo trực tiếp**, và nếu chậm thì nói thẳng thay vì hứa.

---

## 6. CẤM (mỗi dòng đều có lý do đã đo)

1. **Không upscale ảnh thân bài / crop lưu trữ.** CER không đổi ở 1×/2×/3×/4×. Ngoại
   lệ đã được phép: crop góc số trang, crop pill, ô số MỤC LỤC.
2. **Không binarize/Otsu toàn trang** (đo: conf 93,4 → 92,0).
3. **Không đánh số lại / xoá file PNG nguồn.** Bỏ trang khỏi index bằng `role`.
4. **Không `index + 1`** hay hằng số nào làm fallback số trang.
5. **Không tự sửa chữ** (OCR, dấu, caption). Bước tự động chỉ được **drop** hoặc **flag**.
6. **Không lọc dòng OCR bằng ngưỡng confidence** (D-38: xoá cả chữ thật). Muốn lọc
   nhiễu thì dùng tín hiệu **tự hiệu chỉnh** (so với trung vị của chính nó — D-46,
   hoặc IDF đo trên chính index — D-49).
7. **Không `except` im lặng.** Model/bước không dùng được thì phải ồn.
8. **Không so số mới với báo cáo cũ như cùng điều kiện** (§5.1).
9. **Không bật lại caption ảnh** mà không có phép đo mới trên đúng 12 crop đó.
10. **Không thêm `Co-Authored-By` / "Generated with"** vào commit message.
11. **Không chạy cả test suite khi đang lặp** — chỉ test của phần đang sửa.
12. **Không báo cáo G3/recall khi dòng `rerank:` nói nó không chạy.**

---

## 7. Phải HỎI, không được đoán

1. **Cổng G2 — làm hay bỏ?** Thiết kế gốc định nghĩa G2 = gold set **24 trang do
   NGƯỜI xác nhận**, đo CER/WER/tỉ lệ lỗi dấu, so consensus 2 engine với từng engine
   đơn. Người dùng đã từ chối duyệt tay bộ test, nên rất có thể cũng từ chối gold set
   này. Ba lựa chọn: (1) bỏ G2, báo cáo nói thẳng là không có phép đo CER — **khuyến
   nghị**; (2) người dùng xác nhận 24 trang; (3) dựng gold set bằng LLM và ghi rõ —
   nhưng CER đo bằng nhãn LLM thì gần như vô nghĩa. **Hỏi rồi mới làm.**
2. **Cấu hình (a) của ablation** — có trả giá một index MiniLM riêng không (§4).
3. **Hình thức báo cáo** — cập nhật `report/main_chuyende_totnghiep.pdf` hay viết mới.
4. **Push `master` lên origin?** Hiện ahead 12 commit, chưa push.

---

## 8. Thứ tự chốt lại (một dòng)

Xác minh index (§1) → sinh bộ test (§2) → G3 thật + hiệu chỉnh ngưỡng (§3) →
recall/MRR + ablation (§4) → báo cáo theo §5 → demo.
