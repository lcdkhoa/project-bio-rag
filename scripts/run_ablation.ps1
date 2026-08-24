<#
    Bảng đối chiếu 12 cấu hình — hạng mục HỢP ĐỒNG của đề cương (Nội dung 4 +
    bảng Kế hoạch Giai đoạn 3: "BM25 thuần túy vs. Vector Retrieval vs. Hybrid
    Search", nhân với ablation bật/tắt re-ranking và cổng lọc liên quan).

    Dùng:
        powershell -ExecutionPolicy Bypass -File scripts\run_ablation.ps1
        powershell -ExecutionPolicy Bypass -File scripts\run_ablation.ps1 -TestsetDir "src\test\testsets"

    Chạy được KHÔNG CẦN TRÔNG, và KHÔNG gọi LLM lần nào — nên nó không bị chặn
    bởi hạn mức OpenRouter (hạn mức/ngày vẫn chưa đo được, D-67).

    Bốn bước, và vì sao theo đúng thứ tự này:

      1. `--build-bm25`  — chỉ mục thưa phải MỚI hơn hoặc bằng index dày. Nếu cũ
         hơn, mọi bước sau sẽ raise `SparseIndexStale` (cố ý: một chỉ mục thưa cũ
         trả về `chunk_id` không còn tồn tại, và cách hỏng đó IM LẶNG).
      2. `bm25_sweep`    — quét k1 x b + so tách từ + đo lệch IDF do overlap. Vài
         phút, không cần model nào.
      3. `formula_probe` — chuẩn hoá công thức đáng bao nhiêu, đo trực tiếp trên
         12 công thức có thật trong kho. Không cần bộ test, không cần người gán
         nhãn.
      4. `ablation --build-cache` — bước ĐẮT (~30-35 s/câu: bge-m3 + cross-encoder
         trên CPU, đo được trên máy này), rồi phát lại 12 cấu hình từ bộ nhớ đệm.
         Đệm ghi từng đợt 10 câu nên sập giữa chừng không mất trắng.

    Bước 4 chỉ dựng lại đệm khi cần: đệm mang dấu vân index + tham số kênh thưa,
    lệch thì nó RAISE chứ không âm thầm dùng lại (CẤM #6).
#>

param(
    [string]$TestsetDir = "",
    [switch]$RebuildCache
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
# Script này chạy bằng `powershell` (Windows PowerShell 5.1) theo đúng quy ước
# của `run_etl_local.ps1`. Ở đó console mặc định là code page 437/1258, nên chữ
# tiếng Việt do python in ra sẽ thành ký tự rác nếu không ép UTF-8.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

# Bộ test: mặc định lấy `src\test\testsets` nếu ở đó có *_testset.csv, không thì
# rơi về bộ 4 quyển KNTT đã lưu trữ. Bộ lưu trữ VẪN DÙNG ĐƯỢC — đo được 99/100
# gold key khớp index 12 quyển ở offset 0 và R@10 = 0,98 (D-76) — nhưng nó chỉ
# phủ 4/12 quyển và thiếu nhãn phan_mon/khoi/bo_sach/do_kho, nên MỌI bảng số
# sinh từ nó phải nói rõ là "bộ test tạm, 4/12 quyển".
if (-not $TestsetDir) {
    $primary = "src\test\testsets"
    $fallback = "src\test\testsets\_archive_4books_kntt_offset_minus1"
    if (Get-ChildItem -Path $primary -Filter "*_testset.csv" -ErrorAction SilentlyContinue) {
        $TestsetDir = $primary
    } else {
        $TestsetDir = $fallback
    }
}
$isFallback = $TestsetDir -like "*_archive_*"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $root "ablation_run_$stamp.log"

function Say($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Step($title, $cmdArgs) {
    # HAI BẪY, cả hai chỉ lộ ra khi CHẠY THẬT script này (test đơn vị không thấy):
    #
    # 1. `Tee-Object -FilePath` **truyền tiếp** ra luồng output. Nếu để nguyên,
    #    mọi dòng python in ra trở thành GIÁ TRỊ TRẢ VỀ của hàm, nên
    #    `$code = Step ...` nhận một MẢNG chứ không phải số — và `$code -ne 0`
    #    luôn đúng. Lần chạy đầu: bảng 12 cấu hình in ra đẹp, `mã thoát 0`, mà
    #    script vẫn tuyên bố "Bước 4 thất bại" rồi đi dựng lại bộ nhớ đệm 51
    #    phút một cách vô ích. `Out-Host` chặn dòng chảy đó lại.
    # 2. `Add-Content -Encoding utf8` và `Tee-Object` mặc định ghi hai kiểu mã
    #    hoá khác nhau vào CÙNG một file -> log mở ra là ký tự rác. Ép cùng utf8.
    Say "=== $title ==="
    Say "    python $($cmdArgs -join ' ')"
    # `ForEach-Object` vừa in ra ngay (không chờ lệnh xong — quan trọng với lượt
    # dựng đệm 51 phút) vừa ghi log đúng mã hoá, mà KHÔNG phát gì ra luồng
    # output, nên `return $code` trả về đúng một con số.
    & python @cmdArgs 2>&1 | ForEach-Object {
        $line = [string]$_
        Write-Host $line
        Add-Content -Path $log -Value $line -Encoding utf8
    }
    $code = $LASTEXITCODE
    Say "    -> mã thoát $code"
    return $code
}

Say "Bảng ablation 12 cấu hình — log: $log"
Say "Bộ test: $TestsetDir"
if ($isFallback) {
    Say "CẢNH BÁO: đang dùng BỘ TEST TẠM (4/12 quyển KNTT, LLM sinh, CHƯA có"
    Say "          người duyệt). Mọi số sinh ra phải được báo cáo kèm câu đó."
}

# 1 -----------------------------------------------------------------------
$null = Step "1/4 Dựng lại chỉ mục thưa" @("main.py", "--build-bm25")

# 2 -----------------------------------------------------------------------
$null = Step "2/4 Quét k1 x b, tách từ, lệch IDF" @("src/test/bm25_sweep.py", "--testset-dir", $TestsetDir)

# 3 -----------------------------------------------------------------------
$null = Step "3/4 Chuẩn hoá công thức đáng bao nhiêu" @("src/test/formula_probe.py")

# 4 -----------------------------------------------------------------------
$ablArgs = @("src/test/ablation.py", "--testset-dir", $TestsetDir)
if ($RebuildCache) { $ablArgs += "--build-cache" }
$code = Step "4/4 Bảng 12 cấu hình" $ablArgs

if ($code -ne 0 -and -not $RebuildCache) {
    # Đệm thiếu / lệch cấu hình là trạng thái BÌNH THƯỜNG sau khi đổi k1/b hay
    # tokenizer. Dựng lại một lần, và NÓI RA là đã dựng lại — không im lặng.
    Say "Bước 4 thất bại và chưa thử dựng lại đệm -> dựng đệm rồi chạy lại."
    Say "(đắt: ~30-35 s/câu trên CPU; đệm ghi từng đợt 10 câu)"
    $code = Step "4/4 Bảng 12 cấu hình (dựng lại đệm)" ($ablArgs + "--build-cache")
}

# --- KHÔNG được nói "XONG" khi bước 4 thất bại -----------------------------
# Bẫy đã cắn thật (lượt 2026-08-24 15:05): bước 4 chết ở `20/300` với mã -1,
# nhưng script vẫn in "XONG. Bảng: src\test\ablation_report.csv" — và người đọc
# mở ra thấy một bảng ĐẦY ĐỦ 24 dòng nên tưởng là kết quả của lượt vừa chạy.
# Thật ra đó là file của lượt TRƯỚC (mtime 14:11 so với lượt chạy 15:05), đo trên
# **100 câu** của bộ test lưu trữ 4 quyển chứ không phải 300 câu của bộ 12 quyển.
# Một con số SAI MÀ TRÔNG HỢP LÝ, đúng loại nguy hiểm nhất.
$table = "src\test\ablation_report.csv"
if ($code -eq 0) {
    Say "XONG. Bảng: $table · log đầy đủ: $log"
} else {
    Say "!! BƯỚC 4 THẤT BẠI (mã $code) — BẢNG CHƯA ĐƯỢC DỰNG LẠI."
    if (Test-Path $table) {
        $info = Get-Item $table
        Say "   File `"$table`" trên đĩa là của LƯỢT TRƯỚC"
        Say "   (sửa lần cuối $($info.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')))."
        Say "   ĐỪNG đọc nó như kết quả của lượt này. Đối chiếu cột `so_cau` với số"
        Say "   câu thật trong $TestsetDir trước khi dùng bất kỳ con số nào."
    }
    Say "   log đầy đủ: $log"
}
if ($isFallback) {
    Say "NHẮC LẠI: số ở trên là của BỘ TEST TẠM 4/12 quyển KNTT, chưa có người duyệt."
}
exit $code
