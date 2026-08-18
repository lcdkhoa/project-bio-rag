# Colab Pro — chạy M1 text ETL (rebuild `biology_text`)

Copy từng **cell** dưới đây vào Google Colab Pro. Thứ tự quan trọng. DB đổ ra
Google Drive nên **sống sót khi rớt phiên** và **resume không nhân đôi chunk**
(đã validate). Deadline-critical: đọc ghi chú tối ưu ở cuối.

> Chọn **Runtime → Change runtime type → GPU** (T4 đủ; L4/A100 nhanh hơn cho embed).

---

### Cell 1 — Kiểm GPU + mount Drive
```python
import torch
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available()
      else "KHÔNG CÓ GPU — vào Runtime > Change runtime type > GPU rồi chạy lại")
from google.colab import drive
drive.mount('/content/drive')
```

### Cell 2 — Cài Tesseract (vie) + Poppler
```bash
!apt-get -qq update
!apt-get -qq install -y tesseract-ocr tesseract-ocr-vie poppler-utils
!tesseract --version | head -1
!tesseract --list-langs | grep -E 'vie|eng'   # phải thấy 'vie'
```

### Cell 3 — Lấy code + corpus
**Cách A — git clone (corpus là git-LFS):**
```bash
%cd /content
!git lfs install
!git clone <YOUR_REPO_URL> project_rag        # <-- ĐIỀN URL repo của bạn
%cd project_rag
!git lfs pull                                  # kéo 12 PDF (nặng)
!ls datasources/*.pdf | wc -l                  # kỳ vọng: 12
```
**Cách B — nếu repo+corpus đã có sẵn trên Drive (bỏ Cách A):**
```bash
# !cp -r "/content/drive/MyDrive/project_rag" /content/project_rag
# %cd /content/project_rag
# !ls datasources/*.pdf | wc -l
```

### Cell 4 — Cài Python deps
```bash
%cd /content/project_rag
!pip -q install -r requirements.txt
```

### Cell 5 — Cấu hình `.env` cho Colab (bge-m3 + GPU + DB trên Drive)
```python
import os
# HF token lấy từ Colab Secrets (icon chìa khoá bên trái, thêm secret tên HF_TOKEN).
# bge-m3 là model public nên token chỉ cần khi bị rate-limit.
try:
    from google.colab import userdata
    HF = userdata.get('HF_TOKEN')
except Exception:
    HF = ''

DB_DIR = '/content/drive/MyDrive/project_bio_rag/database'   # DB sống trên Drive
os.makedirs(DB_DIR, exist_ok=True)

env = f"""HF_TOKEN={HF}
USE_GPU=true
EMBEDDING_MODEL=BAAI/bge-m3
HF_HUB_OFFLINE=0
DIACRITIC_FIX_ENABLED=true
RENDER_DPI=220
RAG_DATABASE_DIR={DB_DIR}
TESSERACT_CMD=tesseract
POPPLER_PATH=
LOG_LEVEL=INFO
"""
open('/content/project_rag/.env', 'w').write(env)
print(env)
```

### Cell 6 — Xoá sạch DB cũ (CHỈ chạy lần build đầu — BỎ QUA khi resume)
```python
import shutil, os, glob
# Rebuild sạch (D-04). ⚠️ KHÔNG chạy cell này khi đang resume sau rớt phiên!
for p in glob.glob(f'{DB_DIR}/*'):
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
print('đã xoá sạch', DB_DIR)
```

### Cell 7 — Chạy text ETL
```bash
%cd /content/project_rag
!python main.py --text-only
```
- Lần đầu tải **bge-m3 (~2.3GB)** rồi mới chạy. Log hiện theo từng trang.
- **Nếu rớt phiên:** chỉ cần **chạy lại đúng cell này** (BỎ QUA Cell 6). Nhờ checkpoint theo hash + id định danh, nó **chỉ xử lý trang chưa xong, không nhân đôi**. DB trên Drive nên không mất gì.

### Cell 8 — Kiểm tra chất lượng index
```python
import os; os.chdir('/content/project_rag')
from collections import Counter
from src.rag.vectorstore import VectorDB
col = VectorDB().db._collection
g = col.get(include=['metadatas'], limit=20000)
print('Tổng chunk biology_text:', col.count())
print('region_type:', Counter(m.get('region_type') for m in g['metadatas']))   # nhiều 'body' + ít 'sidebar'/'info_box'
print('theo sách:', Counter(os.path.basename(str(m.get('source'))) for m in g['metadatas']))  # đủ 12 sách
# soi 3 chunk body xem có bị lẫn text sidebar không:
gb = col.get(where={'region_type': 'body'}, include=['documents'], limit=3)
for d in gb['documents']:
    print('---', ' '.join(d.split())[:160])
```

### Cell 9 — Tải DB về máy (hàm tái dùng)
```python
def download_db(db_dir=DB_DIR, out='/content/biology_db_backup'):
    """Nén DB thành .zip và tải về máy. DB gốc vẫn nằm trên Drive (bản bền)."""
    import shutil, os
    from google.colab import files
    path = shutil.make_archive(out, 'zip', db_dir)
    print(f'Đã nén {os.path.getsize(path)/1e6:.0f} MB -> {path}')
    files.download(path)   # tải qua trình duyệt

download_db()
```
> DB đã nằm trên **Drive** (`RAG_DATABASE_DIR`) là bản lưu **bền vững**. Hàm trên
> chỉ tạo bản zip tiện tải về máy; nếu DB quá lớn (>vài trăm MB) tải trình duyệt
> có thể chậm — khi đó tải trực tiếp thư mục từ Google Drive.

---

## Ghi chú tối ưu (ETL tốn giờ — làm đúng ngay lần đầu)
- **Nút cổ chai là OCR (Tesseract, CPU)**, không phải GPU. GPU tăng tốc phần
  **embed bge-m3** (đã bật tự động khi `USE_GPU=true` + có CUDA). Chọn máy Colab
  **High-RAM** giúp ổn định hơn là đổi GPU xịn.
- **`RENDER_DPI=220`**: đã cân giữa chất lượng OCR và tốc độ (nguồn scan ~150 DPI,
  render cao hơn không thêm chi tiết thật mà chậm hơn). Đừng tăng vô ích.
- **An toàn mất dữ liệu:** DB trên Drive + resume idempotent → rớt phiên chạy lại
  cell 7 là tiếp tục, không trùng chunk. Nên chạy `download_db()` sau khi xong để có
  thêm 1 bản zip.
- **Thời gian ước lượng:** 12 sách × ~200 trang, mỗi trang OCR nhiều vùng → có thể
  **vài giờ**. Cứ để chạy; nếu ngắt thì resume.
- **Kiểm nhanh 1 trang bất kỳ (tuỳ chọn):**
  `!python -m src.test.qa_layout --pdf "SGK KHTN8 CD.pdf" --page 50 --out-dir report/layout_qa`
  rồi mở PNG xem overlay vùng — đặc biệt nên soi 1 trang **CD** (biến thể CD chưa
  validate box nhạt bằng mắt).

## Sau khi ETL xong
- Đây mới là **text index (M1)**. Ảnh (M3) và reranker/prompt (M2) là bước sau.
- Muốn đo baseline: `python src/test/recall_at_k.py` (cần chỉnh testset dùng bge-m3).
