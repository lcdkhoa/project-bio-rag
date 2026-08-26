# Khởi động CẢ HAI phía để thử luồng thật: backend Flask + frontend Next.js.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1
#
# Vì sao cần script thay vì hai lệnh gõ tay: backend mở cổng 5000 TRƯỚC khi nạp
# xong bge-m3 + CLIP + Qwen2.5 (đo được ~25 giây trên CPU của máy này). Mở giao
# diện trong khoảng đó thì câu hỏi đầu tiên lỗi, và lỗi ấy trông y hệt lỗi cấu
# hình. Script chờ đúng thứ cần chờ: `/api/health` chỉ trả 200 sau khi
# `AppServices` dựng xong.
#
# Tham số:
#   -BackendPort   cổng backend (mặc định 5000)
#   -FrontendPort  cổng frontend (mặc định 3000)
#   -FrontendDir   thư mục frontend (mặc định D:\personal_repo\project_rag_fe)
#   -SkipFrontend  chỉ chạy backend

param(
    [int]$BackendPort = 5000,
    [int]$FrontendPort = 3000,
    [string]$FrontendDir = "D:\personal_repo\project_rag_fe",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repo "database\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$beLog = Join-Path $logDir "backend_$stamp.log"
$feLog = Join-Path $logDir "frontend_$stamp.log"

function Test-PortBusy([int]$port) {
    $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# --- 1. Backend --------------------------------------------------------------
if (Test-PortBusy $BackendPort) {
    Write-Host "Cổng $BackendPort đang bận — dùng lại tiến trình sẵn có." -ForegroundColor Yellow
} else {
    Write-Host "Khởi động backend trên cổng $BackendPort ..." -ForegroundColor Cyan
    Write-Host "  log: $beLog"
    Start-Process -FilePath "python" `
        -ArgumentList "main.py", "--api", "--port", "$BackendPort" `
        -WorkingDirectory $repo `
        -RedirectStandardOutput $beLog -RedirectStandardError "$beLog.err" `
        -WindowStyle Hidden | Out-Null
}

# Chờ mô hình nạp xong. 120 giây là dư trên CPU (đo được ~25 s); vượt quá thì
# gần như chắc chắn là lỗi thật, nên dừng và chỉ vào log thay vì chờ mãi.
Write-Host "Chờ backend nạp mô hình (tối đa 120 giây) ..." -ForegroundColor Cyan
$health = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/health" -TimeoutSec 5
        break
    } catch { }
}

if (-not $health) {
    Write-Host "Backend KHÔNG sẵn sàng sau 120 giây. Xem log:" -ForegroundColor Red
    Write-Host "  $beLog"
    Write-Host "  $beLog.err"
    exit 1
}

Write-Host ("Backend sẵn sàng: {0} đoạn văn bản, {1} hình." -f `
        $health.text_chunks, $health.image_docs) -ForegroundColor Green
Write-Host ("  chế độ truy xuất: {0} | kho ảnh: {1}" -f `
        $health.retrieval_mode, $health.images_dir)

if ($SkipFrontend) {
    Write-Host "Bỏ qua frontend theo yêu cầu (-SkipFrontend)." -ForegroundColor Yellow
    Write-Host "Thử nhanh: python scripts\smoke_demo.py"
    exit 0
}

# --- 2. Frontend -------------------------------------------------------------
if (-not (Test-Path $FrontendDir)) {
    Write-Host "Không thấy thư mục frontend: $FrontendDir" -ForegroundColor Red
    exit 1
}

# Frontend đọc địa chỉ backend từ NEXT_PUBLIC_API_HOST. Đặt ở tiến trình con để
# lượt chạy này luôn trỏ đúng backend vừa khởi động, kể cả khi `.env.local` còn
# giữ một địa chỉ Colab cũ đã tắt.
$env:NEXT_PUBLIC_API_HOST = "http://localhost:$BackendPort"

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "Chưa cài phụ thuộc frontend — chạy npm install ..." -ForegroundColor Cyan
    Push-Location $FrontendDir
    npm install --no-audit --no-fund
    Pop-Location
}

if (Test-PortBusy $FrontendPort) {
    Write-Host "Cổng $FrontendPort đang bận — dùng lại tiến trình sẵn có." -ForegroundColor Yellow
} else {
    Write-Host "Khởi động frontend trên cổng $FrontendPort ..." -ForegroundColor Cyan
    Write-Host "  log: $feLog"
    # Phải gọi qua `cmd.exe /c`: trên Windows `npm` là `npm.cmd`, mà
    # `Start-Process -FilePath npm` thì báo "%1 is not a valid Win32 application"
    # vì tệp .cmd không phải chương trình chạy trực tiếp được.
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run dev -- --port $FrontendPort" `
        -WorkingDirectory $FrontendDir `
        -RedirectStandardOutput $feLog -RedirectStandardError "$feLog.err" `
        -WindowStyle Hidden | Out-Null
}

Write-Host "Chờ frontend biên dịch (tối đa 90 giây) ..." -ForegroundColor Cyan
$feUp = $false
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    try {
        Invoke-WebRequest -Uri "http://localhost:$FrontendPort" -TimeoutSec 5 -UseBasicParsing | Out-Null
        $feUp = $true
        break
    } catch { }
}

if (-not $feUp) {
    Write-Host "Frontend KHÔNG lên. Xem log: $feLog" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host " Backend : http://localhost:$BackendPort" -ForegroundColor Green
Write-Host " Frontend: http://localhost:$FrontendPort" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Thử nhanh không cần trình duyệt:  python scripts\smoke_demo.py"
Write-Host "Dừng:  Get-NetTCPConnection -LocalPort $BackendPort,$FrontendPort -State Listen |"
Write-Host "         ForEach-Object { Stop-Process -Id `$_.OwningProcess -Force }"
