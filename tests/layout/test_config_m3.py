import importlib


def test_m3_config_defaults(monkeypatch):
    for key in ["IMAGE_EXTRACTION_VERSION", "FIGURE_IN_BOX_DROP_RATIO"]:
        monkeypatch.delenv(key, raising=False)
    import src.config as cfg
    importlib.reload(cfg)

    # Bump khi nguồn ảnh đổi: trang PNG 1094x1536 KHÁC bản render
    # poppler 150 DPI trước đây, nên hình học crop đổi -> phải re-extract.
    # v17_png_source -> v18_m3_g4 khi cổng G4 sửa hình học crop (D-45, D-46).
    # v18_m3_g4 -> v19_pill_kernels khi pill hợp ứng viên qua nhiều kernel CLOSE
    # (D-51): thêm 2 nhãn hình -> thêm anchor -> hình học crop đổi.
    assert cfg.IMAGE_EXTRACTION_VERSION == "v19_pill_kernels"
    assert cfg.FIGURE_IN_BOX_DROP_RATIO == 0.80


def test_image_caption_disabled_by_default(monkeypatch):
    """Caption ảnh TẮT theo mặc định — đã đo là bịa chi tiết (D-47).

    Phải vô hiệu cả `load_dotenv` mới đo được ĐÚNG default trong code: máy dev
    có `.env` riêng, không thì test chỉ đang kiểm `.env` của người chạy.
    """
    monkeypatch.delenv("IMAGE_CAPTION_ENABLED", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    import src.config as cfg
    importlib.reload(cfg)

    assert cfg.IMAGE_CAPTION_ENABLED is False
