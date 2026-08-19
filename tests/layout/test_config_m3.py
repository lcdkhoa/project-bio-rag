import importlib


def test_m3_config_defaults(monkeypatch):
    for key in ["IMAGE_EXTRACTION_VERSION", "FIGURE_IN_BOX_DROP_RATIO"]:
        monkeypatch.delenv(key, raising=False)
    import src.config as cfg
    importlib.reload(cfg)

    assert cfg.IMAGE_EXTRACTION_VERSION == "v16_layout_reconcile"
    assert cfg.FIGURE_IN_BOX_DROP_RATIO == 0.80
