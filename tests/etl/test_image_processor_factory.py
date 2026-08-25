"""Factory processor ảnh — BA nhà xuất bản, định tuyến bằng ĐO chứ không bằng đoán.

Lịch sử của file này là một vòng tròn đáng ghi lại. Bản đầu định tuyến theo từ
khoá trong tên file (`CtsstImageProcessor` / `KnttImageProcessor` / lớp cơ sở).
D-50 xoá nó vì corpus chỉ còn KNTT, thay bằng hằng số `LAYOUT_VARIANT = "kntt"`.
`goal.docx` (RULE #0) mở lại phạm vi thành 3 NXB, và D-109 đo được cái giá của
hằng số đó: **11 459/16 393 chunk (69,9%) của CD/CTST mang `variant='kntt'`, 0
chunk mang nhãn đúng** — đúng cái fallback im lặng mà hằng số định ngăn.

Nên bây giờ: đọc NXB từ hậu tố tên quyển, và **ném** khi không khớp cả ba. Khác
bản đầu ở đúng một chỗ, và đó là chỗ quyết định: không có nhánh nào lặng lẽ rơi
về lớp cơ sở. Lớp cho từng NXB được chọn bằng số đo D-110, không bằng trực giác.
"""
import pytest

import src.etl.image_processor as IP


@pytest.fixture
def light_processor(monkeypatch):
    # giữ việc khởi tạo nhẹ: chặn các collaborator nặng trong __init__
    monkeypatch.setattr(IP, "ImageCaptioner", lambda *a, **k: object())
    monkeypatch.setattr(IP, "ProcessingStatus", lambda *a, **k: object())


@pytest.mark.parametrize("name,variant", [
    ("SGK_KHTN_6_KNTT", "kntt"),
    ("SGK_KHTN_9_KNTT", "kntt"),
    ("SGK KHTN 8 KNTT.pdf", "kntt"),
    ("SGK_KHTN_6_CTST", "ctst"),
    ("SGK KHTN 7 CTST.pdf", "ctst"),
    ("SGK_KHTN_8_CD", "cd"),
    ("SGK KHTN 9 CD.pdf", "cd"),
    ("sgk_khtn_6_cd", "cd"),          # thường/hoa không được đổi kết quả
])
def test_variant_read_from_the_book_name(name, variant):
    assert IP.get_pdf_variant(name) == variant


@pytest.mark.parametrize("name,cls_attr", [
    # KNTT: lớp đã QA trên corpus này (D-45, D-46, D-87).
    ("SGK_KHTN_6_KNTT", "KnttImageProcessor"),
    # CD: lớp CƠ SỞ chính là bản Cánh Diều (docstring của lớp).
    ("SGK_KHTN_8_CD", "ImageProcessor"),
    # CTST: lớp cơ sở THẮNG lớp KNTT bằng số đo — 11 vs 10 nhãn, 7,70 vs
    # 8,95 s/trang trên 15 trang của 7_CTST (D-110). Không khôi phục
    # `CtsstImageProcessor` đã xoá: nó viết cho render 150 DPI, chưa từng QA.
    ("SGK_KHTN_7_CTST", "ImageProcessor"),
])
def test_factory_routes_to_the_measured_class(light_processor, name, cls_attr):
    assert type(IP.make_image_processor(name)) is getattr(IP, cls_attr)


@pytest.mark.parametrize("name", [
    "",                          # đường upload PDF cũ có thể không có tên
    "mot quyen la.pdf",
    "SGK_KHTN_6_XYZ",
    "SGK_KHTN_6",                # thiếu hẳn hậu tố NXB
    "CD_SGK_KHTN_6",             # hậu tố phải ở CUỐI, không phải ở đâu cũng được
])
def test_unknown_publisher_raises_instead_of_guessing(light_processor, name):
    """Nguyên tắc 5: hỏng ồn ào còn hơn hỏng im lặng.

    Bản cũ trả 'kntt' cho MỌI tên, nên một quyển CTST được xử lý bằng logic
    KNTT mà không ai biết — D-109 đo được 11 459 chunk dính. Ném ở đây thì lỗi
    lộ ra ngay lệnh đầu tiên, không lộ ra sau 16 393 chunk.
    """
    with pytest.raises(IP.UnknownPublisher):
        IP.get_pdf_variant(name)
    with pytest.raises(IP.UnknownPublisher):
        IP.make_image_processor(name)


def test_error_message_names_the_three_accepted_suffixes():
    """Thông báo lỗi phải nói được cách sửa, không chỉ nói là sai."""
    with pytest.raises(IP.UnknownPublisher) as e:
        IP.get_pdf_variant("quyen la.pdf")
    msg = str(e.value)
    assert "quyen la.pdf" in msg
    for suffix in ("KNTT", "CTST", "CD"):
        assert suffix in msg


def test_ctst_processor_is_still_gone():
    """`CtsstImageProcessor` KHÔNG được khôi phục cùng lúc mở lại 3 NXB.

    Nó viết cho bản render PDF 150 DPI và chưa từng QA trên nguồn pixel; D-110
    đo được lớp cơ sở làm tốt hơn lớp KNTT trên CTST, nên không có lý do gì để
    lôi code cũ về.
    """
    assert not hasattr(IP, "CtsstImageProcessor")
    import src.etl as etl
    assert "CtsstImageProcessor" not in etl.__all__


def test_layout_variant_constant_is_gone():
    """Hằng số cũ phải BIẾN MẤT, không phải chỉ ngừng được dùng.

    Để lại nó là để lại một đường quay về fallback im lặng cho lượt sau.
    """
    assert not hasattr(IP, "LAYOUT_VARIANT")


@pytest.mark.parametrize("name", [
    "SGK KHTN 6 CD.PDF",         # phần mở rộng VIẾT HOA
    "SGK_KHTN_7_Ctst.Pdf",       # trộn hoa thường ở cả hai chỗ
])
def test_uppercase_extension_is_not_rejected(name):
    """Ném OAN một quyển hợp lệ là sai HƯỚNG.

    Ném để chặn ĐOÁN BỪA thì đúng; ném vì phần mở rộng viết hoa thì chỉ chặn
    việc chạy được. Bắt được khi đọc lại chính regex vừa viết, không phải khi
    chạy test — `citations.py` đã có `IGNORECASE` ở đúng chỗ này từ trước.
    """
    assert IP.get_pdf_variant(name) in ("cd", "ctst")
