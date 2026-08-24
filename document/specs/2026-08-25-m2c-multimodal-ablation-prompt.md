# Prompt cho lượt sau — M2C: làm cho "đa phương thức vs chỉ văn bản" ĐO ĐƯỢC

> **Đọc trước, theo thứ tự:** `CLAUDE.md` (RULE #0, "Philosophy" 7 nguyên tắc,
> "Định nghĩa xong"); `document/specs/2026-08-24-m2-track-b-report.md` (báo cáo
> Track B, số đã đo); `document/specs/2026-08-24-m2-bm25-hybrid-prompt.md` §2
> (10 quyết định đã chốt) và §4 (11 điều CẤM); `document/decision_log.html`
> **D-76…D-83**.
>
> Entry mới bắt đầu từ **D-84**. (Prompt này ban đầu ghi D-83; số đó đã bị
> dùng cho bản vá `run_ablation.ps1` in "XONG" khi bước 4 thất bại.)
>
> **Tinh thần:** phản biện chính mình. Mỗi con số phải chạy ra được và dán được
> vào decision log. Một giả thuyết chưa đo là **câu hỏi mở**, không được lặng lẽ
> thành thiết kế. Test pass ≠ đúng.

---

## 0. Hợp đồng, và vì sao đây là việc kế tiếp

Đề cương **Mục tiêu 4**: *"so sánh hiệu năng trực tiếp giữa … **Hệ thống RAG đa
phương thức so với hệ thống RAG chỉ sử dụng văn bản**."*
**Nội dung 4**: *"(ii) RAG đa phương thức so với RAG chỉ văn bản."*
**Bảng Kế hoạch — Giai đoạn 3 (14/08 → 28/08/2026)**: *"cấu hình 2: Text-only vs
Multi-modal."*

Cấu hình 1 (BM25 / dense / hybrid) **đã xong** — D-82, 300 câu / 12 quyển.
Cấu hình 2 **chưa chạy được**, và đó là hạng mục hợp đồng còn lại của Giai đoạn 3.

**Hôm nay 25/08. Giai đoạn 3 đáo hạn 28/08 → còn 3 ngày. Deadline cuối 23/09.**

## 1. ĐÃ ĐO — dùng luôn, ĐỪNG đo lại

| | số đo | nguồn |
|---|---|---|
| index text | **16 393 chunk / 2 387 trang / 12 quyển** | D-73 |
| chỉ mục thưa BM25 | 16 393 chunk / 19 727 từ vựng / **5,5 s** | D-77 |
| mặc định đang chạy | `RETRIEVAL_MODE=hybrid`, `RELEVANCE_GATE_ENABLED=false` | **D-82** |
| bảng cấu hình 1 (300 câu, bề rộng production) | hybrid R@1 0,717 · R@3 0,887 · R@10 **0,977** · MRR **0,808** | D-82 |
| bộ test | **300 câu / 12 quyển**, đủ `phan_mon`/`do_kho`/`khoi`/`bo_sach`; 0 gold key trỏ vào trang không có chunk | D-75, D-82 |
| **`biology_images`** | **0 document** | đo 2026-08-24 |
| **`biology_image_metadata`** | **0 document** | đo 2026-08-24 |
| chi phí phía ảnh | **~8,86 s/trang** (mẫu nhỏ, 4 trang nhiều hình) | D-53 |
| chi phí đệm ablation | **~22–31 s/câu** (bge-m3 + cross-encoder, CPU 16 lõi, không GPU) | D-81, D-82 |
| model local | `models/{clip-vit-base-patch16, owlvit-base-patch32, bge-reranker-v2-m3, Qwen2.5-3B-Instruct}` đủ | đo 2026-08-24 |

**Ba giới hạn phải nhớ trước khi thiết kế:**

1. **Kênh pill đọc được 0 nhãn trên 8/12 quyển** (CD/CTST dùng caption chữ đen,
   KNTT dùng pill) — D-65. Nên phía ảnh chỉ đáng tin ở **4 quyển KNTT**.
2. **Người dùng đã chốt thu hẹp phía ảnh** (D-74 #9): ablation đa phương thức
   chạy trên **4 quyển KNTT** và **NÓI RÕ là 4 quyển**, không pha loãng bằng 8
   quyển không có caption.
3. **Vintern-1B đã bị loại** (D-47, D-74 #1). `IMAGE_CAPTION_ENABLED` phải giữ
   `false`. Bệnh thật không phải "thiếu caption" mà là **kênh ảnh không truy vấn
   được bằng tiếng Việt** (`CLIP_MODEL` là CLIP tiếng Anh; cầu Việt–Anh là một
   từ điển **14 mục** viết cứng) — đọc D-74 §2.1 trước khi động vào.

## 2. VIỆC — bốn bước, mỗi bước một tiêu chí nghiệm thu ĐO ĐƯỢC

### M2C.1 — Dựng kho ảnh cho 4 quyển KNTT (chạy không cần trông, ~2 giờ)

**ĐÃ KIỂM, và câu trả lời là KHÔNG — việc đầu tiên là thêm bộ lọc quyển.**
`main.py:735` gọi `run_etl_image_only()` **không tham số**, và `--book`
(`main.py:696`) hiện chỉ nối vào `--build-manifests`. Nên
`python main.py --image-only` sẽ chạy **cả 12 quyển ≈ 6 giờ**, trong đó 8 quyển
CD/CTST đã biết trước là sai (kênh pill đọc 0 nhãn — D-65). Đó đúng là CẤM #5.

Vậy thứ tự bắt buộc:

1. Nối `--book` vào `--image-only` (và `--etl` nếu tiện), kèm **test nhỏ** chứng
   minh nó lọc đúng và **raise** khi tên quyển không tồn tại — đừng để nó âm thầm
   xử lý 0 quyển rồi báo thành công.
2. Rồi mới chạy, 4 quyển KNTT một lượt:

```bash
python main.py --image-only --book SGK_KHTN_6_KNTT
python main.py --image-only --book SGK_KHTN_7_KNTT
python main.py --image-only --book SGK_KHTN_8_KNTT
python main.py --image-only --book SGK_KHTN_9_KNTT
```

797 trang × ~8,86 s/trang ≈ **2 giờ**. Chia bốn lượt thì mất điện giữa chừng chỉ
mất một quyển, và checkpoint theo trang vẫn cho chạy tiếp.

**Nghiệm thu:** `biology_images` > 0; cổng G4 (`python -m src.test.qa_figures`)
chạy lại trên 4 quyển KNTT và **báo cáo số thật hôm nay**, không trích lại con số
100% cũ — con số đó đo trên corpus 801 trang đã bị thay (CẤM #7).

**Cảnh báo đã biết (D-52):** id của image doc là hash của **crop**, nên crop đổi
thì sinh doc mới chứ không ghi đè. `ImageVectorDB.delete_page_documents` phải
được gọi cho các trang sắp ghi lại. Kho đang rỗng nên lượt đầu không sao, nhưng
lượt **thứ hai** thì có.

### M2C.2 — Caption deterministic vào NGỮ CẢNH (chỗ hiện đang chênh 0)

`src/app/api.py` dựng ngữ cảnh **chỉ từ `text_docs`**; `image_docs` chỉ ra
gallery. Nên dù kho ảnh đầy, ablation vẫn chênh **0 theo cấu trúc**.

- Ngữ cảnh multi-modal = text chunk + `figure_label` + caption đọc từ
  **pill/OCR deterministic**. **KHÔNG sinh chữ bằng model nào.**
- Bật/tắt bằng `.env` (ví dụ `MULTIMODAL_CONTEXT_ENABLED`), mặc định **giữ
  nguyên hành vi hôm nay** cho tới khi có số (nguyên tắc 3 — đúng cách đã làm
  với `RETRIEVAL_MODE` ở D-82).
- **Đo cả hai chiều:** nó có thể làm **tệ hơn** (thêm nhiễu vào ngữ cảnh — chính
  điều đề cương cảnh báo ở phần định tuyến). **Báo cáo cả khi nó tệ hơn** (CẤM #7,
  và quyết định #7 của người dùng).

### M2C.3 — Bảng cấu hình 2

- Chạy trên **100 câu KNTT** của bộ test 300 câu, **nói rõ là 4/12 quyển**.
- Dùng lại `src/test/ablation.py`: nó đã có `--group-by` (tách theo nhãn) và
  `Config.cand_n`. Thêm trục multi-modal on/off theo đúng kiểu đó.
- **BÀI HỌC ĐẮT NHẤT CỦA D-82, ĐỪNG LẶP LẠI:** đo ở **đúng bề rộng production**.
  Bảng cấu hình 1 suýt sai vì đo ở 50 ứng viên/kênh trong khi `.env` chạy 20 —
  ở 50 ưu thế hybrid là +0,005 MRR (nhiễu), ở 20 là +0,014 MRR / +0,020 R@10.
- **Tự kiểm bắt buộc:** cấu hình "multi-modal" mà kho ảnh rỗng phải cho ra
  **đúng** kết quả của text-only. Không đúng thì đường ống có nhánh ẩn.

### M2C.4 — Hai khiếm khuyết rẻ, làm xen kẽ lúc chờ

1. **`src/rag/chain.py:39` khoá cứng `"Bạn là trợ lý AI môn Sinh học THCS"`**
   trong khi phạm vi hợp đồng là **cả Lý – Hoá – Sinh** (Mục tiêu 2). Một câu hỏi
   Vật lý đang được trả lời bởi một trợ lý tự nhận là dạy Sinh học. Sửa thành
   KHTN, **kèm before/after trên câu Lý và câu Hoá** — đừng sửa chuỗi rồi tuyên
   bố cải thiện.
2. **`format_docs` bỏ mọi đoạn ≤ 40 ký tự.** Đã đo: **1 090 / 16 393 = 6,65%**
   chunk bị bỏ **im lặng** (D-76). 10 chunk ngắn nhất là rác OCR thật (`5`, `|`),
   nhưng 6,65% là tỉ lệ phải quyết định có ý thức. Đo trước, rồi quyết.

## 3. CẤM (kế thừa §4 của prompt M2, cộng ba điều mới từ D-81/D-82)

1. Không sửa chữ đã lưu trong `biology_text`.
2. Không bật `IMAGE_CAPTION_ENABLED` (Vintern đã bị loại).
3. Không đổi `EMBEDDING_MODEL` / `CHUNK_SIZE` / `CHUNK_OVERLAP`.
4. **Không bump `TEXT_EXTRACTION_VERSION`** — bump là OCR lại **3 giờ 20**.
5. Không chạy `--image-only` cho cả 12 quyển (~6 giờ, 8/12 quyển đã biết là sai).
6. Không `except` im lặng, không fallback im lặng — **raise** và **in ra**.
7. Không so số mới với số corpus cũ như cùng điều kiện.
8. Không dùng `needs_review` làm điều kiện lọc (đang bật ở 69,31%).
9. Không chạy cả test suite khi đang lặp.
10. Không `Co-Authored-By` / "Generated with" trong commit message.
11. Không tuyên bố "xong" khi chưa đồng bộ 4 chỗ + notebook.
12. **MỚI — không đo ở bề rộng khác bề rộng production** rồi chốt mặc định từ đó
    (D-82: suýt kết luận ngược).
13. **MỚI — mọi phép thay chuỗi bằng script phải `assert` số lần khớp.** Trong
    lượt D-81/D-82 có **BA** bản vá không khớp mà **không kêu gì cả**; tệ nhất là
    một điều kiện kiểm tra **chưa từng tồn tại trong code** dù decision log mô tả
    như đã có. Dùng công cụ sửa file báo lỗi khi không khớp.
14. **MỚI — đừng để hai tiến trình cùng ghi `database/ablation_cache.json`.**
    Đã xảy ra: hai lượt song song ghi đè tiến độ của nhau, tốn gấp đôi CPU.

## 4. Trạng thái file khi bàn giao (khớp `git status` thật)

- `master` đã push tới **`9b0601f`**; `pytest tests/ -q` → **449 passed, 3 skipped**.
- Track B sở hữu và đã commit: `src/rag/{bm25,text_normalize,sparse_store,fusion,
  hybrid_text_retriever,vectorstore}.py`, `src/config.py`, `main.py --build-bm25`,
  `src/test/{ablation,bm25_sweep,formula_probe,review_testset}.py`,
  `scripts/run_ablation.ps1`, `tests/rag/*` (107 test).
- **Không trong git (đúng thiết kế):** `database/*` — gồm `database/sparse/` và
  `database/ablation_cache.json`. Dựng lại: `scripts\run_ablation.ps1`.
- **Bảng kết quả:** `src/test/ablation_report_12books.csv` (300 câu) và
  `src/test/ablation_report.csv` (100 câu, bộ lưu trữ 4 quyển — **mốc lịch sử**).
- **Phiếu chờ người duyệt:** `document/review/testset_review_50.csv`, 50 câu rải
  đều theo (quyển × độ khó). **Không gate gì cả** (`grep -rn review_testset` = 0
  ngoài chính nó) — nhưng không có nó thì mọi bảng số chỉ mang cảnh báo định
  tính "chưa người duyệt" thay vì một tỉ lệ sai đo được. Chấm bằng
  `python -m src.test.review_testset --score`.

## 5. Câu hỏi CÒN MỞ — hỏi người dùng, đừng tự quyết

1. **Hạn mức/ngày của OpenRouter free tier** vẫn **chưa đo được** (không có header
   `x-ratelimit-*`, `/api/v1/key` trả `limit: null` — D-67). Ảnh hưởng
   LLM-as-a-judge của Giai đoạn 3.
2. **Có làm CLIP đa ngữ không** (D-74 §2.1 đường (b))? Nó là phép đo đáng viết
   vào báo cáo (thay một model **sinh** bằng một encoder **truy xuất** đa ngữ),
   nhưng tốn dựng lại index ảnh. Người dùng đã **cố ý cắt** ở D-75; mở lại thì
   phải hỏi.
3. **Spine Bài của 8 quyển CTST/CD** vẫn là nợ đã chấp nhận (D-74 #10) → `bai_so`
   chỉ có ở 4/12 quyển, nên truy vấn theo Bài chỉ chạy trên 1/3 kho.
