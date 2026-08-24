<#
    Sinh bộ test 12 quyển, chạy được không cần trông.

    Dùng:
        powershell -ExecutionPolicy Bypass -File scripts\run_testsets.ps1
        powershell -ExecutionPolicy Bypass -File scripts\run_testsets.ps1 -PerBook 25

    Thiết kế quanh MỘT điều chưa biết: hạn mức/ngày của OpenRouter free tier **chưa
    đo được** (API không trả header `x-ratelimit-*`, `/api/v1/key` trả `limit: null`
    — D-67). Nên script này không giả định gì về hạn mức:

    * chạy **TỪNG QUYỂN MỘT** tiến trình riêng, để một quyển bị chặn không giết lượt
      chạy của quyển sau;
    * `generate_testsets.py` thoát **mã 2** khi hết hạn mức -> script **dừng** ở đó
      thay vì đốt tiếp 11 quyển vào một API đang chặn;
    * chạy lại đúng lệnh này là **tiếp tục** (mỗi câu đã được ghi ngay vào CSV).

    KHÔNG gọi LLM: bước `--dry-run` ở đầu. Nó cho biết cần bao nhiêu trang / bao
    nhiêu lượt gọi TRƯỚC khi tiêu lượt gọi nào.
#>

param(
    [int]$PerBook = 25,
    [int]$PerCall = 3,
    [switch]$DryRunOnly,
    # Bo qua buoc dry-run. Dry-run KHONG ton luot goi nao, nhung no OCR dung
    # nhung trang ma luot that se OCR lai -> ~10-20 phut cho 12 quyen, khong
    # tiet kiem luot goi. Dung khi dang gap.
    [switch]$SkipDryRun
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $root "testsets_run_$stamp.log"

function Say($text) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $text
    Write-Host $line
    Add-Content -Path $log -Value $line
}

$books = @(
    "SGK_KHTN_6_KNTT", "SGK_KHTN_7_KNTT", "SGK_KHTN_8_KNTT", "SGK_KHTN_9_KNTT",
    "SGK_KHTN_6_CTST", "SGK_KHTN_7_CTST", "SGK_KHTN_8_CTST", "SGK_KHTN_9_CTST",
    "SGK_KHTN_6_CD",   "SGK_KHTN_7_CD",   "SGK_KHTN_8_CD",   "SGK_KHTN_9_CD"
)

Say "log: $log"
Say "stderr: testsets_stderr_$stamp.log"
Say "$($books.Count) quyen x $PerBook cau, $PerCall cau/luot goi"
Say "Uoc luong: ~$([math]::Ceiling($PerBook / $PerCall)) luot goi/quyen -> ~$([math]::Ceiling($PerBook / $PerCall) * $books.Count) luot goi tong."

# --- BƯỚC 0: dry-run, 0 lượt gọi LLM ---------------------------------------
if ($SkipDryRun) {
    Say "=== BO QUA DRY RUN (-SkipDryRun) ==="
} else {
Say "=== DRY RUN (0 luot goi LLM) — xem no chon duoc du trang khong ==="
foreach ($book in $books) {
    & python src/test/generate_testsets.py --dry-run --book $book `
        --per-book $PerBook --per-call $PerCall 2>&1 |
        Select-String -Pattern "^==|xet .* trang" | Tee-Object -Append $log
}
}
if ($DryRunOnly) { Say "DryRunOnly -> dung o day."; exit 0 }

# --- BƯỚC 1: sinh thật, từng quyển một -------------------------------------
Say "=== SINH THAT — tung quyen mot tien trinh rieng ==="
$done = 0
foreach ($book in $books) {
    Say "-- $book"
    # KHONG dung `2>&1 | Tee-Object`: PowerShell bien moi dong stderr cua mot
    # native command thanh mot error record (NativeCommandError), va do chinh la
    # nguon cua "SGK_KHTN_6_CD thoat ma -1" trong luot chay 2026-08-24 — quyen do
    # ghi WARNING ra stderr (spine Bai khong lien mach) va PowerShell tra ve -1
    # trong khi tien trinh Python van chay binh thuong. Ghi stderr thang ra file
    # rieng thi $LASTEXITCODE moi la ma thoat THAT cua Python.
    $err = Join-Path $root "testsets_stderr_$stamp.log"
    & python src/test/generate_testsets.py --book $book `
        --per-book $PerBook --per-call $PerCall 2>>$err | Tee-Object -Append $log
    $code = $LASTEXITCODE
    if ($code -eq 2) {
        Say "!! HET HAN MUC o $book (ma thoat 2). DUNG lai, KHONG dot tiep cac quyen sau."
        Say "   Cau da sinh van nam trong CSV. Chay LAI DUNG LENH NAY sau khi han muc"
        Say "   duoc reset — no se tiep tuc tu cho dung."
        break
    }
    if ($code -ne 0) {
        Say "!! $book thoat ma $code — di tiep quyen sau, xem log de biet vi sao."
    }
    $done++
}

# --- BÁO CÁO ---------------------------------------------------------------
Say "=== DA SINH DUOC GI ==="
& python -c @"
import csv, glob, json, os, collections
d = os.path.join('src', 'test', 'testsets')
tong = 0
trang = set()
kho = collections.Counter()
mon = collections.Counter()
for path in sorted(glob.glob(os.path.join(d, '*_testset.csv'))):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    tong += len(rows)
    for r in rows:
        trang.add((r['source_book'], r['source_page']))
        kho[r.get('do_kho') or '(rong)'] += 1
        mon[r.get('phan_mon') or '(rong)'] += 1
    print(f\"{os.path.basename(path):34} {len(rows):4} cau\")
print(f'TONG {tong} cau tu {len(trang)} trang vang')
print('theo do kho :', dict(kho))
print('theo phan mon:', dict(mon))
meta = os.path.join(d, '_generation_meta.json')
if os.path.exists(meta):
    m = json.load(open(meta, encoding='utf-8'))
    print('human_reviewed:', m.get('human_reviewed'), '| stopped_early:', m.get('stopped_early') or '(khong)')
"@ 2>&1 | Tee-Object -Append $log

Say "XONG ($done/$($books.Count) quyen chay het). Log: $log"
Say "Buoc tiep: NGUOI duyet tay ~50 cau (D-74 #6), roi chay bang ablation."
