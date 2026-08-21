"""Factory processor ảnh — MỘT nhà xuất bản, nên không còn định tuyến theo tên file.

Test cũ khẳng định `make_image_processor` chọn `CtsstImageProcessor` /
`KnttImageProcessor` / `ImageProcessor` theo từ khoá trong tên file. Corpus nay
chỉ còn Kết Nối Tri Thức (CD và CTST bị thu hồi), `CtsstImageProcessor` đã bị
xoá, và nhánh "cd" chỉ là lớp cơ sở — nên phép suy ra từ tên file đã bị bỏ.

Test này khoá lại điều quan trọng: mọi quyển đều đi qua `KnttImageProcessor` —
lớp DUY NHẤT được QA trên corpus này (D-45, D-46) — và không có tên file nào lặng
lẽ rơi về lớp cơ sở chưa được kiểm chứng.
"""
import pytest

import src.etl.image_processor as IP


@pytest.fixture
def light_processor(monkeypatch):
    # giữ việc khởi tạo nhẹ: chặn các collaborator nặng trong __init__
    monkeypatch.setattr(IP, "ImageCaptioner", lambda *a, **k: object())
    monkeypatch.setattr(IP, "ProcessingStatus", lambda *a, **k: object())


@pytest.mark.parametrize("name", [
    "SGK_KHTN_6_KNTT",
    "SGK_KHTN_9_KNTT",
    "SGK KHTN 8 KNTT.pdf",
    "",                      # đường upload PDF cũ có thể không có tên
    "mot quyen la.pdf",
])
def test_factory_always_returns_the_qa_d_processor(light_processor, name):
    assert type(IP.make_image_processor(name)) is IP.KnttImageProcessor


def test_variant_is_a_constant_not_inferred_from_the_filename():
    """Suy ra biến thể từ tên file là một fallback im lặng — đã bỏ.

    Đưa một quyển CTST vào thì hệ thống sẽ gán 'kntt' và xử lý bằng logic KNTT
    mà không ai biết. Thêm nhà xuất bản thứ hai là việc phải ĐO lại, không phải
    thêm một từ khoá vào regex.
    """
    assert IP.LAYOUT_VARIANT == "kntt"
    for name in ["SGK_KHTN_6_KNTT", "SGK KHTN 6 CTST.pdf", "SGK KHTN 6 CD.pdf", ""]:
        assert IP.get_pdf_variant(name) == "kntt"


def test_ctst_processor_is_gone():
    assert not hasattr(IP, "CtsstImageProcessor")
    import src.etl as etl
    assert "CtsstImageProcessor" not in etl.__all__
