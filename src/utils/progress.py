"""Heartbeat progress logging cho các vòng lặp dài của ETL.

Vì sao cần: `run_etl` chỉ log MỖI QUYỂN, còn ba vòng lặp tốn thời gian nhất
(index text từng trang, OCR cả trang để neo caption, crop hình) chạy im lặng
hàng chục phút. Người vận hành không phân biệt được "đang chạy" với "treo" —
đúng tình huống đã xảy ra: 196 trang text ≈ 10 phút không một dòng log.

Nguyên tắc 2/5 của repo: không đoán, và không im lặng. Nên progress ở đây chỉ
báo **số đo thật** (đã xử lý / tổng, tốc độ đo được, ETA suy ra từ tốc độ đó, và
các bộ đếm do caller cộng vào). Không có thanh tiến trình giả, không nội suy.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional


def format_duration(seconds: float) -> str:
    """`372.4` -> `"06:12"`; >= 1 giờ thì `"1:06:12"`. Âm/không xác định -> "?"."""
    if seconds is None or seconds != seconds or seconds < 0:  # NaN-safe
        return "?"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class ProgressLogger:
    """Log tiến trình theo nhịp: mỗi `every_items` mục HOẶC mỗi `every_seconds`.

    Dùng như context manager để dòng tổng kết luôn được in ra, kể cả khi vòng lặp
    thoát vì exception (lúc đó lại là dòng log quan trọng nhất):

        with ProgressLogger(logger, "[book] text", total=196) as p:
            for page in pages:
                ...
                p.advance(chunks=len(docs))

    `advance()` nhận bộ đếm tuỳ ý (`chunks=…`, `fail=1`, `skip=1`) và cộng dồn;
    chúng được in kèm mọi dòng progress. Bộ đếm là số thật của caller — lớp này
    không tự suy ra cái gì ngoài tốc độ và ETA.
    """

    def __init__(
        self,
        logger: logging.Logger,
        label: str,
        total: int,
        every_items: int = 10,
        every_seconds: float = 30.0,
        unit: str = "trang",
    ) -> None:
        self.logger = logger
        self.label = label
        self.total = max(int(total), 0)
        self.every_items = max(int(every_items), 1)
        self.every_seconds = max(float(every_seconds), 1.0)
        self.unit = unit
        self.done_count = 0
        self.counters: Dict[str, int] = {}
        self._start = time.monotonic()
        self._last_log_at = self._start
        self._last_log_count = 0
        self._finished = False

    # -- context manager ---------------------------------------------------
    def __enter__(self) -> "ProgressLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Không nuốt exception: chỉ đảm bảo có dòng tổng kết trước khi nó bay lên.
        self.finish(interrupted=exc_type is not None)
        return False

    # -- API ---------------------------------------------------------------
    def advance(self, n: int = 1, **counters: int) -> None:
        """Đánh dấu đã xong `n` mục, cộng thêm các bộ đếm, log nếu tới nhịp."""
        self.done_count += int(n)
        for key, value in counters.items():
            if value:
                self.counters[key] = self.counters.get(key, 0) + int(value)
        if self.total and self.done_count >= self.total:
            # Mục cuối: để `finish()` nói, khỏi in hai dòng cùng nội dung.
            return
        now = time.monotonic()
        since_items = self.done_count - self._last_log_count
        since_seconds = now - self._last_log_at
        if since_items >= self.every_items or since_seconds >= self.every_seconds:
            self._emit(now)

    def note(self, **counters: int) -> None:
        """Cộng bộ đếm mà KHÔNG tính là một mục đã xong (vd. lỗi giữa trang)."""
        for key, value in counters.items():
            if value:
                self.counters[key] = self.counters.get(key, 0) + int(value)

    def finish(self, interrupted: bool = False) -> None:
        """In dòng tổng kết một lần duy nhất."""
        if self._finished:
            return
        self._finished = True
        elapsed = time.monotonic() - self._start
        state = "DỪNG GIỮA" if interrupted else "xong"
        rate = self._per_item(elapsed)
        self.logger.info(
            f"{self.label}: {state} {self.done_count}/{self.total} {self.unit} "
            f"trong {format_duration(elapsed)}"
            f"{self._rate_text(rate)}{self._counters_text()}"
        )

    # -- nội bộ ------------------------------------------------------------
    def _emit(self, now: float) -> None:
        elapsed = now - self._start
        rate = self._per_item(elapsed)
        percent = (100.0 * self.done_count / self.total) if self.total else 0.0
        remaining = self.total - self.done_count
        eta = (remaining * rate) if (rate and remaining > 0) else 0.0
        self.logger.info(
            f"{self.label}: {self.done_count}/{self.total} {self.unit} "
            f"({percent:.1f}%)"
            f"{self._rate_text(rate)}"
            f" | đã chạy {format_duration(elapsed)}"
            f" | còn ~{format_duration(eta) if rate else '?'}"
            f"{self._counters_text()}"
        )
        self._last_log_at = now
        self._last_log_count = self.done_count

    def _per_item(self, elapsed: float) -> Optional[float]:
        if self.done_count <= 0 or elapsed <= 0:
            return None
        return elapsed / self.done_count

    def _rate_text(self, rate: Optional[float]) -> str:
        if not rate:
            return ""
        return f" | {rate:.2f}s/{self.unit}"

    def _counters_text(self) -> str:
        if not self.counters:
            return ""
        body = " ".join(f"{k}={v}" for k, v in self.counters.items())
        return f" | {body}"
