# Thiết kế — thay Tesseract bằng MODEL đọc cả trang, chọn model BẰNG PHÉP ĐO

> Ngày chốt: **2026-08-25**. Người dùng đã chốt: (1) bake-off 15 trang có người
> duyệt tay **trước**, (2) hướng đi là **model đọc CẢ TRANG** (không phải đổi từng
> hàm OCR), (3) chạy trên **Colab GPU**, (4) phạm vi cuối là **cả 12 quyển**.
>
> Deadline: Giai đoạn 3 đáo hạn 28/08 (đã có bảng cấu hình 1 + 2); deadline cuối
> **23/09**. Lượt OCR lại toàn bộ là việc của Giai đoạn 4–5.

---

## 1. Vì sao làm việc này, bằng số đã đo

| Bệnh | Số đo | Nguồn |
|---|---|---|
| chỉ số dưới bị phá | **281 hỏng : 4 đúng** trên toàn index; `₂` Unicode **0 lần** | D-56, D-73 |
| bảng mất quan hệ hàng/cột | `Bảng 12.1` trộn cột *công dụng* vào cột *tính chất*; `Bảng 35.1` mất cả hàng header **và 8 dấu phẩy thập phân** (`26,2`→`262`, sai 10×) | D-63 |
| hệ quả cuối | **4/6 ca fail của người chấm là do chất lượng chữ trích xuất, chỉ 2 do LLM** — recall@10 = 1,00 | D-63 |
| hằng số KNTT còn treo | `text_extract.SINGLE_LINE_MAX_H = 60` px (dòng CD cao ~136 px), `LAYOUT_BOX_MIN_SATURATION = 45` (trên p50 của 11/12 quyển) | CLAUDE.md M0 |
| `needs_review` mất tác dụng | bật ở **57–84% chunk** (9_CD 1 339/1 590) | D-73 |

Nút thắt **không** phải retrieval: hybrid đã đo được R@10 **0,977** · MRR **0,808**
trên 300 câu (D-82). Nên đòn bẩy nằm ở chữ trích xuất.

## 2. Điều PHẢI biết trước khi chọn model

Đã kiểm bằng HF API, không bằng ký ức. **Không model nào trong bốn ứng viên nhắc
tới "Vietnamese" trong model card:**

| model | tham số | "Vietnamese" | công thức/LaTeX | bảng |
|---|---|---|---|---|
| `PaddlePaddle/PaddleOCR-VL-1.6` | 0,9 B | **0** | 8 | 7 |
| `dots-studio/dots.ocr` | 1,7 B | **0** | 22 | 24 |
| `opendatalab/MinerU2.5-Pro-2605-1.2B` | 1,2 B | **0** | 7 | 12 |
| `nanonets/Nanonets-OCR2-3B` | 3 B | **0** | 12 | 12 |

Cả bốn quảng cáo đúng hai bệnh của ta (công thức + bảng) nhưng **chất lượng dấu
tiếng Việt là CHƯA ĐO**. Chọn theo danh tiếng ở đây là lặp lại D-47: Vintern-1B
nghe rất hợp lý, chạy thật thì **bịa 4/12 crop** và tự khai số hình **sai 4/4 lần**.

Vì vậy bước 0 không phải thủ tục — nó là **cổng chặn**.

## 3. Bước 0 — bake-off 15 trang

### 3.1 Mười lăm trang, chọn BẰNG SỐ

Chọn từ chính index: đếm token công thức bị phá (`CO,` `H,SO,` `O,` …) và token số
trên mỗi trang, rồi rải **5 trang mỗi NXB**, phủ 4 loại bệnh + **3 trang đối chứng
chữ thường**. Trang đối chứng là phần quan trọng nhất về mặt thiết kế thí nghiệm:
**93% corpus là chữ thường**, nên một model thắng ở công thức mà tệ ở chữ thường là
một model TỆ HƠN, và không có trang đối chứng thì không ai thấy điều đó.

| # | quyển | trang | loại | vì sao trang này |
|---|---|---|---|---|
| 1 | 7_KNTT | 121 | công thức Hoá | ca **đã đảo đáp án**: index ghi `hấp thụ khí 0, và thải ra khí (0,` → Qwen trả lời ngược (D-63) |
| 2 | 9_KNTT | 21 | công thức Lý | `1 J = 1 N·m` → `1 Ñm`, `(M]` → RAG trả lời **rỗng**, không log gì (D-63) |
| 3 | 6_KNTT | 44 | **bảng** | `Bảng 12.1` trộn cột công dụng vào cột tính chất (D-63) |
| 4 | 9_KNTT | **154** | **bảng** | `Bảng 35.1` mất hàng header + **8 dấu phẩy thập phân** (D-63). **SỬA từ 155:** tr.155 không có tiêu đề bảng nào; 155 là số của corpus 801 trang cũ (offset −1) |
| 5 | 9_KNTT | 74 | **đối chứng** | 2 585 ký tự, **0** công thức hỏng |
| 6 | 9_CTST | 113 | công thức Hoá | **18 token hỏng — cao nhất toàn bộ 2 387 trang** |
| 7 | 8_CTST | 62 | công thức Hoá | 17 token hỏng |
| 8 | 7_CTST | 49 | Lý + số | 9 token hỏng **+ 10 chuỗi số dài** (nghi mất dấu phẩy) |
| 9 | **9_CTST** | **43** | **bảng** | `Bảng 8.3` — bảng SỐ của CTST (7 chuỗi 3 chữ số + 5 dấu phẩy). **THAY 6_CTST tr.134** để mỗi NXB có đúng một bảng |
| 10 | 7_CTST | 141 | **đối chứng** | 2 600 ký tự, 0 công thức hỏng |
| 11 | 9_CD | 113 | công thức Hoá | 11 token hỏng |
| 12 | 9_CD | **134** | **bảng** | `Bảng 27.1` — 15 chuỗi 3 chữ số, **0** dấu phẩy thập phân còn sót. **THAY tr.129:** trang đó thật ra là trang CÔNG THỨC, không có tiêu đề bảng nào |
| 13 | 8_CD | 61 | trang dày chữ | 7 token hỏng, **2 509 ký tự** |
| 14 | 8_CD | 60 | công thức Hoá | 7 token hỏng |
| 15 | 7_CD | 112 | **đối chứng** | 2 587 ký tự, 0 công thức hỏng |

Phân bố: NXB **5/5/5**; khối 6 (1) · 7 (4) · 8 (3) · 9 (7) — nghiêng về lớp 9 vì
công thức Hoá tập trung ở đó, và điều đó được nói ra thay vì che.

**Ba dòng in đậm ở trên là số ĐÃ BỊ LẬT trong chính lượt này**, tìm ra bằng cách
mở phiếu đầu tiên ra đối chiếu chứ không bằng test (nguyên tắc 4). Chúng được
ghi lại thay vì im lặng thay số (nguyên tắc 2).

Danh sách này ghi ra file JSON và **commit**, để lượt sau chấm trên đúng 15 trang
đó chứ không chọn lại.

### 3.2 Cách chấm — ba chỉ số, không phải một

| chỉ số | định nghĩa | vì sao |
|---|---|---|
| **CT** token công thức đúng | tỉ lệ token công thức mà engine đọc **khớp từng ký tự** với bản người duyệt | bệnh chính, hiện 281:4 |
| **DẤU** tỉ lệ lỗi dấu | trên các từ người duyệt đã ghi, tỉ lệ sai **chỉ ở dấu** (bỏ dấu thì khớp) | chỗ model nước ngoài dễ chết; đây là **cổng loại** |
| **BẢNG** ô đúng vị trí | với mỗi bảng: hàng header + 1 hàng dữ liệu, ô nào đúng **cả nội dung và vị trí cột** | bệnh mà cách 1 (đổi hàm OCR) không chữa được |

Một engine chỉ được coi là **thắng** khi nó **không tệ hơn** Tesseract ở chỉ số DẤU
trên 3 trang đối chứng. Thắng công thức mà thua dấu là thua.

### 3.3 Chống đóng dấu cho qua — thiết kế của phiếu duyệt

D-90 vừa dạy bằng tiền thật: phiếu 50 câu được điền **50/50 một nhãn `dung` trong
38 giây**, và D-89 đã công bố con số đó. Bài học: **một phiếu có thể tick là một
phiếu sẽ bị tick.** Nên phiếu này được thiết kế để *không tick được*:

1. **Người duyệt GÕ chữ, không chọn đúng/sai.** Ô trả lời trống, không mồi sẵn chữ
   của máy. Muốn điền thì phải đọc ảnh.
2. **Đơn vị công việc là một DÒNG được crop ra**, không phải cả trang 2 000 ký tự.
   Nhìn một dòng ảnh rồi gõ lại 5–15 ký tự là việc làm được; sửa 2 000 ký tự thì
   không, và chính chỗ đó sinh ra tật đóng dấu cho qua (D-55: 23/24 file gold cũ
   trùng **từng chữ** với output của máy).
3. **Mọi ô CÔNG THỨC/SỐ đều là "ca mồi", và tôi nói trước.** Chúng có mặt trong
   phiếu **vì máy đã đọc sai chúng** — đó là tiêu chí chọn ô. Nên một câu trả lời
   trùng y nguyên chữ máy là dấu hiệu không mở ảnh ra xem, và `--score` đếm nó
   rồi **từ chối công bố** khi tỉ lệ đó ≥ 50%. Không cần cài ca mồi giả: tiêu chí
   chọn ô đã làm sẵn việc đó, và nói trước thì công bằng hơn — cái cần kiểm là
   bạn *có nhìn ảnh không*, không phải bẫy bạn. (Ô ĐỐI CHỨNG thì ngược lại: trùng
   với máy là bình thường và **không** bị tính.)
4. **Kiểm dấu thời gian.** Phiếu HTML tự ghi `_bat_dau`/`_ket_thuc` vào file
   JSON khi tải xuống, nên `--score` tính được **giây/ô** thật. Dưới **5 s/ô** thì
   nó in cảnh báo **và từ chối công bố số** — đúng bài học D-90 (phân bố đáng nghi
   phải CHẶN, không phải đi kèm chú thích). Đo trên một phiếu giả: 24,7 s/ô là
   nhịp bình thường.

### 3.4 Engine chấm trên CROP, không trên cả trang — và vì sao

Bake-off phải **công bằng**, không phải giống production. Engine và người duyệt
chấm trên **cùng một mẩu pixel**. Nếu để engine đọc cả trang rồi ta đi tìm dòng
nào khớp nhất với đáp án của người, đó là **tự chọn kết quả tốt nhất cho engine**
— một phép đo thiên vị mà không ai nhìn thấy trong con số cuối.

Ô loại BẢNG có crop là cả **dải bảng**, nên engine vẫn phải làm đúng việc khó
(giữ quan hệ hàng/cột), chỉ là không phải tự đi tìm bảng nằm ở đâu trên trang.

Sau khi **chọn được** model, production mới cho nó đọc **cả trang** — đó là bước
1, và nó cần phép đo này trước.

Hệ quả vận hành: `--export` xuất luôn `crops/` (**8,2 MB**, 97 PNG + `crops.json`)
để mang lên Colab, thay vì chép corpus **4,1 GB** không nằm trong git (D-68).

### 3.5 Ba luật khiến bảng so trung thực

1. **Ô engine không trả lời được tính là SAI, không phải bỏ qua.** Bỏ qua sẽ
   thưởng cho engine im lặng — đúng loại "một bước thất bại mà lớp gọi nó vẫn
   báo thành công" đã cắn ở D-68/D-75/D-83/D-84.
2. **Ô người để trống, hoặc người ghi `???`, bị loại khỏi MỌI trục.** Không có
   bản người thì không có chuẩn để so. `???` là câu trả lời hợp lệ và có giá
   trị: nó nói rằng chỗ đó không ai đọc được, kể cả người.
3. **`O2` và `O₂` là một; `O,` thì KHÔNG.** Người duyệt không bị phạt vì cách gõ,
   nhưng đoán lại một chỉ số đã mất là bịa (nguyên tắc 1) — mà chính `O,` là thứ
   đang đo.

### 3.6 Phiếu người duyệt phải nằm trong git

`database/` bị `.gitignore` bỏ qua (D-68), nên một phiếu chỉ sống ở đó là một
phiếu sẽ mất — mà đây là 35–50 phút công người, không dựng lại được. `--score`
tự chép nó sang `document/review/ocr_gold/` và nhắc commit. Phiếu thứ hai
**không ghi đè** phiếu thứ nhất: hai phiếu độc lập chính là cách phân giải nghi
ngờ mà D-90 đã chỉ ra.

### 3.4 Ước lượng công cho người: **35–50 phút**

15 trang × ~6 ô × ~20 giây gõ, cộng thời gian nhìn trang. Đây là ước lượng, và
`--score` sẽ in ra con số **thật** để lần sau khỏi phải đoán.

## 4. Bước 1 — model đọc cả trang (cách 2 đã chốt)

### 4.1 Chỗ đúng để cắm vào

Đường text hôm nay: `LayoutOCRLoader.load_page()` → tra manifest → `source.load()`
→ `segment_page` (CV) → `extract_text_units` (Tesseract từng vùng) → `chunk_units`.

Cách 2 thay **hai bước giữa** bằng một lần gọi model trên **cả trang**, trả về các
đơn vị `(loại vùng, bbox, chữ)`. Ba thứ **không đổi**, vì đó là cơ chế chống bịa
đang chạy đúng:

- **số trang in vẫn lấy từ `BookManifest`** — model **không bao giờ** được sinh số
  trang (nguyên tắc 1). Thiếu manifest thì vẫn `raise ManifestMissing`.
- **citation vẫn deterministic** (`src/rag/citations.py`), dựng từ metadata chunk.
- **checkpoint vẫn khoá theo hash từng trang + `TEXT_EXTRACTION_VERSION`**, nên một
  lượt bị ngắt giữa chừng chạy tiếp được — bắt buộc, vì Colab hay đứt phiên.

### 4.2 Hai chỗ phải thiết kế cẩn thận

**(a) `region_type` phải sống.** `citations.py` đọc trường này để in nhãn mục
(sidebar/info-box); chunk thiếu nó **âm thầm** tụt về citation chỉ-có-thân-bài. Nên
nhãn vùng của model phải map sang tập `region_type` hiện có, và **nhãn lạ thì gắn
cờ chứ không đoán**.

**(b) Chống bịa, đo được.** VLM có thể sinh chữ không có trên trang — đúng thứ
nguyên tắc 1 cấm. Hàng rào: chạy **Tesseract song song trên MỘT MẪU 100 trang**,
so độ trùng token; lệch quá ngưỡng thì gắn `needs_review`. Chỉ 100 trang, không
phải 2 399, nên không trả giá gấp đôi. Việc này cũng làm `needs_review` **có nghĩa
lại** — hiện nó bật ở 69% chunk nên gần như không mang tin.

### 4.3 Cái giá phải nói trước

Bump `TEXT_EXTRACTION_VERSION` là **OCR lại toàn bộ 2 399 trang** (version gate,
đúng thiết kế). Kèm theo, ba thứ hạ nguồn **bắt buộc dựng lại**:

| việc | chi phí đã đo |
|---|---|
| OCR lại 12 quyển | Tesseract/CPU **3 giờ 20**; VLM 1B trên GPU Colab: **chưa đo**, sẽ đo ở bước 0 |
| chỉ mục BM25 | 5,5 s |
| đệm bảng ablation | **35–50 phút** (21–31 s/câu × 300 câu) |
| bảng k/recall mới | phát lại từ đệm, tức thì |

Đường cơ sở để so là bảng đã có: hybrid **R@1 0,717 · R@3 0,887 · R@10 0,977 ·
MRR 0,808** (300 câu / 12 quyển, bề rộng production 20 ứng viên/kênh).

## 5. Bước 2 — nói về kết quả thế nào cho đúng

Nếu recall tăng, **chỉ được** nói "tăng vì chữ trích xuất tốt hơn" khi bước 0 đã
cho thấy công thức/bảng/dấu đọc đúng hơn trên 15 trang có người duyệt. Không có
bước 0 thì một con số recall cao hơn cũng có thể đến từ chunk dài hơn, hay từ nhiễu.

Và mọi bảng số vẫn phải mang câu cảnh báo hiện hành: bộ test do **LLM sinh**, mẫu
50 câu người duyệt cho gold key sai **2/49 = 4,1%** (KTC 95% Wilson 1,1–13,7%;
hiệu chỉnh theo trọng số cả bộ ≈ 2,7%) — D-90.

## 6. Việc CỐ Ý KHÔNG làm trong lượt này

- **Không sửa phía ảnh.** Người dùng đã chọn text trước. Crop hình đang có 34,9%
  bị gắn cờ cắt lấn (D-87) — đó là lượt sau, và nó cần model phát hiện bố cục chứ
  không phải model OCR.
- **Không bật `IMAGE_CAPTION_ENABLED`** (Vintern đã bị loại — D-47).
- **Không đổi `EMBEDDING_MODEL` / `CHUNK_SIZE` / `CHUNK_OVERLAP`**: đổi cùng lúc
  với OCR thì không tách được nguyên nhân của bất kỳ thay đổi số nào.
- **Không sửa chữ đã lưu trong `biology_text`** bằng bất kỳ luật đoán nào.
