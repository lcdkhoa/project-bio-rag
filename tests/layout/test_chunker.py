from src.etl.layout.chunker import chunk_units
from src.etl.layout.regions import TextUnit, RegionType

def test_body_split_and_box_atomic():
    body = TextUnit(RegionType.BODY, "câu " * 400, 0, (0,0,1,1))          # long -> splits
    box = TextUnit(RegionType.SIDEBAR, "Câu hỏi 5: giải thích.", 1, (0,0,1,1))
    docs = chunk_units([body, box], source="SGK KHTN 7 CTST.pdf", page=40, variant="ctst")
    body_docs = [d for d in docs if d.metadata["region_type"] == "body"]
    box_docs = [d for d in docs if d.metadata["region_type"] == "sidebar"]
    assert len(body_docs) >= 2          # long body split into multiple chunks
    assert len(box_docs) == 1           # sidebar stays atomic
    assert box_docs[0].page_content.strip().startswith("Câu hỏi 5")
    for d in docs:
        assert d.metadata["source"] == "SGK KHTN 7 CTST.pdf"
        assert d.metadata["page"] == 40
        assert d.metadata["variant"] == "ctst"
        assert "chunk_index" in d.metadata

def test_chunk_index_is_unique_sequential():
    body = TextUnit(RegionType.BODY, "x " * 500, 0, (0,0,1,1))
    docs = chunk_units([body], "s.pdf", 1, "cd")
    idx = [d.metadata["chunk_index"] for d in docs]
    assert idx == list(range(len(idx)))
