<#
    Chạy ETL "treo máy" trên PC: manifest 12 quyển -> text ETL -> báo cáo.

    Dùng:
        powershell -ExecutionPolicy Bypass -File scripts\run_etl_local.ps1

    Vì sao là một script chứ không phải hai lệnh gõ tay:

    * `--build-manifests` **thoát mã 1 khi cổng G1 FAIL**, và hôm nay nó SẼ fail
      (spine Bài của 8 quyển CTST/CD chưa liền mạch — D-70). Nhưng manifest vẫn
      được ghi ra cho từng quyển dựng xong, và text ETL chỉ cần manifest tồn tại.
      Nối hai lệnh bằng `&&` sẽ chặn bước 2 một cách vô lý; script này đọc mã
      thoát, IN RA, rồi vẫn chạy tiếp — và nói rõ đã bỏ qua cái gì.
    * Mọi thứ vào một log có mốc thời gian, để sáng mai đọc lại được.

    KHÔNG chạy `--image-only` ở đây: kênh pill đọc được 0 nhãn trên 8/12 quyển
    (D-65), nên chạy phía ảnh trước M3 là ~6 giờ để lấy kết quả đã biết là sai.
#>

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $root "etl_run_$stamp.log"

function Say($text) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $text
    Write-Host $line
    Add-Content -Path $log -Value $line
}

Say "log: $log"
Say "python: $((Get-Command python).Source)"

# Tesseract là điều kiện cần cho CẢ HAI bước — thiếu nó thì fail ngay ở đây chứ
# đừng để phát hiện sau 40 phút.
$tess = & python -c "from src.config import TESSERACT_CMD; print(TESSERACT_CMD)" 2>&1
Say "TESSERACT_CMD = $tess"
& python -c @"
import sys, pytesseract
from src.config import TESSERACT_CMD
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
langs = pytesseract.get_languages()
print('tesseract langs:', 'vie' in langs, '| ver:', pytesseract.get_tesseract_version())
sys.exit(0 if 'vie' in langs else 1)
"@ 2>&1 | Tee-Object -Append $log
if ($LASTEXITCODE -ne 0) {
    Say "DUNG: tesseract thieu goi ngon ngu 'vie'. Xem windows_tools/."
    exit 1
}

# ---------------------------------------------------------------- BƯỚC 1
Say "=== BUOC 1/2: --build-manifests (12 quyen, ~1,3 s/trang -> ~50 phut) ==="
& python main.py --build-manifests 2>&1 | Tee-Object -Append $log
$g1 = $LASTEXITCODE
if ($g1 -eq 0) {
    Say "G1 PASS het 12 quyen."
} else {
    Say "G1 FAIL (ma $g1) — DU KIEN hom nay: spine Bai cua CTST/CD chua lien mach."
    Say "Manifest van duoc ghi cho tung quyen dung xong, nen buoc 2 chay duoc."
    Say "Quyen nao spine khong lien mach thi `bai_so` KHONG duoc ghi vao metadata"
    Say "chunk — do la hanh vi thiet ke (thieu thi im, khong doan)."
}

$manifests = @(Get-ChildItem -Path (Join-Path $root "database\manifests") -Filter *.json -ErrorAction SilentlyContinue)
Say "manifest tren dia: $($manifests.Count) file"
if ($manifests.Count -eq 0) {
    Say "DUNG: khong co manifest nao -> --text-only se raise ManifestMissing."
    exit 2
}

# ---------------------------------------------------------------- BƯỚC 2
Say "=== BUOC 2/2: --text-only (chi cac quyen CO manifest) ==="
Say "Ngat giua duong khong sao: checkpoint theo TUNG TRANG, chay lai dung lenh nay."
& python main.py --text-only 2>&1 | Tee-Object -Append $log
$etl = $LASTEXITCODE
Say "--text-only thoat ma $etl"

# ---------------------------------------------------------------- BÁO CÁO
Say "=== CON LAI GI ==="
& python -c @"
import os
from src.etl import ProcessingStatus
from src.etl.page_source import discover_page_sources
from src.config import DATA_DIR
status = ProcessingStatus()
tong_text = 0
for source in discover_page_sources(DATA_DIR):
    con = len(status.pages_needing_text(source))
    tong_text += con
    print(f'{source.name}: text con thieu {con}/{len(source.page_numbers())}')
print('TONG text con thieu:', tong_text)
"@ 2>&1 | Tee-Object -Append $log

Say "XONG. Log: $log"
Say "Buoc tiep theo (KHONG chay hom nay): --image-only, cho sau M3."
