# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## RULE #0 — nguồn yêu cầu duy nhất là `document/goal.docx` (đọc trước mọi việc)

**Repo này đã đổi sang thiết kế cho ĐỒ ÁN TỐT NGHIỆP. Mọi yêu cầu đều nằm ở
`D:\personal_repo\project_rag\document\goal.docx` — hãy đọc và phân tích lại.**

`goal.docx` là **Đề cương chi tiết đã có chữ ký CBHD (ThS. Nguyễn Hữu Quyền), ngày
13/07/2026**. Nó thắng mọi tài liệu khác trong repo khi có mâu thuẫn:

- `report/main_chuyende_totnghiep.pdf` là **báo cáo CHUYÊN ĐỀ cũ (06/2026) — ĐÃ LỖI
  THỜI**. Chỉ dùng làm tư liệu lịch sử; không được lấy mục tiêu, phạm vi hay số liệu
  của nó làm chuẩn nghiệm thu nữa.
- Mọi spec trong `document/specs/` viết trước 2026-08-22 đều được soạn theo phạm vi
  cũ (4 quyển KNTT, trọng tâm Sinh học). Phần **đo lường** trong đó vẫn còn giá trị;
  phần **mục tiêu / tiêu chí nghiệm thu** thì không.
- Khi một dòng trong chính CLAUDE.md này mâu thuẫn với `goal.docx`, `goal.docx` đúng
  và dòng đó phải được sửa ngay trong cùng lượt phát hiện.

Tóm tắt yêu cầu chốt (chi tiết đọc thẳng file, đừng nhớ qua bản tóm này):

| # | Yêu cầu trong đề cương | Trạng thái trong code |
|---|---|---|
| MT1 | Truy vấn đa định dạng: văn bản + **công thức** + hình/sơ đồ/biểu đồ | công thức **CHƯA** (D-56/D-63) |
| MT2 | Kho vector phủ **toàn bộ KHTN Lý–Hoá–Sinh, 12 quyển / 3 bộ sách, ~2 319 trang** | mới 4 quyển KNTT / 801 trang |
| MT3 | Tối ưu truy xuất: định tuyến ý định + **truy xuất lai BM25 + dense** + rerank + cổng lọc | BM25 **XONG** (16 393 chunk, D-77); hợp nhất thưa+dày **XONG** (D-80); bảng 12 cấu hình đang chạy |
| MT4 | Khung đánh giá đối chiếu: (i) **hybrid vs BM25 thuần**, (ii) **multi-modal vs text-only**, (iii) ablation bật/tắt rerank + gate | (i)+(iii) **XONG** 300 câu/12 quyển (D-82); (ii) **XONG** 100 câu/4 quyển KNTT (D-87), delta +0,010 nhưng trần bộ test chỉ 0,104 |
| MT5 | Web UI (Next.js) hiển thị công thức Toán/Hoá + hình sắc nét | FE nằm repo khác, chưa xác minh |

Mốc thời gian trong đề cương: 15/07/2026 → 23/09/2026, năm giai đoạn. Giai đoạn 1
(số hoá đủ 12 quyển) đáo hạn **29/07/2026**; Giai đoạn 3 (thực nghiệm đối chiếu
BM25/Hybrid và Text-only/Multi-modal) chạy **14/08 → 28/08/2026**. Khi báo cáo tiến
độ, nói theo mốc này, không nói theo cảm tính.

**Hệ quả trực tiếp phải nhớ:** phạm vi đã **mở lại** thành 3 nhà xuất bản, nên nguyên
tắc 7 ("xoá code mạnh tay khi phạm vi hẹp lại") **đã bị đảo chiều** cho phần xử lý
theo nhà xuất bản — xem mục "What this is".

## What this is

A Vietnamese-language **RAG system over image-only Vietnamese science textbook pages (SGK KHTN, THCS)**. The pipeline OCRs Vietnamese text and crops figures, then serves hybrid text+image retrieval with a local Qwen2.5 LLM answering in Vietnamese with citations.

**Scope per `goal.docx` (RULE #0): the whole KHTN subject — Physics, Chemistry AND Biology — over 12 books / 3 publishers (KNTT, CTST, Cánh Diều), ~2,319 pages.** (2,319 is `goal.docx`'s estimate; the **measured** count on disk is **2,399** — D-65. When the two differ, the disk wins for engineering, the đề cương wins for the report's scope statement.) The "Biology-focused" framing of the old chuyên-đề report is dead: a Physics or Chemistry question is now **in scope by contract**, not a distraction. Chemistry/Physics formulas (`O₂`, `H₂SO₄`, `A = Fs`) are a *named deliverable* ("bổ sung bước xử lý đặc thù cho công thức Hoá, Lý"), which promotes D-56/D-63 from tech debt to contracted work.

**Corpus on disk (re-measured 2026-08-23, D-65): 12 quyển / 3 NXB / 2 399 trang.** `database/` was deleted — there is nothing to resume, the whole ETL is a fresh run. (The "2 403 trang" and the CD counts `172 / 208 / 217` written here on 2026-08-22 were **wrong**; the numbers below come from `page_numbers()` on disk.)

```
datasources/SGK_KHTN_{6,7,8,9}_{KNTT,CTST,CD}/page_NNN.png    12 folders, 0 gaps
CD   179 + 171 + 207 + 215 = 772 | CTST 204 + 188 + 223 + 215 = 830
KNTT 195 + 179 + 196 + 227 = 797                        tổng 2 399
```

Three measured facts that overturn earlier design notes — full table in
`document/specs/2026-08-22-12books-3publishers-etl-rebuild.md`:

1. **KNTT is the LOWEST-resolution set, not the reference.** KNTT 1094×1536 vs CTST/CD
   **2280×3201** (6_CD is 2480×3480) — ~2.1× per edge, ~3.5× the area. Every OCR
   conclusion in this file (CER 0.0048, "upscaling changes nothing", and **D-56 subscript
   loss**) was measured *only on KNTT at 1094×1536*. Whether `O₂`/`H₂SO₄` survive at
   CD/CTST resolution is **unmeasured and must be tested early** — D-56 may be a
   resolution artefact rather than a Tesseract limit.
2. **SETTLED (D-65): every book starts at `page_001` and `printed_page == filenum`
   (offset 0) on all 12.** Measured with `src/etl/book/fingerprint.py` over 40 pages/book:
   offset **0** in 12/12, hit rate **39/40** in eleven books and **38/40** in 9_CD, winner
   margin 36–39. The paragraph that used to stand here — "7_CD and 8_CD start at
   `page_000`", "6_CD and 6_CTST read 0/4" — was a coarse first probe and is **void**.
   Kept for the lesson only: page-number position is still per-book (measured
   `x ≈ 0.104 / 0.894` CD, `0.112 / 0.889` CTST, `0.074 / 0.928` KNTT), so never assume
   a zone — measure it, flag it, never guess (principle 5).

   Historical note: the paragraph replaced here claimed 7_CD and 8_CD started at
   `page_000`. They do not — there is no `page_000` anywhere on disk, and the earlier
   `0/4` reading for 6_CD / 6_CTST came from a coarse top/bottom-band probe, not from a
   missing page number. Both were superseded by the 40-page/book measurement above.

3. **Everything derived from the old corpus is void:** the deleted `database/`, all
   `database/manifests/*`, the 4-book 100-question testset, the 24-page G2 gold set (page
   numbers moved), and every G1/G3/G4/G5 number quoted below.

**Per-publisher handling is now mandatory** (RULE #0 reversed D-50): `LAYOUT_VARIANT =
"kntt"` and the always-KNTT `make_image_processor()` must go. Do **not** restore
`CtsstImageProcessor` (`git show 75b8377^:src/etl/image_processor.py`) — it was written
for the old 150-DPI PDF render and never QA'd on this pixel source. Each book declares a
**measured** layout fingerprint (M0 in the spec); a book without one makes the ETL raise
rather than borrow another book's parameters.

### M0 layout fingerprint — MEASURED per publisher (2026-08-23, D-65)

Artefact: `database/fingerprints/{book}.json`, 12/12 books complete. Full report:
`document/specs/2026-08-23-m0-report.md`. **These three tables overturn assumptions that
are still baked into `toc.py`, `pill.py` and `config.py`.**

| | KNTT (4 quyển) | CTST (4 quyển) | Cánh Diều (4 quyển) |
|---|---|---|---|
| trang MỤC LỤC | **đầu sách** `[4,5]` (6_KNTT: `[4,5,6]`) | **đầu sách** `[4,5]` | **HAI TRANG CUỐI** (178–179 / 170–171 / 206–207 / 214–215) |
| mẫu mục | `Bài N` | `BÀI N:` (hoa) | **`N. Tiêu đề <số>` — KHÔNG có chữ "Bài"** |
| bố cục | một cột logic | hai cột kiểu tạp chí | hai cột kiểu tạp chí |
| `how` | rules (6/9), gutter (7/8) | gutter | gutter |
| spine đọc được hôm nay | **55/42/47/51 = 195, liền mạch** | 0/2/2/5 — **bộ đọc sai bố cục** | chưa có bộ đọc |
| nhãn hình | **pill** (23–28 nhãn / 30 trang) | **caption chữ đen** (41–65) | **caption chữ đen** (30–42) |
| nhãn từ kênh pill | 23–28 | **0** | **0** |
| sat của hộp màu, p10 / p50 | 14–29 / 16–51 | 14–18 / 18–30 | **9–12** / 18–32 |
| hộp màu / trang | 2,0–2,7 | 3,3–3,7 | 1,9–2,7 |

Ba hệ quả trực tiếp, phải nhớ trước khi sửa code:

1. **Trục anchor bằng pill là chuyện RIÊNG của KNTT.** CD/CTST đọc được **0** nhãn từ
   kênh pill nhưng 30–65 nhãn từ OCR thường. Nên **D-45 / D-51** (psm và kernel CLOSE của
   pill) và **D-40** (ba nhãn ô so sánh chưa đọc được) chỉ áp cho 4 quyển KNTT, không phải
   12 — và 8/12 quyển có anchor *dễ hơn* KNTT.
2. **`LAYOUT_BOX_MIN_SATURATION = 45` cao hơn thực tế của MỌI quyển** — nó nằm trên p50
   của 11/12 quyển (chỉ 6_KNTT đạt 51), và nhánh tông nhạt `pale_sat_min = 12` còn cao hơn
   p10 của 6_CD (9). Ngưỡng hộp màu phải là **per-book, lấy từ phân bố đã đo**.
3. **Chạy bộ đọc MỤC LỤC một cột lên bố cục hai cột sinh ra số SAI MÀ TRÔNG HỢP LÝ.** Đo
   trên 7_CTST: `Bài 1 → trang 144` (thật là trang 6), rồi ràng buộc đơn điệu giết 31 Bài
   còn lại. Luật "bỏ entry chứ không đoán" chặn 31 số sai nhưng **không chặn số sai đầu
   tiên**. Bộ đọc cell nay chỉ chạy khi `entry_style == "bai"`, và spine không liền mạch bị
   gắn cờ `KHONG_dang_tin`.

Ngưỡng px của `toc.py` và `pill.py` nay tỉ lệ theo chiều rộng trang
(`toc.geom_for_width(w)`, `pill.bounds_for_width(w)`, tham chiếu 1094 px) — ở đúng 1094 px
chúng trả lại y nguyên bộ số cũ, có test chốt. **Còn một hằng số KNTT chưa xử lý:**
`text_extract.SINGLE_LINE_MAX_H = 60` px (chọn psm 7 vs psm 6); trên CD một dòng cao
~136 px nên sẽ ăn psm 6 — cố ý chưa sửa vì chưa đo trên CD (việc của M2, kèm before/after).

**Numbers below marked "measured" were measured on the OLD 4-book KNTT corpus at
1094×1536 and are historical until re-measured.** In particular the page-identity bullet
below says `printed_page == filenum − 1` on 801 pages — that was the OLD corpus; today it
is `printed_page == filenum` on all 12 books (D-65), and the *mechanism* (manifest is the
single truth source, no `index + 1` fallback) is what still stands.

Most docs (`README.md`, `document/`) are in Vietnamese; code and comments mix English/Vietnamese. Match the surrounding language when editing.

## Philosophy — tư tưởng của repo (đọc trước khi viết bất kỳ dòng code nào)

Đây là **sách giáo khoa cho học sinh**. Một câu trích sai dấu, một số trang sai, một
hình gán sai bài — là dạy sai một đứa trẻ. Toàn bộ repo được thiết kế quanh một câu
hỏi duy nhất: *làm sao để không bao giờ nói điều mình không chứng minh được?*

Bảy nguyên tắc, theo thứ tự ưu tiên. Khi hai nguyên tắc xung đột, nguyên tắc đứng
trước thắng.

1. **Không bịa (no fabrication).** Trang, hình, chú thích, số liệu — tất cả phải truy
   được về pixel/bytes của trang gốc (PNG nguồn). Citations là **deterministic**, dựng từ
   metadata của chunk thật (`src/rag/citations.py`); LLM không bao giờ được sinh số
   trang. Nếu không biết, hệ thống nói "không biết" — không nội suy, không đoán.
2. **Bằng chứng trước khẳng định (evidence before assertion).** Không "chắc là", không
   "thường thì". Trước khi kết luận về corpus: mở trang gốc ra đo. Trước khi nói code chạy
   đúng: chạy nó và dán output. Một giả định chưa đo là một **câu hỏi mở**, phải ghi
   ra rõ ràng, không được lặng lẽ biến thành thiết kế.
3. **Đo, đừng đoán (measure, don't assume).** Mọi lựa chọn kỹ thuật ảnh hưởng độ chính
   xác (OCR engine, render DPI, chunk size, ngưỡng threshold) phải được chọn bằng số
   trên một **gold set do người xác nhận**, không bằng trực giác hay mặc định của thư
   viện. Đổi tham số mà không có phép đo trước/sau là hồi quy chờ xảy ra.
4. **Phản biện chính code của mình (adversarial self-review).** Test pass ≠ đúng. Với
   mỗi thay đổi: truy edge case, off-by-one, lệch hệ toạ độ/hệ chỉ số (0-based vs
   1-based), cache cũ, fallback âm thầm. Chủ động đi tìm trang làm mình sai — QA thật
   trên trang thật, không chỉ unit test trên fixture tổng hợp.
5. **Fail loudly, never silently.** Một trang OCR lỗi phải được **để lại chưa xử lý**
   và log ra, để lần chạy sau làm lại — không được ghi vào index một nửa dữ liệu. Một
   fallback im lặng (ví dụ đoán số trang = index+1) tệ hơn một lỗi ồn ào, vì nó đẩy
   sai lệch xuống tới câu trả lời cho học sinh. Bước "sửa" tự động phải là **drop-only**
   hoặc **flag-for-review**, không tự bịa thêm dữ liệu.
6. **Một nguồn sự thật duy nhất (single source of truth).** Checkpoint là
   `processing_status` (khoá theo **content hash** + version), không phải file log.
   Cấu trúc sách là MỤC LỤC của chính quyển sách, không phải hằng số hardcode. Khi hai
   nguồn độc lập không khớp → không chọn bừa, mà **flag** để người xem.
7. **Xoá code mạnh tay khi phạm vi hẹp lại (delete aggressively).** Heuristic tồn tại
   để phục vụ một thực tế đo được. Khi thực tế đó biến mất (một nhà xuất bản thay vì
   ba), heuristic đó là nợ, không phải tài sản. Code ít hơn = ít chỗ để sai hơn. Ưu
   tiên deterministic (CV/regex có anchor) hơn "model magic" ở mọi chỗ mà kết quả phải
   giải thích được cho giáo viên.

Hệ quả vận hành: mỗi quyết định ghi vào `document/decision_log.html`; mỗi thay đổi
đúng-sai được đo bằng eval trong `src/test/`; test nhỏ và nhắm đúng chỗ (đừng chạy cả
suite khi đang lặp); và khi báo cáo, nói thẳng cái gì đã verify, cái gì chưa.

## Active redesign (2026-08) — read this first

A layout-aware ETL + retrieval-reranking rebuild is **in progress** (deadline-driven). Source of truth:
- **Decisions:** `document/decision_log.html` (data-driven `DECISIONS[]` log; every decision is recorded here — currently **D-01…D-98**).
- **What to do next (updated 2026-08-23, sau khi index 12 quyển đã dựng xong):**
  `document/specs/2026-08-24-m2-bm25-hybrid-prompt.md` — prompt M2 đầy đủ: trích nguyên văn
  hợp đồng của `goal.docx` (Nội dung 2 và 4), mọi số đã đo (index 16 393 chunk, chỉ số dưới
  CD 256:3 / CTST 377:3 / KNTT 408:4), **ba mâu thuẫn giữa đề cương và số đo phải HỎI chứ
  không tự xử** (384 chiều vs bge-m3, Vintern, chunk), 6 việc M2 kèm tiêu chí nghiệm thu đo
  được, 11 điều CẤM. **§2 chứa 10 quyết định người dùng đã chốt (D-74)** — trong đó bỏ
  Vintern-1B và chẩn đoán lại đúng bệnh: vấn đề không phải thiếu caption mà là **kênh ảnh
  không truy vấn được bằng tiếng Việt** (`CLIP_MODEL` là CLIP tiếng Anh, cầu Việt–Anh chỉ là
  từ điển **14 mục** viết cứng; đo được `cá mập` có **5 lần** trong chữ đã index). Bắt đầu
  từ **D-76** (D-75 = kế hoạch M2 hai track). **Đang chạy HAI SESSION song song** —
  prompt của Track B (BM25 + hợp nhất) ở
  `document/specs/2026-08-24-m2-track-b-bm25-prompt.md`, kèm **bảng quyền sở hữu file**
  để hai session không đụng nhau. Nền cũ:
  `document/specs/2026-08-23-m0-toc-and-layout-prompt.md` §4
  (thứ tự M1→M5) + `document/specs/2026-08-23-m0-report.md` §7 (5 việc còn lại của M0/M1),
  trên nền thiết kế `document/specs/2026-08-22-12books-3publishers-etl-rebuild.md`. Bảng
  tiến độ tóm tắt: mục "Trạng thái tiến độ" ngay dưới. **Stale, chỉ đọc như tư liệu:**
  `2026-08-21-eval-numbers-to-report-prompt.md` và `2026-08-21-pending-to-report-prompt.md`
  — cả hai viết cho corpus 4 quyển KNTT đã bị `database/` xoá và corpus 12 quyển thay thế;
  giữ lại vì (a) mọi số G3/G5 đã đo nằm trong đó (mốc lịch sử, KHÔNG phải mục tiêu so sánh)
  và (b) hai cái bẫy còn nguyên giá trị: image doc mồ côi (D-52) và rerank tắt âm thầm khi
  `RERANK_MODEL` là HF id dưới `HF_HUB_OFFLINE=1`.
- **What was already done and measured:** `document/specs/2026-08-21-png-source-etl-report.md`. The prompt that produced it: `document/specs/2026-08-21-png-source-etl-prompt.md` — the PNG-source migration, with every measured number so nothing needs re-measuring. Earlier: `2026-08-20-kntt-only-etl-rebuild-design.md`, `2026-08-18-rag-etl-retrieval-redesign-design.md`, `2026-08-19-m2-*`, `2026-08-19-m3-*`. Implementation plans live alongside in `document/specs/`.

Still locked from the earlier design: full clean rebuild of `database/`; classical-CV layout segmenter spine; text embedding → `BAAI/bge-m3`; `BAAI/bge-reranker-v2-m3` cross-encoder; sidebar/info-box as separate labeled chunks; checkpoint keyed on **content hash** not filename. (Dropped: "Vietnamese diacritic post-correction" — measured useless and it rewrote text, see D-34.)

Measured on the PNG corpus (2026-08-21). Everything marked DONE below is implemented and verified on the real corpus (D-33…D-39); the rest is still open.

- **DONE — page identity is verified, never guessed:** `printed_page == (number in the filename) − 1`. `page_001.png` = printed 0 = front cover. Measured over all 801 pages: offset **−1** in all 4 books (the model *derives* it), parity (even value → left margin, odd → right) with zero exceptions, and `ocr_confirmed` **793/793 = 100.0%** of the pages that print a number (194/194, 178/178, 195/195, 226/226); the unconfirmed set is exactly `{page_001, page_002}` per book, which genuinely print no number. Filenames carry the source's own page index, not download order, so a re-downloaded page slots straight back in. The `BookManifest` JSON per book is the single source of truth and `LayoutOCRLoader` **raises** without it — there is no `index + 1` fallback anywhere any more (`layout/page_number.py` was deleted). Never renumber or delete source PNGs — cover pages get `role="cover"` and are skipped at chunk time.
- **DONE — page-number reading = union of the 1× and 3× corner crops.** The corner crop is 153×115 px at native size, where Tesseract clips digits (`"11"→"1"` conf 83, `"110"→"10"` conf 45). 3× fixes those but is *not* strictly better (`page_165` of book 9 reads only at 1×), so both scales are read and the candidates unioned, deduped by `(value, side)`. **This is the only place upscaling is allowed** — body text CER is identical at 1×/2×/3×/4×.
- **DONE — preprocessing: none.** `preprocess_page` is deleted, not stubbed. Otsu/binarization measurably *hurts* (conf 93.4 → 92.0); the left-6% wipe had no stamp to remove on this source (median of 100 pages/book: 0% pixels < 200) and destroyed real content, including the left-margin page number of every even page. `RENDER_DPI` is gone from config; the legacy PDF path keeps its own `PDF_RENDER_DPI` constant.
- **DONE — region OCR states its psm:** `--psm 6`, or `--psm 7` for crops under 60 px tall. Default psm 3 lost 3.8% of tokens (6293 → 6535 on 14 pages). Whole-page OCR (`RobustOCRLoader`, image-side context only) also moved to `--psm 6`: on a real page psm 3 = 134 words, psm 11 = 150, psm 6 = 194.
- **DONE — `segment_page` recall was the top defect and is rebuilt: 2.17 → 4.10 regions/page** on the same 40-page/4-book sample, 0 pages regressed. Two root causes, both design errors: a single mask + `CLOSE(25)` glued the question box, the panel and every photo into one 39%-of-page blob that then failed the flatness test (so `page_010` yielded **0 boxes**), and flatness was measured over the *bbox* instead of the region's own pixels (the lavender sidebar scored 0.42 vs a 0.45 floor because its bbox included white gaps). Now: small close, flatness over the component's own pixels, and hue-band splitting of a component that fails — hue bands derived from the region's pixels, no hard-coded publisher palette. Verified on `page_010`: the yellow question box comes out in full and the right sidebar reads `"Chỉ ra những lợi ích…"` with its head intact (the exact head-truncation defect of D-32).
- **DONE — checkpoint is keyed on the hash of EACH PAGE plus `TEXT_EXTRACTION_VERSION`** (`page_key = {book}#{md5 of the page}`), so re-downloading 19 pages re-processes 19 pages and changing OCR logic can finally force a re-OCR. Chunks of a page are deleted before the page is re-indexed, so a version bump leaves no orphans.
- **DONE — automatic "fixes" never rewrite text.** `diacritic.py` now only sets `needs_review` / `review_tokens` on the chunk (`DIACRITIC_REVIEW_ENABLED`). It catches structural impossibilities (letter+digit tokens, invalid onsets/codas, two tone marks, a stop-coda syllable with no sắc/nặng such as `mat`); it cannot catch `chế`→`ché` and does not pretend to.
- **OPEN — tables lose their row/column structure, so a question can be answered from the WRONG COLUMN (D-63).** Measured on `Bảng 12.1` (book 6, printed p.44): the text *is* indexed but the cells interleave — `"Nhựa được dùng làm ghế ngồi, ống dẫn . Dẻo, nhẹ, không dẫn điện, dẫn nhiệt kém, nước, tắm lợp,..."` — mixing the *uses* column into the *properties* column. Qwen answered the properties question with the uses. Same class as `Bảng 35.1` (book 9, **p.154** — the "p.155" written here until 2026-08-25 was the 801-page corpus's number; measured on today's index the caption is on 154 and p.155 has no table at all, D-91) which lost its entire year header row **and** all 8 decimal commas (`26,2`→`262`, a 10× error). A chunk currently preserves no row/column relation at all. This is distinct from the subscript defect and needs its own fix.
- **OPEN — the subscript defect PRODUCES WRONG ANSWERS, not just bad matching (D-63).** Book 7 printed p.121 is indexed as `"hấp thụ khí 0, và thải ra khí (0,"` — O₂ and CO₂ both collapse to `0,`-shaped tokens, so Qwen inverted the answer ("absorbs CO₂, releases O₂"). Retrieval was correct (p.121 ×3); the *text* was unusable. A damaged formula gives the other failure mode: book 9 p.21 indexes `"1 J = 1 Ñm"`, `"(M]"`, and the RAG answer came back **empty** — a silent failure with nothing in the log saying the formula was unreadable. **4 of the 6 evaluator failures trace to ETL/OCR, only 2 to the LLM: the bottleneck is extracted-text quality, not retrieval** (recall@10 = 1.00).
- **OPEN — OCR destroys subscripts in formulas, and this is a real retrieval limit (D-56).** `O₂`→`0,`, `CO₂`→`CO,`/`(0,`, `H₂O`→`H,O`, `O₁,O₂`→`O,,`, `F₁,F₂`→`F,`. Measured across the whole indexed text: **281 subscript-loss occurrences in 147/4934 chunks vs only 4 formulas read correctly** (`CO,` 88×, `CH,` 60×, `SO,` 43×, `H,O` 31×, `H,SO,` 21×) — so subscripts are essentially *never* captured (281:4). Consequence: a student typing `CO2` will not lexically match a page storing `CO,`; the dense bge-m3 channel may partly bridge it, the lexical channel cannot. This was found by opening the G3 fail cases, and it is the sole cause of every G3 `cited_wrong` (the cited page was correct and contained the answer verbatim). **Do not "fix" it by rewriting text** (CẤM #5 — re-guessing a subscript is fabrication). The two legitimate routes, both requiring before/after measurement: normalise subscripts *inside the matcher/query only* (never in stored text), or re-OCR formula regions with a different config.
- **OPEN — OCR junk from figure areas is kept on purpose.** Both candidate filters were measured to delete real text: a per-line confidence floor kills `"Em có biết?"` (conf 56) and `"Gai glycoprotein"` (54); "drop lines with no 3+-letter word" kills `"e Ở 20 °C, 100 mL"`. Junk is noise, not fabrication — the chunk carrying it is flagged `needs_review` instead (D-38).
- **DONE (partly) — white-on-colour labels: `src/etl/layout/pill.py`.** Crop the pill → invert → OCR `--psm 7` → accept only what matches `Hình N.M`; wired into both the text units and the image-side anchors. This is **not** a resolution problem: the labels read at no scale (1×, 1.134× = the old 150-DPI render size, 1.5×, 2×) and inverting a whole crop does not help either (Tesseract binarizes locally). Measured: 32 sample pages / 4 books → **13 pages, 17 `Hình N.M` labels** where there were essentially none, and the Bài numbers cross-check against page position. Candidates are unioned over **`CLOSE_KERNELS = (3, 5, 9)`** because one kernel is not enough (D-51 — see the G4 bullet). **Still unread:** a pill nested inside a cell tinted in the *same hue family* (the three comparison labels) — no saturation threshold separates it (`page_010`: the pill is sat **82** on a sat **157** purple band), hue-band splitting was tried and is not better, and no CLOSE kernel helps either. Needs a local-contrast design (D-40).
- **DONE — the Bài spine is complete and contiguous on all 4 books: 55 / 42 / 47 / 51 = 195 Bài, G1 PASS everywhere** (D-43). `MỤC LỤC` is now read as a **table** (`book/toc.py`): find the table geometry with CV first — the page-number column is the band between the last two vertical rules (books 6/9, which are ruled) or the rightmost ink group behind an ≥8 px gutter (books 7/8, which use tinted bands) — then OCR one cell at a time. The old whole-page `--psm 4` regex returned **0 entries for book 6** because no line ever ends with the page number. Three measured traps, all fixed: `TOC_PAGE_NUMBERS = (5, 6)` was **wrong** — book 6 has THREE TOC pages (5–7), so the constant silently lost Bài 40–55; the TOC page range is now discovered per book. Book 8's number column is only **29 px** wide, so the *crop* clipped the leading digit of 3-digit numbers (`180`→`80`, `191`→`9`) — pad the crop 6 px, but **only** when the column came from a gutter, because padding a ruled column licks the rule and an empty chương cell then OCRs as a phantom `149`. No single psm wins: `56` only reads at psm 6, `169` only at psm 8/13, `166` only at psm 7 — so the candidates are unioned over pad × scale × psm and resolved by a **monotonic** constraint (page numbers never decrease); nothing fits → drop the entry and flag, never guess. `bai_so` **can now be written into chunk metadata** — the D-39 block is lifted, verified visually on book 8 (Bài 30 at `page_124`, Bài 47 at `page_192`, titles matching).
- **DONE — M3 figures: G4 PASSES at 100%. Coverage 72/72 figure numbers have a crop, 0 figures assigned to the wrong Bài, no half-page over-crops (D-45, D-46, D-51).** Progression across the fixes: 88.6% → 90.0% → 95.7% → 97.1% → 98.6% → **100.0%**, with mis-assignment at 0 throughout. `IMAGE_EXTRACTION_VERSION` → `v19_pill_kernels`. The gate is `src/test/qa_figures.py` and needs **no hand-labelled pages**: `Hình A.B` means figure B of **Bài A**, so a contiguous spine lets you check both "A equals the page's Bài" and "the B values form 1..max". Treat the missing-count as a **lower bound** — a Bài's last figure going missing drops `max` with it. Seven defects were fixed, each found by opening the page that was wrong: `read_pill` used psm 7 only (`Hình 1.2` needs psm 8/13, `Hình 1.3` needs 7 — same page); `_extract_figure_label` ranked box titles above `Hình N.M`; a caption read twice (pill `Hình 1.9` vs OCR `Hình 19`) survived dedupe-by-number with the broken copy winning; bridging thresholds 0.25 → 0.15 (a 5-config sweep over 24 pages — better on **both** axes); two OCR "words" **54–62 px tall** (real text 18–24) bridged the 60 px column gutter and made a line box cover 51.6% of a photo cell, so the cell was dropped as text; a body reference `Hình 1.1.` on its own line outranked the real pill caption; and an activity box swallowed a figure inside it **twice** (exclusion zone, then 0.85 containment suppression). Two rules now encode real hierarchy: a cell with a `Hình N.M` caption within 6% of page height is **immune to exclusion zones**, and a labelled figure nested in a box is **legitimate nesting**, like sub_figure in composite. **Crop size is not crop error:** both remaining crops above 40% were opened and verified — `Hình 1.12` really is a full-page figure of 8 slides. **`Hình 2.3` is now solved, and D-46 had the cause wrong (D-51).** It was never local contrast: `pill.py` hard-coded a single `CLOSE_KERNEL = 9`. Measured on the component that actually contains the pill — `k=3` gives a clean **113×30, solidity 0.882** component that reads `Hình2.3`, while `k≥5` fuses it into a **505×286, solidity 0.50** blob wider than `MAX_W`, so it was dropped. D-46's "morphology ruled out" test had run at the *segmenter* layer, not in `find_pill_boxes` — when you say a hypothesis is eliminated, say at which layer you measured it. Candidates are now unioned over `CLOSE_KERNELS = (3, 5, 9)` and deduped by IoU (smallest kernel first, so the tightest bbox wins). `k=0` is excluded **structurally**, not by measurement: without a close, `closed == mask` so `holes` is always empty and `hole_frac = 0 < HOLE_FRAC_MIN` rejects every pill. Comparing the *lists* rather than the totals (the D-46 lesson) shows it gained **two** figures and lost none: `Hình 2.3` plus **`Hình 2.5` of book 8, which was missing without the gate ever reporting a gap** because it is the last figure of its Bài — concrete proof that the missing-count really is only a lower bound. **Still open and genuinely D-40:** the three comparison-cell labels, where the pill sits on a band of the *same hue family* (`page_010`: pill sat **82** on a sat **157** purple band) — no kernel separates that. Visual QA `src/test/test_image_extraction_full.py` is ported to `PageSource` (it used to render at poppler 150 DPI while the ETL reads native 1094×1536 — different coordinate spaces, so its overlays said nothing about production).
- **DONE — G3 exists: `src/test/qa_citation_page.py` measures whether the *cited* page really contains the answer (D-49).** Runs production's own text retriever + `build_citations`, then re-reads each cited page's indexed text. It deliberately does **not** use the gold key — that's recall, which `recall_at_k.py` already covers. Reports `ok` / `cited_wrong` / `no_citation` separately, with `G3 = ok/(ok+cited_wrong)` and `no_citation` kept *outside* the fraction because it is a recall failure, not a citation failure. The matcher is IDF-weighted token coverage with IDF **measured on the index itself** — a folded-form stopword list was tried and measurably wrong, because accent folding collides function words with the corpus's most important content words (`khí`→`khi`, `đo`/`độ`→`do`, `lá`→`la`, `tai`, `đá`→`da`, `nguyên tử`→`tu`, `cân`→`can`). It also self-reports whether reranking was actually in effect, which is how the `RERANK_ENABLED=true` + `HF_HUB_OFFLINE=1` + model-not-downloaded silent degradation was caught. **Measured on the full 4-book index + the 100-question testset (2026-08-22): G3 = 0.9900** (99 ok / 1 cited_wrong / **0 no_citation**) at the calibrated threshold, 0.9800 at the old 0.60, and **1.0000** with the judge rescue. `COVERAGE_MIN` is now **0.50, calibrated by measurement, not typed** (D-57): swept 0.25–0.65 against the judge on only the citations the threshold actually governs (`informative_tokens > 3` — short answers take a different branch, so the threshold never applies to them), giving 86.5% agreement at 0.50 vs 75.7% at 0.60, with the error shape at 0.60 being **9 too-strict / 0 too-lenient**. Do **not** lower it further to make G3 look like 1.0000: judge agreement *drops* below 0.50, and every failure at every threshold was already citing the correct page. Raising it above 0.60 is **unmeasured** (134 citations above 0.60 never went to the judge). The remaining 1 failure, and both failures at 0.60, have one shared cause — **OCR destroys subscripts** (D-56). G1 PASSes page identity on all 4 books, spine contiguous 195/195 (D-43). **G2 is half-done** (`qa_ocr_gold.py` built, 24 pages exported, awaiting the human pass; the consensus half needs PaddleOCR, never installed — D-55). G5 still open.
- **The Bài banner reads only book 6, and the number is published rather than hidden (D-44).** The badge is a **white disc with coloured "Bài N"** in book 6 (the old detector assumed the opposite and got 3 hits / 196 pages) but a **solid coloured hexagon with white "Bài N"** in books 7/8/9. Book 6: badge independently confirms **43/55** TOC-derived start pages, with 1 flagged `banner_toc_mismatch` (page 166, badge read 40 where the TOC says 47 — the TOC is right). Books 7/8/9: **0/k**, measured, after three attempts (corner OCR in both polarities 0/48; shape-masked inverted OCR à la `pill.py` **0/24** — the hexagon is *found* reliably at 241×207 px, so the failure is in reading, not locating; same unsolved class as D-40). The manifest carries `banner_votes = [confirmed, total]` and the G1 report prints it, so a `0/k` is visible, not a silent fallback. **The TOC drives the spine; the badge only corroborates and never overrides** — the old "banner wins" rule is reversed, because the TOC now reads 195/195 while the badge reads ~2/3 of one book with self-contradicting cases.
- **DONE (measured, then switched off) — image captioning is `IMAGE_CAPTION_ENABLED=false` by default (D-47).** The InternVL path is now *correct* — `AutoModel` + `AutoTokenizer`, InternVL dynamic-patch preprocessing, and repo-side `_chat`/`_generate_ids` because the vendored `chat()` hardcodes `input_ids.cuda()` and its `generate()` forwards `return_dict` into `forward()` twice on transformers 4.46.3. D-42's diagnosis was right but it was one of **three** stacked failures. Proof it had never run once: `database/image_caption_cache.json` did not exist. Measured on **12 real crops** (4 books, CPU float32, `max_patches=6`, 100 tokens, greedy): **17.6 s/crop** → ~4.8 h for ~976 crops (basis: 39 crops / 32 sample pages = 1.22 crops/page × 801), ~4× the cost of the whole image side; JSON parses **6/12** (prose prompt: 0/12); quality by opening every crop = correct 2/12, partial 6/12, **fabricated 4/12** — a suction-cup hook became "a surgeon … ear surgery", the Hoà Bình dam grew "small lighthouses", plus invented formulas and stray Russian/Chinese tokens. The decisive number: **it volunteers a figure number and is wrong 4/4 times** (1.1→1.3, 2.2→2.1, 16.11→16.3 ×2) — precisely what `layout/pill.py` already reads correctly (D-45). Its only trustworthy output is text it OCRs back off the crop, which the deterministic pipeline already has. So the code stays (re-enabling is one flag) but the default is off, `_load_model` **raises** instead of self-disabling, and `caption()` no longer swallows errors. Re-enabling requires a new measurement on these same 12 crops, not intuition.
- Cost, measured on the dev box (16 cores, 68 GB RAM, **torch 2.11.0+cpu — no CUDA at all**): text OCR ~1.6 s/page → ~21 min for 801 pages; **bge-m3 embedding on CPU 251 ms/chunk** → ~16 min for ~3800 chunks, so a full `--text-only` is **~37–40 min with no GPU**. Image side (OWL-ViT + CLIP on CPU) ~5 s/page → ~70 min. So Colab is optional for ETL; a GPU only really matters for **serving** Qwen2.5-3B. **End-to-end per page is higher than the sum of those parts (measured 2026-08-22, D-53):** the text loop runs at **3.56 s/page** (39 pages of book 6 → ~11–12 min/book, ~47 min for all 4) and the image loop at **8.86 s/page** (4 figure-rich pages, small sample). Trust the progress log's own `s/trang`, not these estimates.
- **DONE — the ETL prints progress, so "running" is distinguishable from "hung" (D-53).** `src/utils/progress.py::ProgressLogger` logs every `PROGRESS_LOG_EVERY_PAGES` pages **or** `PROGRESS_LOG_EVERY_SECONDS` seconds (10 / 30 by default) on the three slow loops — per-page text indexing, the whole-page OCR that anchors figure captions, and figure cropping — with done/total, measured s/page, elapsed, ETA and caller-supplied counters (`chunks`, `trang_rong`, `fail`, `hinh`, `bo_qua`). `tqdm` is **gone from all three ETL entrypoints**: a stderr bar with no timestamp gets shredded by the log lines it shares a terminal with. It reports only measured numbers — unknown rate prints ETA `?`, never a guess. Adding it exposed that `_load_ocr_text_per_page` OCRs **every** page needing images before the first crop (~5 min of former silence per book).
- **Embedding model: `.env` now sets `EMBEDDING_MODEL=BAAI/bge-m3`**, matching the Colab notebook (verified 2026-08-21). The old 384-dim MiniLM/1024-dim bge-m3 split is resolved; if you ever switch back, the index must be rebuilt — the two dimensionalities cannot share a collection.

## Kế hoạch tới (chốt 2026-08-23) — và CHÍNH XÁC khi nào chạy lại ETL toàn bộ

Thứ tự này không đổi được, vì mỗi bước là **đầu vào bắt buộc** của bước sau, không
phải sở thích tổ chức công việc.

| # | Việc | Đầu ra nghiệm thu | Chặn ai |
|---|---|---|---|
| **M1** | Bộ đọc MỤC LỤC cho CTST (hai cột) + CD (`style = so_thu_tu`, MỤC LỤC ở cuối sách); hợp nhất `toc._BAI` (đang phân biệt hoa/thường) với `fp_toc.ROW_PATTERNS` (đã `IGNORECASE`); cho `toc.py` đọc `entry_style`/`toc_pages` từ fingerprint thay vì hằng số | `--build-manifests` chạy hết **12/12 quyển**, G1 PASS, spine Bài liền mạch từng quyển, manifest được **commit** | **mọi thứ** — đường text `raise ManifestMissing` khi thiếu manifest |
| ~~**M1.5**~~ | **XONG 2026-08-23 (D-73)** | chỉ số dưới **không sống ở đâu cả** (CD 256:3, CTST 377:3, KNTT 408:4) → một luật chung; `s/trang` thật = **5,0** end-to-end, manifest 1,79 s/trang | — |
| **M2** | Text ETL 12 quyển: `min_sat` per-book từ fingerprint, xử lý `SINGLE_LINE_MAX_H = 60` (hằng số KNTT; dòng CD cao ~136 px) kèm before/after, **dựng chỉ mục BM25 cùng lượt** (cùng chunk id) | index text đủ 12 quyển + BM25 song song | MT3, và mọi phép đo eval |
| **M3** | Hình ảnh theo từng NXB: gỡ `LAYOUT_VARIANT = "kntt"`, caption chữ đen cho CD/CTST (kênh pill đọc **0** ở 8/12 quyển) | G4 theo từng NXB | MT1 phần hình, MT4 multi-modal |
| **M4** | Bộ test 12 quyển có nhãn `phan_mon`/`khoi`/`bo_sach`/`do_kho`, phân bố đều | testset mới + gold key khớp index | MT4 |
| ~~**M5**~~ | **XONG 2026-08-25** phần đối chiếu: BM25/dense/hybrid × rerank × cổng lọc trên 300 câu/12 quyển (D-82); text-only vs multi-modal trên 100 câu/4 quyển KNTT (D-87) | hai bảng: `src/test/ablation_report_12books.csv` và `src/test/ablation_mm_report.csv` | báo cáo — **còn nợ**: bộ câu hỏi sinh từ HÌNH (trần bộ test hiện tại chỉ 0,104) và chất lượng câu trả lời có LLM chấm |

**Khi nào chạy lại ETL toàn bộ — ba mốc, không phải một.** Đừng chạy 2 399 trang
trước khi qua mốc trước đó, vì mỗi lần chạy lại tốn nhiều giờ:

1. **Ngay hôm nay chạy được:** `--build-manifests --book SGK_KHTN_{6,7,8,9}_KNTT`
   rồi `--text-only` cho **4 quyển KNTT** (~797 trang, đo được 3,56 s/trang ≈ 47
   phút). Mục đích **không** phải dựng DB cuối cùng, mà là (a) xác minh đường ống
   còn chạy sau khi corpus đổi `offset −1 → 0`, (b) có một `s/trang` thật để so.
2. **Lượt text toàn bộ 12 quyển: SAU M2** (M1 xong + `min_sat` per-book + BM25).
   Chạy sớm hơn thì phải chạy lại, vì `TEXT_EXTRACTION_VERSION` sẽ bump ở M2 và
   version gate sẽ OCR lại **toàn bộ** — đúng theo thiết kế.
3. **Lượt ảnh: 4 quyển KNTT ĐÃ CHẠY (2026-08-25, D-87) — 2 h 24, 938 doc, G4 gán
   sai 0 / thiếu 0. Còn 8 quyển CD/CTST thì vẫn SAU M3.** Kênh pill đọc **0
   nhãn** trên 8 quyển đó nên chạy chúng trước M3 là ~4 giờ để lấy kết quả đã
   biết là sai. `--book` nay lọc được (D-84) nên chạy đúng phần cần chạy là
   một lệnh, không phải một bản vá.

**Một lần chạy lại rẻ hơn ba lần:** cả hai `*_EXTRACTION_VERSION` nên bump **một
lần** khi M2/M3 xong, không bump mỗi lần sửa một tham số.

## Trạng thái tiến độ (quét lại 2026-08-23, đối chiếu code + log + memory)

Mốc đề cương: GĐ1 số hoá 12 quyển đáo hạn **29/07/2026**; GĐ3 thực nghiệm đối chiếu
**14/08 → 28/08/2026**. Bảng này là **trạng thái đã kiểm chứng trên code hôm nay**, không
phải kế hoạch — mỗi dòng nói rõ bằng chứng.

| Việc | Trạng thái | Bằng chứng / chỗ chặn |
|---|---|---|
| Corpus 12 quyển trên đĩa | **XONG**, và **cố ý không nằm trong git** | 12 folder, 2 399 trang, 0 khoảng trống (D-65); 4,1 GB nên `.gitignore` bỏ qua `datasources/*` (D-68) — chạy bằng `RAG_DATA_DIR` trỏ sang Drive, xem `datasources/README.md` |
| M0 fingerprint 12/12 | **XONG** | `database/fingerprints/*.json` đủ 12 file, 5 khoá mỗi file |
| Test suite | **XANH** | `pytest tests/ -q` → **488 pass, 3 skip, 24,6 s** (chạy 2026-08-25; 326/7 là số của 2026-08-23) |
| Commit công việc M0 | **CHƯA** | `fingerprint.py`, `fp_*.py`, 2 file test, 12 JSON, 3 spec, `goal.docx` còn untracked; `master` **không ahead** origin → chưa có gì được ghi lại |
| M1 manifest 12 quyển | **GỠ CHẶN**, spine chưa nghiệm thu | `book/toc_lines.py` (D-70): `read_toc` chọn bộ đọc theo fingerprint, nên `--build-manifests` **chạy được cả 12 quyển** (đo: 1,27–1,46 s/trang → ~50 phút). Nhưng spine Bài của 8 quyển CTST/CD **chưa liền mạch** — đọc được CTST 23/17/17/21 và CD 32/24/23/29 mục, gần nhất là 6_CD (thiếu Bài 3, 4, 34) → G1 vẫn FAIL cho 8 quyển và `bai_so` **không** đi vào metadata chunk (đúng thiết kế: thiếu thì im, không đoán). Cờ trội còn lại: `toc_page_unreadable` ~20/quyển ở CTST |
| Tỉ lệ đọc số trang ở đường manifest | **CHƯA**, và nguyên nhân KHÔNG phải scale | Đo 30 trang/quyển với `(1,3)` / `(1,2,3)` / `(2,)` → **cùng một con số**: 6_CD **40%**, 9_CD 87%, 6_CTST 87%, 6_KNTT **100%**. Giả thuyết "thiếu scale 2×" **bị bác bỏ** (D-72). Khác biệt thật: fingerprint đọc trong **dải zone đo được của chính quyển** (`zone_read.band_even`), còn `page_number_ocr` dùng hằng số góc của KNTT. Hệ quả hiện tại: 6_CD có `ocr_confirmed` **37,1%**, 112 trang lấy `printed_page` suy từ offset đã đo, mỗi trang một cờ `page_number_not_read` → G1 FAIL đúng như phải fail |
| Manifest cho quyển có đồng thuận offset yếu | **XONG** | `build_manifest` đối chứng với offset đã đo ở fingerprint: trùng → đi tiếp + gắn cờ, khác → vẫn raise, không có fingerprint → vẫn raise. `MIN_OFFSET_RATIO = 0.8` **không** bị nới (D-72). Chạy thật: `KHTN6-CD.json` 179 trang / offset 0 / 32 Bài, 1,79 s/trang |
| `book_id` theo nhà xuất bản | **XONG** | `book_id_from_source_name` từng nối cứng `-KNTT` nên `SGK_KHTN_6_CTST` ra `KHTN6-KNTT` và **ghi đè manifest của 6_CD** — ba NXB cùng lớp dùng chung một file, im lặng hoàn toàn. Bắt được bằng cách **mở artefact đầu tiên ra đối chiếu** (`n_pages: 204` không thể là của quyển 195 trang), không bằng test: 158 test vẫn xanh khi bug còn sống (D-71) |
| Fingerprint được code sản xuất ĐỌC | **CHƯA** | `grep -rn fingerprint src/` chỉ trúng `image_captioner` (trùng tên biến). M0 đo xong nhưng ETL vẫn chưa dùng → `min_sat` per-book, `entry_style`, vùng số trang vẫn là hằng số KNTT |
| ETL text bằng MODEL đọc cả trang | **BƯỚC 0 XONG — có BASELINE** (D-91, D-92) | người dùng chốt 2026-08-25: bake-off trước, model đọc **cả trang**, Colab GPU, phạm vi cuối 12 quyển. Đo được **0/4 model ứng viên** nhắc tiếng Việt trong model card → phải bake-off. Phiếu **97 ô / 15 trang** đã NGƯỜI duyệt xong (97/97, `document/review/ocr_gold/phieu_nguoi.json`). **BASELINE Tesseract: công thức `CT = 0,048` (4,8% token đúng / 45 ô) · lỗi dấu `DẤU = 0,016` (1,6%) · bảng `BẢNG = 0,000` (0/8)**. Còn lại: chạy **3 engine** trên Colab (`nanonets_ocr2_3b` → `mineru25` → `dots_ocr`; `paddleocr_vl` là ô tuỳ chọn cuối notebook — D-94). Crop 8,3 MB nay **nằm trong git** ở `document/review/ocr_gold/` nên Colab chỉ cần `git clone` (D-93). **Engine 1/3 đã chạy được trên Colab** (2026-08-26): `nanonets_ocr2_3b`, `transformers 5.15.1`, nạp bằng `AutoModelForImageTextToText`, **~29,5 s/ô → ~48 phút cho 97 ô**; mới là lượt thử `--limit 3` nên **chưa có số**. **Bảng `--compare` đã vá (D-96):** engine thiếu ô nay in `—` và bị chặn công bố — trước đó engine chạy 3/97 ô ra `DẤU = 0,000`, tức điểm HOÀN HẢO ở đúng cột quyết định thắng/thua, và luật chốt KHÔNG loại nó (một từ mất hẳn không phải "lỗi dấu"). **Đường nạp model đã vá (D-95):** bản cũ dùng một `AutoModelForCausalLM` cho cả ba engine và sẽ chết ở **2/3** (đo trên `config.json` HF: Nanonets là `Qwen2_5_VLForConditionalGeneration`, MinerU2.5 là `Qwen2VLForConditionalGeneration`, `auto_map` rỗng cả hai); nay `_load_vlm` thử `AutoModelForImageTextToText` → `AutoModelForCausalLM` → `AutoModelForVision2Seq`, **in ra class nào thắng**, hết cách thì raise kèm đủ lỗi. Thiết kế: `document/specs/2026-08-25-ocr-model-bakeoff-design.md` |
| `--book` lọc được cả ba đường ETL | **XONG** (D-84) | trước đó `--book` chỉ nối vào `--build-manifests`, nên `--image-only --book X` **im lặng bỏ qua cờ** và sẽ chạy cả 12 quyển ≈ 6 giờ (8 quyển biết trước là sai). Tên quyển không khớp nay **thoát mã 2** kèm danh sách 12 quyển thật — thử trên CLI thật: `--book SGK_KHTN_6_KNT` → exit 2. 7 test |
| Gỡ `LAYOUT_VARIANT = "kntt"` | **CHƯA** | `src/etl/image_processor.py:4105`, `make_image_processor()` vẫn luôn trả KNTT (D-64 đã đảo chiều D-50) |
| `text_extract.SINGLE_LINE_MAX_H = 60` | **CHƯA** (cố ý) | hằng số KNTT; dòng CD cao ~136 px → việc của M2, phải kèm before/after |
| Phép đo chỉ số dưới ở CD/CTST | **XONG, và nó BÁC BỎ giả thuyết** | đo trên chính index (không cần OCR lại): hỏng:đúng = **CD 256:3, CTST 377:3, KNTT 408:4**, `₂` Unicode **0 lần ở cả ba**. Chỉ số dưới **không sống sót ở đâu cả**, nên D-56 KHÔNG phải artefact của KNTT 1094×1536 → bước xử lý công thức Hoá/Lý là **một luật chung**, không chia theo NXB (D-73) |
| BM25 (MT3) | **XONG** (D-77, D-78, D-79) | `python main.py --build-bm25` -> `database/sparse/`: **16 393 chunk / 19 727 từ vựng / 5,5 s**, khoá là chính `chunk_id` của `biology_text`. Tự cài Okapi BM25 (`src/rag/bm25.py`) thay vì `rank_bm25`, vì `k1`/`b` phải là tham số lúc TRUY VẤN thì quét 5×5 mới rẻ. Dấu vân 6 trường -> chỉ mục cũ hơn index thì `SparseIndexStale`, không có fallback. **Đã quét bằng số:** `k1=0.7, b=0.75`, `BM25_TOKENIZER=plain` — GIỮ dấu thắng BỎ dấu (MRR 0,820 vs 0,755), **lật giả định ban đầu**. Chuẩn hoá công thức (`CO2` ↔ `CO,`) chỉ ở phía truy vấn/chỉ mục thưa, **không sửa một ký tự nào** trong `biology_text`: đo trên 12 công thức, chunk đúng ở top-10 đi từ **6 lên 97**, số truy vấn tìm được từ **1/12 lên 11/12** |
| Hợp nhất thưa+dày (MT3) | **XONG** (D-80) | `src/rag/hybrid_text_retriever.py` (đừng nhầm với `hybrid_retriever.py` = lai text+ảnh). Thứ tự **hợp nhất -> cổng lọc -> rerank**; `RETRIEVAL_MODE` ∈ {dense, bm25, hybrid} × `RERANK_ENABLED` × `RELEVANCE_GATE_ENABLED` = **12 cấu hình**. Phát hiện: trước M2 cổng lọc và rerank **loại trừ nhau** (`RERANK_ENABLED=true` khiến `RelevanceGatedRetriever` không bao giờ chạy -> `RETRIEVER_DISTANCE_MARGIN` là **số chết**). **Mặc định nay là `hybrid`, cổng lọc TẮT** (D-82), chốt bằng bảng **300 câu / 12 quyển** ở ĐÚNG bề rộng production (20 ứng viên/kênh): hybrid R@1 0,717 · R@3 0,887 · R@10 **0,977** · MRR **0,808**, thắng bm25 (0,796) và dense (0,794) ở mọi cột. Ở bề rộng ĐO (50) biên độ chỉ +0,005 MRR = nhiễu; ở bề rộng THẬT (20) là +0,014 MRR / +0,020 R@10 |
| Kho ảnh 4 quyển KNTT | **XONG** (D-87) | `--image-only --book` bốn lượt, **20:40 → 23:04 = 2 h 24**, 4/4 exit 0 → **938 doc** (285/203/215/235). Pha crop **6,51–11,11 s/trang** (biên độ 1,7× giữa các quyển!), khớp ~8,86 s/trang của D-53. `figure_label` 891/938 · `crop_text` 806 · `figure_caption` 557 · `visual_caption_vi` **0/938** (captioner tắt, đúng D-47) · **578/797 trang có hình = 72,5%**. **8 quyển CD/CTST vẫn KHÔNG dựng được** (kênh pill đọc 0 nhãn — M3), nên mọi số phía ảnh phải kèm chữ “4/12 quyển” |
| Cổng G4 trên corpus MỚI | **PASS** (D-87) | chạy lại hôm nay, 4 Bài/quyển: **gán sai Bài 0/0/0/0, thiếu (cận dưới) 0/0/0/0**, 72 hình có nhãn / 12 không nhãn. Con số 72 **trùng** corpus 801 trang cũ là trùng hợp (cùng 4 Bài đầu), không được trích như cùng điều kiện. Cột đáng xem: **`crop nghi cắt lấn` 30/86 = 34,9%** — là CỜ cho người, phần lớn là `activity_box` vốn nhiều chữ; ca cần mở ra xem là `9_KNTT` tr.12 `Hình 1.12` dt = **0,749** |
| Định tuyến `is_image_only_query` | **ĐÃ VÁ** (D-88) | đo được **3/300 câu cần chữ bị định tuyến thành CHỈ ẢNH → 0/300** sau bản vá. `HybridRetriever.search` bỏ HẲN phía text khi cờ bật, nên ba câu đó nhận “Mình tìm thấy N hình ảnh liên quan” thay vì câu trả lời — im lặng hoàn toàn. Một ca là bẫy phạm vi KHTN: trong **Vật lí** “ảnh” là ảnh quang học. Luật mới so trên dạng **còn dấu** vì bỏ dấu thì `nào` đụng `não` (D-49). `query_intent.py` trước đó **không có test nào**; nay 9 |
| Caption deterministic vào prompt (MT4) | **XONG** (D-85) | `src/rag/multimodal_context.py` nối `figure_label` + `figure_caption` + `crop_text` (ba trường đọc lại từ pixel) vào ngữ cảnh LLM; **không** đọc `visual_caption_vi`/`final_caption_vi`/`caption`/`caption_vi` vì bốn trường đó do model **sinh** (D-47). Bật/tắt bằng `MULTIMODAL_CONTEXT_ENABLED`, **mặc định false** cho tới khi có số. Tự kiểm đã chạy khi kho ảnh còn **0 doc**: `delta_R` **0,000**, ngữ cảnh dài thêm **0,0 ký tự** → không có nhánh ẩn. `api.py:95` nay gọi `build_context(...)` |
| Bảng đối chiếu MT4 | **XONG CẢ HAI CẤU HÌNH** (D-82, D-87) | **Cấu hình 1** (BM25 thuần vs dense thuần vs hybrid × rerank × cổng lọc) trên **300 câu / 12 quyển**, `scripts/run_ablation.ps1`, 0 lượt gọi LLM. Ở bề rộng production (20 ứng viên/kênh): **hybrid R@1 0,717 · R@3 0,887 · R@10 0,977 · MRR 0,808** > bm25 0,796 > dense 0,794. **Cấu hình 2** (text-only vs multi-modal) trên **100 câu / 4 quyển KNTT**, `python -m src.test.ablation_multimodal`, 0 lượt gọi LLM, 21,17 s/câu: text_R **0,930** → mm_R **0,940** (**delta +0,010 = ĐÚNG 1 câu**), hình đúng trang vàng **42** vs hình sai trang **93**, độ phủ token đáp án 0,896 → 0,900 (tăng ở 14 câu, **giảm ở 0**), **+492 ký tự/câu**. → `MULTIMODAL_CONTEXT_ENABLED` **giữ false**. **Giới hạn lớn hơn con số:** `cov_txt` đã 0,896 vì `ground_truth` sinh từ chính văn bản trang vàng, nên trần còn lại cho kênh hình chỉ 0,104 — kết luận đúng là “CHƯA đo được ưu thế”, KHÔNG phải “đa phương thức vô ích”. Việc chặn: bộ câu hỏi **sinh từ HÌNH**. **Hai điều bảng 4 quyển nói SAI và đã bị lật:** (a) “BM25 thuần thắng dense” — trên 300 câu là **hoà** (0,804 vs 0,805); (b) “cổng lọc trung tính” — thật ra **có hại** (hybrid R@10 0,977 → 0,930). Bộ test do **LLM sinh**, và từ 2026-08-25 có **mẫu 50 câu người duyệt tay: gold key sai 2/49 = 4,1%, KTC 95% Wilson 1,1–13,7%, 1 câu không quyết được** (D-90) — cận trên 13,7% nghĩa là tới ~41/300 câu vẫn có thể sai mà mẫu không thấy. **Con số 0/50 = 0,0% của D-89 là SAI** (phiếu điền hàng loạt trong 38 s), đừng trích lại. **Cả 2 ca sai cùng một ô `hoa × suy_luan`** — câu đòi tự viết phương trình nên đáp án không nằm nguyên văn ở trang vàng: lỗi **sinh câu hỏi**, không phải lỗi chọn trang. Mẫu **cố ý lệch** về `suy_luan` (25/50 = 50% vs 96/300 = 32%) nên 4,1% là con số **bi quan**; hiệu chỉnh theo trọng số cả bộ ≈ **2,7%**. `_generation_meta.json` **vẫn** ghi `human_reviewed: false` vì đó là trường của cả bộ 300 câu |
| Index text 12 quyển | **XONG** (D-73) | lượt chạy thật 2026-08-23: manifest 49 phút, `--text-only` **3 giờ 20**, **0/2 399 trang còn thiếu**, **16 393 chunk**, 5,0 s/trang end-to-end (cao hơn 3,56 s/trang đo trên KNTT — đúng như đã cảnh báo). Dựng với `SINGLE_LINE_MAX_H = 60` và `LAYOUT_BOX_MIN_SATURATION = 45` **chưa hiệu chỉnh**, nên M2 bump version sẽ OCR lại toàn bộ — hãy gom mọi thay đổi tham số vào MỘT lượt |
| `bai_so` trong metadata chunk | **CHỈ 4/12 QUYỂN** | KNTT 1 086/1 037/1 212/1 522 chunk có `bai_so`; 8 quyển CTST/CD **không chunk nào** (spine chưa liền mạch → tự động thôi ghi, đúng thiết kế). Nghĩa là truy vấn theo Bài chỉ chạy trên 1/3 kho |
| `needs_review` | **MẤT TÁC DỤNG**, phải hiệu chỉnh | bật ở **57–84% chunk** (9_CD 1 339/1 590 = 84%). Ở mức đó cờ này gần như không mang tin — việc của M2 (D-73) |
| LLM đánh giá (OpenRouter) | **CHẠY ĐƯỢC**, hạn mức ngày CHƯA ĐO | `stealth/ox-alpha` qua `https://openrouter.ai/api/v1`, gọi thật 9 lần OK (D-67); không có header `x-ratelimit-*` nên chưa biết cap/ngày |
| Bộ test 100 câu (4 quyển KNTT) | **CÒN DÙNG ĐƯỢC** (D-76 lật ngược) | Số cũ "gold key trỏ vào index đã xoá" là **SAI**: đo được **99/100 gold key khớp index 12 quyển ở offset 0** (offset −1 chỉ 31/100), và `recall_at_k.py` cho **R@10 = 0,98**. Cơ chế: corpus mới ít hơn đúng 1 trang/quyển (bỏ trang bìa) nên **số trang IN không đổi**, mà gold key ghi theo `source_page` = số trang in. Vẫn phải sinh bộ 12 quyển vì bộ này chỉ phủ **4/12 quyển** và thiếu nhãn `phan_mon`/`khoi`/`bo_sach`/`do_kho`. Track A đã chuyển vào `src/test/testsets/_archive_4books_kntt_offset_minus1/` — tên thư mục mô tả sai thực tế |
| G2 gold set 24 trang | **VÔ HIỆU** | số trang đổi (offset −1 → 0); nếu làm lại phải sửa cảnh báo `sua_tay*3 < may2` (23/24 file gold trùng từng chữ với `read_claude.txt`) |
| Xử lý công thức Hoá/Lý (MT1) | **CHƯA** | D-56/D-63 nay là hạng mục hợp đồng, không còn là nợ kỹ thuật |
| Web UI Next.js (MT5) | **CÓ, NHƯNG THIẾU 2 THỨ ĐỀ CƯƠNG ĐÒI** | repo `D:\personal_repo\project_rag_fe` (Next 16.2.6 / React 19, 732 dòng, 4 commit). ▸ **Không có KaTeX/MathJax/latex** ở đâu cả (`grep -rn "katex|mathjax|latex|remark-math"` = 0) → yêu cầu "hiển thị công thức Toán/Hoá" **chưa làm**. ▸ `ChatResponse` = `{answer, images}` — **FE bỏ hẳn trường `citations`** mà `src/app/api.py` đã gắn sẵn, tức cơ chế của nguyên tắc 1 không tới được mắt học sinh. ▸ `src/lib/api.ts:2` **hardcode `http://localhost:5000`** (URL HF Space bị comment ở dòng 1) → chặn demo Colab/remote |

Bốn câu của m0-prompt §6 nay **đã có ba câu trả lời** (2026-08-23): frontend là
`D:\personal_repo\project_rag_fe` (xem dòng MT5); LLM đánh giá đổi sang OpenRouter và **đã
gọi thật** (D-67); người dùng đã cho phép commit + push `master`. Còn mở: **hạn mức/ngày của
OpenRouter free tier** (API không trả header nào để đo) và **G2 làm lại hay thu hẹp thành
gold set CÔNG THỨC** (xem dưới).

**G2 dùng để làm gì, và bỏ nó thì mất gì** — trả lời bằng chỗ code thật, không bằng cảm
tính. G2 **không gate bất kỳ đường chạy nào**: `grep -rn qa_ocr_gold src/ main.py` ngoài
chính nó = **0**, nên ETL và retrieval chạy y nguyên khi không có G2. Nó là **dụng cụ đo**
CER/WER/tỉ lệ lỗi DẤU của OCR trên trang người đã xác nhận. Vì vậy:

- Bỏ G2 **không** làm hỏng MT2/MT3/MT5 (corpus, hybrid, UI) — những cái đó có cổng đo riêng
  (G1, recall@k, bảng ablation).
- Nhưng **MT1 thì có**: "bổ sung bước xử lý đặc thù cho công thức Hoá, Lý" là hạng mục hợp
  đồng, và D-63 đã đo rằng **4/6 ca fail là do chất lượng chữ trích xuất, không phải
  retrieval** (recall@10 = 1,00). Không có phép đo OCR thì câu "bước xử lý công thức đã cải
  thiện được X" **không có số để nói** — vi phạm nguyên tắc 3.
- **Khuyến nghị: đừng làm lại gold set 24 trang tổng quát; thu hẹp thành gold set CÔNG THỨC
  theo NXB.** Chỉ cần vài trang Hoá/Lý mỗi NXB, chỉ chấm token công thức (`O₂`, `H₂SO₄`,
  `A = Fs`), vì (a) nó trả lời trực tiếp câu "chỉ số dưới có sống ở độ phân giải CD/CTST
  không" (m0-report §7.5) — thứ **có thể đổi thiết kế**; (b) rẻ hơn nhiều lần cho người
  duyệt; (c) bộ 24 trang cũ là **KNTT-only**, tức đo đúng bộ có độ phân giải THẤP NHẤT. Nếu
  làm lại theo hướng nào cũng phải sửa cảnh báo `sua_tay*3 < may2` trước, vì 23/24 file gold
  cũ trùng từng chữ với `read_claude.txt` nên cảnh báo đó không bao giờ kích hoạt được.

## Working rules (always)

- **Adversarially review every code change for hidden bugs before claiming done** — trace edge cases, off-by-ones, coordinate/index mismatches, stale caches; don't trust that a passing test means correct.
- **Do NOT run the full test suite while iterating.** Run only the focused test(s) for the code you changed (e.g. `python -m pytest tests/layout/test_segmenter.py -v`). Run the whole suite only when explicitly asked or right before finishing a milestone.
- **Keep tests small and targeted.** Avoid large/slow/expensive tests unless they're truly necessary; prefer focused unit tests with synthetic fixtures over heavy end-to-end runs.
- **Commit messages: NO `Co-Authored-By` trailer** (and no "Generated with" lines). Plain messages only.
- Log each decision in `document/decision_log.html`; keep spec/plan in `document/specs/`; keep CLAUDE.md + memory current.

### Định nghĩa "xong" — ghi log & memory NGAY trong lượt phát hiện

Một việc **chưa xong** cho tới khi bốn chỗ dưới đây đồng bộ với thực tế đã đo. Không hoãn
sang lượt sau: một phép đo không được ghi lại là một phép đo sẽ phải đo lại, và tệ hơn — là
một dòng CLAUDE.md sai đang chỉ đạo lượt sau.

1. **`document/decision_log.html`** — thêm một entry `D-NN` (id tăng dần, `date` là ngày
   thật) cho **mỗi quyết định hoặc mỗi phép đo lật ngược một giả định**. `decision` = kết
   luận một câu; `notes` = **số đo thật** (bao nhiêu trên bao nhiêu, mẫu nào), kèm cả **giả
   thuyết đã bị bác bỏ** để lượt sau không thử lại. Số cũ sai thì **ghi rõ nó sai và sai ở
   đâu** — không im lặng thay số.
2. **`CLAUDE.md`** — dòng nào bị phép đo mới làm sai thì sửa **trong cùng lượt**, và nói rõ
   con số cũ đã bị lật (nguyên tắc 2). Cập nhật luôn bảng "Trạng thái tiến độ" ở trên:
   `XONG` chỉ được viết khi có bằng chứng chạy được dán kèm; `CHƯA`/`BỊ CHẶN` phải nêu chỗ
   chặn cụ thể (file:dòng, hoặc lệnh grep tái lập được). Đổi cả `DONE`/`OPEN` của gạch đầu
   dòng tương ứng trong "Active redesign".
3. **Memory** (`C:\Users\lcdkhoa\.claude\projects\D--personal-repo-project-rag\memory\`) —
   chỉ ghi thứ **không suy được từ code/git**: phạm vi & mốc hợp đồng, ràng buộc môi trường
   (quota LLM, không có GPU), lựa chọn người dùng đã chốt, và **phép đo đắt** (một lượt M0
   ≈ 70 phút OCR). Memory cũ bị phép đo mới phủ định thì **sửa chính file đó**, đừng tạo
   file thứ hai; đánh dấu `HISTORICAL:` thay vì xoá khi nó vẫn giải thích một quyết định.
   Mỗi file kèm đúng một dòng trong `MEMORY.md`.
4. **Spec trong `document/specs/`** — báo cáo phép đo (`*-report.md`) và prompt bàn giao cho
   lượt sau (`*-prompt.md`), trong đó §"việc còn lại" và §"trạng thái file khi bàn giao"
   phải khớp `git status` thật. **Và nếu thay đổi chạm tới ETL thì phải vá luôn
   `document/colab_runtime_etl.ipynb`** (D-69) — đó là thứ người dùng THỰC SỰ chạy, nên một
   dòng sai ở đó đắt hơn một dòng sai trong spec: nó làm mất cả một phiên Colab.

Rồi mới **commit** (message thuần, không `Co-Authored-By`). Chưa commit thì công việc vẫn
là "chưa có gì được ghi lại" — xem dòng "Commit công việc M0" trong bảng tiến độ.

## Commands

All commands run through `main.py` (from repo root). There is no build step — it's a Python app.

```bash
pip install -r requirements.txt
cp .env.example .env          # then set HF_TOKEN (required) and USE_GPU

# STEP 0 — page map + Bài spine per book. REQUIRED before any text indexing:
# the text loader refuses to guess a printed page number and raises without it.
# Prints the G1 report and exits nonzero when G1 fails.
python main.py --build-manifests
python main.py --build-manifests --book SGK_KHTN_6_KNTT   # one book only

# ONE COMMAND, run-unattended (Windows/PowerShell): manifests 12 books -> text
# ETL -> "what's left" report, all into one timestamped log. It reads
# --build-manifests' exit code, PRINTS it, and continues: G1 FAIL is EXPECTED
# today (CTST/CD spines are not contiguous, D-70) while `save_manifest` still
# wrote every book that built, and --text-only only needs the manifests to exist.
# Chaining the two with `&&` would block step 2 for no reason.
powershell -ExecutionPolicy Bypass -File scripts\run_etl_local.ps1

# STEP -1 (M0) — measure each book's own layout fingerprint. Writes/merges
# database/fingerprints/{book}.json; a failed stage never overwrites a good one.
python -m src.etl.book.fingerprint --all --verbose > fp.log 2>&1 &
python -m src.etl.book.fingerprint --all --stages toc --verbose     # one stage only
python -m src.etl.book.fingerprint --book SGK_KHTN_6_CD --sample 40 --verbose

# ETL (offline indexing) — checkpoint resume is per PAGE, keyed on page content
python main.py --text-only    # layout-aware OCR + chunk + index text → ChromaDB
python main.py --image-only   # crop figures + caption + index images
# `--book` works on ALL THREE ETL paths since D-84 — it used to be honoured
# only by --build-manifests, so `--image-only --book X` silently ran all 12
# books (~6 h, 8 of them known-wrong). A name that matches nothing EXITS 2.
python main.py --image-only --book SGK_KHTN_6_KNTT
python main.py --etl          # both (same text path as --text-only)

# Image metadata human-review cycle (see README §6 for exact JSON semantics)
python main.py --export-image-review database/review_images.json
python main.py --apply-image-review database/review_images.json --review-user <name>   # upsert-by-item, NOT full sync
python main.py --replace-image-db database/snapshot.json --review-user <name>          # JSON is source of truth (deletes missing)

# Serve
python main.py --api --port 5000
```

### Evaluation (in `src/test/`)

Requires `EVAL_LLM_*` in `.env` (any OpenAI-compatible endpoint). **`.env` now points at OpenRouter — `EVAL_LLM_BASE_URL=https://openrouter.ai/api/v1`, `EVAL_LLM_MODEL=stealth/ox-alpha` (D-67, tested live 2026-08-23).** Two traps, both measured: the URL must **stop at `/v1`** — the value copied from OpenRouter's docs (`.../v1/chat/completions`) makes the OpenAI client append `/chat/completions` a second time and returns **404**; and **never set `max_tokens`** — `completion_tokens` measured ~5× the visible text (139 tokens for an 81-char answer) even though the API reports `reasoning_tokens: 0`. Latency 4.4–6 s/call with **outliers at 59 s and 63 s**, so keep timeouts ≥ 120 s. Cost 0, key `is_free_tier: true`, and the response carries **no `x-ratelimit-*` header at all** — so the free-tier daily cap is **unmeasured**; 10 consecutive calls passed with no 429, which does *not* prove a 300-call testset run will. Diacritics survive round-trip (`"Quang hợp diễn ra chủ yếu ở lá"`), and `_parse_json` already strips the ```json fences this model emits. **Historical, for the report only (D-54):** the earlier Gemini endpoint `https://generativelanguage.googleapis.com/v1beta/openai` — model choice there was made by measuring the quota error's own `quotaValue`: `gemini-2.5-flash` 404 "no longer available to new users"; `gemini-3.6-flash` **20 requests per DAY**, which killed a 112-request run after exactly 20; `gemini-3.5-flash-lite` **15 per MINUTE**, 1.1 s/call. Split cleanly into deterministic IR metrics vs. LLM-judged answer quality:

```bash
python src/test/generate_testsets.py --dry-run  # pick pages + print stats, NO LLM calls
python src/test/generate_testsets.py            # 25 questions/book via PageSource; gold keys come from real chunk metadata (D-48)
python -m src.test.ablation_multimodal          # Cấu hình 2: text-only vs multi-modal (0 LLM)
python -m src.test.prompt_scope_probe           # before/after câu Lý + câu Hoá khi sửa prompt
python -m src.test.qa_citation_page             # G3 gate: does the CITED page contain the answer (no LLM needed, D-49)
python -m src.test.qa_citation_page --judge     # + LLM rescue pass, calibrates the coverage threshold
python -m src.test.ocr_bakeoff --compare        # bảng bake-off; engine thiếu ô -> in `—`, không in số (D-96)
python -m src.test.ocr_bakeoff --doi-chieu <engine> --so-o 10   # ĐỌC ô bằng mắt: NGƯỜI · engine · tesseract (D-98)
python -m src.test.qa_ocr_gold --export         # G2: build 24-page gold set for a HUMAN to correct (D-55)
python -m src.test.qa_ocr_gold --score --per-page   # G2: CER/WER/diacritic-ER once corrected
python src/test/evaluator.py                    # run real RAG, measure P/R/MRR + LLM judge (1–5)
python src/test/recall_at_k.py                  # fast recall benchmark, no LLM calls; reports baseline vs rerank in ONE pass
python src/test/test_image_extraction_full.py   # canonical VISUAL QA for image cropping (draws boxes on pages)
```

`src/test/testsets/` now holds a **real 4-book testset: 100 questions, 25/25 per book** (generated
2026-08-22 with `gemini-3.5-flash-lite`, seed 42). Verified against the built index: **0/100 gold keys
point at a page with no chunk**, and `tests/test_eval_gold_keys.py` (5 tests) passes. The 12-book ones live in
`testsets/_archive_12books_2026_07/` (outside the `*_testset.csv` glob) because both their gold keys
mismatch today's chunk metadata. **Testsets are LLM-generated and not human-reviewed** —
`_generation_meta.json` records `human_reviewed: false`, and any report using these numbers must say so.
`metrics.PAGE_TOLERANCE` is **0**: chunks never span pages, so a ±1 window only credits a chunk from a
*different* page and inflates recall (it also masked the old off-by-one gold key).

## Architecture

Two phases: **ETL (offline)** builds the indexes; **query (online)** serves via Flask.

### Storage — four ChromaDB collections (`src/config.py`)
- `biology_text` — OCR'd text chunks (bge-m3 embeddings, `CHUNK_SIZE=400/overlap=120`)
- `biology_images` — figure crops (CLIP embeddings)
- `biology_image_metadata` — caption/keyword metadata for figures (separately searchable)
- `processing_status` — per-page checkpoint state enabling resumable ETL

**Checkpoint semantics (all three ETL entrypoints agree):** `processing_status` is the single truth source. Every record is keyed on **`page_key` = `{book name}#{md5 of that page's bytes}`** (`page_source.page_checkpoint_key`) plus a version — `TEXT_EXTRACTION_VERSION` for text, `IMAGE_EXTRACTION_VERSION` for images. So: replacing one page file re-processes **only that page**; bumping either version re-processes everything on that side. Chunk ids are `{page_key}_p{page_number}_c{chunk_index}`, and `_index_source_pages` deletes a page's existing text chunks before writing the new ones, so a version bump never leaves orphaned chunks behind. **The image side needed the same thing and did not have it (D-52):** an image doc's id is `image_id` = the hash of the *crop*, so a changed crop gets a new id and the old doc survives instead of being upserted over. Measured on a 12-page scratch DB: swapping one page's bytes left that page with **3** image docs (one stale). `ImageVectorDB.delete_page_documents(source, pages)` now clears both image collections for the pages about to be rewritten, called from `run_etl` and `run_etl_image_only` *after* extraction succeeds (so a crash deletes nothing) and *even when the page yields no figures* (a page that lost its figure must lose its docs too). `database/processed_files.txt` / `processed_images.txt` are **advisory progress logs only** — nothing skips work because of them. Each entrypoint queries the checkpoint *before* doing any OCR, so a book with nothing left to do costs one md5 per page.

Everything writable lives under `database/` (`PERSIST_DIR`), overridable via `RAG_DATABASE_DIR` (point at Google Drive on Colab). `database/manifests/{book_id}.json` holds the per-book `BookManifest`, overridable **separately** via `RAG_MANIFEST_DIR` so manifests can travel with the repo while the index sits on Drive. `database/fingerprints/{book}.json` (the M0 layout measurement, 12/12 books) works the same way via **`RAG_FINGERPRINT_DIR`**, defaulting to `<repo>/database/fingerprints` — it is a *measurement* that cost ~70 min of OCR, so it belongs to the repo, not to the Drive index. It used to be `Path("database/fingerprints")` hard-coded in `book/fingerprint.py`, a **relative** path that silently read/wrote the wrong place from any cwd but the repo root (D-69). `datasources/` holds the input page PNGs, one folder per book (see "What this is") — no PDFs; override with `RAG_DATA_DIR`. **The PNGs are NOT in git (D-68):** measured 4.1 GB / 2 399 pages against an already-11 GB `.git`, and the CD/CTST batch alone (~3.4 GB) exceeds GitHub's 2 GB per-push limit — PNGs were never LFS-tracked (`.gitattributes` covers only `datasources/*.pdf`). `.gitignore` now ignores `datasources/*` except `datasources/README.md`, which documents the expected layout. Untracking does **not** shrink `.git`: the 801 KNTT PNGs stay in history until someone rewrites it, which nobody has. Consequence to remember: a fresh clone has **no data**, so all four data entrypoints now **exit nonzero** instead of logging and returning 0 — measured `--text-only`/`--image-only`/`--etl` → **2**, `--build-manifests` → **1**.

### Page source (`src/etl/page_source.py`)
`PageSource` is the only way page pixels enter the system: `page_numbers()` (the numbers **in the filenames**, never `enumerate` order), `load(page_number)` → BGR uint8, `content_hash(page_number)`. `PngFolderPageSource` is the real corpus; `PdfPageSource` exists only for the legacy `/api/etl` upload. `discover_page_sources(DATA_DIR)` returns every book (PNG folders first, then any legacy PDFs). Anything that needs a page must go through this — do not re-add `fitz`/poppler calls to the ETL.

### Text ETL (`src/etl/layout/loader.py`)
`LayoutOCRLoader.load_page(source, page_number)` is the layout spine and the **only** text path: manifest lookup (printed page + role) → `source.load()` → `segment_page` → `extract_text_units` → `chunk_units`. There is no preprocess step and no page-number detection here: the **printed page number comes from the `BookManifest`**, and a missing manifest / unknown page / absent `printed_page` raises `ManifestMissing` rather than guessing. Pages with `role="cover"` return no chunks (the source file is never touched or deleted).

Chunks carry `source`/`page` (printed) /`page_index` (source page number) /`variant`/`region_type`/`chunk_index`/`needs_review`/`review_tokens`. `page` and `page_index` are **equal on today's corpus** (offset 0 — D-65; re-measured 2026-08-25: 0/16 393 chunks differ), so never conflate them *by design* even though they now coincide: citations use `page`, tracing back to a file uses `page_index`. The old "differ by exactly 1" note was measured on the 801-page KNTT corpus and is void. `citations.py` reads `region_type` for the section label, so a chunk missing it silently degrades to a body-only citation. Body text is split by `TextSplitter`; a sidebar/info-box stays atomic unless it exceeds `BOX_ATOMIC_MAX_CHARS` (1.5 × `CHUNK_SIZE`), in which case it is split but keeps its `region_type`.

`--etl` and `--text-only` both go through `_index_source_pages()` in `main.py`, one page at a time; a page that raises is logged, left unmarked, and retried next run. The legacy whole-page `RobustOCRLoader` is **not** a text path any more — `ocr_image()` survives only to supply full-page OCR text for figure-caption anchoring on the image side.

### Retrieval flow (`src/rag/`)
1. `hybrid_retriever.py::HybridRetriever.search()` is the entry. It calls `query_intent.py::is_image_only_query()` to **route**: image-only queries (e.g. "cho tôi hình con X") skip text retrieval entirely.
2. Text side: `RETRIEVAL_MODE=dense` (mặc định) giữ nguyên hai lớp cũ — `RerankedRetriever` khi `RERANK_ENABLED`, **RelevanceGatedRetriever** (relative-distance gate `RETRIEVER_DISTANCE_MARGIN`) khi không. Hai nhánh **loại trừ nhau**, nên cổng khoảng cách chưa từng chạy trong cấu hình thật (D-80). `bm25`/`hybrid` đi qua `HybridTextRetriever`: hợp nhất → cổng lọc → rerank, ba công tắc rời nhau. **Đã đo (D-81): cổng lọc TƯƠNG ĐỐI không mua được gì** — dưới `rrf` trung tính ±0,007 MRR, dưới `norm` nó **cắt mất đáp án thật** (R@10 1,000 → 0,890). Cổng lọc thực sự hoạt động là sàn tuyệt đối `RERANK_SCORE_MIN`.
3. Image side combines CLIP similarity + metadata search + a **lexical phrase channel** (accent-sensitive; distinguishes e.g. "trâu" vs "trầu") + rerank, gated by `IMAGE_RELEVANCE_THRESHOLD`.
4. `chain.py::BiologyRAG` builds the prompt and calls the Qwen2.5 LLM (`llm.py`), returning answer + image gallery.

### Image ETL — the complex, actively-evolving part (`src/etl/image_processor.py`, ~4000 lines)
- **Entry point is `extract_images_from_source(source, ocr_text_per_page, pages=…)`** — it takes a `PageSource` and a list of **source page numbers**, and loads each page via `_load_page_image()` (PNG → RGB array + PIL image). No poppler, no DPI: the detector now sees the native 1094×1536 pixels instead of a 150-DPI render, which is why `IMAGE_EXTRACTION_VERSION` was bumped to `v17_png_source`. **The crop geometry has not been re-QA'd on this source** — run the visual QA tool before trusting it.
- **One publisher, no variant dispatch (D-50).** `CtsstImageProcessor` (335 lines) is **deleted**; `make_image_processor(name)` always returns `KnttImageProcessor` — the only class QA'd on this corpus — and `get_pdf_variant()` is now the constant `LAYOUT_VARIANT = "kntt"`, not a filename guess (guessing was a silent fallback: any unrecognised name used to fall through to the never-QA'd base class). A second publisher means **re-measuring** captions/boxes/pills, not adding a regex keyword. `segmenter._VARIANT_PARAMS` is gone too — its three keys all pointed at the same numbers. Verified with the G4 gate before/after: **70/71 = 98.59%, 0 misassigned — identical**, same single gap (`Hình 2.3`). Comments in the base class still cite CTST pages as *evidence* for constants; those stay, because deleting them deletes the rationale.
- Detection is **anchor-first + deterministic** (find figure-caption text anchors, then crop the band above), with OWL-ViT as a secondary detector. When touching this, verify against the visual QA tool above, not just unit output.
- **M3 layout reconcile**: right after `detect_regions_anchor_first`, `extract_images_from_pdf` runs `src/etl/layout/figure_bridge.py::reconcile_with_layout` — a **drop-only** step that removes a region sitting ≥`FIGURE_IN_BOX_DROP_RATIO` (0.80) inside a segmenter colour box (sidebar/info-box false positive). It runs `segment_page` on the detector's **own 150-DPI RGB array (converted to BGR)** so bboxes share one coordinate space; it never clips/grows a figure. **Only generic/unanchored types (`panel`/`figure`) are drop-eligible** — caption/label-anchored figures (`single_figure`/`composite_figure`/`sub_figure`) are trusted and never dropped (real-page QA showed a legit coloured sub-figure was otherwise eaten when its flat background tripped the box detector), and `textbook_info_box`/`activity_box`/`tool_group` are legit boxes, also never dropped. Fail-open on segmentation error. QA overlay `04_reconciled.png` shows kept=green / dropped=red.
- **Entrypoints use `make_image_processor(filename)` per book** (`run_etl`/`run_etl_image_only`) so CTST/KNTT get their subclasses — previously the batch path used base `ImageProcessor()` for every book.
- `IMAGE_EXTRACTION_VERSION` in `.env` gates the crop cache: **bump it to force re-extraction** after changing crop logic (otherwise the per-page checkpoint skips already-processed pages). Current default `v16_layout_reconcile` (M3). A bump is honoured by `--etl` and `--image-only` alike — see the checkpoint-semantics note under Storage.

### API + app (`src/app/`)
- `dependencies.py::AppServices` is a **singleton** that loads all heavy models once (VectorDB, HybridRetriever, LLM, RAG chain). Never instantiate models per-request; go through this.
- `api.py` exposes chat (+SSE stream at `/api/chat/stream`), background ETL upload, and image-metadata CRUD for the review UI.

## Key conventions

- **Models are configured via `.env` / `src/config.py`**, not hardcoded. Defaults: `BAAI/bge-m3` (text embeddings, M2), Qwen2.5-3B-Instruct (LLM), CLIP-ViT (image), OWL-ViT (detection), Vintern-1B (captioning — **off by default**, D-47). `src/utils/download_models.py` pre-fetches them for offline runs.
- **Cross-encoder reranker** `BAAI/bge-reranker-v2-m3` (`src/rag/reranker.py::CrossEncoderReranker`/`get_reranker()`, shared singleton, GPU/CPU-safe) reranks both sides: text via `RerankedRetriever` (`src/rag/vectorstore.py`, toggle `RERANK_ENABLED`, fetch width `RERANK_FETCH_K`, absolute floor `RERANK_SCORE_MIN`) and images as an additive scoring term (`src/rag/image_vectorstore.py`, toggle `IMAGE_RERANK_ENABLED`, `IMAGE_RERANK_TOP_N`, `IMAGE_RERANK_WEIGHT`) — never a replacement for the existing image fusion.
- **Citations are deterministic, not LLM-generated**: `src/rag/citations.py` builds them from real chunk metadata (page/section, including sidebar labels) and `src/app/api.py` attaches them to chat + stream responses — the LLM never invents page numbers. `format_book_name` renders a **reader-facing** name — `SGK_KHTN_6_KNTT` → `Khoa học tự nhiên 6 (Kết nối tri thức)` — reading the publisher off the book id itself, and returns the raw stem unchanged when the name doesn't match the pattern (a wrong label sends a student to the wrong book). The label must stay a **bijection**: the G3 gate maps display labels back to `source`.
- **Windows is the primary dev environment.** OCR needs Tesseract (`vie`) via `TESSERACT_CMD`; Poppler (`POPPLER_PATH`) is only still needed by the legacy PDF paths. Prebuilt zips are in `windows_tools/`.
- **Visual QA for layout**: `python -m src.test.qa_layout --book SGK_KHTN_6_KNTT --page 10` draws the segmented regions; `--pages 10,11,12 --report` prints regions-per-page (the recall metric). `SGK_KHTN_6_KNTT/page_010.png` is the reference page — a human counts ≥4 coloured boxes on it.
- **Running the ETL on Colab — `document/colab_runtime_etl.ipynb` IS THE RUNBOOK, and the user
  confirmed on 2026-08-23 that it stays the one file they run.** 40 cells, Vietnamese, the user's
  own working notebook. **Never start a parallel runbook doc, and never let it drift**: when the ETL
  CLI, an env var, or a measured number changes, patch this notebook **in the same turn** — it is the
  4th place in the "Định nghĩa xong" checklist for anything that touches the ETL. It carries the
  mandatory `--build-manifests` step, the four path env vars, version-gate semantics, the caption-off
  rationale, and which side of the pipeline is trustworthy today. Updated to lượt 3 (2026-08-23):
  header now says 12 quyển / 2 399 trang and opens with a **⛔ blocked** banner, cell 5 points
  `RAG_DATA_DIR` at Drive and adds `RAG_FINGERPRINT_DIR`, cell 5b lists the per-publisher page counts
  and sizes, and §7 **reverses** lượt 2's "skip `--build-manifests`" into "bắt buộc" with a
  per-publisher can/cannot table.
- **Image-review JSON semantics are subtle and easy to get wrong**: `--apply-image-review` upserts per-item (removing an item from the array does NOT delete it from the DB); only `--replace-image-db` treats the file as the full source of truth. To remove a figure from retrieval, set `review_status=rejected|deleted` / `is_active=false` / `delete=true`. See README §6.
- Detailed per-variant image-ETL runbook: `skills/etl-textbook-images/runbook.md`.
