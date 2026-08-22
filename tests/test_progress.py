"""Test cho ProgressLogger — nhỏ, tổng hợp, không chạm ETL thật."""

import logging

from src.utils.progress import ProgressLogger, format_duration


def _logger(name):
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    return log


def test_format_duration_bao_gio_cung_doc_duoc():
    assert format_duration(0) == "00:00"
    assert format_duration(59.4) == "00:59"
    assert format_duration(372.4) == "06:12"
    assert format_duration(3972) == "1:06:12"
    assert format_duration(None) == "?"
    assert format_duration(-1) == "?"


def test_log_theo_nhip_so_muc(caplog):
    log = _logger("progress.nhip")
    with caplog.at_level(logging.INFO, logger="progress.nhip"):
        with ProgressLogger(log, "[x] text", total=10, every_items=4,
                           every_seconds=10_000) as p:
            for _ in range(10):
                p.advance(chunks=2)
    lines = [r.message for r in caplog.records]
    # 10 muc / nhip 4 -> log o 4 va 8, cong dong tong ket.
    assert len(lines) == 3
    assert "4/10 trang (40.0%)" in lines[0]
    assert "8/10 trang (80.0%)" in lines[1]
    assert "chunks=8" in lines[0] and "chunks=16" in lines[1]
    assert "xong 10/10 trang" in lines[2] and "chunks=20" in lines[2]


def test_bo_dem_zero_khong_lam_ban_log(caplog):
    log = _logger("progress.zero")
    with caplog.at_level(logging.INFO, logger="progress.zero"):
        with ProgressLogger(log, "[x] text", total=2, every_items=99,
                           every_seconds=10_000) as p:
            p.advance(fail=0, chunks=3)
            p.advance(fail=1, chunks=0)
    summary = caplog.records[-1].message
    assert "chunks=3" in summary and "fail=1" in summary


def test_exception_van_co_dong_tong_ket_va_khong_bi_nuot(caplog):
    log = _logger("progress.exc")
    with caplog.at_level(logging.INFO, logger="progress.exc"):
        try:
            with ProgressLogger(log, "[x] text", total=5, every_items=99,
                               every_seconds=10_000) as p:
                p.advance()
                raise KeyboardInterrupt
        except KeyboardInterrupt:
            pass
        else:  # pragma: no cover - phai bay len den day
            raise AssertionError("ProgressLogger da nuot exception")
    summary = caplog.records[-1].message
    assert "DỪNG GIỮA 1/5 trang" in summary


def test_total_zero_khong_chia_cho_khong(caplog):
    log = _logger("progress.empty")
    with caplog.at_level(logging.INFO, logger="progress.empty"):
        with ProgressLogger(log, "[x] text", total=0, every_items=1) as p:
            pass
    assert "xong 0/0 trang" in caplog.records[-1].message


def test_finish_chi_in_mot_lan(caplog):
    log = _logger("progress.once")
    with caplog.at_level(logging.INFO, logger="progress.once"):
        p = ProgressLogger(log, "[x] text", total=1, every_items=99)
        p.advance()
        p.finish()
        p.finish()
    assert sum("xong 1/1" in r.message for r in caplog.records) == 1


def test_iter_books_dem_du_ca_khi_body_continue_hoac_raise(caplog):
    """`_iter_books` phải đếm mọi quyển, kể cả quyển thoát bằng continue/except."""
    import main

    log = _logger("progress.books")
    with caplog.at_level(logging.INFO, logger="progress.books"):
        p = ProgressLogger(log, "books", total=3, every_items=1,
                           every_seconds=10_000, unit="quyển")
        for i, book in enumerate(main._iter_books(["a", "b", "c"], p)):
            if i == 0:
                continue          # quyển đã index xong -> skip
            try:
                if i == 1:
                    raise RuntimeError("lỗi quyển b")
            except RuntimeError:
                pass
        p.finish()
    lines = [r.message for r in caplog.records]
    assert "1/3 quyển" in lines[0]
    assert "2/3 quyển" in lines[1]
    assert "xong 3/3 quyển" in lines[-1]
