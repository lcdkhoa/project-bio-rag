#!/usr/bin/env bash
# ETL ảnh cho ĐÚNG 4 quyển KNTT (M2C.1). Không chạy 12 quyển: kênh pill đọc 0
# nhãn trên 8 quyển CD/CTST (D-65) nên 4 giờ CPU kia cho kết quả biết trước là
# sai. Chia bốn lượt: mất điện giữa chừng chỉ mất một quyển, checkpoint theo
# trang cho chạy tiếp.
set -u
LOG="logs/image_etl_kntt_$(date +%Y%m%d_%H%M%S).log"
echo "log -> $LOG"
for BOOK in SGK_KHTN_6_KNTT SGK_KHTN_7_KNTT SGK_KHTN_8_KNTT SGK_KHTN_9_KNTT; do
  echo "===== $BOOK  $(date +%H:%M:%S) =====" >> "$LOG"
  python main.py --image-only --book "$BOOK" >> "$LOG" 2>&1
  echo "----- $BOOK exit=$?  $(date +%H:%M:%S) -----" >> "$LOG"
done
echo "XONG $(date +%H:%M:%S)" >> "$LOG"
