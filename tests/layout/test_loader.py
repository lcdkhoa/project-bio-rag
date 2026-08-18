import fitz
import numpy as np
from src.etl.layout import loader as L
from src.etl.layout.regions import Region, RegionType

def test_load_page_wires_pipeline(monkeypatch):
    img = np.full((200, 200, 3), 255, np.uint8)
    monkeypatch.setattr(L, "_render_page", lambda pdf, i, dpi: img)
    monkeypatch.setattr(L, "preprocess_page", lambda im, v: im)
    monkeypatch.setattr(L, "segment_page", lambda im, v: [Region(RegionType.BODY, (0,0,200,200), 0, {})])
    monkeypatch.setattr(L, "detect_printed_page_number", lambda im, v, idx: 88)
    from src.etl.layout import text_extract as TE
    monkeypatch.setattr(L, "extract_text_units", lambda im, regs, v: [
        __import__("src.etl.layout.regions", fromlist=["TextUnit"]).TextUnit(RegionType.BODY, "quang hợp là gì", 0, (0,0,1,1))])
    docs = L.LayoutOCRLoader().load_page("SGK KHTN 7 CTST.pdf", 90)
    assert len(docs) == 1
    assert docs[0].metadata["page"] == 88          # printed number, not pdf index 90
    assert docs[0].metadata["variant"] == "ctst"
    assert docs[0].metadata["region_type"] == "body"


def _one_page_pdf(tmp_path, name="page.pdf"):
    """A minimal real single-page PDF (20x10pt) fitz can open by path."""
    path = tmp_path / name
    doc = fitz.open()
    doc.new_page(width=20, height=10)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_render_page_handles_grayscale_pixmap(tmp_path, monkeypatch):
    """pix.n == 1 (grayscale scan) must still yield HxWx3 BGR uint8."""
    path = _one_page_pdf(tmp_path)
    real_get_pixmap = fitz.Page.get_pixmap

    def fake_get_pixmap(self, matrix=None):
        pix = real_get_pixmap(self, matrix=matrix)
        return fitz.Pixmap(fitz.csGRAY, pix)  # n == 1

    monkeypatch.setattr(fitz.Page, "get_pixmap", fake_get_pixmap)
    arr = L._render_page(path, 0, 72)
    assert arr.shape == (10, 20, 3)
    assert arr.dtype == np.uint8


def test_render_page_handles_rgba_pixmap(tmp_path, monkeypatch):
    """pix.n == 4 (RGBA) must drop alpha and still yield HxWx3 BGR uint8."""
    path = _one_page_pdf(tmp_path, name="page_rgba.pdf")
    real_get_pixmap = fitz.Page.get_pixmap

    def fake_get_pixmap(self, matrix=None):
        pix = real_get_pixmap(self, matrix=matrix)
        return fitz.Pixmap(pix, 1)  # n == 4 (adds alpha)

    monkeypatch.setattr(fitz.Page, "get_pixmap", fake_get_pixmap)
    arr = L._render_page(path, 0, 72)
    assert arr.shape == (10, 20, 3)
    assert arr.dtype == np.uint8


def test_render_page_handles_rgb_pixmap(tmp_path):
    """pix.n == 3 (plain RGB) is the common case and must also work."""
    path = _one_page_pdf(tmp_path, name="page_rgb.pdf")
    arr = L._render_page(path, 0, 72)
    assert arr.shape == (10, 20, 3)
    assert arr.dtype == np.uint8
