# Prompt bàn giao — VIẾT LẠI BÁO CÁO ĐỒ ÁN theo thực tế đã đo

**Ngày lập:** 2026-08-26 · **Chốt tại:** D-129 (nguồn sự thật), D-130 (số eval), D-131 (kho ảnh)
**Trạng thái repo khi bàn giao:** `master` sạch, **3 commit chưa push** (`86d534dc`, `0951ef2b`,
`d172985b`) + commit của chính spec này. `pytest tests/ -q` chưa chạy lại sau D-131 — chạy
trước khi kết thúc mốc.

---

## 0. Luật bất di bất dịch cho session sau

1. **Đọc `CLAUDE.md` trước.** RULE #0: `document/goal.docx` (đề cương đã ký 13/07/2026) là
   nguồn yêu cầu duy nhất.
2. **`report/tex_source/` CHỈ LÀ KHUNG CẤU TRÚC (D-129).** Nó là source của **báo cáo chuyên
   đề cũ**. Dùng nó để tham vấn **bố cục chương mục**; **mọi số liệu và phương pháp** lấy từ
   `goal.docx` + phép đo thật trong repo hôm nay. **Đừng vá từng chỗ lint bắt được rồi mặc
   nhiên coi phần còn lại là đúng** — đó chính là sai lầm của các lượt trước.
3. **Không bịa.** Mỗi con số vào báo cáo phải chỉ được ra file/lệnh sinh ra nó. Số nào chưa đo
   thì viết "chưa đo", không viết "khoảng", không viết "dự kiến đạt".
4. **Máy KHÔNG có LaTeX.** Kiểm bằng `python report/kiem_tra_tex.py` (ref/cite/gói/ký tự điều
   khiển/**số cũ**). Mục tiêu: **thoát 0**.
5. **Bẫy backslash khi vá `.tex`:** heredoc làm sập `\\` thành `\`, rồi Python biến `\a` thành
   BEL, `\t` thành TAB. **Dùng Write tool + chuỗi thô**, rồi quét ký tự điều khiển. (memory
   `backslash_heredoc_trap`)
6. **Ghi log ngay trong lượt:** `document/decision_log.html` (tiếp từ **D-131**) + `CLAUDE.md`
   (kể cả bảng "Trạng thái tiến độ") + memory + spec, **rồi mới commit**. Commit message
   thuần, **không** `Co-Authored-By`.

---

## 1. Việc phải làm, theo thứ tự

### V1. Ch.4 §4.5.2 → hết §4.6 (`report/tex_source/src/chapters/4.hien_thuc_danh_gia_thao_luan.tex`)

Hiện trạng: từ dòng ~317 tới hết file là **nguyên văn báo cáo chuyên đề cũ** (bộ 120 câu,
judge MiMo, MiniLM, A100, Vintern). Các mục:

| Mục | Dòng | Phải làm |
|---|---|---|
| §4.5.2 Độ đo tổng quát | 317 | thay bảng `tab:summary` bằng số ở §2 dưới |
| §4.5.3 Xếp hạng 12 bộ sách | 344 | thay bảng `tab:leaderboard` + 2 hình |
| §4.5.4 Phân tích Recall@k | 390 | **viết lại lập luận**: khoảng cách trần/production đã bị XOÁ |
| §4.5.5 Chất lượng câu trả lời | 437 | số giám khảo mới + `judge_scores.png` |
| §4.6 Thảo luận | 447 | **viết lại 5 nhận định** — xem §4 dưới |
| §4.6.1 Đa phương thức | 459 | **XOÁ tuyên bố giáo viên đánh giá**; dùng phép đo 39 câu hình |
| §4.6.2 Ưu điểm | 462 | bỏ Vintern, bỏ "giao diện mượt mà" (không đo) |
| §4.6.3 Hạn chế | 470 | bỏ A100, bỏ "recall 0,63", thêm hạn chế THẬT ở §5 |

### V2. Ch.5 `5.ket_luan.tex` + Tóm tắt `0.tom_tat.tex`

Cả hai **chưa động tới**. Sai từ gốc: gọi đề tài là *"trợ lý ảo … môn **Sinh học**"* và
*"báo cáo **chuyên đề**"*. Phải theo `goal.docx`: **ĐỒ ÁN TỐT NGHIỆP**, môn **Khoa học tự
nhiên** tích hợp Lý–Hoá–Sinh, 5 mục tiêu MT1–MT5.

### V3. Rà lại Ch.1, Ch.2, Ch.3

Đã viết lại ở D-117/D-118 nhưng **chưa rà theo luật D-129**. Đọc lại một lượt, đối chiếu
`goal.docx`; đừng giả định chúng đúng.

### V4. Sinh lại 5 hình của Ch.4

`report/tex_source/src/images/chapter4/{leaderboard,retrieval_vs_answer,recall_at_k,recall_per_book,judge_scores}.png`
đều dựng từ bộ 120 câu cũ và **repo KHÔNG có script sinh lại**
(`grep -rl matplotlib src/ report/ scripts/` = 0). Viết `report/ve_hinh_chuong4.py` đọc
`src/test/evaluation_report_240.csv` — **đừng vẽ tay, đừng chỉnh số trong hình**.

### V5. `python report/kiem_tra_tex.py` phải thoát 0

Hiện **9 vấn đề**: `120 câu` ×3 (`0.tom_tat.tex:6`, `4.…:4`, `4.…:322`, `5.ket_luan.tex:13`),
`MiMo-v2.5-pro` ×4 (`4.…:177, 213, 349, 443`), `A100` ×1 (`4.…:474`).
**Cảnh báo:** `120 câu` phải thành **231 câu**, KHÔNG phải 240 — bộ test thực tế là
192 văn bản + **39** hình (9/48 khung cắt bị người duyệt loại). Nếu `kiem_tra_tex.py` gợi ý
"240 câu" thì **sửa chính bộ lint**, vì nó đang mang số dự kiến chứ không phải số thật.

---

## 2. SỐ ĐỂ DÙNG — đã đo, KHÔNG cần đo lại

### 2.1 Kho tri thức (`python -m src.test.report_numbers`)

| | Giá trị | Số cũ trong `.tex` |
|---|---|---|
| Trang trên đĩa | **2 399** (12 quyển / 3 NXB) | 2 319 |
| Trang có chỉ mục | **2 387** (chênh đúng 12 = trang bìa, `role=cover`) | — |
| Chunk văn bản | **16 393** | 13 754 |
| Vector hình | **3 881** | 2 408 |
| Nhúng | `BAAI/bge-m3`, **1024 chiều** | MiniLM 384 chiều |
| BM25 | 16 393 chunk / **19 727 từ vựng**, `k1=0,7 b=0,75`, giữ dấu | không có |
| Caption sinh bởi model | **0** (captioner TẮT — D-47) | 2 384 |
| Môi trường | **CPU**, `torch 2.11.0+cpu`, 16 lõi, 63,9 GB | A100 40GB |

Loại hình: `single_figure` 1 418 · `sub_figure` 824 · `activity_box` 339 ·
`composite_figure` 274 · `textbook_info_box` 68 · `tool_group` 19.

### 2.2 Bảng đối chiếu truy xuất — MT4 (i)+(iii) (`src/test/ablation_report_240.csv`)

**Bề rộng production (20 ứng viên/kênh, rerank BẬT, cổng lọc TẮT), 231 câu:**

| Cấu hình | MRR | R@1 | R@3 | R@5 | R@10 |
|---|---|---|---|---|---|
| **hybrid** | **0,8255** | **0,7403** | **0,9091** | **0,9264** | **0,9697** |
| bm25 | 0,8130 | 0,7316 | 0,8874 | 0,9221 | 0,9481 |
| dense | 0,7981 | 0,7229 | 0,8658 | 0,8831 | 0,9264 |

**Tác dụng rerank (bề rộng 50, rrf, gate off):** hybrid MRR 0,7619→**0,8321**, R@1
0,6710→**0,7446** · dense MRR 0,6988→**0,8135**, R@1 0,6017→**0,7316** (+21,6%) · bm25
0,7654→0,8251. **Rerank là công tắc đóng góp lớn nhất.**

**Cổng lọc tương đối CÓ HẠI:** hybrid n=20 R@10 **0,9697→0,8918**, MRR 0,8255→0,7746;
tệ nhất `dense+gate+norm` R@10 **0,7922**. → `RELEVANCE_GATE_ENABLED=false` là mặc định.

**`trầnP@5 = 0,979` ở mọi hàng** — trần do bộ test quy định, không do hệ thống.

### 2.3 Đánh giá đầu-cuối (`src/test/evaluation_report_240.{csv,md}`) — D-130

Gộp trên **231 câu** (không phải trung bình theo quyển):

| Độ đo | Giá trị | Số cũ |
|---|---|---|
| Recall (production, page) | **0,9091** | 0,63 |
| MRR (page) | **0,8153** | 0,51 |
| Precision (page) | **0,4113** | 0,38 |
| Recall thô @3 / @5 / @10 | **0,7706 / 0,8225 / 0,8961** | 0,66 / 0,77 / 0,84 |
| Recall (book-level) | **0,9567** | — |
| Precision (book-level) | **0,5455** | — |
| Correctness /5 | **4,065** | 3,76 |
| Faithfulness /5 | **4,394** | 4,25 |
| Relevancy /5 | **4,602** | 4,36 |
| overall (TB theo quyển) | **0,7924** | 0,67 |

Xếp hạng (overall · R · MRR · Correct/5): `8_KNTT` 0,879 · 1,00 · 0,944 · 4,44 |
`6_CTST` 0,862 · 1,00 · 0,939 · 4,26 | `8_CD` 0,821 · 0,95 · 0,867 · 4,30 |
`6_CD` 0,812 · 0,95 · 0,892 · 4,05 | `6_KNTT` 0,806 · 0,94 · 0,882 · 4,00 |
`8_CTST` 0,804 · 0,95 · 0,808 · 4,10 | `9_KNTT` 0,798 · 0,94 · 0,852 · 3,94 |
`9_CD` 0,788 · 0,85 · 0,767 · 4,25 | `7_KNTT` 0,786 · 0,95 · 0,892 · 3,90 |
`7_CD` 0,756 · 0,95 · 0,719 · 3,68 | `9_CTST` 0,701 · 0,80 · 0,625 · 3,75 |
`7_CTST` 0,697 · 0,65 · 0,625 · 4,10.

Judge: **`stealth/ox-alpha` qua OpenRouter** (KHÔNG phải MiMo, KHÔNG phải Gemini).

### 2.4 Bộ kiểm thử: **231 câu**

192 văn bản + **39 hình** · CD 79 / CTST 79 / KNTT 73 · 179 trực tiếp + 52 suy luận ·
phân môn: hoá 69 · lý 54 · sinh 47 · khác 22 · 39 câu hình chưa gán phân môn.

### 2.5 Kho ảnh & chất lượng khung cắt

Độ phủ nhãn (`python -m src.test.qa_figure_coverage`): CD 94/92/96/97% · KNTT **96/95/97/95%** ·
CTST 72/83/88/89% (chỉ `6_CTST` dưới ngưỡng 0,80).
Dải dọc hẹp (`python -m src.test.qa_crop_shape`): KNTT **17,5% → 1,7%** sau vá D-126/D-131;
toàn kho **8,4% → 4,6%**. G4 trên 4 quyển KNTT: **0 gán sai Bài, 0 thiếu**.

---

## 3. §4.6.1 — NGƯỜI DÙNG ĐÃ CHỐT: dùng phép đo 39 câu hình

**XOÁ** hai khẳng định sai trong bản cũ: *"đánh giá thủ công với sự tham gia của giáo viên bộ
môn"* và *"chú thích tiếng Việt do Vintern-1B sinh"*. Thay bằng đúng những gì đã xảy ra, đọc
từ `src/test/testsets_240/_selection_meta.json`:

- Máy chọn **48 khung cắt** (4/quyển) → LLM viết **nháp** câu hỏi + đáp án **từ chú thích và
  chữ OCR quanh hình** → người duyệt qua phiếu HTML.
- **Người đã làm:** loại **9/48 khung cắt hỏng**, ghi lý do — **7 "cắt thiếu"**, 1 "cắt lấn",
  1 khác; **6/9 thuộc Kết nối tri thức**. Chính tín hiệu này dẫn tới D-125 → D-126 → D-131.
- **Người CHƯA làm:** không sửa nội dung câu hỏi nào — **39/39 câu giữ nguyên 100% bản nháp
  của mô hình**. Đo trên chính tệp phiếu: lượt 1 duyệt 48 ô trong 2,3 phút; lượt 2 duyệt 40 ô
  trong 3,3 phút (**4,9 giây/ô**).
- **Hệ quả phải viết ra:** mô hình sinh nháp **không nhìn thấy hình**, nó suy từ chú thích +
  OCR. Nên 39 câu hình là **do LLM sinh, chưa được người đối chiếu ảnh**.
- **Kết quả đa phương thức (D-87), phải kèm giới hạn:** text_R 0,930 → mm_R 0,940
  (**delta +0,010 = đúng 1 câu**); độ phủ token đáp án 0,896 → 0,900 (tăng ở 14 câu, giảm ở 0);
  +492 ký tự ngữ cảnh/câu. Vì `ground_truth` sinh từ chính văn bản trang vàng nên
  **trần còn lại cho kênh hình chỉ 0,104** → kết luận đúng là **"CHƯA đo được ưu thế"**,
  KHÔNG phải "đa phương thức vô ích". `MULTIMODAL_CONTEXT_ENABLED` giữ **false**.

---

## 4. §4.6 — 5 nhận định cũ SAI ở đâu

| Nhận định cũ | Vì sao sai hôm nay |
|---|---|
| "Nút thắt ở khâu xếp hạng/cắt-k: trần 0,84 vs production 0,63, khoảng cách 0,21" | **Khoảng cách đã bị xoá**: production **0,909** ≈ trần **0,896**. Viết lại thành *đã khắc phục bằng cách nào* (tắt cổng lọc + bật cross-encoder), kèm số trước/sau |
| "MiniLM yếu với câu hỏi ngắn/trừu tượng" | Hệ nay dùng **bge-m3 1024 chiều** + `bge-reranker-v2-m3`. Thay bằng nhận định đo được: **dense thuần yếu nhất khi TẮT rerank (R@1 0,602) và được rerank cứu nhiều nhất (+21,6%)** |
| "Nhiễu chéo giữa các bộ sách → Precision 0,38" | Vẫn đúng về bản chất, số mới **0,411**; bằng chứng mạnh hơn: `Precision(book)` **0,5455** và `Recall(book)` **0,9567** |
| "Khoảng cách giữa độ đo IR và giám khảo" | Giữ, cập nhật số |
| "Sai số OCR" | Giữ nhưng **cụ thể hoá bằng D-56/D-63**: chỉ số dưới hỏng:đúng = CD 256:3 · CTST 377:3 · KNTT 408:4, `₂` Unicode **0 lần**; và bake-off D-108 đã chứng minh **có model đọc được** `CO₂` nhưng bị loại vì lỗi DẤU 0,037 > 0,016 |

---

## 5. Hạn chế THẬT phải đưa vào §4.6.3 và Ch.5 (thay danh sách cũ)

1. **Bộ test do LLM sinh, chưa người duyệt toàn bộ** — `human_reviewed: false`; mẫu 50 câu
   người duyệt cho **gold key sai 2/49 = 4,1%**, KTC Wilson 95% **1,1–13,7%** (cận trên nghĩa
   là tới ~9/231 câu vẫn có thể sai mà mẫu không thấy). 39 câu hình thì **chưa ai đối chiếu ảnh**.
2. **Công thức Hoá/Lý (MT1) chưa xử lý** — D-56 chưa giải; đây là **hạng mục hợp đồng** của
   đề cương, phải nói thẳng là còn nợ, kèm hướng đã có số (MinerU chỉ cho vùng công thức).
3. **`bai_so` chỉ có ở 4/12 quyển** — 4 857/16 393 chunk; 8 quyển CD/CTST spine chưa liền mạch
   nên hệ **cố tình không ghi** (thiết kế: thiếu thì im, không đoán).
4. **11 459 chunk CD/CTST vẫn mang `variant='kntt'`** (D-109) — code đã sửa (D-111) nhưng dữ
   liệu chỉ sạch sau lần bump `TEXT_EXTRACTION_VERSION`. **Đừng viết là đã khắc phục.**
5. **Khung cắt hình ghép còn hụt** — D-131: dải hẹp KNTT 17,5%→1,7% nhưng ca gốc
   (`8_KNTT` tr.6 `Hình 1.1`, 3 panel) **vẫn cắt sai** (135×289 → 209×289); phần hụt còn lại
   **chưa lượng hoá được**.
6. **`needs_review` mất tác dụng** — bật ở 57–84% chunk.
7. **MT5 chưa đủ** — FE (`D:\personal_repo\project_rag_fe`) **không có KaTeX/MathJax**, **bỏ
   hẳn trường `citations`** mà API đã trả, và hardcode `http://localhost:5000`.
8. **Bảng/cột (D-63)** — chunk không giữ quan hệ hàng/cột nên có thể trả lời từ **sai cột**.

---

## 6. Câu hỏi `bai_so` — ĐÃ TRẢ LỜI, đừng đo lại

**Không cần chạy lại ETL.** `loader.py:107` chỉ **tra bảng**: `manifest.pages[page].bai_so`,
gác bởi `spine_is_trusted(source)`. Manifest CD/CTST **đã có** `bai_so` theo trang
(`KHTN6-CD` 176/179, `KHTN6-CTST` 187/204); thứ chặn là cờ `bai_numbers_not_contiguous`.

Hai bước, không bước nào là ETL:
1. **Sửa bộ đọc MỤC LỤC CD/CTST** cho spine liền mạch → `--build-manifests` (**~50 phút**,
   không OCR thân bài). Hiện CTST đọc 23/17/17/21 mục, CD 32/24/23/29; `6_CD` thiếu Bài 3, 4, 34.
2. **Nạp bù metadata** cho 11 536 chunk: `collection.update(ids=..., metadatas=...)` — **vài
   phút, KHÔNG nhúng lại**. Chroma chỉ nhúng lại khi truyền `documents=` (bẫy D-122).

**CẤM** nạp bù trước khi spine sạch: ghi `bai_so` từ spine mang cờ `not_contiguous` là ghi vào
index một con số mình không tin (nguyên tắc 1). Bump `TEXT_EXTRACTION_VERSION` **không giúp gì**
cho `bai_so` mà tốn 3 h 20 OCR lại.

---

## 7. CẤM (11 điều, rút từ các lượt đã dính)

1. Cấm lấy bất kỳ số nào từ `report/main_chuyende_totnghiep.pdf` hoặc từ bản `.tex` cũ.
2. Cấm viết "đã khắc phục" cho `variant='kntt'`, cho D-56, cho crop hình ghép.
3. Cấm nói "giáo viên bộ môn đã đánh giá" — **chưa hề có**.
4. Cấm nhắc Vintern-1B như một thành phần đang chạy (captioner TẮT, `visual_caption_vi` = 0).
5. Cấm ghi môi trường là GPU/A100/Colab Pro — **CPU**.
6. Cấm viết "240 câu" — bộ test thật là **231**.
7. Cấm `git add -A` khi có tiến trình nền đang sửa file nguồn (D-126 đã dính: một commit
   *docs* cuốn theo thay đổi ETL chưa duyệt).
8. Cấm sửa text đã OCR để "chữa" công thức (CẤM cũ #5 — đoán lại chỉ số dưới là bịa).
9. Cấm chạy cả `pytest tests/` trong lúc lặp; chỉ chạy test của phần vừa sửa.
10. Cấm tuyên bố một cổng đo xanh là "phần việc đó đúng" — mỗi cổng chỉ trả lời câu hỏi của
    nó (memory `measurement_blind_spots`).
11. Cấm để `kiem_tra_tex.py` thoát khác 0 mà vẫn nói "báo cáo xong".

---

## 8. Trạng thái file khi bàn giao

- `report/tex_source/src/chapters/`: `0.tom_tat.tex` (9 dòng, **cũ**), `1` (55, xong),
  `2` (99, xong), `3` (136, xong), `4` (475, **xong tới §4.5.1**), `5` (32, **cũ**).
- `report/kiem_tra_tex.py`: **9 vấn đề**, tất cả là `[socu]`.
- `src/test/`: `evaluation_report_240.{csv,md}` (12 quyển, 231 câu), `ablation_report_240.csv`
  (30 hàng), `testsets_240/*_result.csv` (12 file), `qa_crop_shape.py` (cổng mới).
- `tests/`: `test_evaluator_cli.py` (11), `test_fallback_crop_width.py` (4) — mới, đã xanh.
- Kho dữ liệu: text 16 393 chunk / ảnh 3 881 doc, **KNTT vừa dựng lại 26/08**.

## 9. Còn chờ người dùng

- **Push 3–4 commit lên `origin/master`?** (đã hỏi, chưa trả lời)
- Sau khi báo cáo xong, thứ tự đề xuất: **MT5 (FE: KaTeX + citations + URL)** → **MT1 (MinerU
  cho vùng công thức)** → **`bai_so` cho 8 quyển CD/CTST**.
