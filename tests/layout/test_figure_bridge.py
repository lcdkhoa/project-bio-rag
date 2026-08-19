import numpy as np

import src.etl.layout.figure_bridge as FB
from src.etl.layout.regions import Region, RegionType


def _fig(bbox, image_type="single_figure"):
    return {"bbox": bbox, "image_type": image_type}


def _patch_boxes(monkeypatch, boxes):
    """Make segment_page return SIDEBAR regions for the given bboxes."""
    captured = {}

    def fake_segment(image, variant):
        captured["image"] = image
        captured["variant"] = variant
        regs = [Region(RegionType.BODY, (0, 0, 10, 10), 0, {})]
        regs += [Region(RegionType.SIDEBAR, b, i + 1, {}) for i, b in enumerate(boxes)]
        return regs

    monkeypatch.setattr(FB, "segment_page", fake_segment)
    return captured


def test_containment_ratio():
    assert FB._containment((10, 10, 20, 20), (0, 0, 100, 100)) == 1.0
    assert FB._containment((0, 0, 10, 10), (5, 0, 100, 10)) == 0.5
    assert FB._containment((0, 0, 10, 10), (50, 50, 60, 60)) == 0.0


def test_drops_figure_inside_box(monkeypatch):
    _patch_boxes(monkeypatch, [(0, 0, 100, 100)])
    regions = [_fig((10, 10, 90, 90))]              # fully inside the box
    out = FB.reconcile_with_layout(regions, np.zeros((120, 120, 3), np.uint8), "cd")
    assert out == []


def test_keeps_marginally_overlapping_figure(monkeypatch):
    _patch_boxes(monkeypatch, [(0, 0, 100, 100)])
    regions = [_fig((80, 80, 300, 300))]            # mostly outside the box
    out = FB.reconcile_with_layout(regions, np.zeros((320, 320, 3), np.uint8), "cd")
    assert out == regions


def test_keeps_figure_when_no_boxes(monkeypatch):
    _patch_boxes(monkeypatch, [])
    regions = [_fig((10, 10, 90, 90))]
    out = FB.reconcile_with_layout(regions, np.zeros((120, 120, 3), np.uint8), "cd")
    assert out == regions


def test_never_drops_info_or_activity_box(monkeypatch):
    _patch_boxes(monkeypatch, [(0, 0, 100, 100)])
    # these ARE colour boxes by design; being inside a box must NOT drop them
    regions = [_fig((10, 10, 90, 90), image_type="textbook_info_box"),
               _fig((10, 10, 90, 90), image_type="activity_box"),
               _fig((10, 10, 90, 90), image_type="tool_group")]
    out = FB.reconcile_with_layout(regions, np.zeros((120, 120, 3), np.uint8), "cd")
    assert out == regions


def test_feeds_segmenter_bgr_view(monkeypatch):
    captured = _patch_boxes(monkeypatch, [])
    img = np.zeros((4, 4, 3), np.uint8)
    img[..., 0] = 255       # pure RED in RGB (channel 0)
    FB.reconcile_with_layout([_fig((0, 0, 1, 1))], img, "ctst")
    # bridge must hand segment_page the BGR view: red ends up in channel 2
    assert captured["image"][0, 0, 2] == 255
    assert captured["image"][0, 0, 0] == 0
    assert captured["variant"] == "ctst"


def test_segmentation_error_is_fail_open(monkeypatch):
    def boom(image, variant):
        raise RuntimeError("cv exploded")
    monkeypatch.setattr(FB, "segment_page", boom)
    regions = [_fig((10, 10, 90, 90))]
    out = FB.reconcile_with_layout(regions, np.zeros((120, 120, 3), np.uint8), "cd")
    assert out == regions


def test_to_layout_regions_maps_types():
    regions = [{"bbox": (0, 0, 10, 10), "image_type": "composite_figure"},
               {"bbox": (0, 0, 10, 10), "image_type": "activity_box"}]
    out = FB.to_layout_regions(regions)
    assert out[0].type is RegionType.FIGURE
    assert out[1].type is RegionType.INFO_BOX
    assert out[0].meta["image_type"] == "composite_figure"
    assert [r.reading_order for r in out] == [0, 1]
