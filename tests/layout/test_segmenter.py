import numpy as np, cv2
from src.etl.layout.segmenter import segment_page, _params_for, _is_box_pixels
from src.etl.layout.regions import RegionType

def _synthetic_page():
    img = np.full((1000, 800, 3), 255, np.uint8)
    # main text: black lines on left 60% of width
    for y in range(120, 700, 40):
        cv2.putText(img, "dòng văn bản chính của bài học", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    # colored sidebar box on right (green fill) with text
    cv2.rectangle(img, (560, 120), (770, 480), (120, 200, 120), -1)
    cv2.putText(img, "cau hoi 5", (580, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    return img

def _synthetic_page_no_box():
    img = np.full((1000, 800, 3), 255, np.uint8)
    for y in range(120, 700, 40):
        cv2.putText(img, "dòng văn bản chính của bài học", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    return img

def _synthetic_page_two_boxes():
    img = np.full((1000, 800, 3), 255, np.uint8)
    for y in range(120, 700, 40):
        cv2.putText(img, "dòng văn bản chính của bài học", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    # upper box on the right
    cv2.rectangle(img, (560, 120), (770, 300), (120, 200, 120), -1)
    cv2.putText(img, "cau hoi 5", (580, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    # lower box on the right, lower on the page
    cv2.rectangle(img, (560, 600), (770, 820), (200, 120, 120), -1)
    cv2.putText(img, "ghi nho", (580, 700), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    return img

def test_detects_one_colored_box_and_main_text():
    regs = segment_page(_synthetic_page(), "ctst")
    types = [r.type for r in regs]
    assert RegionType.SIDEBAR in types or RegionType.INFO_BOX in types
    assert RegionType.BODY in types
    # main body reads before the sidebar box
    body = next(r for r in regs if r.type == RegionType.BODY)
    box = next(r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX))
    assert body.reading_order < box.reading_order

def test_box_bbox_is_on_the_right():
    regs = segment_page(_synthetic_page(), "ctst")
    box = next(r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX))
    assert box.bbox[0] > 400   # x0 on right half


def test_no_box_page_returns_only_body_with_no_excludes():
    regs = segment_page(_synthetic_page_no_box(), "ctst")
    assert len(regs) == 1
    assert regs[0].type == RegionType.BODY
    assert regs[0].meta["excludes"] == []


def test_two_boxes_reading_order_top_to_bottom():
    regs = segment_page(_synthetic_page_two_boxes(), "ctst")
    boxes = [r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX)]
    assert len(boxes) == 2
    upper = next(r for r in boxes if r.bbox[1] < 400)
    lower = next(r for r in boxes if r.bbox[1] >= 400)
    assert upper.reading_order < lower.reading_order


def test_params_for_known_and_unknown_variant():
    kntt_params = _params_for("kntt")
    assert set(("min_sat", "min_area_frac")) <= set(kntt_params.keys())
    unknown_params = _params_for("unknown")
    assert set(unknown_params.keys()) == set(kntt_params.keys())


# --- F-A: pale-tint boxes must be caught; figures/photos on white must not ---

def test_is_box_accepts_tint_rejects_figure_on_white():
    p = _params_for("ctst")
    everything = np.ones((200, 200), bool)
    # a pale-green tinted, uniform background => a real box
    tint = np.full((200, 200, 3), (225, 243, 231), np.uint8)
    assert _is_box_pixels(tint, everything, p) is True
    # white background with sparse dark outlines => a figure on white, NOT a box
    fig = np.full((200, 200, 3), 255, np.uint8)
    for cx in (40, 100, 160):
        cv2.circle(fig, (cx, 100), 22, (150, 90, 40), 2)
    assert _is_box_pixels(fig, everything, p) is False


def test_is_box_pixels_judges_only_the_regions_own_pixels():
    """Đo trên bbox thay vì trên chính vùng là lý do sidebar tím ở page_010 bị
    trượt (độ phẳng 0,42 < 0,45): bbox của nó bao cả khe trắng và đuôi bong bóng
    thoại. Cùng một hộp, khi chỉ tính pixel của nó, phải đạt."""
    p = _params_for("kntt")
    image = np.full((200, 200, 3), 255, np.uint8)
    image[0:100, 0:100] = (225, 243, 231)      # nửa trên-trái là hộp
    box_pixels = np.zeros((200, 200), bool)
    box_pixels[0:100, 0:100] = True
    assert _is_box_pixels(image, box_pixels, p) is True
    # cùng ảnh, nhưng tính cả nền trắng -> trung vị thành trắng -> loại
    assert _is_box_pixels(image, np.ones((200, 200), bool), p) is False


def _synthetic_page_pale_box():
    img = np.full((1000, 800, 3), 255, np.uint8)
    for y in range(120, 700, 40):
        cv2.putText(img, "noi dung chinh cua bai", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    # PALE-green sidebar (sat ~19, below the strong-saturation floor of 45) that
    # the old saturation-only detector missed -> the pale channel must catch it.
    cv2.rectangle(img, (560, 100), (770, 460), (225, 243, 231), -1)
    cv2.putText(img, "cau hoi", (575, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    return img


def test_pale_tint_sidebar_is_detected():
    regs = segment_page(_synthetic_page_pale_box(), "ctst")
    boxes = [r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX)]
    assert any(b.bbox[0] > 400 for b in boxes), "pale-tint sidebar must be detected"


def _synthetic_page_nested_boxes():
    """Hộp con nằm trong panel lớn, khác tông màu — như panel so sánh của KNTT."""
    img = np.full((1000, 800, 3), 255, np.uint8)
    cv2.rectangle(img, (60, 100), (740, 600), (200, 225, 245), -1)   # panel đào
    cv2.rectangle(img, (100, 160), (400, 400), (150, 235, 250), -1)  # ô vàng
    cv2.rectangle(img, (420, 160), (700, 400), (150, 240, 180), -1)  # ô xanh
    return img


def test_nested_boxes_collapse_to_the_outermost_box():
    # Không sinh hai chunk cho cùng một đoạn chữ: giữ hộp ngoài cùng, chữ của hộp
    # con vẫn được OCR vì nó nằm trong vùng đó.
    regs = segment_page(_synthetic_page_nested_boxes(), "kntt")
    boxes = [r for r in regs if r.type in (RegionType.SIDEBAR, RegionType.INFO_BOX)]
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0].bbox
    assert x0 <= 61 and y0 <= 101 and x1 >= 739 and y1 >= 599


def test_a_page_sized_tint_is_not_a_box():
    # Nền trang có tông nhạt không phải "hộp": nếu nhận, cả trang bị coi là một
    # info_box và thân bài rỗng.
    img = np.full((1000, 800, 3), (235, 245, 250), np.uint8)
    for y in range(120, 700, 40):
        cv2.putText(img, "noi dung chinh cua bai", (40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    regs = segment_page(img, "kntt")
    assert [r.type for r in regs] == [RegionType.BODY]


def test_params_for_reads_min_sat_from_fingerprint(tmp_path, monkeypatch):
    import json
    from src.etl.layout import segmenter as mod

    fp_dir = tmp_path / "fingerprints"
    fp_dir.mkdir()
    (fp_dir / "SGK_KHTN_9_CD.json").write_text(json.dumps(
        {"box_palette": {"sat_percentiles": {"p10": 12.0}}}), encoding="utf-8")
    monkeypatch.setattr(mod, "FINGERPRINT_DIR", fp_dir)

    params = mod._params_for(book="SGK_KHTN_9_CD")

    # p10=12 > MIN_SAT_FLOOR(9) -> gia tri RIENG cua quyen thang, khong phai san
    assert params["min_sat"] == 12


def test_params_for_clamps_to_floor_when_p10_below_it(tmp_path, monkeypatch):
    import json
    from src.etl.layout import segmenter as mod

    fp_dir = tmp_path / "fingerprints"
    fp_dir.mkdir()
    (fp_dir / "SGK_KHTN_9_CD.json").write_text(json.dumps(
        {"box_palette": {"sat_percentiles": {"p10": 3.0}}}), encoding="utf-8")
    monkeypatch.setattr(mod, "FINGERPRINT_DIR", fp_dir)

    params = mod._params_for(book="SGK_KHTN_9_CD")

    assert params["min_sat"] == mod.MIN_SAT_FLOOR  # p10=3 duoi san -> dung san


def test_params_for_falls_back_to_default_when_fingerprint_missing(tmp_path, monkeypatch, caplog):
    from src.etl.layout import segmenter as mod

    monkeypatch.setattr(mod, "FINGERPRINT_DIR", tmp_path)  # thu muc rong

    params = mod._params_for(book="SGK_KHTN_KHONG_TON_TAI")

    assert params["min_sat"] == 45
    assert "fingerprint" in caplog.text.lower()


def test_params_for_no_book_keeps_old_constant_behaviour():
    from src.etl.layout import segmenter as mod

    params = mod._params_for()

    assert params["min_sat"] == 45

