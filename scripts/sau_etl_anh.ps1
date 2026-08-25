# Chạy sau khi ETL ảnh kết thúc: đo độ phủ -> G4 rút gọn -> chuẩn bị phiếu 48 hình.
#
# Gộp ba bước vào một lệnh vì chúng luôn đi cùng nhau và thứ tự có ý nghĩa:
# đo phủ trước (rẻ, đọc index sẵn có, phát hiện quyển tụt hạng trên TOÀN bộ),
# rồi G4 (đắt hơn, chạy detector thật, soi sâu vài Bài), rồi mới lập phiếu.
#
# KHÔNG dừng giữa chừng khi một bước thoát khác 0: `qa_figure_coverage` thoát 1
# khi có quyển dưới ngưỡng, mà đó là THÔNG TIN cần thấy chứ không phải lỗi làm
# hỏng các bước sau. Mã thoát của từng bước được IN RA để đọc, không bị nuốt.

$ErrorActionPreference = "Continue"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = "logs\sau_etl_anh_$stamp.log"
New-Item -ItemType Directory -Force logs | Out-Null

function Buoc($ten, $lenh) {
    $dong = "=" * 70
    Write-Host "`n$dong`n== $ten`n$dong"
    Add-Content $log "`n$dong`n== $ten`n$dong"
    & cmd /c "$lenh 2>&1" | Tee-Object -FilePath $log -Append
    $ma = $LASTEXITCODE
    Write-Host "[$ten] mã thoát = $ma"
    Add-Content $log "[$ten] mã thoát = $ma"
}

Buoc "1/4 Độ phủ nhãn hình, 12 quyển" `
     "python -m src.test.qa_figure_coverage --json database\qa_figure_coverage.json"

Buoc "2/4 G4 rút gọn — CD" `
     "python -m src.test.qa_figures --book SGK_KHTN_6_CD --trang-mau 12"

Buoc "3/4 G4 rút gọn — CTST" `
     "python -m src.test.qa_figures --book SGK_KHTN_6_CTST --trang-mau 12"

Buoc "4/4 Chọn 48 crop cho bộ câu hỏi hình" `
     "python -m src.test.build_image_questions --chon"

Write-Host "`nLog: $log"
Write-Host "Bước tiếp (cần .env có EVAL_LLM_*):"
Write-Host "  python -m src.test.build_image_questions --nhap"
Write-Host "  python -m src.test.build_image_questions --phieu"
Write-Host "  rồi mở document\review\image_questions\phieu.html"
