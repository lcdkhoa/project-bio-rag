# CLAUDE.md

File này hướng dẫn Claude Code (claude.ai/code) khi làm việc với code trong repo.

## RULE #0 — nguồn yêu cầu duy nhất là `document/goal.docx` (đọc trước mọi việc)

**Repo này đã đổi sang thiết kế cho ĐỒ ÁN TỐT NGHIỆP. Mọi yêu cầu đều nằm ở
`D:\personal_repo\project_rag\document\goal.docx` — hãy đọc và phân tích lại.**

`goal.docx` là **Đề cương chi tiết đã có chữ ký CBHD (ThS. Nguyễn Hữu Quyền), ngày
13/07/2026**. Nó thắng mọi tài liệu khác trong repo khi có mâu thuẫn:

- `report/main_chuyende_totnghiep.pdf` là **báo cáo CHUYÊN ĐỀ cũ (06/2026) — ĐÃ LỖI
  THỜI**. Chỉ dùng làm tư liệu lịch sử; không được lấy mục tiêu, phạm vi hay số liệu
  của nó làm chuẩn nghiệm thu nữa.
- **`report/tex_source/` là SOURCE CỦA CHÍNH BÁO CÁO CŨ ĐÓ, nên nó chỉ là KHUNG CẤU
  TRÚC** (D-129, người dùng chốt 2026-08-26). Dùng nó để tham vấn **bố cục chương mục**;
  mọi **số liệu và phương pháp** phải lấy từ `goal.docx` + phép đo thật của repo hôm nay.
  Đừng vá từng chỗ lint bắt được rồi mặc nhiên coi phần còn lại là đúng — **mọi chương**
  phải rà lại theo thực tế.
- Mọi spec trong `document/specs/` viết trước 2026-08-22 đều được soạn theo phạm vi
  cũ (4 quyển KNTT, trọng tâm Sinh học). Phần **đo lường** trong đó vẫn còn giá trị;
  phần **mục tiêu / tiêu chí nghiệm thu** thì không.
- Khi một dòng trong chính CLAUDE.md này mâu thuẫn với `goal.docx`, `goal.docx` đúng
  và dòng đó phải được sửa ngay trong cùng lượt phát hiện.

Tóm tắt yêu cầu chốt (chi tiết đọc thẳng file, đừng nhớ qua bản tóm này):

| # | Yêu cầu trong đề cương | Trạng thái trong code |
|---|---|---|
| MT1 | Truy vấn đa định dạng: văn bản + **công thức** + hình/sơ đồ/biểu đồ | **XONG — ETL THẬT ĐÃ CHẠY, ĐO XÁC NHẬN** (D-162). Lượt Colab 8: 4293/16515 chunk merge MinerU thành công (`applied`+`unmatched_count`), 0 lỗi gọi model, đủ 12/12 quyển, BM25 dựng lại khớp. `recall_at_k`/`evaluator.py`/`ablation.py` đã đo lại trên corpus mới (D-167/D-170, 2026-09-02, cả 3 đều xong) — còn nợ: đo lại 2 quyển vừa đổi số câu (240 đều 20/quyển, D-172) và cập nhật `report/tex_source/` |
| MT2 | Kho vector phủ **toàn bộ KHTN Lý–Hoá–Sinh, 12 quyển / 3 bộ sách, ~2 319 trang** | **XONG**: 2 387/2 399 trang lập chỉ mục, 16 393 chunk + 3 881 vector hình |
| MT3 | Tối ưu truy xuất: định tuyến ý định + **truy xuất lai BM25 + dense** + rerank + cổng lọc | **XONG**. Mặc định `hybrid` + rerank BẬT + cổng lọc TẮT (D-82). Đo trên 231 câu ở bề rộng production: MRR **0,8255** · R@1 0,7403 · R@10 **0,9697**, thắng bm25 và dense ở MỌI cột. **Khoảng cách recall của đề cương đã bị xoá** — prod 0,9091 > 0,8961 là trần của riêng kênh dense (D-132) |
| MT4 | Khung đánh giá đối chiếu: (i) **hybrid vs BM25 thuần**, (ii) **multi-modal vs text-only**, (iii) ablation bật/tắt rerank + gate | (i)+(iii) **XONG** trên bộ 231 câu/12 quyển (D-127); (ii) **CHƯA KẾT LUẬN ĐƯỢC** — 100 câu/4 quyển KNTT (D-87) cho delta +0,010 nhưng trần bộ test chỉ 0,104, nên phải nói "chưa đo được ưu thế", KHÔNG phải "vô ích" |
| MT5 | Web UI (Next.js) hiển thị công thức Toán/Hoá + hình sắc nét | **XONG** (D-137..D-139) — xem dòng MT5 ở bảng tiến độ |

Mốc thời gian trong đề cương: 15/07/2026 → 23/09/2026, năm giai đoạn. Giai đoạn 1
(số hoá đủ 12 quyển) đáo hạn **29/07/2026**; Giai đoạn 3 (thực nghiệm đối chiếu
BM25/Hybrid và Text-only/Multi-modal) chạy **14/08 → 28/08/2026**. Khi báo cáo tiến
độ, nói theo mốc này, không nói theo cảm tính.

**Hệ quả trực tiếp phải nhớ:** phạm vi đã **mở lại** thành 3 nhà xuất bản, nên nguyên
tắc 7 ("xoá code mạnh tay khi phạm vi hẹp lại") **đã bị đảo chiều** cho phần xử lý
theo nhà xuất bản — xem mục "Repo này là gì".

## Repo này là gì

Một hệ thống **RAG tiếng Việt trên trang SGK KHTN THCS chỉ có ảnh** (không có lớp
text). Pipeline OCR chữ tiếng Việt + crop hình, rồi phục vụ truy xuất lai văn bản +
hình bằng Qwen2.5 chạy local, trả lời tiếng Việt kèm trích dẫn.

**Phạm vi theo `goal.docx` (RULE #0): toàn bộ môn KHTN — Lý, Hoá VÀ Sinh — trên 12
quyển / 3 nhà xuất bản (KNTT, CTST, Cánh Diều), ~2 319 trang.** (2 319 là số ước của
`goal.docx`; số **đo được** trên đĩa là **2 399** — D-65. Khi hai số khác nhau: đĩa
thắng cho kỹ thuật, đề cương thắng cho câu chữ về phạm vi trong báo cáo.) Khung "trọng
tâm Sinh học" của báo cáo chuyên đề cũ đã hết hiệu lực: một câu hỏi Lý hoặc Hoá nay
**nằm trong phạm vi theo hợp đồng**, không phải ngoài lề. Công thức Hoá/Lý (`O₂`,
`H₂SO₄`, `A = Fs`) là **hạng mục có tên trong đề cương** ("bổ sung bước xử lý đặc thù
cho công thức Hoá, Lý"), nên D-56/D-63 từ nợ kỹ thuật trở thành việc có hợp đồng.

**Corpus trên đĩa (đo lại 2026-08-23, D-65): 12 quyển / 3 NXB / 2 399 trang.**
`database/` đã bị xoá — không có gì để resume, cả ETL là một lượt chạy mới.

```
datasources/SGK_KHTN_{6,7,8,9}_{KNTT,CTST,CD}/page_NNN.png    12 thư mục, 0 khoảng trống
CD   179 + 171 + 207 + 215 = 772 | CTST 204 + 188 + 223 + 215 = 830
KNTT 195 + 179 + 196 + 227 = 797                        tổng 2 399
```

Ba sự thật đo được, lật lại thiết kế cũ — bảng đầy đủ trong
`document/specs/2026-08-22-12books-3publishers-etl-rebuild.md`:

1. **KNTT là bộ ẢNH ĐỘ PHÂN GIẢI THẤP NHẤT, không phải bộ chuẩn.** KNTT 1094×1536
   so với CTST/CD **2280×3201** (6_CD là 2480×3480) — ~2,1× mỗi cạnh, ~3,5× diện
   tích. Mọi kết luận OCR trong file này (CER 0,0048, "upscale không đổi gì", và
   **D-56 mất chỉ số dưới**) chỉ đo *trên KNTT ở 1094×1536*. Việc `O₂`/`H₂SO₄` có
   sống sót ở độ phân giải CD/CTST hay không **đã được đo (D-73): KHÔNG** — chỉ số
   dưới không sống ở bất kỳ NXB nào, xem bảng tiến độ.
2. **CHỐT (D-65): mọi quyển bắt đầu từ `page_001` và `printed_page == filenum`
   (offset 0) trên cả 12.** Đo bằng `src/etl/book/fingerprint.py` trên 40 trang/quyển:
   offset **0** ở 12/12, tỉ lệ khớp **39/40** ở mười một quyển và **38/40** ở 9_CD.
   Vị trí số trang vẫn là **theo từng quyển** (đo được `x ≈ 0,104/0,894` CD,
   `0,112/0,889` CTST, `0,074/0,928` KNTT) — đừng bao giờ giả định một vùng, phải đo,
   gắn cờ, không đoán (nguyên tắc 5).
3. **Mọi thứ suy ra từ corpus cũ đều vô hiệu:** `database/` đã xoá, mọi
   `database/manifests/*` cũ, bộ test 100 câu/4 quyển cũ, gold set G2 24 trang cũ
   (số trang đã đổi), và mọi số G1/G3/G4/G5 đo trên corpus cũ.

**Xử lý theo từng nhà xuất bản nay là bắt buộc** (RULE #0 đảo ngược D-50):
`LAYOUT_VARIANT = "kntt"` cứng và `make_image_processor()` luôn-KNTT phải bỏ. **Không**
khôi phục `CtsstImageProcessor` cũ (`git show 75b8377^:src/etl/image_processor.py`) —
nó viết cho bản PDF render 150-DPI cũ, chưa từng QA trên nguồn pixel này. Mỗi quyển
khai báo một **fingerprint layout đã đo** (M0); quyển nào chưa có thì ETL phải raise,
không được mượn tham số của quyển khác.

### M0 fingerprint layout — ĐÃ ĐO theo từng NXB (2026-08-23, D-65)

Artefact: `database/fingerprints/{book}.json`, đủ 12/12 quyển. Báo cáo đầy đủ:
`document/specs/2026-08-23-m0-report.md`. **Ba bảng dưới đây lật lại giả định vẫn
đang nằm cứng trong `toc.py`, `pill.py` và `config.py`.**

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
   kênh pill nhưng 30–65 nhãn từ OCR thường. Nên **D-45/D-51** (psm và kernel CLOSE của
   pill) và **D-40** (ba nhãn ô so sánh chưa đọc được) chỉ áp cho 4 quyển KNTT, không
   phải 12 — và 8/12 quyển có anchor *dễ hơn* KNTT.
2. **`LAYOUT_BOX_MIN_SATURATION = 45` cao hơn thực tế của MỌI quyển** — nó nằm trên
   p50 của 11/12 quyển (chỉ 6_KNTT đạt 51). Ngưỡng hộp màu **đã được làm per-book**
   (D-145 Task 7, sửa lại ở D-146): `segmenter._params_for(variant, book)` tra
   `sat_percentiles.p10` của chính fingerprint quyển đó, sàn an toàn `MIN_SAT_FLOOR =
   9` (đúng bằng p10 thấp nhất đo được, 6_CD) chỉ chặn trường hợp suy biến chứ không
   còn đè lên số đo như bản D-145 ban đầu (bản đó dùng sàn 20 — cao hơn p10 thật của
   11/12 quyển, D-146 đã sửa). Đo đủ 12/12 quyển trên dải sàn 9-15 (D-150): 10/12
   quyển không đổi số hộp; `6_CD` tăng 21→23 (đúng hướng), `7_CD` giảm 11→9 (có thể
   là hộp bị nối, CHƯA xem bằng mắt để xác nhận). Xem bảng tiến độ, dòng `min_sat`.
3. **Chạy bộ đọc MỤC LỤC một cột lên bố cục hai cột sinh ra số SAI MÀ TRÔNG HỢP LÝ.**
   Đo trên 7_CTST: `Bài 1 → trang 144` (thật là trang 6), rồi ràng buộc đơn điệu giết
   31 Bài còn lại. Luật "bỏ entry chứ không đoán" chặn 31 số sai nhưng **không chặn số
   sai đầu tiên**. Bộ đọc cell nay chỉ chạy khi `entry_style == "bai"`, và spine không
   liền mạch bị gắn cờ `KHONG_dang_tin`.

Ngưỡng px của `toc.py` và `pill.py` nay tỉ lệ theo chiều rộng trang
(`toc.geom_for_width(w)`, `pill.bounds_for_width(w)`, tham chiếu 1094 px) — ở đúng
1094 px chúng trả lại y nguyên bộ số cũ, có test chốt. **`text_extract.
SINGLE_LINE_MAX_H = 60` px (chọn psm 7 vs psm 6) đã được làm per-book** (D-145 Task 8,
`single_line_max_h_for_book(book)`), nhưng phép đo trên cả 12 quyển đều cho **n < 5
mẫu dòng đơn cô lập** nên KHÔNG quyển nào ghi được giá trị riêng vào fingerprint —
mọi quyển (kể cả CD, dòng cao ~136 px) vẫn chạy với **60px mặc định y hệt trước khi
có D-145**. Nghĩa là cơ chế đã nối dây nhưng **hành vi thực tế chưa đổi cho quyển
nào** — đây vẫn là một câu hỏi mở, không phải đã đóng; xem bảng tiến độ.

Triết lý, bảng "Kế hoạch tới" và "Trạng thái tiến độ" bên dưới là nơi cập nhật liên
tục — phần trên chỉ là bối cảnh corpus, không cần đọc lại mỗi lượt.

## Triết lý — tư tưởng của repo (đọc trước khi viết bất kỳ dòng code nào)

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
   trên trang thật, không chỉ unit test trên fixture tổng hợp. **Kể cả số đo trong
   chính decision log/CLAUDE.md cũng phải bị nghi ngờ và đối chiếu lại với artefact
   thật** (D-146: một con số p10 bịa đã nằm trong log một lượt trước khi bị bắt).
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

## Redesign đang chạy (2026-08) — đọc trước

Một đợt viết lại ETL theo layout + rerank truy xuất đang **chạy dở** (chạy theo
deadline). Nguồn sự thật:

- **Quyết định:** `document/decision_log.html` (log `DECISIONS[]`, hiện **D-01…D-161**).
  **Nó từng hỏng âm thầm một lần (D-136)** — một chuỗi `notes` xuống dòng vật lý giữa
  chừng là lỗi cú pháp JS, nên trang render ra **trống trơn** cả một ngày dù file vẫn
  trông ổn trong editor. `tests/test_decision_log.py` nay lex mọi chuỗi giống hệt JS;
  chạy nó sau khi sửa file này.
- **MT1 XONG (cập nhật 2026-09-01, D-162) — lượt Colab 8 chạy thật, đo xác nhận
  trên `database/` local, không chỉ tin log.** Ba lượt trước (5,6,7) đều báo
  "xong" (exit code 0) mà vẫn hỏng — chuỗi bug: D-154/D-155 (gate `CO_DAU_BANG`
  khớp xuyên dòng, đã sửa regex), D-157 (checkpoint khôi phục kéo về bản CŨ có
  bug, version-gate coi 63,9% trang cũ là "đã xong" nên không OCR lại), D-158
  (root cause cuối: `download_models.py --profile text-etl` chưa từng tải model
  MinerU + notebook chưa trỏ `FORMULA_MINERU_MODEL` local → 100% lượt gọi MinerU
  thất bại dưới `HF_HUB_OFFLINE=1` — đã sửa cả hai trong `master`), D-159 (viết
  lại sạch notebook, bump `TEXT_EXTRACTION_VERSION` → `v4_formula_hybrid_fix`,
  `scripts/reset_text_all_books.py --all` resume-safe), D-160 (% tiến độ sống),
  D-161 (`_copy_resilient()` chịu Drive-FUSE rớt kết nối). **D-162: người dùng
  chạy Run all, đo lại độc lập trên `database/` local tải về** — `processing_
  status` 2399/2399 trang đúng version mới (cả text lẫn ảnh); `biology_images`
  3881 doc, không mất; `biology_text` 16515 chunk, `formula_hybrid_status`:
  `applied` 1063 + `unmatched_count` 3230 = **4293 lần merge MinerU thành công**
  (so với 0/16513 ở D-157/D-158), `mineru_call_failed*` = 0,
  `gate_hit_no_line_located` = 1; BM25 (`database/sparse/`) 16515 id khớp đúng
  `biology_text`. Khớp chính xác với output cell mục 11 của notebook — không
  phải checkpoint cũ lẫn vào. Đã xoá `document/colab_runtime_etl_done.ipynb`
  (bản tải về, hết giá trị). **D-167 (2026-09-02): đã đo lại `recall_at_k`/
  `evaluator.py` trên corpus mới** (238 câu, Groq giám khảo D-163) — xem dòng
  "Đánh giá đầu-cuối" trong bảng này cho số. Việc tiếp theo (ngoài ETL, xem
  `document/specs/2026-08-26-bao-cao-viet-lai-report.md` §8): `bai_so` cho 8
  quyển CD/CTST (không cần chạy lại ETL) → bộ câu hỏi sinh từ HÌNH có người đối
  chiếu ảnh (điều kiện tiên quyết cho vế (ii) của MT4 — trần 0,104 đang chặn);
  chạy lại `ablation.py --build-cache` (fail lượt đầu, đã vá notebook); điều
  tra lệch 231 (văn bản báo cáo) vs 238 (đo được) câu; rồi mới cập nhật báo
  cáo (`report/tex_source/` hiện build trên số liệu TRƯỚC lượt hybrid).
  Xem D-154..D-167.
- **Spec cũ, chỉ đọc như tư liệu (đã hoàn thành hoặc bị corpus sau đè lên):**
  `document/specs/2026-08-24-m2-bm25-hybrid-prompt.md` (M2: BM25 + hợp nhất, D-74..D-82),
  `2026-08-23-m0-toc-and-layout-prompt.md` + `2026-08-23-m0-report.md` (M0/M1),
  `2026-08-22-12books-3publishers-etl-rebuild.md` (thiết kế nền 12 quyển),
  `2026-08-21-png-source-etl-report.md` (migration sang nguồn PNG, mọi số đã đo).
  **Stale, chỉ đọc như tư liệu:** `2026-08-21-eval-numbers-to-report-prompt.md` và
  `2026-08-21-pending-to-report-prompt.md` — viết cho corpus 4 quyển KNTT cũ đã bị
  `database/` xoá; giữ lại vì hai cái bẫy trong đó còn nguyên giá trị: image doc mồ
  côi (D-52) và rerank tắt âm thầm khi `RERANK_MODEL` là HF id dưới `HF_HUB_OFFLINE=1`.

Vẫn giữ nguyên từ thiết kế trước: dựng lại sạch `database/`; segmenter layout bằng CV
cổ điển; embedding text → `BAAI/bge-m3`; cross-encoder `BAAI/bge-reranker-v2-m3`;
sidebar/info-box là chunk riêng có nhãn; checkpoint khoá theo **content hash**, không
theo tên file. (Đã bỏ: "sửa dấu tiếng Việt tự động sau OCR" — đo được là vô dụng và
còn ghi đè text gốc, xem D-34.)

**Tóm tắt các mốc DONE/OPEN quan trọng nhất còn chưa nằm trong bảng "Trạng thái tiến
độ" bên dưới** (đo trên corpus PNG 2026-08-21, D-33…D-39, chi tiết đầy đủ ở
`document/specs/2026-08-21-png-source-etl-report.md`):

- **Danh tính trang không đoán:** `BookManifest` là nguồn sự thật duy nhất cho số
  trang in; `LayoutOCRLoader` **raise** nếu thiếu, không có fallback `index+1`.
- **Không tiền xử lý ảnh:** `preprocess_page` đã xoá hẳn — Otsu/binarize đo được là
  *hại* (conf 93,4 → 92,0); không có "vệt mực" nào ở lề trái 6% để xoá.
  `region OCR` luôn nói rõ psm đang dùng (`--psm 6`, hoặc `7` cho crop dưới 60px).
- **`segment_page` đã dựng lại, recall 2,17 → 4,10 vùng/trang** (cùng mẫu 40
  trang/4 quyển) nhờ tách "flatness" đo trên pixel của chính vùng thay vì trên bbox,
  và close-kernel nhỏ thay vì một mask dán chết mọi hộp lại với nhau.
- **Checkpoint khoá theo hash TỪNG TRANG + `TEXT_EXTRACTION_VERSION`**; đổi version
  ép re-OCR toàn bộ, chunk cũ của trang bị xoá trước khi ghi chunk mới (không rác).
- **Sửa tự động không bao giờ ghi đè text** — `diacritic.py` chỉ gắn cờ
  `needs_review`/`review_tokens`, không tự đoán lại một âm tiết.
- **OPEN — bảng mất cấu trúc hàng/cột, có thể trả lời SAI CỘT (D-63).** Đo trên
  `Bảng 12.1` (quyển 6, tr.44): cột "công dụng" và "tính chất" bị trộn vào nhau khi
  OCR tuần tự theo dòng; `Bảng 35.1` (quyển 9, tr.154) mất cả hàng tiêu đề năm và
  8/8 dấu phẩy thập phân (`26,2`→`262`, sai 10×). Một chunk hiện không giữ quan hệ
  hàng/cột nào — khác lớp lỗi với chỉ số dưới công thức, cần hướng sửa riêng, **chưa
  làm**.
- **Nhãn hình chữ trắng trên nền màu (`pill.py`):** crop → đảo màu → OCR `--psm 7` →
  chỉ nhận khớp `Hình N.M`. Không phải vấn đề độ phân giải (đọc được ở mọi scale) mà
  là polarity + binarize cục bộ của Tesseract. **Còn chưa đọc được:** pill lồng trong
  ô cùng họ màu (D-40, ví dụ `page_010`: pill sat 82 trên nền sat 157).
- **G3 (`qa_citation_page.py`) đo trang được trích dẫn có thực sự chứa câu trả lời
  không** — IDF-weighted token coverage, ngưỡng `COVERAGE_MIN=0,50` hiệu chỉnh bằng
  số trên judge LLM (D-49, D-57). G1 (spine Bài liền mạch) PASS 195/195 trên 4 quyển
  KNTT cũ (D-43); G2 (gold set OCR) nửa chừng, đang đề xuất thu hẹp thành gold set
  công thức (xem cuối bảng tiến độ).
- **`IMAGE_CAPTION_ENABLED=false` mặc định (D-47), đã đo rồi mới tắt, không phải tắt
  theo cảm tính:** InternVL trên 12 crop thật — bịa 4/12 (móc treo thành "bác sĩ phẫu
  thuật tai"), và khi tự nêu số hình thì SAI 4/4 lần trên chính thứ `pill.py` đã đọc
  đúng. Không dùng làm caption cho tới khi có phép đo mới trên đúng 12 crop đó.
- **Progress logging có ETA thật** (`src/utils/progress.py`), không dùng `tqdm` (bar
  không timestamp bị log dòng khác xé nát). Tốc độ đo được trên máy dev (16 core,
  không GPU): text OCR ~3,56 s/trang, ảnh ~8,86 s/trang — coi log thật hơn ước tính
  này (D-53).
- **`EMBEDDING_MODEL=BAAI/bge-m3`** trong `.env`, khớp Colab notebook; đổi model là
  đổi chiều vector, phải build lại toàn bộ index.

## Kế hoạch tới (chốt 2026-08-23) — và CHÍNH XÁC khi nào chạy lại ETL toàn bộ

Thứ tự này không đổi được, vì mỗi bước là **đầu vào bắt buộc** của bước sau, không
phải sở thích tổ chức công việc.

| # | Việc | Đầu ra nghiệm thu | Chặn ai |
|---|---|---|---|
| **M1** | Bộ đọc MỤC LỤC cho CTST (hai cột) + CD (`style = so_thu_tu`, MỤC LỤC ở cuối sách); hợp nhất `toc._BAI` (đang phân biệt hoa/thường) với `fp_toc.ROW_PATTERNS` (đã `IGNORECASE`); cho `toc.py` đọc `entry_style`/`toc_pages` từ fingerprint thay vì hằng số | `--build-manifests` chạy hết **12/12 quyển**, G1 PASS, spine Bài liền mạch từng quyển, manifest được **commit** | **mọi thứ** — đường text `raise ManifestMissing` khi thiếu manifest |
| ~~**M1.5**~~ | **XONG 2026-08-23 (D-73)** | chỉ số dưới **không sống ở đâu cả** (CD 256:3, CTST 377:3, KNTT 408:4) → một luật chung; `s/trang` thật = **5,0** end-to-end, manifest 1,79 s/trang | — |
| ~~**M2**~~ | **XONG** — BM25 (D-77..D-79), `min_sat` per-book (D-145 Task 7, sửa D-146), `single_line_max_h` per-book đã nối dây nhưng chưa có quyển nào đủ mẫu để ghi giá trị riêng (D-145 Task 8, xem mục M0 phía trên) | index text đủ 12 quyển + BM25 song song | MT3, và mọi phép đo eval |
| **M3** | Hình ảnh theo từng NXB. Gỡ `LAYOUT_VARIANT` **XONG** (D-111). Kênh pill đọc **0** ở 8/12 quyển nhưng **kênh anchor chữ đen đọc tốt** nên không phải viết bộ đọc mới (D-110) | G4 theo từng NXB — **chạy được ngay**, xem dòng dưới | MT1 phần hình, MT4 multi-modal |
| **M4** | Bộ test 12 quyển có nhãn `phan_mon`/`khoi`/`bo_sach`/`do_kho`, phân bố đều | testset mới + gold key khớp index | MT4 |
| ~~**M5**~~ | **XONG 2026-08-25** phần đối chiếu: BM25/dense/hybrid × rerank × cổng lọc trên 300 câu/12 quyển (D-82); text-only vs multi-modal trên 100 câu/4 quyển KNTT (D-87) | hai bảng: `src/test/ablation_report_12books.csv` và `src/test/ablation_mm_report.csv` | báo cáo — **còn nợ**: bộ câu hỏi sinh từ HÌNH (trần bộ test hiện tại chỉ 0,104) và chất lượng câu trả lời có LLM chấm |

**Khi nào chạy lại ETL toàn bộ — ba mốc, không phải một.** Đừng chạy 2 399 trang
trước khi qua mốc trước đó, vì mỗi lần chạy lại tốn nhiều giờ:

1. **Lượt xác minh 4 quyển KNTT (đã chạy).** Mục đích không phải dựng DB cuối cùng,
   mà xác minh đường ống còn chạy và có `s/trang` thật để so.
2. **Lượt text toàn bộ 12 quyển với hybrid công thức: ĐÃ CHẠY (2026-09-01, D-162).**
   `TEXT_EXTRACTION_VERSION=v4_formula_hybrid_fix`, 2399/2399 trang, 4293/16515 chunk
   merge MinerU thành công (`applied`+`unmatched_count`), 0 lỗi gọi model. Đừng bump
   version thêm lần nữa trước khi có lý do đo được, kẻo tốn thêm một lượt OCR đầy đủ.
3. **Lượt ảnh: 4 quyển KNTT ĐÃ CHẠY (2026-08-25, D-87) — 2 h 24, 938 doc, G4 gán
   sai 0 / thiếu 0. 8 quyển CD/CTST ĐÃ CHẠY** (xem bảng tiến độ, dòng "Kho ảnh 12/12
   quyển").

**Một lần chạy lại rẻ hơn ba lần:** cả hai `*_EXTRACTION_VERSION` nên bump **một
lần** khi các tham số đã chốt xong, không bump mỗi lần sửa một tham số.

## Trạng thái tiến độ (quét lại 2026-08-28, đối chiếu code + log + memory)

Mốc đề cương: GĐ1 số hoá 12 quyển đáo hạn **29/07/2026**; GĐ3 thực nghiệm đối chiếu
**14/08 → 28/08/2026**. Bảng này là **trạng thái đã kiểm chứng trên code hôm nay**, không
phải kế hoạch — mỗi dòng nói rõ bằng chứng.

| Việc | Trạng thái | Bằng chứng / chỗ chặn |
|---|---|---|
| Corpus 12 quyển trên đĩa | **XONG**, và **cố ý không nằm trong git** | 12 folder, 2 399 trang, 0 khoảng trống (D-65); 4,1 GB nên `.gitignore` bỏ qua `datasources/*` (D-68) — chạy bằng `RAG_DATA_DIR` trỏ sang Drive, xem `datasources/README.md` |
| M0 fingerprint 12/12 | **XONG** | `database/fingerprints/*.json` đủ 12 file, 5 khoá mỗi file |
| Test suite | **XANH** | `pytest tests/ -q` → **769 pass, 3 skip** (2026-08-31 sau D-155; các con số **761**, **686**, **488**, **584**, **617**, **732** ghi ở đây trước đó đã cũ) |
| Commit công việc M0 | **XONG, đã cũ** (dòng "CHƯA" trước đây là stale, sửa 2026-08-28) | `fingerprint.py`/`fp_*.py`/12 JSON fingerprint/`goal.docx` đã commit từ D-65/D-69; `git status` hôm nay **0 file untracked**, `master` đã push hết (xem dòng dưới) |
| M1 manifest 12 quyển | **GỠ CHẶN, G1 PASS cả 12/12 quyển** — dòng "G1 FAIL cho 8 quyển" ghi ở đây từ trước là SAI, sửa 2026-08-28 sau khi chạy thật | `book/toc_lines.py` (D-70, sửa D-149): `read_toc` chọn bộ đọc theo fingerprint, nên `--build-manifests` **chạy được cả 12 quyển** (đo: 1,27–1,46 s/trang → ~50 phút). Chạy thật `--build-manifests --book SGK_KHTN_7_CTST` (2026-08-28): báo cáo in rõ `PASS` — **G1 chỉ đo danh tính trang (số trang in), không đo spine Bài** (`manifest.py:216-217`: cờ `bai_numbers_not_contiguous` "KHÔNG chặn G1"). Spine Bài của 8 quyển CTST/CD **vẫn chưa liền mạch** sau khi vá một bug index lệch (D-149) — CTST đọc thêm được 4 mục (**23/17/17/21 → 25/17/17/23**), CD **không đổi** (32/24/23/29, bug không áp dụng cho CD) → `bai_so` **không** đi vào metadata chunk cho 8 quyển đó (đúng thiết kế: thiếu thì im, không đoán) — đây mới là thứ bị chặn, không phải G1. Cờ trội còn lại: `toc_page_reader_conflict` (hai bộ đọc bất đồng, có ca cả hai đều SAI — vd Bài 20 của 8_CTST thật là trang 90 nhưng hai bộ đọc ra `[3,93]`, không khớp cái nào) — **cố ý KHÔNG dùng heuristic "chọn số hợp lý theo thứ tự tăng dần"** vì nó có thể chọn đúng số sai (93 cũng monotonic-hợp-lý), đúng loại lỗi module này sinh ra để tránh |
| Tỉ lệ đọc số trang ở đường manifest | **CHƯA**, và nguyên nhân KHÔNG phải scale | Đo 30 trang/quyển với `(1,3)` / `(1,2,3)` / `(2,)` → **cùng một con số**: 6_CD **40%**, 9_CD 87%, 6_CTST 87%, 6_KNTT **100%**. Giả thuyết "thiếu scale 2×" **bị bác bỏ** (D-72). Khác biệt thật: fingerprint đọc trong **dải zone đo được của chính quyển** (`zone_read.band_even`), còn `page_number_ocr` dùng hằng số góc của KNTT. Hệ quả hiện tại: 6_CD có `ocr_confirmed` **37,1%**, 112 trang lấy `printed_page` suy từ offset đã đo, mỗi trang một cờ `page_number_not_read` → G1 FAIL đúng như phải fail |
| Manifest cho quyển có đồng thuận offset yếu | **XONG** | `build_manifest` đối chứng với offset đã đo ở fingerprint: trùng → đi tiếp + gắn cờ, khác → vẫn raise, không có fingerprint → vẫn raise. `MIN_OFFSET_RATIO = 0.8` **không** bị nới (D-72). Chạy thật: `KHTN6-CD.json` 179 trang / offset 0 / 32 Bài, 1,79 s/trang |
| `book_id` theo nhà xuất bản | **XONG** | `book_id_from_source_name` từng nối cứng `-KNTT` nên `SGK_KHTN_6_CTST` ra `KHTN6-KNTT` và **ghi đè manifest của 6_CD** — ba NXB cùng lớp dùng chung một file, im lặng hoàn toàn. Bắt được bằng cách **mở artefact đầu tiên ra đối chiếu** (`n_pages: 204` không thể là của quyển 195 trang), không bằng test: 158 test vẫn xanh khi bug còn sống (D-71) |
| Fingerprint được code sản xuất ĐỌC | **GẦN NHƯ HẾT** | Đường MỤC LỤC/manifest **có đọc**: `book/toc.py:418 load_fingerprint`, `toc.py:488` (chọn `toc_pages` + `entry_style`), `toc_lines.py:394`, `manifest.py:77 _fingerprint_offset`. `min_sat` per-book **ĐÃ NỐI** (D-145 Task 7, sàn sửa lại D-146: `MIN_SAT_FLOOR = 9`, `segmenter._params_for(variant, book)`). `single_line_max_h` per-book **đã nối dây nhưng chưa đổi hành vi cho quyển nào** (D-145 Task 8 — n<5 mẫu ở cả 12 quyển nên mọi quyển vẫn dùng 60px mặc định). Phần duy nhất còn nợ hoàn toàn: vùng số trang của `page_number_ocr` |
| ETL text bằng MODEL đọc cả trang (bake-off OCR) | **XONG, GIỮ TESSERACT** (D-91..D-108) | Bake-off đo trên gold set **97 ô / 15 trang / cả 3 NXB**: baseline Tesseract `CT=0,048 · DẤU=0,016 · BẢNG=0,000`. `nanonets_ocr2_3b` loại vì lý do MÔI TRƯỜNG (transformers 5.x nạp hỏng lm_head, sinh token rác — D-101/D-102, KHÔNG phải đọc kém tiếng Việt). `mineru25` (`opendatalab/MinerU2.5-Pro-2605-1.2B`) đọc được và giữ chỉ số dưới: `CT=0,441` (gấp 9,2× Tesseract) nhưng `DẤU=0,037 > 0,016` → **LOẠI theo luật chốt §3.2, giữ Tesseract, không OCR lại 12 quyển** (D-108). Hướng mở đã CHỌN: dùng MinerU **chỉ cho vùng công thức**, giữ Tesseract cho văn xuôi — xem dòng "Xử lý công thức Hoá/Lý" |
| `--book` lọc được cả ba đường ETL | **XONG** (D-84) | trước đó `--book` chỉ nối vào `--build-manifests`, nên `--image-only --book X` **im lặng bỏ qua cờ** và sẽ chạy cả 12 quyển ≈ 6 giờ (8 quyển biết trước là sai). Tên quyển không khớp nay **thoát mã 2** kèm danh sách 12 quyển thật — thử trên CLI thật: `--book SGK_KHTN_6_KNT` → exit 2. 7 test |
| Gỡ `LAYOUT_VARIANT = "kntt"` | **XONG** (D-111) — nhưng **dữ liệu cũ vẫn mang nhãn sai** | Hằng số đã **xoá**; `get_pdf_variant()` đọc hậu tố tên quyển (`KNTT`/`CTST`/`CD`, phải ở CUỐI) và **ném `UnknownPublisher`** khi không khớp — không có mặc định. Chạy thật: 12/12 quyển ra đúng biến thể. Bảng lớp là số đo D-110: `cd`+`ctst` → lớp **cơ sở**, `kntt` → `KnttImageProcessor`. ▸ **Còn nợ:** 11 459 chunk CD/CTST đã dựng vẫn mang `variant='kntt'` (D-109) cho tới lượt bump `TEXT_EXTRACTION_VERSION` (đã bump — xong ở lượt Colab tới). ▸ **Đổi hành vi có chủ ý:** upload PDF tên lạ qua `/api/etl` nay ném thay vì xử lý như KNTT |
| Phép đo chỉ số dưới ở CD/CTST | **XONG, và nó BÁC BỎ giả thuyết — củng cố thêm bằng gold set người duyệt** (D-73, D-147) | Trên index: hỏng:đúng = **CD 256:3, CTST 377:3, KNTT 408:4**, `₂` Unicode **0 lần ở cả ba** (D-73). Trên gold set 97 ô/15 trang đã người duyệt, cắt lát theo NXB (`ocr_bakeoff --compare --theo-nxb`, D-147): **KNTT CT=0,104 · CTST CT=0,031 · CD CT=0,000** — CD là NXB TỆ NHẤT (Tesseract đọc sai 100% token công thức), KNTT (độ phân giải THẤP NHẤT) lại cao nhất → bác bỏ luôn giả thuyết "độ phân giải cao hơn cứu được chỉ số dưới". Bước xử lý công thức Hoá/Lý vẫn là **một luật chung**, không chia theo NXB |
| BM25 (MT3) | **XONG** (D-77, D-78, D-79) | `python main.py --build-bm25` -> `database/sparse/`: **16 393 chunk / 19 727 từ vựng / 5,5 s**, khoá là chính `chunk_id` của `biology_text`. Tự cài Okapi BM25 (`src/rag/bm25.py`) thay vì `rank_bm25`, vì `k1`/`b` phải là tham số lúc TRUY VẤN thì quét 5×5 mới rẻ. Dấu vân 6 trường -> chỉ mục cũ hơn index thì `SparseIndexStale`, không có fallback. **Đã quét bằng số:** `k1=0.7, b=0.75`, `BM25_TOKENIZER=plain` — GIỮ dấu thắng BỎ dấu (MRR 0,820 vs 0,755), **lật giả định ban đầu**. Chuẩn hoá công thức (`CO2` ↔ `CO,`) chỉ ở phía truy vấn/chỉ mục thưa, **không sửa một ký tự nào** trong `biology_text`: đo trên 12 công thức, chunk đúng ở top-10 đi từ **6 lên 97**, số truy vấn tìm được từ **1/12 lên 11/12** |
| Hợp nhất thưa+dày (MT3) | **XONG** (D-80) | `src/rag/hybrid_text_retriever.py` (đừng nhầm với `hybrid_retriever.py` = lai text+ảnh). Thứ tự **hợp nhất -> cổng lọc -> rerank**; `RETRIEVAL_MODE` ∈ {dense, bm25, hybrid} × `RERANK_ENABLED` × `RELEVANCE_GATE_ENABLED` = **12 cấu hình**. Phát hiện: trước M2 cổng lọc và rerank **loại trừ nhau** (`RERANK_ENABLED=true` khiến `RelevanceGatedRetriever` không bao giờ chạy -> `RETRIEVER_DISTANCE_MARGIN` là **số chết**). **Mặc định nay là `hybrid`, cổng lọc TẮT** (D-82), chốt bằng bảng **300 câu / 12 quyển** ở ĐÚNG bề rộng production (20 ứng viên/kênh): hybrid R@1 0,717 · R@3 0,887 · R@10 **0,977** · MRR **0,808**, thắng bm25 (0,796) và dense (0,794) ở mọi cột |
| Vá crop dải hẹp (D-126) + dựng lại 4 quyển KNTT | **XONG** (D-131) | `_FALLBACK_MIN_CW_FRAC = 0.32` ở `image_processor.py` (sàn chiều rộng lấy theo TRANG, không theo chú thích) + `reset_image_books.py --nxb KNTT` + `--image-only --book` ×4, **1 h 59**, 4/4 exit 0. ▸ Cổng `python -m src.test.qa_crop_shape`: KNTT **17,5% → 1,7%** dải hẹp. ▸ Không hồi quy: phủ nhãn 95/95/96/95% → **96/95/97/95%**, G4 **0 gán sai / 0 thiếu**. ▸ **Ca gốc VẪN CẮT SAI** — 1,7% nghĩa là hết dải HẸP, không phải hết cắt SAI; gốc rễ (detector không thấy cụm nhiều panel) chưa xử lý |
| Kho ảnh **12/12 quyển** | **XONG — 3 881 doc** (D-110, D-111, D-121, D-124, D-131) | KNTT `6/7/8/9` = 286/203/216/234. Độ phủ nhãn hình (`qa_figure_coverage`): CD 92-97% · KNTT 95-96% · CTST 72-89% (chỉ 6_CTST dưới ngưỡng 0,80) |
| Lỗi ▲ của CTST | **ĐÃ VÁ** — thu thêm 737 hình (+90%) (D-121, D-123, D-124) | CTST in `▲` trước mọi chú thích hình, Tesseract đọc thành `À`/`A`, regex neo `^\s*Hình` loại sạch 49% dòng đó. Sau vá: CTST 815 → 1 552 doc |
| Cổng G4 cho CD/CTST | **CHẠY ĐƯỢC** (D-114) | G4 đọc `bai_so` từ manifest (có cho cả 12 quyển) chứ không từ metadata chunk. Spine CD/CTST mang cờ `bai_numbers_not_contiguous` nên lệch Bài hiện KHÔNG quy được lỗi cho crop hay cho manifest — cổng tự đổi nhãn thành "SPINE CHƯA TIN ĐƯỢC" thay vì in số đọc như đã kiểm |
| Định tuyến `is_image_only_query` | **ĐÃ VÁ** (D-88) | đo được 3/300 câu cần chữ bị định tuyến sai thành CHỈ ẢNH → 0/300 sau vá. So trên dạng còn dấu (bỏ dấu thì `nào` đụng `não`, D-49) |
| Caption deterministic vào prompt (MT4) | **XONG, mặc định TẮT** (D-85) | `src/rag/multimodal_context.py` nối `figure_label`+`figure_caption`+`crop_text` (đọc lại từ pixel, không phải model sinh) vào ngữ cảnh LLM. `MULTIMODAL_CONTEXT_ENABLED=false` cho tới khi có số đủ thuyết phục — xem dòng ablation |
| Bảng đối chiếu MT4 | **XONG CẢ HAI CẤU HÌNH** (D-82, D-87) | Cấu hình 1 (300 câu/12 quyển): hybrid thắng bm25 và dense ở mọi cột. Cấu hình 2 (100 câu/4 quyển KNTT): delta +0,010 (đúng thêm 1 câu) nhưng trần đo được cho kênh hình chỉ 0,104 (vì `ground_truth` sinh từ chính văn bản trang vàng) → kết luận đúng là "CHƯA đo được ưu thế", không phải "vô ích". `MULTIMODAL_CONTEXT_ENABLED` giữ false. Bộ test do LLM sinh, mẫu 50 câu người duyệt tay: gold key sai 2/49 = 4,1% (D-90) |
| Index text 12 quyển | **XONG, đã OCR lại với hybrid công thức** (D-162, 2026-09-01) | Lượt Colab 8: 2 399/2 399 trang, 16 515 chunk, `TEXT_EXTRACTION_VERSION=v4_formula_hybrid_fix`. Dựng với `SINGLE_LINE_MAX_H=60` và `LAYOUT_BOX_MIN_SATURATION` per-book (`MIN_SAT_FLOOR=9`, D-146) — thay bản 2026-08-23 (16 393 chunk, `v2_bai_spine`, chưa có hybrid công thức) |
| `bai_so` trong metadata chunk | **CHỈ 4/12 QUYỂN** | KNTT có `bai_so`; 8 quyển CTST/CD không chunk nào (spine chưa liền mạch → tự động thôi ghi, đúng thiết kế) |
| `needs_review` | **MẤT TÁC DỤNG**, phải hiệu chỉnh | bật ở 57–84% chunk theo quyển, gộp toàn kho 69,3% — ở mức đó cờ gần như không mang tin |
| LLM đánh giá (Groq, đổi từ OpenRouter D-163) | **CHẠY ĐƯỢC, nhưng lượt 240 câu đầu (2 model) dính hạn mức TPD giữa chừng — đã tăng lên 4 model (D-173), chưa chạy lại để xác nhận đủ** | 4 model xoay vòng qua `JudgePool`, `https://api.groq.com/openai/v1`: `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `qwen/qwen3.6-27b`, `openai/gpt-oss-20b`. Mỗi model **8000 token/phút riêng** (D-163) VÀ **200 000 token/NGÀY riêng** (D-173, phát hiện khi cả 2 model cũ cùng cạn TPD lúc chạy 240 câu — 106/240 câu mất điểm judge). `stealth/ox-alpha`/OpenRouter (D-67, D-128) **ngừng dùng vì hết free** |
| Bộ test câu hỏi (CBHD kê 240) | **ĐỦ 240 CÂU, ĐỀU 20/quyển · 80/NXB — ĐÃ NGƯỜI DÙNG DUYỆT TOÀN BỘ CÂU HÌNH (D-170/D-172, 2026-09-02)** | 192 câu văn bản (16/quyển) rút mẫu từ pool 300, 0 lượt LLM, 192/192 gold key khớp index. 48 câu HÌNH (4/quyển đều) sau duyệt tay thật (41 phút/50 ô ban đầu, có sửa lỗi nháp LLM — D-170): người dùng giữ lại CẢ 2 khung cắt từng bị đánh giá hỏng trước đây (`crop hỏng`, `ảnh trang trí`) thay vì loại; 2 khung THAY THẾ đã bù (D-169) hoá ra dư — D-172 chốt bỏ 2 khung thay thế đó để 12 quyển đều 4 hình, đưa tổng về đúng **240** (192+48), theo NXB đều **80/80/80** (CD/CTST/KNTT). **CẢNH BÁO đã gỡ:** câu hỏi/đáp án HÌNH nay đều do người viết SAU khi có nháp AI (D-113/D-148 — trước D-170 là AI best-effort một mình, nay là người duyệt độc lập thật) |
| Đánh giá đầu-cuối bộ câu (12 quyển) | **XONG, ĐỦ 240/240 CÂU, ĐÃ ĐỒNG BỘ VÀO `report/tex_source/` (D-173/D-174/D-175, 2026-09-02)** | `Recall(page)` 0,8833 · `MRR(page)` 0,7889 · `R@10` thô 0,9042 · `Correct` 3,896/5 · `Faithful` 4,100/5 · `Relevancy` 4,129/5 — đo trên **đúng 240 câu** (192 văn bản + 48 hình, chốt D-172), index 16 515 chunk `v4_formula_hybrid_fix`, giám khảo Groq **4 model xoay vòng** (D-173, mở từ 2 lên 4 sau khi 106/240 câu mất điểm vì hạn mức TPD). Số cũ (231 câu, D-130, giám khảo OpenRouter): Recall 0,9091 · MRR 0,8153 · R@10 0,8961 · Correct 4,065 · Faithful 4,394 · Relevancy 4,602. **KHÔNG được viết "hybrid công thức/đổi giám khảo làm Recall giảm"** — bộ câu hỏi, giám khảo, VÀ có thể cả index đều đổi cùng lúc giữa hai lượt, không có lượt đối chứng giữ nguyên hai biến kia. Ablation (`ablation_report_240.csv`, 240 câu): bề rộng production (`n=20`, hybrid rerank=on gate=off): MRR 0,8038 · R@1 0,7083 · R@3 0,8875 · R@10 0,9583 — hybrid **hoà tuyệt đối** với BM25 ở R@1 (cả hai 0,7083 tới 4 chữ số thập phân, KHÁC lượt 238/231 câu trước khi hybrid còn thắng rõ), vẫn thắng bm25/dense ở mọi cột khác, nhất quán hướng D-82/D-132. **D-175: `report/tex_source/` Ch.0/3/4/5 đã viết lại đủ số MỚI + lập luận đi kèm** — phát hiện quan trọng nhất: recall production (0,8833) nay THẤP HƠN trần kênh ngữ nghĩa (0,9042, hụt 0,021) — khác hẳn bản nháp trước (231 câu) từng báo production VƯỢT trần; khoảng cách so với báo cáo chuyên đề cũ (0,21) đã thu hẹp ~10 lần nhưng KHÔNG đóng hẳn/đảo chiều như từng viết. `tests/test_bao_cao_so_lieu.py` xanh (đã đổi `test_tong_so_cau_la_231`→`_240`). Build PDF thật xác nhận: **76 trang** (từ 73), 0 lỗi. **D-168 (phân tích cũ, vẫn còn giá trị định tính, số tuyệt đối đã đổi):** `7_CTST`/`9_CTST` vẫn yếu nhất về `overall`, do truy xuất chứ không do trả lời — đặc tính cấu trúc chunk/index của CTST, không phải nhiễu đo lường. **Còn nợ, CỐ Ý ngoài phạm vi D-175:** Bảng~tab:corpus và mọi trích dẫn "16.393 đoạn" trong `report/tex_source/` vẫn tính trên index TRƯỚC hybrid — index thật hiện có **16.515 đoạn** (D-162); cần chạy `python -m src.test.report_numbers --latex` để lấy số đúng trước khi sửa các dòng đó (Mục tiêu 2, `bai_so`, `11.459 đoạn nhãn sai`, cờ "cần rà soát"). Ablation multimodal (M2C, vế 2 Mục tiêu 4) vẫn chưa chạy lại bằng bộ 48 câu hình mới đã người duyệt. |
| G2 gold set 24 trang | **VÔ HIỆU** | số trang đổi (offset −1 → 0); khuyến nghị thu hẹp thành gold set CÔNG THỨC thay vì làm lại bản tổng quát — xem cuối phần này |
| Xử lý công thức Hoá/Lý (MT1) | **XONG (D-162, 2026-09-01) — ETL thật đã chạy, đo xác nhận trên `database/` local, không chỉ tin log Colab** | Kiến trúc Hybrid Tesseract + MinerU patch: `ocr_lines.py` (tách dòng), `formula_signals.py` & `formula_gate.py` (bắt dòng nghi — precision 0,8654/recall 1,0000 trên gold set 89 ô/3 NXB, D-144, KHÔNG đổi sau D-155), `formula_ocr.py` (client MinerU `opendatalab/MinerU2.5-Pro-2605-1.2B`), `formula_merge.py` (merge cục bộ từng dòng). **Chuỗi bug đã tìm ra và sửa hết, theo thứ tự:** D-154 (bug gốc: gate khớp xuyên dòng, 527 `gate_hit_no_line_located`) → D-155 (sửa `CO_DAU_BANG` `\s*`→`[ \t]*`) → D-157 (checkpoint khôi phục kéo về bản CŨ trước D-155, version-gate coi 63,9% trang cũ là "đã xong" nên không OCR lại — 0/16513 chunk `applied`) → D-158 (root cause cuối: `download_models.py --profile text-etl` chưa từng tải model MinerU + notebook chưa trỏ `FORMULA_MINERU_MODEL` local → 100%/3714 lượt gọi MinerU thất bại dưới `HF_HUB_OFFLINE=1`; đã sửa cả hai trong `master`) → D-159 (viết lại sạch notebook 57→35 cell, bump `TEXT_EXTRACTION_VERSION`→`v4_formula_hybrid_fix`, `scripts/reset_text_all_books.py --all` resume-safe, mục "XÁC NHẬN kết quả" đo trực tiếp trên DB) → D-160 (% tiến độ sống qua `PYTHONUNBUFFERED=1`) → D-161 (`_copy_resilient()` chịu Drive-FUSE rớt kết nối ENOTCONN, thay mọi `shutil.copytree`). **D-162: lượt Colab 8 chạy thành công, đo lại độc lập trên `database/` local tải về** (không chỉ tin cell mục 11 của chính notebook): `processing_status` 2399/2399 trang đúng version mới (text `v4_formula_hybrid_fix`, ảnh `v19_pill_kernels`); `biology_images` 3881 doc không mất; `biology_text` 16515 chunk, `formula_hybrid_status`: `applied` 1063 + `unmatched_count` 3230 = **4293 lần merge MinerU thành công**, `mineru_call_failed*` = 0, `gate_hit_no_line_located` = 1 (đúng kỳ vọng D-155); BM25 (`database/sparse/`) 16515 id khớp đúng `biology_text`. Bốn con số khớp chính xác output notebook — không phải checkpoint cũ lẫn vào. **Phát hiện phụ:** `.env` local từng có dòng `TEXT_EXTRACTION_VERSION=v3_formula_hybrid` cũ đè lên default, gây phép đo đầu tiên báo sai — đã xoá, không phải bug repo (`.env` không nằm trong git). `MIN_SAT_FLOOR=9` (Task 7, sửa D-146), `single_line_max_h` per-book chưa đổi hành vi cho quyển nào (Task 8, xem mục M0). Box-detection ở `MIN_SAT_FLOOR=9` đã đo đủ 12/12 quyển (D-150): 10/12 không đổi số hộp trong dải 9-15; `6_CD` tăng 21→23, `7_CD` giảm 11→9 (CHƯA xem bằng mắt để xác nhận). **D-167 (2026-09-02): đo lại xong** `recall_at_k`/`evaluator.py` trên corpus hybrid (238 câu, giám khảo Groq) — xem dòng "Đánh giá đầu-cuối". **Còn nợ:** bảng `ablation.py` (fail lượt đầu do thiếu `--build-cache`, đã vá, chưa chạy lại), điều tra lệch 231/238 câu, rồi mới cập nhật `report/tex_source/` (số hiện tại vẫn là TRƯỚC lượt hybrid) |
| Báo cáo (`report/tex_source/`) | **XONG cả 5 chương + Tóm tắt + front matter, đã dịch ra PDF thật, ĐÃ CẬP NHẬT SỐ 240 CÂU + GIÁM KHẢO GROQ (D-175, 2026-09-02)** | `pdflatex`+`biber`×2 (không qua `build.ps1`, script đó có bug `$ErrorActionPreference=Stop` chặn fallback khi dò `latexmk`) → `build/main.pdf` **76 trang** (73→76 sau D-175), 60 mục tham khảo. **D-175 lật lại một phần lập luận trung tâm của D-132:** "trần recall" (0,9042, kênh ngữ nghĩa thô) nay KHÔNG bị vượt qua nữa — recall cấu hình thật (0,8833) THẤP HƠN trần, hụt 0,021 (so với 0,21 của báo cáo chuyên đề cũ — thu hẹp ~10 lần, KHÔNG đóng hẳn/đảo chiều như D-132 từng ghi trên bộ 231 câu). Nguyên nhân lệch 0,004 giữa recall production và ablation-simulated: 1/240 câu hình được định tuyến đúng sang "chỉ-cần-ảnh" (bỏ qua truy xuất văn bản), độ đo recall mức-trang không ghi nhận được ca này. Giám khảo đổi từ `stealth/ox-alpha` (OpenRouter, hết free D-163) sang **Groq 4 model xoay vòng** (D-173) — thêm Mục~4.2.2 (`sec:judge_pha2`) giải thích đánh đổi (giám khảo không đồng nhất giữa các câu) như một hạn chế MỚI. Mục 3.4 (câu hỏi hình) viết lại hoàn toàn: 48/48 câu đã người đối chiếu trực tiếp với ảnh (70,8% bị sửa nội dung), không còn "39 câu chưa ai đối chiếu" như bản trước. 5 hình Ch.4 sinh lại bằng `report/ve_hinh_chuong4.py` (đã bỏ số cứng `231` trong tiêu đề hình). `tests/test_bao_cao_so_lieu.py` xanh (đổi `test_tong_so_cau_la_231`→`_240`); `report/kiem_tra_tex.py` cấm list đổi ("240 câu" từ bị-cấm sang hợp lệ, thêm cấm "231 câu"/"238 câu"/"stealth/ox-alpha"). **Sửa thêm một lỗi build CÓ SẴN, không liên quan D-175:** Ch.3 có ký tự Unicode subscript trần (`₂`,`₃`) trong `\texttt{}` gây lỗi FATAL — đổi sang `x$_2$`. **CẦN SỬA TIẾP, CỐ Ý ngoài phạm vi D-175:** Bảng~tab:corpus + mọi trích "16.393 đoạn" vẫn tính trên index TRƯỚC hybrid (D-162 đã đưa lên 16.515 đoạn) — cần chạy `report_numbers.py --latex` lấy số mới. Ablation multimodal (M2C) chưa chạy lại bằng bộ 48 câu hình mới |
| Web UI Next.js (MT5) | **XONG** (D-137, D-138, D-139) | repo `D:\personal_repo\project_rag_fe` (Next 16.2.6/React 19.2.4). KaTeX + `src/lib/formula.ts` hạ chỉ số dưới cho Hoá/Lý (chỉ biến đổi HIỂN THỊ, không đụng text lưu trữ); API trả `citations` + `answer_text` riêng; ảnh phục vụ qua `/images/<sách>/<tệp>`, không chép corpus sang FE. Smoke test 13/13 đạt |

**G2 dùng để làm gì, và bỏ nó thì mất gì.** G2 **không gate bất kỳ đường chạy nào** —
nó là dụng cụ đo CER/WER/tỉ lệ lỗi DẤU trên trang người đã xác nhận, không phải điều
kiện để ETL/retrieval chạy. Bỏ G2 không làm hỏng MT2/MT3/MT5 (có cổng đo riêng: G1,
recall@k, bảng ablation), nhưng MT1 thì có ảnh hưởng — "bổ sung bước xử lý đặc thù
cho công thức Hoá, Lý" là hạng mục hợp đồng, và không có phép đo OCR thì không có số
để nói "bước xử lý công thức đã cải thiện được X" (vi phạm nguyên tắc 3).
**XONG (D-147, 2026-08-28) — không cần làm lại gold set 24 trang, và không cần gold
set công thức MỚI:** gold set bake-off 97 ô/15 trang đã cân đối 5/5/5 theo NXB và đã
người duyệt thật từ D-108/D-144 — chỉ cần cắt lát lại. `python -m src.test.ocr_bakeoff
--compare --theo-nxb` trả lời thẳng câu "chỉ số dưới có sống ở độ phân giải CD/CTST
không": **KHÔNG, và CD tệ nhất** (CT: KNTT 0,104 · CTST 0,031 · CD 0,000). Gold set 24
trang cũ (G2 tổng quát, `qa_ocr_gold.py`) **vẫn VÔ HIỆU** và cảnh báo `sua_tay*3 <
may2` của nó **vẫn hỏng** như mô tả — nhưng không còn cần sửa, vì câu hỏi mà nó định
trả lời đã có số từ nguồn khác.

## Sửa lỗi FE/retrieval ngoài phạm vi MT (2026-09-02/03, D-177..D-180)

Người dùng test FE thật, báo 4 lỗi bằng ảnh chụp: trích dẫn lạc đề, trích dẫn vẫn
hiện dù câu trả lời là "không được đề cập", `cho tôi hình con cá` chỉ trả 1 ảnh sai
chủ đề, ảnh tự động đính kèm mọi câu hỏi kể cả câu thuần chữ. Đây là lỗi **phục vụ
(serving)**, không thuộc corpus/ETL nên không đổi số liệu MT1-MT5 ở bảng dưới. Đã
sửa 3/4 (`src/app/api.py`, `src/rag/hybrid_retriever.py`, `src/rag/image_vectorstore.py`)
— chi tiết root cause + đo trước/sau xem D-177..D-179 trong `document/decision_log.html`.

**`RERANK_SCORE_MIN` ĐÃ ĐỔI (D-180, 2026-09-03): `0,2` → `0,59`** trong
`src/config.py` (mặc định, `.env` không ghi đè). Căn cứ (D-179): lọc dùng
`score >= score_min` nên ngưỡng phải LỚN HƠN điểm cao nhất của hai chunk lạc đề
đo được thật ("con cá có màu gì" → CD tr.129=0,589, KNTT tr.105=0,575) — 0,59 là
mốc THẤP NHẤT thoả điều kiện đó, rẻ hơn mốc tròn 0,60 (D-178, không có căn cứ
riêng) mà đạt cùng đảm bảo. Đánh đổi đã CHẤP NHẬN, đo trên 240 câu: MRR
0,8038→0,7972 (−0,82%), R@10 0,9583→0,9417 (−1,73%), 3/240 câu (1,25%) không còn
kết quả nào lọt rerank (LLM trả fallback). Verify bằng ca gốc: câu "con cá có màu
gì" trước 3 trích dẫn (2 lạc đề) → sau đúng 1 trích dẫn đúng chủ đề.
`tests/rag/test_config_m2.py::test_m2_config_defaults` đã cập nhật theo giá trị
mới; `pytest tests/`: 781 passed, 3 skipped. **Còn nợ, ngoài phạm vi D-180:** bảng
đầu-cuối 240 câu trong `report/tex_source/` (D-175) vẫn đo trên `0,2` cũ — cần
chạy lại `evaluator.py`/`report_numbers.py` trước khi nộp báo cáo nếu muốn số liệu
khớp cấu hình production hiện tại.

## Quy tắc làm việc (luôn áp dụng)

- **Phản biện mọi thay đổi code tìm bug ẩn trước khi báo xong** — truy edge case,
  off-by-one, lệch toạ độ/chỉ số, cache cũ, fallback âm thầm; test xanh không có
  nghĩa là đúng.
- **KHÔNG chạy cả bộ test khi đang lặp.** Chỉ chạy test nhắm đúng file vừa sửa (ví
  dụ `python -m pytest tests/layout/test_segmenter.py -v`). Chạy cả suite khi được
  yêu cầu rõ hoặc ngay trước khi chốt một mốc.
- **Test nhỏ và nhắm đúng chỗ.** Tránh test nặng/chậm/tốn trừ khi thật cần; ưu tiên
  unit test có fixture tổng hợp hơn end-to-end nặng nề.
- **Commit message: KHÔNG có dòng `Co-Authored-By`** (và không có dòng "Generated
  with"). Chỉ message thuần.
- Ghi mỗi quyết định vào `document/decision_log.html`; giữ spec/plan trong
  `document/specs/`; giữ CLAUDE.md + memory luôn khớp thực tế.

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
   chặn cụ thể (file:dòng, hoặc lệnh grep tái lập được). Đổi cả các gạch đầu dòng tương ứng
   trong "Redesign đang chạy" nếu chúng cũng mô tả cùng việc đó.
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

## Lệnh

Mọi lệnh chạy qua `main.py` (từ repo root). Không có bước build — đây là app Python.

```bash
pip install -r requirements.txt
cp .env.example .env          # rồi set HF_TOKEN (bắt buộc) và USE_GPU

# BƯỚC 0 — bản đồ trang + spine Bài cho từng quyển. BẮT BUỘC trước khi index text:
# đường text từ chối đoán số trang in và raise nếu thiếu. In báo cáo G1, thoát mã
# khác 0 khi G1 fail.
python main.py --build-manifests
python main.py --build-manifests --book SGK_KHTN_6_KNTT   # chỉ một quyển

# MỘT LỆNH, chạy không cần canh (Windows/PowerShell): manifest 12 quyển -> ETL
# text -> báo cáo "còn lại gì", gộp vào một log có timestamp. Nó đọc mã thoát của
# --build-manifests, IN RA, rồi vẫn chạy tiếp: G1 FAIL là chuyện BÌNH THƯỜNG hôm
# nay (spine CTST/CD chưa liền mạch, D-70) trong khi `save_manifest` vẫn ghi mọi
# quyển dựng được, và --text-only chỉ cần manifest tồn tại. Đừng nối hai lệnh
# bằng `&&` — mã thoát 1 của G1 sẽ chặn bước 2 một cách vô lý.
powershell -ExecutionPolicy Bypass -File scripts\run_etl_local.ps1

# BƯỚC -1 (M0) — đo fingerprint layout riêng của từng quyển. Ghi/hợp nhất vào
# database/fingerprints/{book}.json; một stage lỗi không bao giờ ghi đè lên một
# stage đã tốt.
python -m src.etl.book.fingerprint --all --verbose > fp.log 2>&1 &
python -m src.etl.book.fingerprint --all --stages toc --verbose     # chỉ một stage
python -m src.etl.book.fingerprint --book SGK_KHTN_6_CD --sample 40 --verbose

# ETL (index offline) — checkpoint resume theo TỪNG TRANG, khoá theo nội dung trang
python main.py --text-only    # OCR theo layout + chunk + index text -> ChromaDB
python main.py --image-only   # crop hình + caption + index ảnh
# `--book` lọc được cả BA đường ETL từ D-84 — trước đó chỉ --build-manifests nghe
# theo, nên `--image-only --book X` từng ÂM THẦM bỏ qua cờ và chạy cả 12 quyển
# (~6 giờ, 8 quyển biết trước là sai). Tên quyển không khớp nay THOÁT MÃ 2.
python main.py --image-only --book SGK_KHTN_6_KNTT
python main.py --etl          # cả hai (đường text giống --text-only)

# Chu trình người duyệt metadata ảnh (xem README §6 để biết đúng ngữ nghĩa JSON)
python main.py --export-image-review database/review_images.json
python main.py --apply-image-review database/review_images.json --review-user <ten>   # upsert-tung-item, KHÔNG đồng bộ toàn bộ
python main.py --replace-image-db database/snapshot.json --review-user <ten>          # JSON là nguồn sự thật (xoá cái gì thiếu trong file)

# Serve
python main.py --api --port 5000
```

### Đánh giá (trong `src/test/`)

Cần `EVAL_LLM_*` trong `.env` (endpoint tương thích OpenAI bất kỳ). **`.env` hiện
trỏ vào Groq (D-163, 2026-09-01 — OpenRouter `stealth/ox-alpha` hết free):
`EVAL_LLM_BASE_URL=https://api.groq.com/openai/v1`, BỐN model xoay vòng qua
`EVAL_LLM_MODELS=qwen/qwen3.8-27b,openai/gpt-oss-120b,qwen/qwen3.6-27b,openai/gpt-oss-20b`**
(D-173, tăng từ 2 lên 4 — xem lý do ở dòng D-173 ngay dưới; `EVAL_LLM_MODEL` chỉ còn
là model đầu danh sách, giữ cho tương thích code cũ). `get_eval_llm()`
(`src/test/eval_llm.py`) trả về `JudgePool` khi có ≥2 model trong `EVAL_LLM_MODELS`
— `.invoke()` cùng chữ ký `ChatOpenAI` nên mọi nơi gọi không đổi code; khi model
đang active bị 429/5xx thì xoay NGAY sang model kế (không sleep, khác lớp với
backoff 5/20/60s sẵn có trong `evaluator.py::judge_answer`), lỗi 401/400 thì raise
ngay không xoay. Bẫy URL **vẫn y hệt OpenRouter cũ**: phải dừng ở `/v1`, đưa nguyên
`.../v1/chat/completions` sẽ bị client nối lần hai, ra 404. **Đo thật 2026-09-01
(D-163):** cả hai model id tồn tại đúng chữ (`GET /v1/models`), mỗi model có hạn
mức TPM RIÊNG `8000 token/phút` (không dùng chung bucket) — đo bằng header
`x-ratelimit-limit-tokens` trên chính lượt gọi thật, không phải tra docs. Vẫn giữ
**đừng bao giờ set `max_tokens`** (bẫy đã đo trên OpenRouter, chưa kiểm lại trên
Groq nhưng an toàn hơn để giữ nguyên). **Đã đo trên 238 câu thật (D-167):** 8000
TPM/model đủ dùng, chỉ 1/238 câu lỗi — nhưng KHÔNG phải rate-limit mà là JSON hỏng
cú pháp từ model (`json.JSONDecodeError`). Dấu tiếng Việt sống sót qua round-trip;
`_parse_json` đã tự bóc fence ```json``` model này hay in ra (đã kiểm cả
`openai/gpt-oss-120b`, model này trả `reasoning` tách khỏi `content` nên không làm
hỏng parse). **D-168: đã thêm retry cho JSON hỏng cú pháp** —
`_la_loi_tam_thoi()` khớp thêm `json.JSONDecodeError`, và vì `temperature=0.0` khiến
CÙNG model thử lại sinh lại y hệt lỗi cũ (deterministic), `judge_answer()` gọi
`JudgePool.force_rotate()` (mới) để ép đổi sang model kế trước khi thử lại — chỉ có
tác dụng khi `EVAL_LLM_MODELS` có ≥2 model. **D-173 (2026-09-02): TPM KHÔNG phải hạn
mức duy nhất — lượt chạy thật 240 câu (2 model) dính hạn mức TPD (token/NGÀY,
200 000/model) giữa chừng, cả hai model cùng cạn cùng lúc nên xoay vòng vô ích, backoff
tối đa ~85s không đủ chờ token nạp lại (thông báo lỗi đòi 3–5 phút) → 106/240 câu
(44%) mất điểm judge, lệch hẳn về khối CD/CTST (4 quyển KNTT sống 100%). Đã mở rộng
lên 4 model (nhân đôi ngân sách/ngày, mỗi model một bucket riêng) thay vì sửa
backoff — đơn giản hơn, không đụng code retry. **D-174 (2026-09-02): lượt chạy lại
sau D-173 crash ở cổng mtime (mục 15 notebook)** — bug THẬT trong `_copy_resilient()`
(`shutil.copy2` giữ nguyên mtime GỐC trên Drive khi khôi phục), không phải trong
logic D-173. File 4 quyển KNTT hợp lệ bị khôi phục với mtime CŨ (từ lần đồng bộ
Drive trước), cổng mtime D-168 coi là "dữ liệu sót lại" và raise dừng notebook. Đã
vá: `khoi_phuc_tien_do_da_co()` gọi `dich.touch()` ngay sau khi copy về, đặt mtime =
lúc phiên NÀY xác nhận file hợp lệ. Không cần làm lại gì trên Drive — 8 quyển
CD/CTST đã tính lại đúng trong phiên bị crash, đã đồng bộ lên Drive trước khi crash
xảy ra; chỉ cần chạy lại notebook (git clone kéo bản vá mới).

```bash
python src/test/generate_testsets.py --dry-run  # chọn trang + in thống kê, KHÔNG gọi LLM
python src/test/generate_testsets.py            # 25 câu/quyển qua PageSource; gold key từ metadata chunk thật (D-48)
python -m src.test.ablation_multimodal          # Cấu hình 2: text-only vs multi-modal (0 LLM)
python -m src.test.prompt_scope_probe           # before/after câu Lý + câu Hoá khi sửa prompt
python -m src.test.qa_citation_page             # cổng G3: trang được TRÍCH DẪN có chứa câu trả lời không (không cần LLM, D-49)
python -m src.test.qa_citation_page --judge     # + lượt LLM cứu xét, hiệu chỉnh ngưỡng coverage
python -m src.test.ocr_bakeoff --compare        # bảng bake-off; engine thiếu ô -> in `—`, không in số (D-96)
python -m src.test.ocr_bakeoff --doi-chieu <engine> --so-o 10   # ĐỌC ô bằng mắt: NGƯỜI · engine · tesseract (D-98)
python -m src.test.qa_ocr_gold --export         # G2: dựng gold set 24 trang cho NGƯỜI sửa (D-55)
python -m src.test.qa_ocr_gold --score --per-page   # G2: CER/WER/tỉ lệ lỗi dấu sau khi đã sửa
python src/test/evaluator.py                    # chạy RAG thật, đo P/R/MRR + LLM chấm (1-5)
python -m src.test.recall_at_k                  # benchmark recall nhanh, không gọi LLM; in cả baseline lẫn rerank MỘT lượt
python -m src.test.recall_at_k --testset-dir src/test/testsets_240   # bộ 240 câu (CBHD kê)
python src/test/evaluator.py --testset-dir src/test/testsets_240 --hau-to _240
# 231 cau tren may dev (GPU 4 GB) do duoc ~3-3,5 phut/cau (D-164) -> 5-12 gio.
# Neu can nhanh hon: document/colab_runtime_eval.ipynb chay ca ba script tren
# (recall_at_k/ablation/evaluator) tren Colab, doc DB da upload thu cong len
# Drive (`database_png`, D-165), khong can RAG_DATA_DIR/manifest/fingerprint.
# D-166: LUOT DAU chay notebook nay BI BUG - git clone mang theo *_result.csv
# CU (2026-08-26) nen --bo-qua-da-co tuong nham 12/12 quyen da xong, khong tinh
# lai cau nao (da vao muc 1b). Sau ban va: LUON kiem cot `luot_chay` = `moi`
# trong evaluation_report_240.csv truoc khi tin so - `da_co` nghia la doc lai
# du lieu CU, khong phai phep do moi.
python -m src.test.build_testset_240            # 192 câu văn bản, rút mẫu từ pool 300, 0 LLM
python -m src.test.build_image_questions --chon # 48 câu HÌNH: máy chọn crop -> --nhap -> người duyệt
python -m src.test.report_numbers [--latex]     # số liệu Bảng 4.2/4.3 đọc thẳng từ index
python -m src.test.qa_figure_coverage           # độ phủ nhãn hình 12 quyển (không tốn OCR); thoát 1 nếu có quyển < 80%
python scripts/reset_image_books.py --nxb CTST  # chạy lại luồng ẢNH cho riêng một NXB (đừng bump version — nó ép cả 12 quyển)
python scripts/reset_text_all_books.py --all    # hạ cờ checkpoint TEXT (mặc định resume-safe: chỉ trang chưa đạt version mới), KHÔNG đụng ẢNH (D-158)
python report/kiem_tra_tex.py                   # lint .tex: ref/cite/gói/ký tự điều khiển/SỐ CŨ (KHÔNG dịch, chỉ lint)
powershell -File report/tex_source/build.ps1 -Clean   # dịch THẬT ra PDF (MiKTeX 25.12 đã cài, D-140); latexmk hỏng vì thiếu Perl nên script tự rơi về pdflatex+biber
python report/ve_hinh_chuong4.py                # sinh lại 5 hình Ch.4 từ evaluation_report_240.csv (đừng vẽ tay)
python src/test/test_image_extraction_full.py   # QA thị giác chuẩn cho crop hình (vẽ box lên trang)
```

`src/test/testsets/` giữ **bộ test 4 quyển thật: 100 câu, 25/25 mỗi quyển** (sinh
2026-08-22 bằng `gemini-3.5-flash-lite`, seed 42) — đây là **pool nguồn** mà
`build_testset_240.py` rút mẫu ra 192 câu văn bản của bộ `testsets_240/`, và là
`--testset-dir` mặc định của `ablation.py`/`evaluator.py`/`recall_at_k.py` khi
không truyền cờ. Kiểm chứng trên index đã dựng: **0/100 gold key trỏ vào trang
không có chunk**. Hai bộ cũ hơn (12 quyển 2026-07, 4 quyển KNTT offset −1) đã
**xoá** (2026-09-01) — gold key không khớp metadata chunk từ lâu, không script nào
còn đọc tới (0 tham chiếu, đã grep xác nhận trước khi xoá), lịch sử xem
`document/decision_log.html`. **Bộ test do LLM sinh, chưa người duyệt** —
`_generation_meta.json` ghi `human_reviewed: false`, báo cáo dùng số này phải nói rõ
điều đó. `metrics.PAGE_TOLERANCE` là **0**: chunk không bao giờ tràn trang, nên cửa
sổ ±1 chỉ tính điểm cho chunk ở trang KHÁC và thổi phồng recall.

## Kiến trúc

Hai pha: **ETL (offline)** dựng index; **truy vấn (online)** phục vụ qua Flask.

### Lưu trữ — bốn collection ChromaDB (`src/config.py`)
- `biology_text` — chunk text đã OCR (embedding bge-m3, `CHUNK_SIZE=400/overlap=120`)
- `biology_images` — crop hình (embedding CLIP)
- `biology_image_metadata` — caption/từ khoá của hình (tìm kiếm riêng được)
- `processing_status` — trạng thái checkpoint theo trang, cho phép ETL resume

**Ngữ nghĩa checkpoint (cả ba đường ETL thống nhất):** `processing_status` là nguồn
sự thật duy nhất. Mỗi record khoá theo **`page_key` = `{tên sách}#{md5 bytes của
trang đó}`** (`page_source.page_checkpoint_key`) cộng một version —
`TEXT_EXTRACTION_VERSION` cho text, `IMAGE_EXTRACTION_VERSION` cho ảnh. Nên: thay
một file trang chỉ re-process **đúng trang đó**; bump version thì re-process lại
toàn bộ bên đó. Chunk id là `{page_key}_p{page_number}_c{chunk_index}`, và
`_index_source_pages` xoá chunk text cũ của trang trước khi ghi chunk mới, nên bump
version không để lại chunk mồ côi. **Phía ảnh từng thiếu cơ chế này (D-52):** id của
doc ảnh là hash của CROP, nên đổi crop ra id mới và doc cũ tồn tại song song thay vì
bị ghi đè. `ImageVectorDB.delete_page_documents(source, pages)` nay xoá cả hai
collection ảnh cho các trang sắp ghi lại, gọi từ `run_etl`/`run_etl_image_only`
**sau khi** extract thành công (crash giữa chừng không xoá gì) và **kể cả khi trang
không cho ra hình nào** (trang mất hình phải mất luôn doc). `database/
processed_files.txt`/`processed_images.txt` chỉ là log tiến độ THAM KHẢO — không gì
bỏ qua công việc vì chúng.

Mọi thứ có thể ghi nằm dưới `database/` (`PERSIST_DIR`), override qua
`RAG_DATABASE_DIR` (trỏ Google Drive trên Colab). `database/manifests/{book_id}.json`
giữ `BookManifest` từng quyển, override RIÊNG qua `RAG_MANIFEST_DIR` để manifest đi
theo repo trong khi index nằm trên Drive. `database/fingerprints/{book}.json` (đo M0,
đủ 12/12 quyển) cũng vậy qua **`RAG_FINGERPRINT_DIR`**, mặc định
`<repo>/database/fingerprints` — đây là một **phép đo** tốn ~70 phút OCR nên thuộc về
repo, không thuộc về index trên Drive. `datasources/` chứa PNG trang gốc, mỗi quyển
một thư mục (không có PDF); override bằng `RAG_DATA_DIR`. **PNG KHÔNG nằm trong git
(D-68):** đo được 4,1 GB/2 399 trang trong khi `.git` đã 11 GB, riêng lô CD/CTST
(~3,4 GB) vượt trần 2 GB/lượt push của GitHub. `.gitignore` bỏ qua `datasources/*`
trừ `datasources/README.md` (mô tả cấu trúc mong đợi). Hệ quả cần nhớ: clone mới
**không có data**, nên cả bốn entrypoint dữ liệu nay **thoát mã khác 0** thay vì log
rồi trả về 0 — đo được `--text-only`/`--image-only`/`--etl` → **2**,
`--build-manifests` → **1**.

### Page source (`src/etl/page_source.py`)
`PageSource` là đường DUY NHẤT để pixel trang đi vào hệ thống: `page_numbers()` (số
**trong tên file**, không phải thứ tự `enumerate`), `load(page_number)` → mảng BGR
uint8, `content_hash(page_number)`. `PngFolderPageSource` là corpus thật;
`PdfPageSource` chỉ còn phục vụ upload `/api/etl` cũ. `discover_page_sources
(DATA_DIR)` trả về mọi quyển (thư mục PNG trước, PDF cũ sau). Bất cứ chỗ nào cần
đọc trang phải đi qua đây — đừng thêm lại lời gọi `fitz`/poppler vào ETL.

### Text ETL (`src/etl/layout/loader.py`)
`LayoutOCRLoader.load_page(source, page_number)` là xương sống layout và là đường
text **DUY NHẤT**: tra manifest (trang in + role) → `source.load()` → `segment_page`
→ `extract_text_units` → `chunk_units`. Không có bước tiền xử lý, không có phát hiện
số trang ở đây — **số trang in lấy từ `BookManifest`**, thiếu manifest/trang lạ/thiếu
`printed_page` thì raise `ManifestMissing` chứ không đoán. Trang có `role="cover"`
trả về không chunk nào (file nguồn không bị đụng hay xoá).

Chunk mang `source`/`page` (số in)/`page_index` (số trang nguồn)/`variant`/
`region_type`/`chunk_index`/`needs_review`/`review_tokens`. `page` và `page_index`
**bằng nhau trên corpus hôm nay** (offset 0 — D-65; đo lại 2026-08-25: 0/16 393
chunk khác nhau), nhưng vẫn KHÔNG được gộp chung theo thiết kế: citation dùng
`page`, truy ngược về file dùng `page_index`. `citations.py` đọc `region_type` để
gắn nhãn mục — chunk thiếu trường này tự động rớt xuống citation chỉ-thân-bài. Thân
bài do `TextSplitter` cắt; sidebar/info-box giữ nguyên một khối trừ khi vượt
`BOX_ATOMIC_MAX_CHARS` (1,5 × `CHUNK_SIZE`), lúc đó bị cắt nhưng vẫn giữ
`region_type`.

`--etl` và `--text-only` đều qua `_index_source_pages()` trong `main.py`, từng trang
một; trang nào raise thì được log, để lại chưa đánh dấu, chạy lại lượt sau.
`RobustOCRLoader` cũ (OCR cả trang) **không còn** là đường text — `ocr_image()` chỉ
còn phục vụ OCR cả trang để làm anchor cho chú thích hình ở phía ảnh.

### Luồng truy xuất (`src/rag/`)
1. `hybrid_retriever.py::HybridRetriever.search()` là điểm vào. Nó gọi
   `query_intent.py::is_image_only_query()` để **định tuyến**: câu hỏi chỉ-cần-ảnh
   (vd "cho tôi hình con X") bỏ qua truy xuất text hoàn toàn.
2. Phía text: `RETRIEVAL_MODE=dense` (mặc định) giữ nguyên hai lớp cũ —
   `RerankedRetriever` khi `RERANK_ENABLED`, **`RelevanceGatedRetriever`** (cổng
   khoảng cách tương đối `RETRIEVER_DISTANCE_MARGIN`) khi không. Hai nhánh **loại
   trừ nhau**, nên cổng khoảng cách chưa từng chạy trong cấu hình thật (D-80).
   `bm25`/`hybrid` đi qua `HybridTextRetriever`: hợp nhất → cổng lọc → rerank, ba
   công tắc rời nhau. **Đã đo (D-81): cổng lọc TƯƠNG ĐỐI không mua được gì** — dưới
   `rrf` trung tính ±0,007 MRR, dưới `norm` nó **cắt mất đáp án thật** (R@10
   1,000 → 0,890). Cổng lọc thực sự hoạt động là sàn tuyệt đối `RERANK_SCORE_MIN`.
3. Phía ảnh kết hợp CLIP similarity + tìm theo metadata + một **kênh cụm từ lexical**
   (nhạy dấu; phân biệt "trâu" với "trầu") + rerank, gate bằng
   `IMAGE_RELEVANCE_THRESHOLD`. **Text phía document của kênh cụm từ được che theo
   danh sách "false-friend" đã đo trước khi so khớp (D-141..D-143):** tiếng Việt là
   ngôn ngữ phân tích, nên "cá" trần cũng mở luôn "cá heo"/"cá sấu"/"cá cóc"/"cá
   nhân" — trọng số +0,45 của kênh cụm từ từng khớp "con cá" như substring thô bên
   trong "con cá heo", kéo ảnh cá heo lên ngang ảnh cá thật. Đo trên index thật:
   129→87 doc còn khớp "cá" trần sau khi vá.
4. `chain.py::BiologyRAG` dựng prompt và gọi LLM Qwen2.5 (`llm.py`), trả về câu trả
   lời + gallery ảnh.

### Image ETL — phần phức tạp, đang đổi liên tục (`src/etl/image_processor.py`, ~4000 dòng)
- **Điểm vào là `extract_images_from_source(source, ocr_text_per_page, pages=…)`** —
  nhận một `PageSource` và danh sách **số trang nguồn**, nạp từng trang qua
  `_load_page_image()` (PNG → mảng RGB + ảnh PIL). Không poppler, không DPI: detector
  nay thấy đúng pixel gốc 1094×1536 thay vì bản render 150-DPI, nên
  `IMAGE_EXTRACTION_VERSION` đã bump lên `v17_png_source`.
- **Một nhà xuất bản, không còn dispatch theo variant (D-50) — NAY ĐÃ ĐẢO NGƯỢC LẠI
  (D-110, D-111):** mỗi NXB có class xử lý riêng thật sự, xem dòng "Gỡ
  `LAYOUT_VARIANT`" ở bảng tiến độ.
- Phát hiện là **anchor-first + deterministic** (tìm anchor chữ chú thích hình rồi
  crop dải phía trên), OWL-ViT là detector phụ. Khi đụng vào chỗ này, verify bằng
  công cụ QA thị giác, không chỉ bằng output unit test.
- **M3 layout reconcile**: ngay sau `detect_regions_anchor_first`,
  `extract_images_from_pdf` chạy `src/etl/layout/figure_bridge.py::
  reconcile_with_layout` — bước **chỉ xoá, không sửa** loại bỏ một vùng nằm
  ≥`FIGURE_IN_BOX_DROP_RATIO` (0,80) bên trong một hộp màu của segmenter (false
  positive dạng sidebar/info-box). Chỉ loại vùng dạng generic/không anchor
  (`panel`/`figure`) — vùng có caption/nhãn (`single_figure`/`composite_figure`/
  `sub_figure`) luôn được tin, không bao giờ bị xoá.
- `IMAGE_EXTRACTION_VERSION` trong `.env` gate cache crop: **bump để ép crop lại**
  sau khi đổi logic crop (không thì checkpoint theo trang sẽ bỏ qua trang đã xử lý).

### API + app (`src/app/`)
- `dependencies.py::AppServices` là **singleton** nạp mọi model nặng một lần
  (VectorDB, HybridRetriever, LLM, RAG chain). Không bao giờ khởi tạo model theo
  từng request — đi qua đây.
- `api.py` expose chat (+SSE stream tại `/api/chat/stream`), ETL upload nền, và CRUD
  metadata ảnh cho UI review.

## Quy ước quan trọng

- **Model cấu hình qua `.env`/`src/config.py`**, không hardcode. Mặc định:
  `BAAI/bge-m3` (embedding text), Qwen2.5-3B-Instruct (LLM), CLIP-ViT (ảnh), OWL-ViT
  (phát hiện), Vintern-1B (caption — **tắt mặc định**, D-47).
  `src/utils/download_models.py` tải trước để chạy offline.
- **Reranker cross-encoder** `BAAI/bge-reranker-v2-m3`
  (`src/rag/reranker.py::CrossEncoderReranker`/`get_reranker()`, singleton dùng
  chung, an toàn CPU/GPU) rerank cả hai phía: text qua `RerankedRetriever`
  (`RERANK_ENABLED`, `RERANK_FETCH_K`, sàn tuyệt đối `RERANK_SCORE_MIN`) và ảnh như
  một số hạng cộng thêm (`IMAGE_RERANK_ENABLED`, `IMAGE_RERANK_TOP_N`,
  `IMAGE_RERANK_WEIGHT`) — không bao giờ thay thế hợp nhất ảnh hiện có.
- **Citation là deterministic, không do LLM sinh**: `src/rag/citations.py` dựng từ
  metadata chunk thật (trang/mục, cả nhãn sidebar) và `src/app/api.py` gắn vào
  response chat + stream — LLM không bao giờ tự bịa số trang. `format_book_name`
  render tên **cho người đọc** (`SGK_KHTN_6_KNTT` → `Khoa học tự nhiên 6 (Kết nối
  tri thức)`) và trả lại nguyên tên khi không khớp mẫu. Nhãn phải là **song ánh**:
  cổng G3 map ngược nhãn hiển thị về `source`.
- **Windows là môi trường dev chính.** OCR cần Tesseract (`vie`) qua
  `TESSERACT_CMD`; Poppler (`POPPLER_PATH`) chỉ còn cần cho đường PDF cũ. Zip dựng
  sẵn nằm ở `windows_tools/`.
- **QA thị giác cho layout**: `python -m src.test.qa_layout --book SGK_KHTN_6_KNTT
  --page 10` vẽ vùng đã segment; `--pages 10,11,12 --report` in số vùng/trang (độ đo
  recall). `SGK_KHTN_6_KNTT/page_010.png` là trang tham chiếu — người đếm được
  ≥4 hộp màu trên đó.
- **Chạy ETL trên Colab — `document/colab_runtime_etl.ipynb` LÀ RUNBOOK**, người
  dùng xác nhận đây là file duy nhất họ chạy. **Đừng bao giờ mở một runbook song
  song, và đừng để nó trôi**: khi CLI ETL, một biến env, hay một số đã đo thay đổi,
  vá notebook này **trong cùng lượt** — đây là chỗ thứ 4 trong checklist "Định nghĩa
  xong" cho bất cứ gì đụng tới ETL. Bản mới nhất (lượt 7, 2026-08-31, D-153): DB
  local đo trực tiếp trước khi vá — **0/2 399 trang có `v3_formula_hybrid`**
  (100% còn `v2_bai_spine`, `formula_hybrid_status` vắng mặt ở cả 16 393 chunk) →
  việc chính của lượt Colab là OCR lại TOÀN BỘ text; **ảnh đã 2 399/2 399 trang ở
  `v19_pill_kernels`** → mục ảnh của notebook đổi từ chạy cứng "chỉ 4 quyển KNTT"
  (lỗi thời từ khi 8 quyển CD/CTST xong 2026-08-25..28, chưa từng được vá) sang
  tự kiểm tra + chỉ chạy lại quyển thực sự thiếu. DB + datasources nay nằm trên
  Drive của **chính tài khoản Colab Pro đang chạy** (không phải tài khoản mượn
  của lượt 6, đã bỏ) — không còn bước tải zip về máy cuối phiên, đồng bộ Drive
  luôn bật, `gpuType` mặc định đổi `T4` → `L4`. Việc trong `/content/database`
  (đĩa cục bộ suốt phiên) + đồng bộ phần nhẹ lên Drive sau mỗi quyển giữ nguyên
  từ lượt 5 (D-152).
- **Ngữ nghĩa JSON review ảnh dễ hiểu nhầm**: `--apply-image-review` upsert theo
  từng item (xoá một item khỏi mảng KHÔNG xoá nó khỏi DB); chỉ
  `--replace-image-db` coi file là nguồn sự thật đầy đủ. Để loại một hình khỏi
  truy xuất: set `review_status=rejected|deleted`/`is_active=false`/`delete=true`.
  Xem README §6.
- Runbook ETL ảnh chi tiết theo từng NXB: `skills/etl-textbook-images/runbook.md`.
