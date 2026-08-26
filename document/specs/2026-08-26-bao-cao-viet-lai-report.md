# Báo cáo — VIẾT LẠI BÁO CÁO ĐỒ ÁN theo thực tế đã đo

**Ngày:** 2026-08-26 · **Prompt đầu vào:** `document/specs/2026-08-26-bao-cao-viet-lai-prompt.md`
**Quyết định ghi lại:** D-132 … D-136

---

## 0. Kết quả một dòng

Báo cáo đồ án **xong cả 5 chương + Tóm tắt + front matter**; `python report/kiem_tra_tex.py`
**thoát 0** (13 tệp); `pytest tests/ -q` → **686 pass, 3 skip**; 5 hình của Chương 4 nay
**sinh lại được** từ tệp kết quả thay vì là ảnh mồ côi.

Ngoài phạm vi được giao, ba lỗi thật bị phát hiện khi rà: sổ quyết định **không render
được từ 2026-08-25** (D-136), `_selection_meta.json` ghi sai một con số (D-135), và front
matter còn gọi tài liệu là *khoá luận* / *chuyên đề* (D-134).

---

## 1. Việc đã làm, đối chiếu với 5 việc được giao

| Việc | Trạng thái | Bằng chứng |
|---|---|---|
| **V1** Ch.4 §4.5.2 → hết §4.6 | **XONG**, và rộng hơn yêu cầu | Viết lại **từ §4.2 tới hết**, không chỉ từ §4.5.2 — vì §4.2/§4.3/§4.4 cũng mang số cũ (`3.880` vector hình, `240 câu`, `MiMo-v2.5-pro`) và một khẳng định sai (`người mở từng hình ra xem rồi viết câu hỏi`) |
| **V2** Ch.5 + Tóm tắt | **XONG** | Ch.5 nay đối chiếu thẳng MT1–MT5; Tóm tắt viết lại hoàn toàn |
| **V3** Rà lại Ch.1–3 | **XONG**, tìm được 8 lỗi | xem §3 dưới |
| **V4** `report/ve_hinh_chuong4.py` | **XONG** | 5 hình sinh từ `evaluation_report_240.csv`, đã **mở ra xem từng hình** |
| **V5** `kiem_tra_tex.py` thoát 0 | **XONG** | 13 tệp sạch; bộ lint được mở rộng thêm 10 mục cấm |

---

## 2. Lập luận trung tâm đã đổi (D-132) — phần quan trọng nhất

Báo cáo cũ nêu *"phát hiện quan trọng nhất"* là khoảng cách **trần 0,84 vs production
0,63**. Hai phép trùng khớp chính xác cho thấy cách gọi đó sai:

1. `evaluator.raw_recall_at_ks` gọi `hybrid_retriever.text_db.db.similarity_search_with_score`
   — Chroma thuần, **không** BM25, **không** rerank, **không** cổng lọc. Ba giá trị gộp
   231 câu **0,7706 / 0,8225 / 0,8961** trùng tới **chữ số thập phân thứ tư** với hàng
   `dense rerank=off gate=off` của `ablation_report_240.csv`.
   → Đó là trần của **một kênh**, không phải trần của hệ thống.
2. Recall production **0,9091** trùng **đúng** ô R@3 của hàng
   `hybrid rerank=on gate=off n=20`. Hợp lý vì hệ giữ `RETRIEVER_K = 3`.

**Kết luận mới:** cấu hình thật (0,9091) **vượt** trần của kênh ngữ nghĩa (0,8961).
Phần hụt do cắt-$k$ nay là **0,061** (R@3 0,9091 vs R@10 0,9697), không phải 0,21.

Nhờ đâu: **tắt** cổng lọc tương đối (R@10 kênh lai 0,892 → 0,970) và **bật** cross-encoder
(R@1 kênh dense 0,602 → 0,732, +21,6%). Điều đáng ghi về phương pháp: biện pháp được kỳ
vọng nhất — *siết* nhiễu bằng cổng lọc — hoá ra **có hại**.

**Ngoại lệ không được che:** `7_CTST` là quyển duy nhất prod (0,650) thấp hơn hẳn top-10
thô (0,900). Đếm từng câu trong `SGK_KHTN_7_CTST_result.csv`: **5 câu** trang vàng nằm
trong top-10 thô mà prod trượt, **0 câu** chiều ngược lại.

---

## 3. Rà lại Ch.1–3 và front matter (D-134) — lỗi mà bộ lint KHÔNG bắt

Bộ lint chỉ chặn được chuỗi mà **ai đó đã nghĩ ra để cấm**. Đọc đủ **13 tệp `.tex`** (không
chỉ 6 chương) tìm ra:

| Tệp | Lỗi | Đã sửa thành |
|---|---|---|
| `hoi_dong.tex` | tiêu đề *"KHÓA LUẬN TỐT NGHIỆP"*, mục lục *"CHUYÊN ĐỀ TỐT NGHIỆP"* | ĐỒ ÁN TỐT NGHIỆP |
| `loi_cam_on.tex` | *"báo cáo chuyên đề tốt nghiệp"* | đồ án tốt nghiệp |
| `2.co_so_ly_thuyet.tex` | *"Google Colab Pro hoặc GPU cá nhân"* | trỏ về Bảng môi trường (máy **CPU**) |
| `2.co_so_ly_thuyet.tex` | *"trợ lý ảo môn Sinh học"* | môn Khoa học tự nhiên |
| `3.phuong_phap_thuc_hien.tex` | metadata ảnh *"bao gồm caption tiếng Việt"* | ba trường **đọc lại từ điểm ảnh**; trường model-sinh **rỗng toàn kho** |
| `3.phuong_phap_thuc_hien.tex` | *"Next.js 14"* | **16.2.6 / React 19.2.4** (đọc `package.json`) |
| `3.phuong_phap_thuc_hien.tex` | 4 chỗ *"giao diện trợ lý ảo Sinh học"* | Khoa học tự nhiên |
| `4.…tex` | `3.880` vector hình, `20.273` tổng vector, KNTT 285/215/235 | **3.881**, **20.274**, **286/216/234** |

Thêm: `danh_muc_viet_tat` thiếu hẳn CPU/ETL/BM25/MRR/RRF/CLIP/IR; `danh_muc_dich` thiếu 11
thuật ngữ truy xuất lai / xếp hạng lại / ablation — dù Ch.2–4 dùng dày đặc.

**Hai chỗ Ch.3 được bổ sung chứ không chỉ sửa:** (i) nói rõ **chưa có giáo viên bộ môn nào**
rà soát siêu dữ liệu ảnh của cả kho (công cụ có, quy trình chưa chạy ở quy mô đó); (ii) mục
§3.4 liệt kê **ba khoảng cách của giao diện so với MT5**, kiểm được bằng cách đọc mã nguồn FE.

---

## 4. Hai lỗi ngoài phạm vi, phát hiện khi rà

### 4.1 Sổ quyết định không render được (D-136) — nghiêm trọng nhất

`document/decision_log.html` là **SyntaxError từ 2026-08-25**: mục D-117 có trường `notes`
xuống dòng giữa chừng, mà chuỗi JavaScript trong dấu nháy kép không được chứa ký tự xuống
dòng thật. Cả trang không render nổi **một** mục nào, trong khi tệp vẫn mở được bằng trình
soạn thảo và vẫn được commit bình thường.

Ba giả thuyết **bị bác bỏ** trước khi tìm ra (ghi lại để khỏi thử lại):

- *ký tự điều khiển lọt vào* — quét `ord(c) < 32` cho **0**, vì phép quét đó **cố ý loại trừ
  `\n`**, đúng thứ đang gây lỗi;
- *escape hỏng* — đọc lại byte thì `\"` hợp lệ;
- *`\u` / `\x` thiếu chữ số hex* (thứ **duy nhất** JS coi là lỗi trong các escape lạ, khác
  `\a` hay `\l` vốn hợp lệ) — quét ra **0**.

Chỉ khi **tự viết bộ lex chuỗi theo luật JS** mới lộ ra: đúng **1/136 mục**, dòng 703.
Mỉa mai: mục hỏng chính là mục **viết về bẫy dấu gạch chéo ngược**.

Đã sửa (nối lại một dòng, không đổi ký tự nội dung) và thêm `tests/test_decision_log.py`.
**Test đã được kiểm là không rỗng:** trả tệp về bản HEAD thì test đỏ đúng dòng 703.

### 4.2 `_selection_meta.json` ghi sai (D-135)

Tệp ghi *"6/9 khung cắt bị loại thuộc Kết nối tri thức"*. Đếm lại trên chính bộ test:
phần hình còn **CD 15 · CTST 15 · KNTT 9** trên nền dự kiến 16 mỗi bộ → mất
**CD 1 · CTST 1 · KNTT 7**. Con số **7** còn khớp với "7 ca cắt thiếu" mà chính phiếu ghi.
Đã sửa tại chỗ kèm ghi rõ nó sai ở đâu; báo cáo thì **suy từ phân bố cuối cùng**, là thứ
người đọc kiểm lại được.

---

## 5. `report/ve_hinh_chuong4.py` (D-133)

Trước đó repo có **0** script vẽ (`grep -rl matplotlib src/ report/ scripts/` = 0), nên 5
tệp PNG dựng từ bộ 120 câu cũ là số không ai kiểm và không ai cập nhật được.

- Mọi giá trị đọc từ `evaluation_report_240.csv`, gộp theo **CÂU** (`_gop`), không phải
  trung bình theo quyển — hai cách lệch nhau ở hàng thập phân thứ ba.
- `recall_at_k.png` **đổi hẳn nội dung** để khớp D-132: ba cột top-$k$ thô của kênh ngữ
  nghĩa + một cột **cấu hình thật nằm trên đường trần**.
- Màu lấy từ bộ ba đã qua bộ kiểm CVD ở chế độ all-pairs; vì báo cáo **đem đi in**, mỗi màu
  kèm một kiểu gạch chéo 45°/135°.
- **Đã mở ra xem cả 5 hình**: bắt được 3 lỗi bố cục mà script không tự biết (chú thích đè
  nhãn giá trị, chú giải đè cột ở 3 hình, nhãn giá trị đè chấm). **Bộ kiểm màu không kiểm
  bố cục.**

---

## 6. Số đã đo lại trong lượt này (không lấy từ prompt)

| | Giá trị | Ghi chú |
|---|---|---|
| Vector hình | **3 881** | prompt ghi 3 881, `.tex` ghi 3 880 → đo lại, `.tex` sai |
| Loại hình | `single_figure` **2 172** · `sub_figure` 824 · `activity_box` 442 · `composite_figure` 324 · `textbook_info_box` 87 · `tool_group` 32 | tổng 3 881 |
| Vector hình KNTT 6/7/8/9 | **286 / 203 / 216 / 234** | `.tex` cũ ghi 285/215/235 |
| Chunk có `bai_so` | **4 857 / 16 393 = 29,6%** | KNTT 1 086/1 037/1 212/1 522; 8 quyển kia **0** |
| `needs_review` | **11 362 / 16 393 = 69,3%** | trước chỉ có dải theo quyển 57–84% |
| `variant='kntt'` sai | CD 5 282 + CTST 6 177 = **11 459** | khớp prompt |
| Dải dọc hẹp | KNTT 1,4/2,0/1,8/1,7% → gộp **1,7%**; toàn kho **4,6%** | `qa_crop_shape` |
| Độ phủ nhãn hình | CD 94/92/96/97 · CTST 72/83/88/89 · KNTT **96/95/97/95** | `qa_figure_coverage` |
| Precision (page), gộp | **0,4112** | prompt ghi 0,4113 — đó là `P@3` của bảng ablation, khác nguồn |
| Test suite | **686 pass, 3 skip** | CLAUDE.md ghi 617 đã cũ |

---

## 7. Trạng thái tệp khi bàn giao

**Đã sửa / thêm (chưa commit khi viết dòng này):**

```
report/tex_source/src/chapters/0.tom_tat.tex          viết lại
report/tex_source/src/chapters/1.tong_quan_de_tai.tex  thêm 1 câu trỏ tới §4.5.4
report/tex_source/src/chapters/2.co_so_ly_thuyet.tex   2 chỗ
report/tex_source/src/chapters/3.phuong_phap_thuc_hien.tex  7 chỗ + mục MT5 mới
report/tex_source/src/chapters/4.hien_thuc_danh_gia_thao_luan.tex  viết lại từ §4.2
report/tex_source/src/chapters/5.ket_luan.tex          viết lại
report/tex_source/src/loi_cam_on.tex                   1 chỗ
report/tex_source/src/hoi_dong.tex                     3 chỗ
report/tex_source/src/danh_muc_viet_tat.tex            +7 dòng
report/tex_source/src/danh_muc_dich.tex                +11 dòng
report/tex_source/src/images/chapter4/*.png            5 hình sinh lại
report/ve_hinh_chuong4.py                              MỚI
report/kiem_tra_tex.py                                 +10 mục cấm
tests/test_bao_cao_so_lieu.py                          MỚI (5 test)
tests/test_decision_log.py                             MỚI (3 test)
src/test/testsets_240/_selection_meta.json             sửa con số sai
document/decision_log.html                             sửa D-117 + thêm D-132..D-136
CLAUDE.md                                              bảng MT + bảng tiến độ + lệnh
```

---

## 8. Việc tiếp theo — đề xuất thứ tự

1. **MT5 (FE)** — ba việc nhỏ, tác động lớn nhất: nạp KaTeX; **hiển thị lại trường
   `citations`** mà API đã trả (cơ chế của nguyên tắc 1 hiện **không tới được mắt học
   sinh**); đưa URL máy chủ ra biến môi trường. Repo: `D:\personal_repo\project_rag_fe`.
2. **MT1 (công thức)** — dùng MinerU **chỉ cho vùng công thức**, giữ Tesseract cho văn xuôi
   (D-108). Chưa đo, cần before/after trên chính phiếu 97 ô.
3. **`bai_so` cho 8 quyển CD/CTST** — không cần chạy lại ETL; xem §6 của prompt bàn giao.
4. **Bộ câu hỏi sinh từ HÌNH có người đối chiếu ảnh** — điều kiện tiên quyết để kết luận
   được vế (ii) của MT4; trần hiện tại 0,104 chặn mọi so sánh.

## 9. Còn chờ người dùng

**Không còn gì.** Câu hỏi *"push các commit lên `origin/master`?"* đã được người dùng trả
lời 2026-08-26: **đã push hết**. Kiểm lại bằng `git rev-list --left-right --count
origin/master...master` → **`0  0`**, tức hai nhánh bằng nhau và `85ee3f2d` đã ở trên remote.

Từ đây trở đi cứ commit thẳng lên `master` và push, không cần hỏi lại.
