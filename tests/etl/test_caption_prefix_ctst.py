"""Chú thích hình của CTST mở đầu bằng ▲, và OCR đọc ký tự đó thành chữ.

## Phép đo dẫn tới test này

`FIG_CAPTION_STRICT_REGEX` neo `^\\s*Hình`, tức chú thích phải nằm ở ĐẦU dòng.
Đúng với Cánh Diều và Kết nối tri thức, sai với Chân trời sáng tạo: bộ này in một
tam giác ▲ trước mọi chú thích hình (`▲ Hình 2.1. Kích thước của một số vật thể`),
và Tesseract đọc ▲ thành `À` / `A` / `AÀ` / `Á`.

Đếm trên chữ đã lập chỉ mục, theo từng nhà xuất bản, các dòng có chứa `Hình N.M`:

    CTST   À 571 · A 139 · AÀ 124 · Á 39  = 873/1796 = 49%   (đầu dòng: 64)
    CD     đầu dòng 752/947 = 79%                            (không có ▲)
    KNTT   đầu dòng 362 · `[` 70 · `(` 55                    (không có ▲)

Con số 49% khớp đúng tỉ lệ hình bị bỏ sót đo được độc lập ở phía kho ảnh: CTST chỉ
cắt được 51--65% số nhãn `Hình N.M` mà chữ trên trang có nhắc, trong khi CD đạt
92--97% và KNTT 95--96%.

## Ranh giới mà test này canh

Nới regex để bắt được chú thích CTST thì dễ; nới quá tay thì **tham chiếu trong
thân bài** ("Quan sát Hình 2.1 ta thấy...") cũng bị nhận là chú thích, và mỗi lần
như vậy sinh ra một khung cắt sai chỗ. Nên nửa dưới của test này quan trọng ngang
nửa trên: các dòng thân bài phải TIẾP TỤC bị loại.
"""
import pytest

from src.etl.image_processor import FIG_CAPTION_STRICT_REGEX as R


@pytest.mark.parametrize("dong", [
    # CTST: ▲ đọc thành các biến thể đo được trên chính corpus
    "À Hình 2.1. Kích thước của một số vật thể",
    "A Hình 2.2. Mô phỏng cấu tạo của một số chất",
    "AÀ Hình 11.9. Sơ đồ mạch điện",
    "Á Hình 5.3. Quá trình quang hợp",
    # KNTT: nhiễu dấu ngoặc đã biết
    "[ Hình 1.2. Một số hoạt động",
    "( Hình 3.4. Kính lúp",
    # dạng chuẩn, không được hồi quy
    "Hình 2.1. Kích thước của một số vật thể",
    "  Hình 12.3 Sơ đồ",
])
def test_nhan_duoc_chu_thich_hinh(dong):
    assert R.match(dong), f"phải nhận là chú thích: {dong!r}"


@pytest.mark.parametrize("dong", [
    # Tham chiếu thân bài — nới regex quá tay là những dòng này lọt vào
    "Quan sát Hình 2.2, em hãy cho biết khí oxygen",
    "trong Hình 2.1 ta có thể quan sát bằng mắt thường",
    "1 Quan sát Hình 3.1 và trả lời câu hỏi",
    "Dựa vào Hình 1.2, hãy so sánh các phương tiện",
    "í nghiệm như Hình 4.5 rồi ghi kết quả",
    "2. Quan sát Hình 7.1 và mô tả",
    " và quan sát Hình 9.2 để trả lời",
    " mô tả trong Hình 6.3 dưới đây",
    # Bảng thì luôn bị loại, kể cả có tiền tố
    "À Bảng 12.1. Tính chất của một số vật liệu",
])
def test_van_loai_tham_chieu_than_bai(dong):
    assert not R.match(dong), f"KHÔNG được nhận là chú thích: {dong!r}"


def test_khong_cho_tien_to_dai_tuy_y():
    """Tiền tố chỉ được là nhiễu ngắn, không phải một từ.

    Nếu cho phép tiền tố dài tuỳ ý thì mọi câu có nhắc `Hình N.M` đều thành chú
    thích, và mỗi cái sinh một khung cắt sai chỗ.
    """
    assert not R.match("Đây là một câu dài có nhắc Hình 2.1 ở giữa")
    assert not R.match("xem Hình 2.1")
