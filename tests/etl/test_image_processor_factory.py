import src.etl.image_processor as IP


def test_factory_routes_by_filename(monkeypatch):
    # keep construction cheap: stub the heavy collaborators __init__ builds
    monkeypatch.setattr(IP, "ImageCaptioner", lambda *a, **k: object())
    monkeypatch.setattr(IP, "ProcessingStatus", lambda *a, **k: object())

    assert type(IP.make_image_processor("SGK KHTN 6 CTST.pdf")) is IP.CtsstImageProcessor
    assert type(IP.make_image_processor("SGK KHTN 8 KNTT.pdf")) is IP.KnttImageProcessor
    assert type(IP.make_image_processor("SGK KHTN 6 CD.pdf")) is IP.ImageProcessor
