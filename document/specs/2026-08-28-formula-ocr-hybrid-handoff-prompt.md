# Prompt bàn giao — thực thi plan hybrid Tesseract + MinerU (Bước 2+3)

**Dùng file này khi:** phiên Claude Code cũ đã hết hạn mức, hoặc bạn đem việc
này sang một công cụ AI khác (Antigravity, Cursor, v.v.) không có sẵn skill
"superpowers", không đọc được memory cá nhân của Claude Code, và không tự biết
những quyết định/quy ước đã có trong repo này. File này TỰ ĐỦ — không giả định
người/AI đọc nó biết bất kỳ điều gì ngoài chính nó và các file nó trỏ tới.

## 0. Việc cần làm, tóm tắt một câu

Thực thi ĐÚNG THEO THỨ TỰ 11 task đã viết sẵn, đầy đủ code, trong file:

**`document/specs/2026-08-28-formula-ocr-hybrid-buoc23-plan.md`**

File đó là plan hoàn chỉnh theo phong cách TDD (mỗi task: viết test thất bại →
chạy xác nhận FAIL → viết code → chạy xác nhận PASS → commit). Đọc file đó
TRƯỚC, đọc file này để hiểu bối cảnh và các quy ước phải theo mà bản thân plan
không nhắc lại (vì plan giả định người thực thi đã biết các quy ước của repo).

## 1. Bối cảnh dự án (để hiểu VÌ SAO, không chỉ LÀM GÌ)

Đây là một RAG system tiếng Việt trên sách giáo khoa KHTN (Khoa học Tự nhiên,
THCS), OCR bằng Tesseract, phục vụ hỏi-đáp có trích dẫn. Repo là một **đồ án
tốt nghiệp** — nguồn yêu cầu duy nhất là `document/goal.docx` (đề cương đã ký).

**Vấn đề đang giải quyết:** Tesseract phá hỏng chỉ số dưới trong công thức Hoá
(`O₂` → đọc thành `0,`, `CO₂` → `CO,` hoặc `(0,`), khiến RAG trả lời sai kiến
thức hoá học cho học sinh (ví dụ: đảo ngược "hấp thụ CO₂, thải O₂" thành ngược
lại vì cả hai đều đọc ra `0,`). Đã đo: chỉ **4/281** lần chỉ số dưới xuất hiện
là được Tesseract đọc đúng trên toàn kho 12 quyển sách.

**Giải pháp đã CHỐT (người dùng quyết định, chấp nhận trễ deadline đồ án):**
hybrid OCR — giữ Tesseract cho văn xuôi (đọc tốt, 93% nội dung), gọi model
MinerU2.5 (một Vision-Language Model, cần GPU) CHỈ cho những dòng bị nghi là
công thức, rồi ghép kết quả đúng của MinerU vào đúng vị trí, không đụng phần
còn lại.

**Việc đã xong trước khi có plan này (đọc để không làm lại):**
- Đã thử THAY HẲN Tesseract bằng MinerU cho cả trang — bị LOẠI vì MinerU đọc
  công thức tốt hơn 9,2 lần nhưng đọc dấu tiếng Việt TỆ HƠN 2,3 lần (93% nội
  dung là chữ thường, nên thua ở đó là thua chung cuộc). Quyết định này đã
  KHOÁ, đừng thử lại thay-cả-trang.
- Đã xây và đo được một "gate" (bộ lọc) quyết định "dòng chữ Tesseract đọc
  được này có nghi là công thức bị vỡ không" — đo trên 89 dòng mẫu (người đã
  xác nhận đáp án đúng), đủ cả 3 nhà xuất bản: precision 0,8654, recall 1,0000.
  Code đã có sẵn ở `src/etl/layout/formula_gate.py::is_formula_suspect()`.
- Plan 11 task (file ở mục 0) thiết kế CÁCH GỌI MinerU thật và GHÉP kết quả
  vào chunk mà không phá phần đã đúng — đây là việc CẦN LÀM TIẾP.

## 2. Quy ước repo PHẢI theo (Claude Code có các "skill" tự nhắc; công cụ khác
   thì KHÔNG — nên phải làm thủ công theo danh sách này)

### 2a. Bảy nguyên tắc của repo (thứ tự ưu tiên, đọc đủ trong `CLAUDE.md` mục
"Philosophy"). Tóm tắt bắt buộc nhớ:

1. **Không bịa.** Không đoán số trang, không tự sửa chữ khi không chắc — khi
   không đọc được, GIỮ NGUYÊN bản cũ và gắn cờ cho người xem, không tự viết ra
   nội dung mới.
2. **Bằng chứng trước khẳng định.** Trước khi nói "code chạy đúng" — chạy nó
   thật và dán output ra. Đừng suy luận suông.
3. **Đo, đừng đoán.** Mọi ngưỡng số (ví dụ sàn độ bão hoà màu, chiều cao dòng
   chữ) phải có script đo thật, không gõ số theo cảm tính.
4. **Phản biện chính code của mình.** Sau khi viết xong một phần, tự hỏi: có
   off-by-one không, có case biên nào bị bỏ sót không, có fallback im lặng
   nào không.
5. **Fail loudly, never silently.** Một bước lỗi phải dừng lại và báo, không
   được âm thầm bỏ qua rồi coi như thành công.
6. **Một nguồn sự thật duy nhất.** Đừng định nghĩa lại cùng một hằng số/regex
   ở hai nơi — nếu cần dùng chung, tách ra module dùng chung (plan này đã làm
   vậy với `formula_signals.py`, `ocr_lines.py`, `vlm_loader.py`).
7. **Xoá code mạnh tay khi không cần** — nhưng đây không phải lúc để refactor
   ngoài phạm vi plan.

### 2b. Quy tắc thao tác cụ thể

- **KHÔNG chạy full test suite liên tục khi đang lặp code** — chỉ chạy đúng
  file test của phần vừa sửa. Chạy full suite (`python -m pytest tests/ -q`)
  ở CUỐI mỗi task (đã có trong plan) và bắt buộc ở Task 11.
- **Commit sau MỖI task** (không phải sau mỗi bước nhỏ), message THUẦN — commit
  message KHÔNG được có dòng `Co-Authored-By` hay "Generated with". Plan đã ghi
  message mẫu cho mỗi task, dùng đúng như vậy hoặc tương đương ngắn gọn bằng
  tiếng Việt không dấu (repo quen dùng kiểu này cho commit message, xem `git log`
  để thấy ví dụ — ví dụ thật: `feat(etl): xay gate phat hien vung nghi cong thuc Hoa/Ly`).
- **Trước bất kỳ lệnh git nào có thể xoá việc đang làm dở** (`git checkout --`,
  `git reset --hard`, v.v.) — chạy `git status` trước, và KHÔNG làm nếu không
  chắc chắn.
- File nằm trên Windows, git sẽ cảnh báo `LF will be replaced by CRLF` khi
  `git add` — đây là cảnh báo bình thường của repo này, KHÔNG phải lỗi, bỏ qua.
- Sau khi sửa `document/decision_log.html` (Task 11), PHẢI chạy
  `python -m pytest tests/test_decision_log.py -q` — file đó lint cú pháp
  JavaScript của trang, một chuỗi bị xuống dòng giữa chừng có thể làm hỏng cả
  trang mà không có exception Python nào bắt được lúc sửa.

### 2c. Việc TUYỆT ĐỐI KHÔNG được làm trong lượt thực thi plan này

1. KHÔNG tự đoán số liệu ở Task 7/Task 8 (sàn `min_sat`, `single_line_max_h`)
   — plan có script đo cụ thể, PHẢI chạy script đó lấy số thật rồi mới điền
   vào code. `MIN_SAT_FLOOR = 45` trong code mẫu ở Task 7 là placeholder CỐ
   Ý phải thay, không phải số cuối cùng.
2. KHÔNG chạy ETL thật cho 12 quyển sách trong máy không có GPU — plan này chỉ
   CHUẨN BỊ code + notebook Colab, KHÔNG tự chạy ETL 12 quyển (Task 10 chỉ sửa
   file notebook, không thực thi nó).
3. KHÔNG viết lại phần nạp model MinerU từ đầu — PHẢI dùng lại
   `scripts/colab_run_ocr_engines.py::_load_vlm` (chuyển sang
   `src/etl/layout/vlm_loader.py` ở Task 3) vì nó đã có logic phòng vệ
   "tie-weights" chống lỗi model sinh token rác trên `transformers>=5` — bỏ
   qua bước này sẽ lặp lại đúng một bug đã tốn nhiều giờ debug trước đó.
4. KHÔNG dùng `str.replace()` toàn cục để ghép chữ đã sửa vào text — plan quy
   định rõ cách ghép theo dòng nguyên vẹn (đếm số lần xuất hiện, chỉ thay khi
   khớp đúng 1 lần) để tránh thay nhầm chỗ khi cùng một chuỗi lỗi xuất hiện 2
   lần với 2 đáp án đúng khác nhau — xem Task 2 (`formula_merge.py`) và test
   `test_repeated_identical_hole_maps_to_different_correct_tokens`.
5. KHÔNG nhét trạng thái ghép MinerU vào field `review_flags`/`needs_review`
   có sẵn — field đó đã đo được bật ở 69,3% chunk toàn kho (gần vô nghĩa vì
   quá phổ biến), phải dùng field MỚI `formula_hybrid_status` (Task 4).
6. KHÔNG bump `TEXT_EXTRACTION_VERSION` nhiều lần trong lượt này — chỉ bump
   MỘT LẦN ở Task 9, gộp đủ cả 3 thay đổi (hybrid formula + 2 tham số hiệu
   chỉnh ở Task 7/8), vì bump version sẽ ép toàn bộ 12 quyển bị OCR lại (tốn
   nhiều giờ).

## 3. File cần đọc, ĐÚNG THỨ TỰ, trước khi viết bất kỳ dòng code nào

1. `document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md` — thiết kế
   đầy đủ mà plan hiện thực hoá (lý do kỹ thuật đằng sau mỗi quyết định trong
   plan, bao gồm mục "Lịch sử sửa" ghi lại 5 nhóm lỗi thiết kế đã bị phát hiện
   và sửa trước khi chốt — đọc để không lặp lại đúng những lỗi đó).
2. `document/specs/2026-08-28-formula-ocr-hybrid-buoc23-plan.md` — **PLAN
   CHÍNH, thực thi theo đúng file này, từng task theo thứ tự 1→11.**
3. `CLAUDE.md` (ở gốc repo) — quy ước toàn repo: kiến trúc, cách chạy test,
   cấu trúc thư mục `src/etl/layout/`, ý nghĩa `TextUnit`/`chunk_units`, và
   TOÀN BỘ lịch sử quyết định liên quan (tìm "D-56", "D-144" trong file để đọc
   đúng đoạn liên quan tới việc này).
4. `document/decision_log.html` — mở bằng trình duyệt hoặc đọc thô — tìm các
   entry `D-56`, `D-63`, `D-99`, `D-101`, `D-104`, `D-108`, `D-144` để hiểu số
   liệu gốc mà mọi quyết định trong plan dựa vào (bake-off đã LOẠI MinerU thay
   cả trang, và VÌ SAO).

**Không có "memory" hay "skill" nào khác cần đọc** — mọi thứ Claude Code biết
thêm về việc này (qua hệ thống ghi nhớ riêng) đã được chép lại đầy đủ vào 4
file trên khi viết plan. Nếu công cụ bạn dùng không phải Claude Code, 4 file
này là TOÀN BỘ ngữ cảnh cần thiết.

## 4. Vị trí các file quan trọng trong repo (đường dẫn tuyệt đối tính từ gốc)

```
document/goal.docx                                     - de cuong da ky, nguon yeu cau duy nhat
CLAUDE.md                                               - quy uoc toan repo
document/decision_log.html                              - lich su quyet dinh (D-1..D-144+)
document/specs/2026-08-27-formula-ocr-hybrid-buoc23-design.md   - thiet ke
document/specs/2026-08-28-formula-ocr-hybrid-buoc23-plan.md     - PLAN THUC THI
document/review/ocr_gold/                               - gold set 97 o nguoi da duyet (D-144)
src/config.py                                            - hang so cau hinh (them FORMULA_HYBRID_ENABLED o day)
src/etl/layout/regions.py                                - dataclass TextUnit/Region
src/etl/layout/text_extract.py                           - noi hybrid formula vao day (Task 5, 8)
src/etl/layout/chunker.py                                - Task 6
src/etl/layout/loader.py                                 - Task 6, 7, 8 (noi book/formula_client)
src/etl/layout/segmenter.py                              - Task 7 (min_sat per-book)
src/etl/layout/formula_gate.py                           - GATE DA CO SAN (D-144), khong sua
src/etl/layout/formula_signals.py                        - regex cong thuc dung chung (D-144), Task 2 sua nho
src/test/ocr_bakeoff.py                                  - noi cac ham tren duoc trich ra tu day
scripts/colab_run_ocr_engines.py                         - noi _load_vlm goc dang o day, Task 3 chuyen di
database/fingerprints/{ten_sach}.json                    - 12 file, moi sach mot file, doc o Task 7/8
document/colab_runtime_etl.ipynb                         - notebook Colab THAT nguoi dung se chay (Task 10)
tests/layout/                                            - noi phan lon test moi nam (Task 1-8)
```

## 5. Môi trường máy chạy (biết trước để không bất ngờ)

- Máy dev: Windows, CPU-only (`torch` cài rồi nhưng KHÔNG có CUDA). MinerU
  KHÔNG chạy được thật trên máy này — mọi test liên quan tới `FormulaMinerUClient`
  PHẢI dùng client giả (đã thiết kế sẵn trong plan, dependency injection qua
  tham số `formula_client`).
- `datasources/` (ảnh PNG gốc từng trang sách, ~4,1 GB) **CÓ SẴN** trên máy dev
  này — nếu máy bạn KHÔNG có thư mục này, các test đọc ảnh thật (Task 5, 7, 8)
  sẽ tự `pytest.skip(...)` với lý do rõ ràng (đã viết sẵn trong plan) — chấp
  nhận được, nhưng ghi rõ lại là "chưa verify trên ảnh thật" khi báo cáo xong.
- `database/fingerprints/*.json` (12 file, kết quả đo layout mỗi sách) **CÓ
  SẴN** và NẰM TRONG GIT (không giống `database/` chính, vốn bị gitignore).
- Python: chạy bằng lệnh `python` (không phải `python3`) trên máy Windows này.
  Thư viện Tesseract cần biến `TESSERACT_CMD` trong `.env` — file `.env` đã có
  sẵn, không cần tạo lại.
- Nếu gặp lỗi `ImportError: tokenizers>=0.20,<0.21 is required ... found
  tokenizers==X` khi import `src.rag`/`src.etl`: chạy
  `pip install tokenizers==0.20.3 --no-deps` (một thư viện khác trên máy này,
  `litellm`, hay ghi đè phiên bản `tokenizers` mà `transformers==4.46.3` của
  repo cần — không phải lỗi của code plan này).

## 6. Cách thực thi plan (nếu công cụ hỗ trợ thao tác agent nhiều bước)

Với mỗi task trong `2026-08-28-formula-ocr-hybrid-buoc23-plan.md` (Task 1 đến
Task 11, THEO ĐÚNG THỨ TỰ — task sau phụ thuộc file task trước tạo ra):

1. Đọc trọn phần "Files" + "Interfaces" + toàn bộ các Step của task đó.
2. Với mỗi Step: làm ĐÚNG như code/lệnh đã viết trong plan (đã viết đầy đủ,
   không cần tự suy nghĩ thêm logic — nếu thấy code trong plan có vẻ sai/thiếu
   so với code THẬT hiện có trong repo, MỞ FILE THẬT ra đọc và đối chiếu trước
   khi sửa — plan có vài chỗ tự ghi chú "đọc file thật trước khi copy nguyên",
   tuân theo đúng ghi chú đó).
3. Chạy lệnh test/Run đã cho, đối chiếu với "Expected" — nếu khác, dừng lại,
   tìm nguyên nhân thật (đọc traceback), không tự sửa test để nó pass giả.
4. Sau khi Step cuối của task (thường là "Commit") xong, chuyển sang task
   tiếp theo.
5. Nếu một task có bước ĐO THẬT (Task 7, Task 8) — bắt buộc chạy script đo,
   dán output thật vào chỗ code cần điền số, và ghi số đó + cách đo vào
   `document/decision_log.html` như Task 11 hướng dẫn (có thể làm ngay trong
   lúc chạy Task 7/8 thay vì đợi tới Task 11, miễn là số liệu được ghi lại).

**Sau khi xong cả 11 task:** báo cáo lại cho người dùng — số test pass/skip
cuối cùng (`python -m pytest tests/ -q`), số đã đo ở Task 7/8, và xác nhận rõ
"ĐÃ chuẩn bị xong code + notebook Colab, CHƯA chạy ETL 12 quyển thật — bước đó
cần người dùng tự chạy trên Colab GPU".

## 7. Nếu bị lỡ hoặc phải dừng giữa chừng

- Mỗi task commit riêng — `git log --oneline` sẽ cho thấy đã làm tới đâu.
  Task tiếp theo có thể tiếp tục từ đó, không cần làm lại từ đầu.
- Nếu không chắc trạng thái hiện tại khớp task nào: chạy
  `python -m pytest tests/layout/ -q` và so số lượng test pass với con số ghi
  trong từng Step "Expected" của plan để suy ra đã xong tới đâu.
