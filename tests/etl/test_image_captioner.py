"""Caption ảnh: tắt thì im lặng, BẬT mà hỏng thì phải ỒN (D-42, D-47).

Hai test dưới đây khoá lại đúng cái defect của D-42: `_load_model` từng bắt mọi
Exception, log `warning`, rồi đặt `self.enabled = False` — nên
`IMAGE_CAPTION_ENABLED=true` vẫn cho ra chunk ảnh KHÔNG có caption mà không ai
biết. Không test nào ở đây nạp model thật (nặng ~1,9 GB); chúng chỉ kiểm hợp
đồng lỗi và tiền xử lý ảnh.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from src.etl.image_captioner import (
    INTERNVL_TILE_SIZE,
    ImageCaptioner,
    _dynamic_preprocess,
)


def _captioner(tmp_path, enabled: bool) -> ImageCaptioner:
    return ImageCaptioner(
        model_name="./models/does-not-exist",
        enabled=enabled,
        cache_path=tmp_path / "cache.json",
    )


def test_disabled_returns_empty_and_never_loads(tmp_path):
    cap = _captioner(tmp_path, enabled=False)
    result = cap.caption(Image.new("RGB", (32, 32)), "hash-1")

    assert result["visual_caption_vi"] == ""
    assert result["caption_source"] == "none"
    assert cap._model is None and cap._tokenizer is None
    assert cap._load_model() is False


def test_enabled_but_model_missing_raises(tmp_path):
    """Bật mà không nạp được model thì phải RAISE, không trả caption rỗng."""
    cap = _captioner(tmp_path, enabled=True)

    with pytest.raises(Exception):
        cap.caption(Image.new("RGB", (32, 32)), "hash-2")

    # và phải KHÔNG tự tắt mình đi sau lỗi — chính hành vi đó là D-42
    assert cap.enabled is True


def test_cache_hit_skips_model(tmp_path):
    """Đã có trong cache thì không cần model — nên không raise dù model hỏng."""
    cap = _captioner(tmp_path, enabled=True)
    key = cap._cache_key("hash-3", None)
    cap._cache[key] = {"visual_caption_vi": "con cá", "caption_source": "x"}

    assert cap.caption(Image.new("RGB", (32, 32)), "hash-3")[
        "visual_caption_vi"] == "con cá"


def test_cache_key_carries_version(tmp_path):
    """Khoá cache phải mang version, kể cả khi không có context.

    Trước đây khoá không-context là `{model}:{hash}`, nên đổi prompt/logic là
    cache cũ sống sót âm thầm.
    """
    cap = _captioner(tmp_path, enabled=False)
    from src.etl.image_captioner import CAPTION_CONTEXT_VERSION

    assert CAPTION_CONTEXT_VERSION in cap._cache_key("hash-4", None)
    assert CAPTION_CONTEXT_VERSION in cap._cache_key(
        "hash-4", {"figure_label": "Hình 1.1"})
    assert cap._cache_key("hash-4", None) != cap._cache_key(
        "hash-4", {"figure_label": "Hình 1.1"})


@pytest.mark.parametrize(
    "size,max_num,expect_thumbnail",
    [
        ((448, 448), 6, False),   # đúng 1 ô -> InternVL KHÔNG thêm thumbnail
        ((900, 450), 6, True),
        ((184, 222), 6, True),
    ],
)
def test_dynamic_preprocess_tiles(size, max_num, expect_thumbnail):
    img = Image.fromarray(
        np.zeros((size[1], size[0], 3), dtype=np.uint8), mode="RGB")
    tiles = _dynamic_preprocess(img, max_num=max_num)

    assert 1 <= len(tiles) <= max_num + 1
    assert all(t.size == (INTERNVL_TILE_SIZE, INTERNVL_TILE_SIZE)
               for t in tiles)
    assert (len(tiles) > 1) is expect_thumbnail
