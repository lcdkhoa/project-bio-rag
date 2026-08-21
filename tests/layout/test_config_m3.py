import importlib


def test_m3_config_defaults(monkeypatch):
    for key in ["IMAGE_EXTRACTION_VERSION", "FIGURE_IN_BOX_DROP_RATIO"]:
        monkeypatch.delenv(key, raising=False)
    import src.config as cfg
    importlib.reload(cfg)

    # Bump khi nguồn ảnh đổi: trang PNG 1094x1536 KHÁC bản render
    # poppler 150 DPI trước đây, nên hình học crop đổi -> phải re-extract.
    assert cfg.IMAGE_EXTRACTION_VERSION == "v17_png_source"
    assert cfg.FIGURE_IN_BOX_DROP_RATIO == 0.80
