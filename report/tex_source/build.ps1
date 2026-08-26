# Script build bao cao LaTeX (pdflatex + biber + pdflatex x2 hoac latexmk)
param (
    [switch]$Clean,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
$WorkingDir = $PSScriptRoot
Set-Location $WorkingDir

# Tu dong nap lai PATH tu Registry va cac thu muc MiKTeX pho bien neu chua co trong session hien tai
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$env:Path = "$userPath;$machinePath;$env:Path"

$miktexPaths = @(
    "$env:LOCALAPPDATA\Programs\MiKTeX\miktex\bin\x64",
    "C:\Program Files\MiKTeX\miktex\bin\x64",
    "C:\Program Files (x86)\MiKTeX\miktex\bin"
)
foreach ($p in $miktexPaths) {
    if ((Test-Path $p) -and ($env:Path -notlike "*$p*")) {
        $env:Path = "$p;$env:Path"
    }
}

$OutputDir = "build"
$MainTex = "src/main.tex"
$MainBase = "main"

if ($Clean) {
    Write-Host "[*] Dang don dep thu muc $OutputDir..." -ForegroundColor Yellow
    if (Test-Path $OutputDir) {
        Remove-Item -Recurse -Force $OutputDir
    }
    Write-Host "[+] Don dep hoan tat." -ForegroundColor Green
    if (-not (Test-Path $MainTex)) { return }
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  BIEN DICH BAO CAO LATEX (MiKTeX / TeX Live)" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# Kiem tra cong cu build
$hasPdflatex = [bool](Get-Command pdflatex -ErrorAction SilentlyContinue)

# CHU Y: chi co file latexmk.exe la CHUA DU. Ban latexmk cua MiKTeX la script Perl,
# neu may khong cai Perl thi no thoat voi loi "could not find the script engine 'perl'".
# Vi vay phai THU CHAY that su, khong duoc chi kiem tra su ton tai.
$hasLatexmk = $false
if (Get-Command latexmk -ErrorAction SilentlyContinue) {
    & latexmk -v *> $null
    $hasLatexmk = ($LASTEXITCODE -eq 0)
    if (-not $hasLatexmk) {
        Write-Host "[!] Tim thay 'latexmk' nhung KHONG chay duoc (thuong do thieu Perl)." -ForegroundColor Yellow
        Write-Host "    Chuyen sang duong pdflatex + biber. Muon dung latexmk thi cai Strawberry Perl." -ForegroundColor Yellow
    }
}

if ($hasLatexmk) {
    Write-Host "[1/1] Su dung latexmk de build tu dong (kem biber)..." -ForegroundColor Green
    # CHU Y: doi so bat dau bang '-' PHAI dat trong nhay kep, neu khong PowerShell
    # KHONG noi suy bien -> tao ra thu muc ten dung nghia den la '$OutputDir'.
    latexmk -pdf -enable-installer -interaction=nonstopmode -synctex=1 "-outdir=$OutputDir" $MainTex
} elseif ($hasPdflatex) {
    Write-Host "[1/4] Chay pdflatex lan 1..." -ForegroundColor Green
    pdflatex -enable-installer -interaction=nonstopmode "-output-directory=$OutputDir" $MainTex

    if (Get-Command biber -ErrorAction SilentlyContinue) {
        Write-Host "[2/4] Chay biber xu ly tai lieu tham khao..." -ForegroundColor Green
        # --output-directory: bat buoc, neu khong main.bbl roi ra cwd chu khong vao build/
        biber "--output-directory=$OutputDir" "$OutputDir/$MainBase"
    } else {
        Write-Host "[!] Khong tim thay 'biber'. Danh muc tham khao co the chua duoc cap nhat." -ForegroundColor Yellow
    }

    Write-Host "[3/4] Chay pdflatex lan 2 de cap nhat danh muc..." -ForegroundColor Green
    pdflatex -enable-installer -interaction=nonstopmode "-output-directory=$OutputDir" $MainTex

    Write-Host "[4/4] Chay pdflatex lan 3 de chot so trang va cross-ref..." -ForegroundColor Green
    pdflatex -enable-installer -interaction=nonstopmode "-output-directory=$OutputDir" $MainTex
} else {
    Write-Host "[X] Khong tim thay 'latexmk' hoac 'pdflatex' trong PATH!" -ForegroundColor Red
    Write-Host "    Vui long khoi dong lai Terminal / VS Code de he thong cap nhat PATH tu MiKTeX." -ForegroundColor Yellow
    exit 1
}

$PdfPath = Join-Path $OutputDir "$MainBase.pdf"
if (Test-Path $PdfPath) {
    Write-Host "`n[+] BUILD THANH CONG: $PdfPath" -ForegroundColor Green
    if ($Open) {
        Start-Process $PdfPath
    }
} else {
    Write-Host "`n[X] Khong tim thay file PDF sau khi build." -ForegroundColor Red
    exit 1
}
