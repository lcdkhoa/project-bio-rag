"""Chạy bộ kiểm JS của phiếu duyệt qua pytest, để nó không bị quên.

Logic chặn nằm trong JavaScript của trang HTML — pytest không với tới được, và
đó chính là chỗ vừa hỏng: lượt duyệt đầu xuất ra một phiếu trông đủ 48 ô trong
2,3 phút với 40 ô giữ nguyên 100% nháp LLM.

`tests/js/kiem_phieu_js.mjs` dựng một DOM giả tối thiểu và kiểm đúng một điều
quyết định: **điền đủ chữ mà chưa bấm "Tôi đã xem ảnh" thì nút Tải vẫn bị chặn**.

Bỏ qua khi máy không có Node hoặc chưa dựng phiếu — không phải máy nào cũng cần.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "js" / "kiem_phieu_js.mjs"
PHIEU = ROOT / "document" / "review" / "image_questions" / "phieu.html"


@pytest.mark.skipif(shutil.which("node") is None, reason="máy không có Node")
@pytest.mark.skipif(not PHIEU.exists(), reason="chưa dựng phiếu (--phieu)")
def test_phieu_chan_xuat_khi_chua_xem_anh():
    r = subprocess.run(["node", str(SCRIPT)], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="replace")
    print(r.stdout)
    assert r.returncode == 0, f"bộ kiểm JS thất bại:\n{r.stdout}\n{r.stderr}"
    assert "kiểm tra đạt" in r.stdout
    # Dòng quyết định — chính kịch bản đã xảy ra ở lượt duyệt đầu.
    assert "OK   điền đủ chữ mà chưa xem ảnh -> VẪN CHẶN" in r.stdout
