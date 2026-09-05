# Prompt bàn giao — cập nhật `report/tex_source/` với số liệu mới (240 câu D-182/D-187 + M2C D-189)

**Dùng file này làm prompt đầu vào cho phiên làm việc tiếp theo.** Phiên hiện
tại (2026-09-05) đã đo xong mọi số cần thiết nhưng **cố ý chưa sửa
`report/tex_source/`** — người dùng yêu cầu để một phiên riêng. Đọc
`CLAUDE.md` (RULE #0 + bảng "Trạng thái tiến độ") trước khi bắt đầu — file này
chỉ tóm số liệu và lộ trình, không thay thế CLAUDE.md.

## 1. Vì sao phải sửa

`report/tex_source/` hiện build trên số liệu của lượt trước D-182 (đổi cấu
trúc bộ test) và trước D-189 (ablation multimodal M2C). Ba việc đã xảy ra kể
từ bản báo cáo hiện tại mà báo cáo CHƯA phản ánh:

1. **D-182 (2026-09-04):** huỷ bộ test 240-câu-cố-định-theo-quyển (192 văn bản
   16/quyển + 48 hình 4/quyển), thay bằng **lấy mẫu ngẫu nhiên toàn corpus**
   qua `build_testset.py` — không còn ràng buộc đều theo quyển.
2. **D-187 (2026-09-05):** chạy lại end-to-end trên bộ test MỚI (240 câu:
   **158 văn bản + 52 hình + 30 ngoài phạm vi**), GPU thật, 0 lỗi, kết quả ở
   `src/test/eval_results/`.
3. **D-189 (2026-09-05):** ablation multimodal M2C (MT4 vế ii) chạy xong,
   **kết luận dứt khoát**: multi-modal context KHÔNG cải thiện, tệ đi nhẹ.
   Kết quả ở `src/test/eval_results_m2c/` + `src/test/testset_m2c/m2c_ket_qua.md`
   (file sau KHÔNG có trong git, tái lập bằng `python -m src.test.compare_m2c`
   — chạy lại nếu cần, dữ liệu nguồn `eval_results/` + `eval_results_m2c/` đã
   commit).

Ngoài ra còn **một món nợ cũ hơn, KHÔNG liên quan D-182/D-187/D-189**: chỉ mục
text đã tăng từ 16.393 lên **16.515 đoạn** từ lượt hybrid công thức (D-162,
2026-09-01) — báo cáo hiện tại vẫn ghi 16.393 ở mọi nơi.

**Cấm suy luận nhân quả giữa các lượt đổi này** (đã cảnh báo trong CLAUDE.md,
D-175): bộ câu hỏi, index, `RERANK_SCORE_MIN` (0,2→0,59 ở D-180), và giám khảo
đều có thể đã đổi giữa các lượt đo — không viết kiểu "đổi X làm số Y giảm" trừ
khi có lượt đối chứng giữ nguyên các biến còn lại.

## 2. Số liệu THẬT — dùng đúng các số này, đừng suy diễn lại

### 2.1 Corpus / kho tri thức (Bảng 4.2, Mục tiêu 2, Tóm tắt, Ch.5)

Đo bằng `python -m src.test.report_numbers` (đã chạy, dữ liệu snapshot dưới
đây — chạy lại nếu nghi ngờ `database/` local đã đổi):

```
Khối Bộ sách               Trang   Chunk  Vector hình
   6 Cánh Diều               178    1124          418
   6 Chân trời sáng tạo      203    1280          470
   6 Kết nối tri thức        194    1125          286
   7 Cánh Diều               170    1156          269
   7 Chân trời sáng tạo      187    1316          335
   7 Kết nối tri thức        178    1073          203
   8 Cánh Diều               206    1451          324
   8 Chân trời sáng tạo      222    1764          423
   8 Kết nối tri thức        195    1253          216
   9 Cánh Diều               214    1613          379
   9 Chân trời sáng tạo      214    1814          324
   9 Kết nối tri thức        226    1546          234
     TỔNG                   2387   16515         3881
```

- **2 387 trang nội dung** lập chỉ mục (2 399 trên đĩa, chênh 12 = trang bìa,
  bỏ theo thiết kế — KHÔNG đổi so với báo cáo hiện tại).
- **16 515 đoạn văn bản** (đổi từ 16.393 — do lượt hybrid công thức D-162,
  KHÔNG liên quan D-182/D-187/D-189, đừng gán nhầm nguyên nhân).
- **3 881 vector hình** (không đổi).
- **Tổng vector: 20 396** (= 16515+3881; báo cáo hiện tại ghi 20.274, SAI vì
  dùng mẫu số cũ 16.393).
- Loại hình (không đổi so với báo cáo hiện tại):
  `single_figure 2172 · sub_figure 824 · activity_box 442 · composite_figure
  324 · textbook_info_box 87 · tool_group 32` (tổng = 3881).
- **`bai_so`: 4 919/16 515 = 29,8%** (báo cáo hiện tại ghi 4.857/16.393=29,6%
  — cập nhật mẫu số, tỉ lệ gần như không đổi, vẫn "chỉ 4/12 quyển KNTT có").
  Đo bằng:
  ```python
  import chromadb
  client = chromadb.PersistentClient(path='database')
  metas = client.get_collection('biology_text').get(include=['metadatas'])['metadatas']
  co_bai_so = sum(1 for m in metas if m.get('bai_so') not in (None, '', 0))
  ```
- **`needs_review`: 11 699/16 515 = 70,8%** (báo cáo hiện tại ghi
  11.362/16.393=69,3% — cùng kết luận "mất tác dụng phân biệt", chỉ đổi số).
- **`variant` (nhãn NXB) đã ĐÚNG cho cả 3 nhóm** — `ctst 6174 · cd 5344 ·
  kntt 4997` — món nợ cũ "11.459 đoạn mang nhãn variant='kntt' sai" (D-109,
  nhắc trong bảng tiến độ CLAUDE.md dòng "Gỡ `LAYOUT_VARIANT`") **ĐÃ TỰ HẾT**
  sau lượt hybrid công thức bump `TEXT_EXTRACTION_VERSION` (mọi chunk được
  OCR lại với code mới, đã gán đúng biến thể) — XÁC NHẬN bằng số trên, và nên
  **xoá dòng "cần rà soát nhãn variant" khỏi Ch.4/Ch.5 nếu còn**.

### 2.2 Bộ kiểm thử (Bảng 4.3, Ch.4 mục "Xây dựng bộ dữ liệu kiểm thử")

**Cấu trúc đổi hoàn toàn — viết lại đoạn mô tả, không chỉ đổi số:**

- Tổng **240 câu**, nhưng KHÔNG còn "192 văn bản (16/quyển) + 48 hình
  (4/quyển)" — đó là cấu trúc ĐÃ BỊ HUỶ (D-182). Cấu trúc mới:
  **158 văn bản + 52 hình + 30 ngoài phạm vi**, lấy mẫu HOÀN TOÀN NGẪU NHIÊN
  trên toàn corpus (một câu văn bản = rút 1 chunk `biology_text` ngẫu nhiên,
  một câu hình = rút 1 doc `biology_image_metadata` ngẫu nhiên), KHÔNG ràng
  buộc phủ đều 12 quyển. Tỉ lệ văn_bản/hình tính từ kích thước THẬT của index
  tại thời điểm sinh (`p_hinh = n_anh/(n_chunk+n_anh)` trên pool đã lọc,
  `n_chunk≈11444, n_anh≈3780 → p_hinh≈0,2483`), không phải một tỉ lệ chọn tay.
  **Nhóm thứ ba MỚI HOÀN TOÀN, chưa từng có trong báo cáo:** 30 câu **ngoài
  phạm vi** (Sử/Địa/Toán/Ngữ văn/...) — hệ thống PHẢI trả lời "không biết"
  thay vì bịa; đây là phép đo trực tiếp cho nguyên tắc 1 (không bịa) của repo,
  đáng đưa vào báo cáo như một đóng góp phương pháp, không chỉ một dòng phụ.
- **Phân bố thực tế theo quyển/NXB KHÔNG còn đều** (hệ quả tất yếu của lấy mẫu
  ngẫu nhiên) — tính bảng mô tả (không phải ràng buộc thiết kế) bằng:
  ```python
  import pandas as pd
  d = pd.read_csv('src/test/eval_results/draft.csv')
  print(d.groupby('source_book').size())
  print(d['loai'].value_counts())
  ```
  rồi trình bày như một bảng thống kê MÔ TẢ (không phải "đã chốt đều N/quyển"
  như bản cũ).
- Nguồn sinh câu hỏi: LLM (Groq) soạn câu bám sát chunk/ảnh cụ thể, **người
  duyệt tay xác nhận `human_reviewed:true`** (`src/test/eval_results/meta.json`)
  trước khi dùng — giữ nguyên tinh thần "người duyệt" của bản cũ, chỉ đổi cơ
  chế lấy mẫu.
- **Xoá mọi câu/bảng nói "đều 20 câu/quyển" hoặc "80 câu/NXB"** — không còn
  đúng.

### 2.3 Kết quả truy xuất (Bảng "4 phương pháp", đúng yêu cầu CBHD)

Nguồn: `src/test/eval_results/retrieval_report.csv`, cột `phuong_phap_bao_cao`
(bề rộng mặc định `cand_n=50`, KHÔNG phải bảng "n=20" — dùng đúng 4 dòng CBHD
yêu cầu, tái lập bằng `python -m src.test.retrieval_benchmark --chi-4-phuong-phap`):

| Phương pháp | MRR | R@1 | R@3 | R@10 |
|---|---|---|---|---|
| keyword (BM25 thuần) | 0,6636 | 0,0905 | 0,1475 | 0,2303 |
| dense (ngữ nghĩa thuần) | 0,5664 | 0,0647 | 0,1338 | 0,2302 |
| truyền thống (hybrid, rerank tắt) | 0,6947 | 0,0914 | 0,1609 | 0,2643 |
| **đề xuất (hybrid + rerank, production)** | **0,7789** | **0,1041** | **0,1804** | **0,2458** |

Đề xuất thắng mọi cột trừ R@10 (thua truyền thống 0,2458 vs 0,2643 — **khác
báo cáo cũ**, cần giải thích: giả thuyết hợp lý là `RERANK_SCORE_MIN=0,59`
(D-180, tăng từ 0,2) lọc bỏ một số ứng viên đúng ở hạng xa top-10; KHÔNG khẳng
định chắc nếu chưa đối chiếu thêm — nói đúng mức bằng chứng có, đừng đoán).

Bảng "Bề rộng PRODUCTION n=20" (đúng cấu hình `.env` thật, `cand_n=20`) cho
dòng đề xuất: **MRR 0,7789 · R@1 0,1037 · R@3 0,1790 · R@10 0,2410** — gần như
không đổi so với `cand_n=50`, khác biệt nằm trong dải làm tròn.

**Lưu ý quan trọng khi diễn giải R@k tuyệt đối thấp (~0,10-0,25):** đây là độ
đo trên **210 câu có gold chunk** (240−30 ngoài_phạm_vi), TÍNH TRÊN TOÀN BỘ
ỨNG VIÊN ĐÃ RERANK — số nhỏ hơn nhiều so với "Recall(page)" 0,88 của báo cáo
cũ vì đơn vị đo khác nhau (recall theo TRANG vs recall theo CHUNK CHÍNH XÁC ở
từng hạng k) — **đừng so trực tiếp hai bộ số này**, nói rõ đơn vị đo mỗi bảng.

### 2.4 Đánh giá đầu-cuối LLM-judge (theo LOẠI câu hỏi)

Nguồn: `src/test/eval_results/eval_report.md` (giám khảo Groq, 4 model xoay
vòng qua `JudgePool` — header CSV chỉ in tên model ĐẦU tiên của pool, không
phải model duy nhất, nói rõ trong báo cáo để không gây hiểu lầm):

| Loại | Số câu | Correct/5 | Faithful/5 | Relevancy/5 |
|---|---|---|---|---|
| Văn bản | 158 | 4,19 | 4,56 | 4,59 |
| Hình | 52 | 3,08 | 3,65 | 3,90 |
| Ngoài phạm vi | 30 | 4,87 | 5,00 | 5,00 |

Nhóm "Ngoài phạm vi" gần như hoàn hảo — bằng chứng trực tiếp hệ thống từ chối
đúng khi câu hỏi ngoài phạm vi KHTN, đáng nêu bật (đây là phép đo MỚI, D-182,
báo cáo cũ chưa từng có nhóm này). Nhóm "Hình" vẫn yếu nhất — nhất quán với
D-168 (retrieval yếu hơn ở CTST) nhưng cần xem lại lập luận cũ vì bộ câu hỏi
hình đã đổi hoàn toàn cách sinh.

### 2.5 Ablation multimodal M2C (MT4 vế ii) — D-189

| Độ đo | Text-only | Multi-modal-on | Δ |
|---|---|---|---|
| Correct | 3,077 | 3,000 | −0,077 |
| Faithful | 3,654 | 3,615 | −0,038 |
| Relevancy | 3,904 | 3,865 | −0,038 |

Đo trên đúng 52 câu "hình" (ghép cặp theo từng câu, không phải trung bình rời
rạc): 46/52 không đổi, 5 tệ đi 1 điểm, 1 tốt lên 1 điểm. **Kết luận DỨT
KHOÁT** (khác báo cáo cũ vốn viết "chưa đo được ưu thế" vì trần 0,104 của bộ
câu D-87 cũ): multi-modal context KHÔNG cải thiện, giữ
`MULTIMODAL_CONTEXT_ENABLED=false`. Đây là lần đầu MT4 vế (ii) có SỐ THẬT
đưa vào báo cáo — trước giờ chỉ có kết luận định tính. Nguồn:
`src/test/testset_m2c/m2c_ket_qua.md` (tái lập bằng `python -m
src.test.compare_m2c` nếu file không còn — không nằm trong git).

## 3. Công cụ cần SỬA TRƯỚC khi lấy số (đang trỏ nhầm đường dẫn cũ)

Ba script sau vẫn tham chiếu cấu trúc test cũ (đã xoá ở D-182) — sửa xong mới
tin số chúng in ra:

1. **`src/test/report_numbers.py`** — hàm đọc bộ test (dòng ~77, glob
   `*_testset.csv` trong `testsets_240/`) và `--testset-dir` mặc định
   (dòng ~170) vẫn trỏ thư mục ĐÃ XOÁ → in ra "0 câu". Sửa để đọc
   `src/test/eval_results/draft.csv` (một file, cột `question/loai/
   source_book/source_page/figure_label/ground_truth`) thay vì glob nhiều
   file theo quyển.
2. **`report/ve_hinh_chuong4.py`** — `CSV_EVAL` (dòng ~29) trỏ
   `src/test/evaluation_report_240.csv` (ĐÃ XOÁ ở D-182). Đổi thành
   `src/test/eval_results/eval_report.csv` — **schema đã KHỚP SẴN**
   (`loai_cau_hoi, num_questions, so_cau_co_diem_judge, judge_correctness,
   judge_faithfulness, judge_relevancy` — đúng cột `aggregate_by_loai()` của
   `run_eval.py` sinh ra), chỉ cần đổi đường dẫn, không cần sửa logic vẽ.
3. **`tests/test_bao_cao_so_lieu.py`** — `CSV_EVAL` (dòng ~20) cùng vấn đề,
   cùng cách sửa. Đây là lý do 2 test đang **SKIP** (không FAIL) — sửa xong,
   chạy lại để chúng PASS thật, đừng chỉ coi "skip" là chấp nhận được.

Sau khi sửa cả 3, chạy `python report/ve_hinh_chuong4.py` để sinh lại 5 hình
Ch.4 từ SỐ THẬT (đừng vẽ tay), rồi `pytest tests/test_bao_cao_so_lieu.py -v`
phải toàn PASS (0 skip).

## 4. Việc cần làm trong `report/tex_source/`

Đọc toàn bộ các chapter dưới trước khi sửa (đừng chỉ tìm-thay chuỗi mù —
nguyên tắc 4, phản biện chính mình):

- `src/chapters/0.tom_tat.tex` — đổi "16.393 đoạn văn bản" → "16.515", số
  R@1/R@10/MRR trong đoạn tóm tắt theo bảng §2.3, xoá câu "recall của cấu
  hình thật đạt 0,8833..." (đo trên bộ câu CŨ, phải viết lại theo đơn vị đo
  mới ở §2.3 — ĐỪNG chỉ đổi số mà giữ nguyên câu văn nếu đơn vị đo đã đổi).
- `src/chapters/4.hien_thuc_danh_gia_thao_luan.tex` (553 dòng) — viết lại:
  mục mô tả bộ test (§2.2 ở trên), Bảng 4.2 (giữ nguyên, chỉ đổi tổng chunk/
  vector nếu có ghi tay), Bảng 4.3 (theo §2.2), bảng 4 phương pháp (§2.3),
  bảng đánh giá theo LOẠI (§2.4), thêm một mục MỚI cho ablation M2C (§2.5 —
  báo cáo cũ chỉ có kết luận định tính "chưa đo được", nay có bảng số thật).
  Grep các chuỗi cần thay: `16.393`, `0,8833`, `192 câu`, `48 câu`, `20 câu/
  quyển`, `80 câu/NXB`, `chưa đo được ưu thế` (M2C).
- `src/chapters/5.ket_luan.tex` — đổi "16.393"/"20.274" theo §2.1; cập nhật
  câu kết luận MT4 nếu còn nói "vế (ii) chưa kết luận được" → nay ĐÃ kết
  luận (không cải thiện). Xoá dòng "cần rà soát nhãn variant" nếu còn (đã
  hết, xem §2.1).
- Kiểm `src/chapters/3.*` (thiết kế thực nghiệm — nếu có mô tả cấu trúc bộ
  test cũ) và bảng phụ lục nếu có.

## 5. Cập nhật `report/kiem_tra_tex.py` (danh sách cấm)

Thêm vào `SO_CU_BI_CAM`:
- `("16.393", "chunk văn bản: nay là 16.515 sau lượt hybrid công thức D-162")`
- `("20.274", "tổng vector: nay là 20.396 (16.515+3.881)")`
- `("192 câu văn bản", "cấu trúc bộ test cũ đã huỷ D-182; nay 158 văn bản + 52 hình + 30 ngoài phạm vi, lấy mẫu ngẫu nhiên")`
- `("48 câu hình", "cùng lý do trên — cấu trúc cũ đã huỷ")`
- `("chưa đo được ưu thế", "M2C nay đã có kết luận dứt khoát (D-189): không cải thiện")` — cẩn thận cụm này có thể khớp nhầm chỗ khác, đọc lại `.tex` trước khi thêm.

Sau khi thêm, chạy `python report/kiem_tra_tex.py` — PHẢI xanh trước khi build
PDF (nó chỉ lint, không dịch — xem `CLAUDE.md` mục "Lệnh").

## 6. Thứ tự thực hiện đề xuất

1. Sửa 3 công cụ (§3) → chạy `report_numbers.py --latex` xác nhận số khớp §2.1.
2. Chạy `ve_hinh_chuong4.py` sinh lại hình.
3. Viết lại 4 chapter (§4) theo số ở §2.
4. Cập nhật `kiem_tra_tex.py` (§5), chạy lint xanh.
5. `pytest tests/test_bao_cao_so_lieu.py tests/test_decision_log.py -v` — toàn
   PASS, 0 skip.
6. `powershell -File report/tex_source/build.ps1 -Clean` — build PDF thật, ghi
   lại số trang mới (báo cáo hiện tại 76 trang) và xác nhận 0 lỗi.
7. Ghi một entry **D-190** vào `document/decision_log.html` (số đo trước/sau,
   file đã sửa, số trang PDF mới) — theo đúng "định nghĩa xong" 4 bước của
   CLAUDE.md (decision log → CLAUDE.md → memory → spec → rồi mới commit).
8. Cập nhật CLAUDE.md: xoá mọi dòng "báo cáo LỖI THỜI HOÀN TOÀN" hiện đang
   gắn ở các dòng "Bộ test câu hỏi"/"Đánh giá đầu-cuối"/"Báo cáo" trong bảng
   tiến độ — thay bằng XONG + số mới + tham chiếu D-190.
9. Cập nhật memory `thesis_report_and_goals.md` (+ `MEMORY.md` index).
10. Hỏi người dùng trước khi commit (thay đổi lớn, nhiều file `.tex`) — không
    tự ý commit như quy tắc mặc định của phiên trước, TRỪ KHI người dùng đã
    dặn trước ở đầu phiên là cứ tự làm hết.

## 7. Việc KHÔNG nằm trong phạm vi prompt này

- Không sinh lại bộ câu hỏi hay chạy lại eval — dùng đúng dữ liệu đã có ở
  `src/test/eval_results/` + `src/test/eval_results_m2c/` (đã commit).
- Không đổi `RERANK_SCORE_MIN`/cấu hình production — chỉ phản ánh số đã đo.
- Không cần giải thích SÂU nguyên nhân R@10 giảm nhẹ ở cấu hình đề xuất (§2.3)
  nếu không có thời gian đo thêm — nói đúng mức bằng chứng, gắn cờ là câu hỏi
  mở, không bắt buộc phải đóng trong phiên này.
