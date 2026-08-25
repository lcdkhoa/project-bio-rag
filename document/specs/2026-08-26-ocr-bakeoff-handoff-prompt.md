# Prompt bàn giao — chạy xong bake-off OCR rồi quyết định thay Tesseract hay không

> **Đọc trước, theo thứ tự:** `CLAUDE.md` (RULE #0, 7 nguyên tắc, "Định nghĩa xong");
> `document/specs/2026-08-25-ocr-model-bakeoff-design.md` (thiết kế đầy đủ của việc này);
> `document/decision_log.html` **D-84 … D-94**.
>
> **Entry mới bắt đầu từ D-95.**
>
> **Trạng thái git khi bàn giao:** `master` đã push tới `3cdf5a3`.
> `pytest tests/ -q` → **546 passed, 3 skipped**. Working tree sạch.

---

## 0. Bối cảnh — đọc kỹ phần này, nó quyết định giọng của cả lượt

Đồ án đang **sát deadline**: Giai đoạn 3 đáo hạn 28/08 (đã xong), deadline cuối
**23/09**. Người dùng đã mệt vì nhiều lượt "bày vẽ" mà chưa thấy kết quả cuối, và
đã nói thẳng điều đó. Vì vậy:

- **Không mở rộng phạm vi.** Việc của lượt này chỉ có một câu hỏi: *engine nào
  đọc chữ tốt hơn Tesseract, hay không engine nào cả?*
- **Không thêm công cụ mới.** Mọi thứ cần thiết đã có và đã chạy được.
- **Nếu một engine không cài được trong ~15 phút, BỎ nó và đi tiếp.** Bake-off
  cần **ít nhất một** engine, không cần cả bốn. Điều này đã ghi trong notebook.
- Khi báo cáo, nói thẳng cái gì đo được và cái gì không. Người dùng không cần
  được trấn an, họ cần biết con số.

**Điều đã làm hỏng lượt trước, đừng lặp lại:** một lệnh `pip install` sai làm
engine chết ở bước nạp model, nhưng cell notebook vẫn chạy tiếp và **in ra bảng
baseline trông như một kết quả bình thường**. Đã vá (D-94, exit code 3 + `&&`),
nhưng bài học rộng hơn: **mọi bước có thể hỏng phải hỏng ỒN ÀO.** Đây là lần
thứ năm cùng một bệnh trong repo này (D-68, D-75, D-83, D-84, D-94).

---

## 1. ĐÃ XONG — dùng luôn, ĐỪNG làm lại

| Việc | Số đo | Nguồn |
|---|---|---|
| Gold set OCR **97 ô / 15 trang**, NGƯỜI duyệt tay xong | 97/97 ô, 0 ô `???`, 310,9 s/ô | D-91, D-92 |
| **BASELINE Tesseract** trên gold set đó | **CT 0,048 · DẤU 0,016 · BẢNG 0,000** | D-92 |
| Crop cho Colab | 97 PNG, **8,3 MB**, nằm TRONG git | D-93 |
| Bộ chấm 3 chỉ số + `--compare` | 58 test, đã chạy E2E | D-91, D-92 |
| Notebook mục 12 | một cell làm tất cả, không cần Drive | D-93, D-94 |
| Index text 12 quyển | 16 393 chunk / 2 399 trang | D-73 |
| Retrieval hybrid (mặc định đang chạy) | R@1 0,717 · R@3 0,887 · **R@10 0,977** · MRR **0,808** | D-82 |
| Bảng đối chiếu cấu hình 2 (đa phương thức) | delta +0,010, trần bộ test chỉ 0,104 | D-87 |

**Ba con số baseline nghĩa là gì** (phải hiểu trước khi đọc bảng engine):

- **CT = 0,048** — Tesseract đọc đúng 4,8% token công thức, trên 45 ô có công
  thức. Khớp bậc với D-56 (281 hỏng : 4 đúng).
- **DẤU = 0,016** — chỉ 1,6% từ sai dấu. **Đây là mốc RẤT CAO.** Tesseract có
  model tiếng Việt riêng; bốn model ứng viên **không model nào nhắc tới tiếng
  Việt trong model card** (đo bằng HF API, 0/4).
- **BẢNG = 0,000** — 0/8. Tesseract đọc cả dải bảng ra chuỗi phẳng, không có
  ranh giới cột. *Giới hạn phải nói kèm:* Tesseract không **có khả năng** xuất
  cấu trúc bảng, còn 4 ứng viên xuất Markdown table — khác biệt về năng lực,
  nhưng người đọc bảng cần biết điều đó.

---

## 2. VIỆC — ba bước, mỗi bước một tiêu chí đo được

### Bước 1 — chạy engine trên Colab (việc của NGƯỜI DÙNG, ~30–60 phút/engine)

Notebook `document/colab_runtime_etl.ipynb`, upload lên colab.research.google.com,
Runtime → GPU (T4).

**Chỉ chạy mục 1 (clone) rồi nhảy thẳng mục 12.** Bỏ qua mục 2–11: không cần
Drive, không cần model ETL, không cần corpus 4,1 GB.

Thứ tự engine, mỗi lượt đổi một dòng `ENGINE = …` rồi Runtime → Restart:

    nanonets_ocr2_3b  →  mineru25  →  dots_ocr

`paddleocr_vl` là **cell tuỳ chọn ở CUỐI notebook** — nó cần `paddlepaddle` cài
riêng và bản GPU không nằm trên PyPI. **Lỗi thì bỏ qua**, đừng đốt thời gian.

Cell tự chạy thử **3 ô trước**, và nối `--compare` bằng `&&` nên engine lỗi thì
DỪNG (không in bảng giả). Chạy được rồi thì bỏ comment khối dưới để chạy đủ 97 ô.

**Nghiệm thu bước 1:** có ít nhất một file `document/review/ocr_gold/engine_*.json`
và bảng `--compare` in ra ít nhất 2 dòng (tesseract + 1 engine).

### Bước 2 — đọc bảng, và PHẢN BIỆN nó trước khi tin

`python -m src.test.ocr_bakeoff --compare` in bảng:

```
engine                          CT↑   DẤU↓  BẢNG↑   n
tesseract (hiện tại)         0.048 0.016 0.000   ct=45 dc=24 b=8
<engine>                     ?     ?     ?
```

**Luật chốt (thiết kế §3.2):** một engine chỉ THẮNG khi nó **không tệ hơn
Tesseract ở cột DẤU**. 93% corpus là chữ thường; model giỏi công thức mà sai dấu
là model **tệ hơn**. Script tự in dòng `✗ … -> LOẠI` cho engine vi phạm.

**Bốn thứ PHẢI kiểm trước khi tin bảng** (nguyên tắc 4 — mỗi thứ đều đã cắn thật
trong repo này):

1. **Mở 5–10 ô ra đọc bằng mắt.** So `engine_<ten>.json` với bản người trên vài
   ô `cong_thuc` và vài ô `doi_chung`. Một CT cao mà chữ đọc ra là rác thì con số
   đó sai, không phải engine tốt.
2. **Đếm ô rỗng.** Script in `N ô rỗng` khi chạy xong. Ô rỗng được tính là SAI
   (cố ý), nhưng nhiều ô rỗng nghĩa là engine crash chứ không phải đọc kém — hai
   chuyện khác nhau, phải nói ra chuyện nào.
3. **Xem engine có BỊA không.** VLM có thể sinh chữ không có trên ảnh — đúng thứ
   nguyên tắc 1 cấm, và đúng thứ đã loại Vintern-1B (D-47: bịa 4/12 crop, tự khai
   số hình sai 4/4 lần). Nếu thấy engine "đọc" ra chữ mà crop không hề có, **đó
   là căn cứ loại thẳng**, dù CT cao.
4. **Nhớ giới hạn đã biết của gold set:** ở **2/4 bảng** (`6_KNTT` tr.44,
   `9_CTST` tr.43) người duyệt gõ **cùng nội dung header cho cả hai câu hỏi**, vì
   hai câu dùng chung một ảnh. Nên **4/8 ô bảng thực chất chỉ đo hàng header**
   (D-92). Đừng sửa dữ liệu người; nói ra khi báo cáo cột BẢNG.

### Bước 3 — quyết định, và ghi lại

Ba kết cục có thể, **cả ba đều là kết quả hợp lệ**:

| Nếu | Thì |
|---|---|
| Có engine thắng CT **và** không thua DẤU | Đề xuất thay Tesseract. Nhưng **chưa OCR lại** — xem §3 |
| Mọi engine thua ở DẤU | **Giữ Tesseract.** Đây là kết quả có giá trị: nó đóng lại một hướng bằng số, thay vì để nó lơ lửng |
| Engine bịa chữ | Loại thẳng, dù CT cao. Ghi rõ ca bịa vào decision log |

**Cấm tuyệt đối:** không được kết luận "model tốt hơn" nếu chưa mở ô ra đọc.

---

## 3. Cái giá của bước SAU — phải nói với người dùng TRƯỚC khi đề xuất

Nếu bake-off chọn được một model, việc thay thật sự **chưa làm trong lượt này**.
Nó tốn:

| Việc | Chi phí đã đo |
|---|---|
| Bump `TEXT_EXTRACTION_VERSION` → OCR lại 12 quyển | Tesseract/CPU **3 giờ 20**; VLM trên GPU Colab **chưa đo** |
| Dựng lại chỉ mục BM25 | 5,5 s |
| Dựng lại đệm bảng ablation | **35–50 phút** |
| Chạy lại bảng k/recall để so | phát lại từ đệm, tức thì |

Và phải viết `region_type` cho chunk (citation đọc trường này), giữ số trang từ
`BookManifest` (model **không bao giờ** được sinh số trang), giữ checkpoint theo
hash từng trang.

**Đường cơ sở để so sau khi OCR lại:** hybrid R@10 **0,977** · MRR **0,808**.

Nếu recall tăng, **chỉ được** nói "tăng vì chữ trích xuất tốt hơn" khi bake-off
đã cho thấy công thức/bảng/dấu đọc đúng hơn. Không có điều đó thì một recall cao
hơn cũng có thể đến từ chunk dài hơn hoặc từ nhiễu.

---

## 4. CẤM (kế thừa các lượt trước, cộng ba điều mới)

1. Không sửa chữ đã lưu trong `biology_text`.
2. Không bật `IMAGE_CAPTION_ENABLED` (Vintern đã bị loại — D-47).
3. Không đổi `EMBEDDING_MODEL` / `CHUNK_SIZE` / `CHUNK_OVERLAP`.
4. **Không bump `TEXT_EXTRACTION_VERSION` trong lượt này** — đó là việc của lượt
   sau, sau khi người dùng đồng ý.
5. Không `except` im lặng, không fallback im lặng — **raise** và **in ra**.
6. Không so số mới với số corpus cũ như cùng điều kiện.
7. Không `Co-Authored-By` / "Generated with" trong commit message.
8. Không chạy cả test suite khi đang lặp (chỉ `tests/test_ocr_bakeoff.py`).
9. **MỚI — không sửa `phieu_nguoi.json`.** Đó là công người, và sửa nó là bịa.
   Thấy chỗ người duyệt hiểu nhầm thì **ghi lại**, đừng "sửa hộ".
10. **MỚI — không chạy `--export` lại** trừ khi có lý do đo được. Nó ghi đè
    `items.json`, và nếu id đổi thì phiếu người thành mồ côi. (Lượt trước có
    kiểm: 97/97 id giữ nguyên — nhưng đó là may, không phải bảo đảm.)
11. **MỚI — không kết luận từ bảng mà chưa mở ô ra đọc bằng mắt.** Xem §2 bước 2.

---

## 5. Trạng thái file khi bàn giao

**Trong git, đã push tới `3cdf5a3`:**

```
document/review/ocr_gold/
    phieu_nguoi.json      <- CÔNG NGƯỜI, 97 ô, không dựng lại được
    items.json            <- 97 ô kèm may_doc / may_doc_vung / cau_hoi
    crops/                <- 97 PNG + crops.json, 8,3 MB
    bakeoff.csv           <- bảng baseline hiện tại (chỉ có tesseract)
src/test/ocr_bakeoff.py           <- --export / --score / --compare
src/test/ocr_bakeoff_pages.json   <- 15 trang, chọn bằng số, kèm `vi_sao`
scripts/colab_run_ocr_engines.py  <- chạy engine trên Colab
tests/test_ocr_bakeoff.py         <- 58 test
document/colab_runtime_etl.ipynb  <- mục 12 = bake-off; cell paddle ở cuối
document/specs/2026-08-25-ocr-model-bakeoff-design.md
```

**Không trong git (đúng thiết kế):** `database/*` (index 16 393 chunk, kho ảnh
938 doc, `datasources/` 4,1 GB).

**Lệnh hay dùng:**

```bash
python -m src.test.ocr_bakeoff --compare        # bảng, chạy được ngay
python -m src.test.ocr_bakeoff --score          # kiểm phiếu người
python -m pytest tests/test_ocr_bakeoff.py -q   # 58 test, 1 giây
```

---

## 6. Câu hỏi CÒN MỞ — hỏi người dùng, đừng tự quyết

1. **Có OCR lại 12 quyển không, nếu bake-off chọn được model?** Tốn vài giờ
   Colab + dựng lại BM25 + đệm ablation. Deadline 23/09.
2. **Hạn mức/ngày của OpenRouter free tier** vẫn chưa đo được (D-67) — chặn
   LLM-as-a-judge cho chất lượng câu trả lời.
3. **Phía ẢNH vẫn còn nợ:** 34,9% crop bị gắn cờ cắt lấn (D-87), và 8 quyển
   CD/CTST **chưa dựng được kho ảnh** (kênh pill đọc 0 nhãn). Người dùng đã nói
   "hình cắt sai nhiều" — đây là việc thật, nhưng đã **cố ý hoãn** để làm text
   trước (người dùng chọn 2026-08-25).
4. **Bộ câu hỏi sinh từ HÌNH** — việc chặn kết luận của cấu hình 2 (trần bộ test
   hiện tại chỉ 0,104 nên delta +0,010 không nói lên điều gì chắc chắn).
