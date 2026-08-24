# Báo cáo Track B — M2.0/M2.1/M2.2: BM25 + hợp nhất thưa/dày

> Ngày 2026-08-24. Decision log: **D-76 … D-81**. Prompt sinh ra lượt này:
> `2026-08-24-m2-track-b-bm25-prompt.md` (và prompt M2 tổng thể
> `2026-08-24-m2-bm25-hybrid-prompt.md`).
>
> Mốc đề cương: M2 = **Giai đoạn 2, đáo hạn 13/08/2026**; hôm nay 24/08 → **trễ
> 11 ngày**. Giai đoạn 3 (thực nghiệm đối chiếu) đáo hạn **28/08/2026**.

Mọi con số dưới đây chạy lại được bằng một lệnh:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_ablation.ps1
```

---

## 0. Tóm tắt: cái gì xong, cái gì chưa, cái gì bị lật

| Hạng mục hợp đồng | Trạng thái | Bằng chứng |
|---|---|---|
| Nội dung 2 — chỉ mục **BM25** | **XONG** | `python main.py --build-bm25` → 16 393 chunk / 19 727 từ vựng / 5,5 s |
| Nội dung 2 — **hợp nhất thưa + dày** | **XONG** | `src/rag/hybrid_text_retriever.py`, chạy thật trên index 12 quyển |
| Nội dung 2 — "không bỏ sót **thuật ngữ khoa học đặc thù**" | **XONG, đo được** | chunk đúng ở top-10 cho 12 công thức: **6 → 97** |
| Nội dung 4 — ablation **rerank × cổng lọc** | **XONG (cấu trúc)** | 12 cấu hình bật/tắt bằng `.env`, §5 |
| Giai đoạn 3 — **BM25 vs dense vs hybrid** | **CÓ BẢNG** (bộ test tạm) | §5.5 — đề xuất **hybrid + rerank + rrf**: R@1 0,830 · R@10 **1,000** · MRR 0,898 |
| Bộ test 12 quyển có nhãn | **của Track A**, đang chạy | — |
| M2.3 caption vào ngữ cảnh · M2.4 sửa `chain.py` | **CHƯA** | ngoài phạm vi ba mốc B1/B2/B3 |

**Ba phép đo lật ngược điều đã tin trước đó** — chi tiết ở §1, §3, §4:

1. Bộ test 100 câu cũ **KHÔNG vô hiệu** (D-75 nói vô hiệu): 99/100 gold key khớp
   index 12 quyển ở offset 0; `recall_at_k` cho **R@10 = 0,98**.
2. Bộ tách từ **GIỮ dấu thắng BỎ dấu** (MRR 0,820 vs 0,755) — ngược với giả
   thuyết "OCR làm hỏng dấu nên bỏ dấu sẽ tốt hơn".
3. Cổng lọc liên quan và rerank **trước M2 là loại-trừ-nhau**, nên
   `RETRIEVER_DISTANCE_MARGIN = 0.3` là **số chết** trong cấu hình đang chạy.

---

## 1. B1 — "sự thật hiện tại" trước khi sửa gì (D-76)

### 1.1 Bộ test cũ CÒN DÙNG ĐƯỢC — và giải thích được vì sao

Prompt dự đoán bộ test 100 câu (4 quyển KNTT, corpus cũ) đã hỏng vì gold key theo
`offset −1`. **Phải kiểm chứ không được giả định** (đúng lời prompt), nên đã đo
hai cách độc lập:

**Cách 1 — không LLM, không embedding.** Dùng chính bộ so khớp IDF của G3
(`page_supports_answer`, `COVERAGE_MIN = 0.50`, D-57), thử offset −2..+2 quanh
`source_page` trên chữ đã index:

| offset | số câu có đáp án được trang hỗ trợ |
|---|---|
| −2 | 20 |
| −1 | 31 |
| **0** | **99** |
| +1 | 39 |
| +2 | 34 |

Offset tốt nhất theo độ phủ: **0 ở 87/100 câu**. Sức phân biệt rõ ràng.

**Cách 2 — qua đường truy xuất thật.** `python src/test/recall_at_k.py`:

| quyển | R@3 (base/rer) | R@5 | R@10 | MRR |
|---|---|---|---|---|
| 6_KNTT | 0,76 / 0,92 | 0,96 / 0,92 | 1,00 / 1,00 | 0,72 / 0,83 |
| 7_KNTT | 0,88 / 1,00 | 0,92 / 1,00 | 1,00 / 1,00 | 0,83 / 1,00 |
| 8_KNTT | 0,88 / 0,96 | 0,96 / 0,96 | 0,96 / 0,96 | 0,77 / 0,92 |
| 9_KNTT | 0,72 / 0,84 | 0,92 / 0,88 | 0,96 / 0,96 | 0,59 / 0,78 |
| **TB** | **0,810 / 0,930** | 0,940 / 0,940 | **0,980 / 0,980** | 0,727 / 0,882 |

**Cơ chế, để không ai phải tin vào may mắn:** corpus KNTT cũ 801 trang / 4 quyển,
corpus mới **797** — ít hơn **đúng 1 trang mỗi quyển**. Corpus cũ đánh số
`printed = filenum − 1` (bìa là `page_001` = trang in 0); corpus mới bỏ trang đó
nên `printed = filenum`. Cùng một trang giấy, cùng một **số trang IN** → gold key
ghi theo `source_page` (số trang in) vẫn đúng. Gold key ghi theo
`source_page_index` (số trong tên file) thì sai đúng 1 — nhưng `recall_at_k.py` và
`metrics.make_page_relevance` dùng `source_page`.

**Hệ quả cho Track A:** việc chuyển bộ test vào
`src/test/testsets/_archive_4books_kntt_offset_minus1/` vẫn **đúng về lý do cơ
khí** (nó làm lượt sinh mới lặng lẽ bỏ qua 4 quyển KNTT — D-75 mục 3), nhưng lý
do *dữ liệu* thì sai, và **tên thư mục mô tả sai thực tế**. Vẫn cần bộ 12 quyển,
vì bộ này chỉ phủ 4/12 quyển và thiếu nhãn `phan_mon`/`khoi`/`bo_sach`/`do_kho`.

### 1.2 Bảng "trước M2" — đo trên 16 393 chunk

| | số đo |
|---|---|
| chunk | 16 393 · 2 387 cặp (source, page) · **0** chunk id trùng |
| độ dài chunk (ký tự) | min 1 · p10 67 · **p50 326** · p90 392 · max 600 · TB 269,2 |
| chunk **≤ 40 ký tự** | **1 090 = 6,65%** — bị `chain.py::format_docs` bỏ **im lặng** |
| `region_type` **thiếu** | **0** (body 9 727 / info_box 3 718 / sidebar 2 948) |
| `bai_so` | 4 857 = **29,63%** (đúng 4 quyển KNTT) |
| `needs_review` | 11 362 = **69,31%** |

Hai kết luận, một xác nhận một bác bỏ:

- §1.5.3 của prompt M2 nói nên đo xem `format_docs` bỏ đoạn < 40 ký tự có vô hại
  không. **Không vô hại: 6,65%.** 10 chunk ngắn nhất là rác OCR đúng nghĩa
  (`'5'`, `'|'`, một dấu nháy đơn lẻ), nhưng 6,65% là một tỉ lệ phải quyết định
  có ý thức chứ không để mặc định.
- Lo ngại "thiếu `region_type` làm citation suy giảm âm thầm" **không có cơ sở**:
  0/16 393 chunk thiếu.

### 1.3 Số KHÔNG đo được trong lượt này

`qa_citation_page` (G3) **chưa chạy**: nó cần nạp bge-m3 và ưu tiên đã dồn cho
B2/B3 theo đúng chỉ dẫn "B1 làm nhanh, đừng sa vào chữa bộ test cũ". G3 không
chặn bảng ablation.

---

## 2. B2 — chỉ mục thưa (D-77)

```
python main.py --build-bm25
→ database/sparse/{bm25_tf.npz, bm25_doclen.npy, bm25_meta.json}
   16 393 chunk · 19 727 từ vựng · độ dài TB 56,8 token · 5,5 s
```

**Bốn ràng buộc thiết kế, mỗi cái có lý do đã cắn thật:**

1. **Khoá là chính `chunk_id` của `biology_text`** (`{page_key}_p{page}_c{index}`).
   Dựng tập tài liệu riêng với id riêng là tạo nguồn sự thật thứ hai — đúng loại
   lỗi D-71 (`book_id` nối cứng `-KNTT` khiến ba NXB ghi đè manifest của nhau,
   im lặng hoàn toàn, 158 test vẫn xanh).
2. **Dấu vân 6 trường:** `n_chunks`, **digest md5 của TẬP chunk id**,
   `TEXT_EXTRACTION_VERSION`, tokenizer, `NORMALIZER_VERSION`, định dạng. Lệch
   bất kỳ trường nào → `SparseIndexStale`, **không** có nhánh dùng tạm bản cũ.
   Đếm số chunk một mình là **không đủ** — dựng lại index với cùng số chunk nhưng
   khác nội dung sẽ lọt, nên phải có digest. Có test riêng cho đúng ca đó.
3. **`k1`/`b` là tham số lúc TRUY VẤN.** Đây là lý do **không** dùng `rank_bm25`:
   nó chốt `k1`/`b` lúc khởi tạo nên mỗi ô của bảng quét 5×5 là một lần dựng lại
   chỉ mục. Bản tự cài (`src/rag/bm25.py`, scipy CSC) cho cả bảng 25 ô chạy trong
   vài phút.
4. **Chuẩn hoá công thức chỉ ở phía truy vấn/chỉ mục thưa.** `biology_text`
   không bị sửa một ký tự nào — có test chốt hàm là hàm thuần.

**Test số-tính-tay bắt được một lỗi thật.** Đối chiếu điểm BM25 với số tính tay
lệch **7,5e-8 tương đối**: `df` tính từ `tf` float32 nên `idf` cũng float32. Sửa
gốc (ép float64), **không nới ngưỡng test**. Một test chỉ so đầu ra với chính
mình sẽ không bao giờ thấy điều này.

**Ba phép đo phản biện mà §3.2 bắt buộc:**

| câu hỏi | kết quả |
|---|---|
| Chunk ngắn / rác OCR có cướp top-k không? | **Không.** 1 090 chunk ≤ 40 ký tự trong kho; trên 100 truy vấn chúng chiếm **0/1 000** suất top-10 và **0/100** hạng 1 — chunk rác không có từ nào khớp nên điểm bằng 0 bất kể ngắn |
| `overlap=120` làm lệch IDF bao nhiêu? | Spearman(hạng IDF chunk, IDF trang) = **0,886**; lệch hạng p50 = 145/13 791 (~1%), p90 = 3 753; **12 từ lệch nhất đều có df 1–3** (rác OCR: `vich`, `throong`, `sinhtuong`) → lệch nằm ở **đuôi hiếm**, không đổi thiết kế |
| `k1`/`b` chọn thế nào? | Quét, §4 |

**Nghiệm thu bằng mắt trên truy vấn thật** — mọi `chunk_id` trả về đều tồn tại
trong `biology_text` (5/5 truy vấn):

| truy vấn | hạng 1 |
|---|---|
| `H2SO4 loang tac dung voi kim loai` | 8_KNTT tr.36 — `H,SO, đặc tác dụng với kim loại` |
| `khi CO2 va O2 trong ho hap` | 7_KNTT tr.114 — `Nồng độ khí CO, ngoài môi trường` |
| `dinh luat Ohm` | 9_KNTT tr.56 — `3. Định luật Ohm` |

---

## 3. Chuẩn hoá công thức: bỏ chữ số thay vì đoán nó (D-78)

Đề cương nêu tên BM25 vì **"thuật ngữ khoa học đặc thù"**, và D-73 đo được chỉ số
dưới **không sống sót ở bất kỳ độ phân giải nào** (hỏng:đúng = CD 256:3, CTST
377:3, KNTT 408:4; ký tự `₂` Unicode **0 lần**). Nên đây là cùng một bài toán.

### 3.1 Luật, và vì sao nó không phải là bịa

```
CO,   -> co#, co            CO2   -> co#, co, co2
H,O   -> h#o, ho            H2O   -> h#o, ho, h2o
H,SO, -> h#so#, hso         H2SO4 -> h#so#, hso, h2so4
```

Chỗ dễ sai nhất là **đoán chữ số**: `SO,` có thể là SO₂ *hoặc* SO₃; `H,SO,` là
H₂SO₄ với hai chữ số **khác nhau**. Viết lại chúng là bịa (CẤM #5, nguyên tắc 1).
Nên luật **xoá** chữ số thay vì đoán. Mất mát `SO2 ≡ SO3` là **cố ý và thành
thật**: chữ đã index không chứa chữ số nên thông tin đó không tồn tại trong kho
để mà giữ. Trang đọc **đúng** vẫn thắng trang đọc **hỏng** vì nó khớp thêm token
nguyên văn.

### 3.2 Phép đo quyết định — không cần người gán nhãn

`src/test/formula_probe.py`. Mẹo: "chunk đúng" = chữ **đã lưu** của nó chứa dạng
OCR hỏng — kiểm được bằng `in`, không phải phán đoán. Cùng kiểu lập luận với cổng
G4 (cấu trúc dữ liệu làm ra đáp án).

| truy vấn | dạng hỏng | chunk chứa dạng hỏng | TẮT chuẩn hoá | BẬT |
|---|---|---|---|---|
| CO2 | `CO,` | 164 | 0/1 | **9/10** |
| O2 | `O,` | 520 | 0/3 | 7/10 |
| H2O | `H,O` | 114 | 0/0 | **10/10** |
| H2SO4 | `H,SO,` | 34 | 0/0 | **10/10** |
| CH4 | `CH,` | 79 | 0/0 | **10/10** |
| SO2 | `SO,` | 161 | 0/0 | 9/10 |
| N2 | `N,` | 120 | 0/10 | 0/10 |
| CaCO3 | `CaCO,` | 17 | 0/0 | **10/10** |
| CuSO4 | `CuSO,` | 39 | 0/0 | **10/10** |
| Fe2O3 | `Fe,O,` | 9 | 0/0 | 7/10 |
| Na2SO4 | `Na,SO,` | 15 | 0/0 | **10/10** |
| CuO | `CuO,` | 12 | **6/10** | 5/10 |
| **TỔNG** | | 1 284 | **6 chunk · 1/12 truy vấn** | **97 chunk · 11/12 truy vấn** |

### 3.3 Ba giả thuyết bị bác bỏ trên đường đi

**(1) Homoglyph `0`→`O` — bác bỏ.** Ca D-63 (`hấp thụ khí 0, và thải ra khí (0,`)
gợi ý coi chữ số 0 là chữ O. Đếm thật: token `0,` xuất hiện **46 lần** trong
16 393 chunk, và mở ngữ cảnh ra thì phần lớn là **số thật** ("ghi số 0, vạch cuối
cùng", "biên độ là 0, mm"). Không thêm luật.

**(2) Luật hình dạng là đủ — bác bỏ hai lần.** Quét 1 001 276 token: luật đầu
(cho phép chỉ số `0`) khớp 3 959 token / 715 dạng, trong đó **`H0C` 82 lần,
`KH0A` 58, `TRA0` 14** — là "KHOA HỌC" bị OCR đọc `Ọ`→`0`. Chỉ số dưới bằng 0
**vô nghĩa trong hoá học**, nên loại nó là luật có nguyên tắc: còn 3 590 token /
634 dạng = **0,359%**. Rồi bộ test lộ tiếp ba dương tính giả nữa — `Bo,` (tên
Bohr), `I,`, **`XIII,`** (số La Mã dài, đọc theo hình dạng là X+I+I+I). Thêm hai
tầng: nhóm **hai chữ** phải là ký hiệu nguyên tố thật (vốn từ đóng 118 ký hiệu —
**dữ liệu**, không phải heuristic), và số La Mã ≥ 2 ký tự bị loại.

**(3) Lỗi do CHÍNH bước chuẩn hoá gây ra.** Bản đầu chỉ sinh khung + dạng nguyên
văn, nên tài liệu chứa `CuO,` thôi phát token `cuo` và truy vấn `CuO` (không chỉ
số) **tệ đi** so với khi không chuẩn hoá: **6/10 → 4/10**. Thêm dạng chữ thuần:
**5/10**. **Vẫn thấp hơn 6/10 khi tắt** — ghi ra chứ không giấu.

### 3.4 Dương tính giả CÒN LẠI, đã đo và chấp nhận

Token một chữ cái + phẩy (`A,` 111 lần, `R,` 105, `B,` 67) vừa có thể là biến vật
lý có chỉ số (F₁, F₂ — đề cương nêu `A = Fs`) vừa có thể là nhãn phương án trắc
nghiệm. Hình dạng token không tách được hai nghĩa. Cụ thể **`N2` cho 0/10 cả khi
bật lẫn tắt**, vì `n#` (df 75) phần lớn đến từ "cực bắc được đánh dấu là N,".
IDF chặn bớt nhưng **không** triệt tiêu: `a#` có df 122, idf 4,897 — chưa gần 0.

---

## 4. Quét tham số bằng số (D-79)

`python src/test/bm25_sweep.py --testset-dir <bộ test>`

### 4.1 Tách từ — phép đo bác bỏ giả thuyết của chính lượt này

Giả thuyết ban đầu: OCR làm hỏng dấu (chính vì thế G3 phải so khớp trên dạng đã
bỏ dấu — D-49), nên **bỏ dấu sẽ tăng recall**. Số thật:

| | từ vựng | R@1 | R@3 | R@5 | R@10 | MRR |
|---|---|---|---|---|---|---|
| (a) **giữ dấu** | 19 727 | **0,760** | 0,860 | 0,900 | 0,950 | **0,820** |
| (c) bỏ dấu | 13 830 | 0,660 | 0,830 | 0,860 | 0,930 | 0,755 |

Giữ dấu thắng ở **mọi k** → `BM25_TOKENIZER = plain`. Dấu mang nhiều thông tin
phân biệt hơn phần OCR làm hỏng nó.

**(b) `underthesea`/`pyvi`: KHÔNG cài.** Đường (a) đã thắng (c) và không có bằng
chứng nào nói tách từ tiếng Việt còn dư địa — nguyên tắc 7. Đây là **câu hỏi còn
mở**, không phải kết luận.

### 4.2 `k1 × b` — và vì sao phải nới lưới

Lưới của prompt ({0,9;1,2;1,5} × {0,3;0,5;0,75}) cho ô thắng nằm **ĐÚNG BIÊN**
(k1=0,9, b=0,3) — không biết là đỉnh hay là tường. Nới thành 5×5. Cũng phải quét
**lại** sau khi đổi tokenizer: trên `folded` ô thắng là k1=0,7 **b=0,30**, tức
tối ưu của một cấu hình khác.

MRR trên `plain` (bảng đầy đủ in ra từ `bm25_sweep.py`):

| k1 \ b | 0,00 | 0,15 | 0,30 | 0,50 | 0,75 |
|---|---|---|---|---|---|
| 0,5 | 0,791 | 0,794 | 0,800 | 0,813 | 0,815 |
| **0,7** | 0,779 | 0,797 | 0,799 | 0,803 | **0,820** |
| 0,9 | 0,779 | 0,790 | 0,794 | 0,808 | 0,814 |
| 1,2 | 0,779 | 0,785 | 0,793 | 0,801 | 0,806 |
| 1,5 | 0,764 | 0,772 | 0,803 | 0,800 | 0,794 |

Ô thắng **k1 = 0,7 · b = 0,75** (MRR 0,820 · R@1 0,760 · R@10 0,950), nằm trong
lòng lưới. Ô tệ nhất 0,764 → **mặt tối ưu khá phẳng**: k1/b đáng chọn bằng số
nhưng không phải thứ quyết định kết quả.

### 4.3 Một lỗi của chính lượt này, ghi lại vì nó đúng lớp lỗi repo sợ nhất

Một bản vá chuỗi ở mục 4 của `bm25_sweep.py` **không khớp và không kêu gì cả**,
nên chỉ mục theo trang bị dựng bằng `folded` trong khi chỉ mục theo chunk là
`plain` → phép so ra **R@1 = 0,16**, trông như một phát hiện lớn. Bắt được vì con
số vô lý: vốn từ theo trang **phải chứa** vốn từ theo chunk (văn bản trang là nối
các chunk của nó). Nay mục 4 **kiểm bất biến đó và raise** trước khi so.

---

## 5. B3 — hợp nhất, cổng lọc, và bảng 12 cấu hình (D-80, D-81)

### 5.1 Phát hiện: trước M2, cổng lọc và rerank LOẠI TRỪ NHAU

`VectorDB.get_retriever` cũ:

```python
if RERANK_ENABLED:
    return RerankedRetriever(...)
return RelevanceGatedRetriever(...)
```

`.env` đặt `RERANK_ENABLED=true`, nên **`RelevanceGatedRetriever` chưa từng
chạy** và `RETRIEVER_DISTANCE_MARGIN = 0.3` là **số chết**. Cái đang thực sự đóng
vai cổng lọc là sàn tuyệt đối `RERANK_SCORE_MIN = 0.2`. Bảng ablation 4 tổ hợp
{rerank on/off} × {cổng lọc on/off} **không thể dựng** nếu giữ nguyên cấu trúc đó.

### 5.2 Cổng lọc: định nghĩa ĐÃ ĐỔI — và nói rõ là đã đổi

Cổng cũ so **khoảng cách dày**. Sau hợp nhất, thứ tự không do khoảng cách quyết
định nữa, nên `fusion.relevance_gate` được tổng quát thành "tương đối quanh ứng
viên tốt nhất **theo điểm xếp hạng hiện hành**", thêm tham số `higher_is_better`.
Ở đúng ngữ cảnh cũ (một kênh dày, khoảng cách) nó trả về **đúng** công thức cũ
`d <= best*(1+margin)` — có test chốt.

**Cái bẫy của §3.3, tính ra được chứ không phải phỏng đoán:** với RRF, điểm hạng
1 là `1/(60+1) = 0,01639`, hạng 10 là `1/(60+10) = 0,01429` — chênh **12,86%**,
nằm gọn trong `margin = 0,3`, nên **cổng tương đối không cắt gì trong top 10**.
Một cổng lọc "bật" mà không cắt gì là một cột ablation **rỗng mà trông có nghĩa**.
Vì thế `FUSION_METHOD = norm` (chuẩn hoá min-max, giữ độ chênh thật) tồn tại song
song với `rrf`, và `GateStats` đo **tỉ lệ truy vấn thực sự bị cắt**.

### 5.3 Tự kiểm bắt buộc — đã cài thành test, không phải lời hứa

- `hybrid` với kênh thưa rỗng cho ra **đúng** dãy kết quả của `dense` thuần (và
  ngược lại) — nếu không thì đường ống có nhánh ẩn.
- `dense` thuần **không chạm** kênh thưa và ngược lại (bơm đối tượng nổ tung vào
  kênh kia).
- Thiếu chỉ mục thưa → **raise**, không âm thầm rơi về dense.
- Cross-encoder hỏng → **raise**, không xếp theo điểm hợp nhất.
  (`RerankedRetriever` cũ rơi về thứ tự khoảng cách kèm một dòng warning — đúng
  cách hỏng âm thầm đã cắn thật một lần dưới `HF_HUB_OFFLINE=1`.)

### 5.4 Chạy thật trên index 12 quyển — một ca minh hoạ

Không phải đồ giả: đi qua đúng `VectorDB.get_retriever()` với bge-m3 và
cross-encoder thật. Truy vấn `"Dinh luat Ohm phat bieu the nao"`:

| chế độ | ba kết quả đầu |
|---|---|
| dense (rerank on) | 8_KNTT tr.116 · 8_CD tr.157 · 8_CD tr.92 |
| **hybrid** | **9_CD tr.42 · 9_KNTT tr.56 · 9_CTST tr.39** |

9_KNTT tr.56 chứa `3. Định luật Ohm`; 9_CTST tr.39 chứa `Điện trở. Định luật
Ohm`. **Kênh dày trượt bài, kênh thưa tìm ra.** *Cảnh báo về chính ca này:* ba
truy vấn khói này viết **không dấu**, mà bge-m3 được huấn luyện trên tiếng Việt
có dấu — nên ca này minh hoạ tốt cho "thuật ngữ đặc thù, hiếm, không dấu"
(`Ohm`), **không** đại diện cho câu hỏi của học sinh nói chung. Con số đại diện
là bảng §5.5.

### 5.5 Bảng 12 cấu hình

**Bộ test: 100 câu / 4 quyển KNTT / LLM sinh, CHƯA có người duyệt.** Mọi con số
dưới đây phải được báo cáo kèm câu đó, và kèm §5.6.

`trầnP@5 = 0,966` cho mọi hàng: trang vàng trung bình có ~6 chunk, nên
precision@5 hoàn hảo cũng chỉ đạt 0,966. P@5 thực tế 0,23–0,32 → **precision còn
xa trần của chính nó**, tức top-5 chủ yếu là chunk của trang khác. Đây là con số
§2.2 đòi báo cáo cạnh precision.

| cấu hình | R@1 | R@3 | R@5 | R@10 | MRR | P@5 |
|---|---|---|---|---|---|---|
| bm25 · rerank off · gate off | 0,760 | 0,860 | 0,900 | 0,950 | 0,820 | 0,288 |
| bm25 · rerank off · gate on | 0,760 | 0,860 | 0,900 | 0,950 | 0,820 | 0,288 |
| bm25 · rerank **on** · gate off | 0,830 | 0,960 | 0,960 | **1,000** | 0,897 | 0,314 |
| bm25 · rerank **on** · gate on | 0,830 | 0,960 | 0,960 | 0,990 | 0,896 | 0,314 |
| dense · rerank off · gate off | 0,600 | 0,810 | 0,940 | 0,980 | 0,727 | 0,298 |
| dense · rerank off · gate on | 0,600 | 0,810 | 0,940 | 0,980 | 0,727 | 0,298 |
| dense · rerank **on** · gate off | 0,810 | 0,940 | 0,950 | 0,990 | 0,881 | 0,308 |
| dense · rerank **on** · gate on | 0,810 | 0,950 | 0,950 | 0,990 | 0,882 | 0,308 |
| hybrid · rerank off · gate off | 0,670 | 0,920 | 0,980 | **1,000** | 0,792 | 0,318 |
| hybrid · rerank off · gate on | 0,670 | 0,920 | 0,980 | **1,000** | 0,792 | 0,318 |
| hybrid · rerank **on** · gate off | 0,820 | 0,950 | 0,960 | **1,000** | 0,891 | 0,312 |
| **hybrid · rerank on · gate on** | **0,830** | **0,960** | 0,960 | **1,000** | **0,898** | 0,312 |

**Bốn điều bảng này nói, theo thứ tự quan trọng:**

1. **BM25 thuần ĐÁNH BẠI dense thuần** ở đầu danh sách: R@1 **0,760 vs 0,600**,
   MRR **0,820 vs 0,727**. Dense chỉ hơn ở đuôi (R@10 0,980 vs 0,950). Đây là kết
   quả ngược với kỳ vọng thông thường và **phải đọc kèm §5.6** trước khi đưa vào
   báo cáo.
2. **Hybrid là cấu hình DUY NHẤT đạt R@10 = 1,000 mà KHÔNG cần rerank**
   (bm25 0,950 · dense 0,980). Nghĩa là **tập ứng viên** của hybrid thật sự tốt
   hơn, chứ không phải nhờ rerank cứu. Đó là lý do đề xuất hybrid chứ không phải
   bm25, dù MRR của hai cái gần bằng nhau khi bật rerank (0,898 vs 0,897).
3. **Rerank là thành phần có tác dụng lớn nhất**, ở cả ba chế độ:
   MRR bm25 0,820 → 0,897 · dense 0,727 → 0,882 · hybrid 0,792 → 0,898.
4. **Cổng lọc tương đối gần như KHÔNG có tác dụng** — xem §5.6.

**Đề xuất: `RETRIEVAL_MODE=hybrid` + `RERANK_ENABLED=true` + `FUSION_METHOD=rrf`.**
Lý do: nó thắng hoặc hoà ở mọi cột (R@1 0,830 · R@3 0,960 · R@10 1,000 · MRR
0,898), và là cấu hình duy nhất **không phụ thuộc rerank để đạt R@10 = 1,000** —
quan trọng vì rerank là thứ đắt nhất trong đường chạy và là thứ đã từng **tắt âm
thầm** một lần. `RELEVANCE_GATE_ENABLED` để `true` cũng được (chênh +0,007 MRR,
trong khoảng nhiễu của n = 100).

### 5.6 Ba điều phải nói ra, không được để bảng số tự nói

**(a) Cổng lọc tương đối không mua được gì, và dưới `norm` thì có hại.** Tách
riêng tác dụng của nó (rerank BẬT ở mọi hàng):

| | R@10 (gate off → on) | MRR (gate off → on) |
|---|---|---|
| bm25 · rrf | 1,000 → 0,990 | 0,897 → 0,896 |
| dense · rrf | 0,990 → 0,990 | 0,881 → 0,882 |
| hybrid · rrf | 1,000 → 1,000 | 0,891 → **0,898** |
| bm25 · **norm** | 1,000 → **0,890** | 0,897 → **0,833** |
| dense · **norm** | 0,990 → **0,870** | 0,881 → **0,829** |
| hybrid · **norm** | 1,000 → **0,940** | 0,891 → **0,884** |

Dưới `rrf` cổng lọc **trung tính** (±0,007); dưới `norm` nó **cắt mất đáp án
thật** (R@10 rơi tới 0,890). Nên **cổng lọc liên quan thực sự đang hoạt động
trong hệ thống là sàn tuyệt đối `RERANK_SCORE_MIN`, không phải cổng tương đối**.
Ghi nhận này quan trọng cho báo cáo: đề cương gọi tên "cổng lọc liên quan" như
một thành phần, và số đo nói thành phần *dạng tương đối* không đóng góp gì.

Cũng chỉnh lại một câu ước lượng ở D-80: ở đó tính "RRF nén điểm nên cổng không
cắt gì" **cho top-10**. Với `CANDIDATE_N = 50` thì cổng **có** cắt — `cắt = 1,00`
ở mọi hàng, tức mọi truy vấn đều bị bỏ bớt ứng viên. Nó chỉ cắt phần **đuôi sau
hạng ~26**, nên không thấy được ở k ≤ 10. Ước lượng cũ đúng về cơ chế, sai về
phạm vi.

**(b) Khi rerank BẬT và cổng lọc TẮT, cách hợp nhất không còn ảnh hưởng gì cả** —
`rrf` và `norm` cho **số giống hệt nhau** (hybrid: 0,820/0,950/0,960/1,000/0,891
ở cả hai). Hiển nhiên khi nhìn ra: hợp nhất chỉ quyết định **tập** ứng viên và
thứ tự *trước* rerank, mà rerank thì sắp lại toàn bộ tập đó. Vậy câu hỏi "chọn
RRF hay chuẩn hoá" thực chất là câu hỏi "cổng lọc cư xử thế nào dưới mỗi cách" —
và (a) trả lời: **rrf**.

**(c) Bộ test này THIÊN VỊ kênh từ khoá, và điều đó có thể giải thích trọn vẹn
điểm (1).** Câu hỏi do LLM sinh **trong lúc đọc chính trang vàng**, nên nó có xu
hướng dùng lại thuật ngữ đặc trưng của trang đó nguyên văn — đúng thứ BM25 giỏi
nhất. Học sinh thật diễn đạt bằng lời của mình. Nên **không được viết vào báo cáo
rằng "BM25 thuần tốt hơn vector"** từ bảng này; câu đúng là *"trên bộ test sinh
tự động, kênh từ khoá đủ mạnh để không được bỏ, và hợp nhất thắng cả hai"*. Cách
kiểm tra rẻ: bộ test 12 quyển của Track A có nhãn `do_kho`, nên chạy lại bảng này
**tách theo `do_kho`** — nếu ưu thế của BM25 tập trung ở nhóm `truc_tiep` và biến
mất ở nhóm `suy_luan`, thiên vị đã được xác nhận bằng số.

---

## 6. Trạng thái file khi bàn giao

**Đã commit và push** (`47ced14`, `bc90863`):

```
src/rag/bm25.py                  chỉ mục thưa Okapi BM25 (scipy)
src/rag/text_normalize.py        chuẩn hoá công thức + tách từ
src/rag/sparse_store.py          dựng/nạp + đối chiếu dấu vân
src/rag/fusion.py                RRF / chuẩn hoá min-max + cổng lọc + GateStats
src/rag/hybrid_text_retriever.py hợp nhất -> cổng lọc -> rerank
src/rag/vectorstore.py           định tuyến theo RETRIEVAL_MODE + ChunkLookup dùng chung
src/config.py                    9 công tắc mới (§7)
main.py                          --build-bm25
src/test/{ablation,bm25_sweep,formula_probe}.py
scripts/run_ablation.ps1
tests/rag/{test_bm25,test_fusion,test_hybrid_text_retriever,test_sparse_store}.py
```

`pytest tests/rag/ -q` → **102 passed, 1 skipped**.

**Không commit (đúng thiết kế):** `database/sparse/` và `database/ablation_cache.json`
— `.gitignore` bỏ qua `database/*`, và cả hai là **artefact sinh lại được** bằng
`scripts\run_ablation.ps1`.

**Không đụng tới (của Track A):** `src/test/generate_testsets.py`,
`src/test/testsets/`, `scripts/run_testsets.ps1`, `tests/test_eval_gold_keys.py`.

## 7. Công tắc mới trong `src/config.py`

| biến | mặc định | ghi chú |
|---|---|---|
| `RETRIEVAL_MODE` | `dense` | `dense` \| `bm25` \| `hybrid`. Mặc định = **hành vi hôm nay**, có chủ ý: chỉ đổi sang `hybrid` khi bảng §5.5 có số |
| `SPARSE_INDEX_DIR` | `database/sparse` | đổi bằng `RAG_SPARSE_INDEX_DIR` |
| `BM25_K1` / `BM25_B` | **0.7 / 0.75** | chọn bằng phép quét §4.2 |
| `BM25_TOKENIZER` | **plain** | chọn bằng phép đo §4.1 |
| `BM25_FETCH_K` | 20 | ứng viên từ kênh thưa |
| `FUSION_METHOD` | `rrf` | `rrf` \| `norm` |
| `FUSION_RRF_K` | 60 | |
| `FUSION_DENSE_WEIGHT` | 0.5 | |
| `RELEVANCE_GATE_ENABLED` | `true` | tách rời khỏi `RERANK_ENABLED` |

## 8. Việc còn lại của M2

| # | việc | ai | ghi chú |
|---|---|---|---|
| 1 | Bộ test 12 quyển có nhãn | Track A | đang chạy |
| 2 | Chạy lại §5.5 trên bộ test 12 quyển, **tách theo `do_kho`** | Track B | một lệnh; kiểm thiên vị BM25 ở §5.6(c) |
| 3 | Đổi mặc định `RETRIEVAL_MODE` → `hybrid` | Track B | **sau (2)**, không đổi dựa trên bộ test 4/12 quyển |
| 3b | Cân nhắc bỏ hẳn cổng lọc tương đối | Track B | §5.6(a): nó không mua được gì, và dưới `norm` thì có hại |
| 4 | M2.3 caption deterministic vào ngữ cảnh | chưa ai | không có nó thì ablation "đa phương thức vs chỉ văn bản" chênh **0 theo cấu trúc** |
| 5 | M2.4 `chain.py` bỏ "môn Sinh học" → KHTN; quyết định về `format_docs` bỏ 6,65% chunk | chưa ai | §1.2 đã có số |
| 6 | Hiệu chỉnh `needs_review` (đang bật 69,31%) | chưa ai | gom vào lượt OCR lại |
| 7 | Đổi tên `_archive_4books_kntt_offset_minus1/` | Track A | tên mô tả sai thực tế (§1.1) |
