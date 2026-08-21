"""Gộp caption hình của KNTT: một dòng chú thích chỉ được ra MỘT anchor.

Defect đã đo trên `SGK_KHTN_9_KNTT/page_009` (D-45): dòng `Hình 1.9 Bình cầu`
được đọc HAI lần — pill đọc đúng `Hình 1.9`, OCR thường đọc `Hình 19` (mất dấu
chấm). Bản gộp cũ chỉ gộp theo SỐ nên "1.9" và "19" là hai khoá khác nhau, cả
hai cùng sống; rồi vùng hình lại được gán cho bản hỏng, nên hình có crop nhưng
mang nhãn `Hình 19` — không khớp `Hình N.M` và bị đếm là MẤT ở cổng G4.
"""
from src.etl.image_processor import KnttImageProcessor

dedupe = KnttImageProcessor._dedupe_kntt_captions


def cap(text, bbox):
    return {"index": 0, "text": text, "bbox": bbox}


def test_the_well_formed_reading_wins_when_two_readings_overlap():
    caps = dedupe([cap("Hình 19", (107, 717, 282, 755)),      # OCR mất dấu chấm
                   cap("Hình 1.9", (112, 721, 221, 750))])    # pill đọc đúng
    assert [c["text"] for c in caps] == ["Hình 1.9"]


def test_overlap_wins_even_when_the_broken_reading_is_longer():
    """Luật cũ giữ bản DÀI hơn; dài hơn không có nghĩa là đúng hơn."""
    caps = dedupe([cap("Hình 19 Bình cầu thuỷ tinh", (107, 717, 282, 755)),
                   cap("Hình 1.9", (112, 721, 221, 750))])
    assert [c["text"] for c in caps] == ["Hình 1.9"]


def test_two_real_captions_side_by_side_are_both_kept():
    """`Hình 27.3` và `Hình 27.4` cạnh nhau là hai hình thật, không được gộp."""
    caps = dedupe([cap("Hình 27.3", (100, 700, 200, 730)),
                   cap("Hình 27.4", (400, 700, 500, 730))])
    assert sorted(c["text"] for c in caps) == ["Hình 27.3", "Hình 27.4"]


def test_the_longer_caption_still_wins_when_both_are_well_formed():
    caps = dedupe([cap("Hình 1.9", (112, 721, 221, 750)),
                   cap("Hình 1.9 Bình cầu", (110, 720, 300, 752))])
    assert [c["text"] for c in caps] == ["Hình 1.9 Bình cầu"]


def test_captions_are_returned_in_reading_order():
    caps = dedupe([cap("Hình 1.11", (800, 1115, 906, 1142)),
                   cap("Hình 1.7", (122, 333, 225, 362))])
    assert [c["text"] for c in caps] == ["Hình 1.7", "Hình 1.11"]


def pill(text, bbox):
    return {"index": 0, "text": text, "bbox": bbox, "from_pill": True}


def test_a_pill_beats_a_body_reference_carrying_the_same_number():
    """Ô câu hỏi xuống dòng làm `Hình 1.1.` thành một dòng riêng, trông y hệt
    một caption. Nhãn PILL mới là cái nhãn in trên trang (D-46)."""
    caps = dedupe([cap("Hình 1.1.", (826, 933, 914, 951)),      # trích dẫn
                   pill("Hình 1.1", (318, 1081, 414, 1109))])   # nhãn thật
    assert len(caps) == 1
    assert caps[0]["bbox"] == (318, 1081, 414, 1109)


def test_an_overlapping_pill_and_full_caption_merge_to_the_union_bbox():
    """Pill cho SỐ HIỆU đúng, dòng chú thích đầy đủ cho BỀ NGANG thật. Giữ pill
    mà bỏ bề ngang thì caption quá hẹp, không ô ảnh nào giao ngang -> mất hình."""
    caps = dedupe([cap("[ Hình 1.4 ] Đo huyết áp bằng huyết áp kế",
                       (582, 1038, 1015, 1074)),
                   pill("Hình 1.4", (586, 1043, 682, 1070))])
    assert len(caps) == 1
    assert caps[0]["text"] == "Hình 1.4"          # số hiệu từ pill
    assert caps[0]["bbox"] == (582, 1038, 1015, 1074)   # bề ngang từ caption
