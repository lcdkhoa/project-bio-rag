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

def test_chunk_units_carries_page_index_bai_and_review_flags():
    body = TextUnit(RegionType.BODY, "câu " * 400, 0, (0, 0, 1, 1),
                    review_flags=["kh6ng"])
    box = TextUnit(RegionType.SIDEBAR, "Câu hỏi 5: giải thích.", 1, (0, 0, 1, 1))
    docs = chunk_units([body, box], source="SGK_KHTN_6_KNTT", page=9,
                       variant="kntt", page_index=10, bai_so=3)
    for d in docs:
        # `page` = số trang IN, `page_index` = số trang NGUỒN. Lệch nhau 1 trên
        # corpus này, nên gộp lại là mời off-by-one vào citation.
        assert d.metadata["page"] == 9
        assert d.metadata["page_index"] == 10
        assert d.metadata["bai_so"] == 3
    body_docs = [d for d in docs if d.metadata["region_type"] == "body"]
    box_docs = [d for d in docs if d.metadata["region_type"] == "sidebar"]
    assert all(d.metadata["needs_review"] for d in body_docs)
    assert all(d.metadata["review_tokens"] == "kh6ng" for d in body_docs)
    # cờ của vùng nào chỉ áp cho vùng đó
    assert box_docs[0].metadata["needs_review"] is False
    assert box_docs[0].metadata["review_tokens"] == ""


def test_chunk_units_metadata_has_no_list_values_chroma_would_reject():
    unit = TextUnit(RegionType.INFO_BOX, "Thông tin: abc def.", 0, (0, 0, 1, 1),
                    review_flags=["mat", "kh6ng"])
    docs = chunk_units([unit], "SGK_KHTN_6_KNTT", 9, "kntt", page_index=10)
    assert docs[0].metadata["review_tokens"] == "mat,kh6ng"
    assert all(not isinstance(v, (list, dict, set))
               for v in docs[0].metadata.values())

def test_a_very_long_box_is_split_but_keeps_its_region_label():
    from src.etl.layout.chunker import BOX_ATOMIC_MAX_CHARS
    long_box = TextUnit(RegionType.INFO_BOX, "Em có biết? " * 200, 0, (0, 0, 1, 1))
    docs = chunk_units([long_box], "SGK_KHTN_6_KNTT", 9, "kntt", page_index=10)
    assert len(docs) > 1
    assert all(d.metadata["region_type"] == "info_box" for d in docs)
    assert all(len(d.page_content) <= BOX_ATOMIC_MAX_CHARS for d in docs)
    assert [d.metadata["chunk_index"] for d in docs] == list(range(len(docs)))


def test_an_ordinary_box_stays_atomic():
    # Một câu hỏi bị cắt giữa là câu hỏi vô nghĩa -> hộp thường KHÔNG bị cắt.
    box = TextUnit(RegionType.SIDEBAR, "Câu hỏi 5: " + "giải thích. " * 20,
                   0, (0, 0, 1, 1))
    docs = chunk_units([box], "SGK_KHTN_6_KNTT", 9, "kntt", page_index=10)
    assert len(docs) == 1


def test_formula_hybrid_status_propagates_to_body_chunk_metadata():
    from src.etl.layout.chunker import chunk_units
    from src.etl.layout.regions import RegionType, TextUnit

    units = [
        TextUnit(RegionType.BODY, "một đoạn văn bản đủ dài để không bị bỏ qua",
                 0, (0, 0, 10, 10), formula_hybrid_status=["applied"]),
    ]

    docs = chunk_units(units, source="SGK_KHTN_7_KNTT", page=121, variant="kntt")

    assert docs[0].metadata["formula_hybrid_status"] == "applied"


def test_formula_hybrid_status_empty_when_no_unit_has_it():
    from src.etl.layout.chunker import chunk_units
    from src.etl.layout.regions import RegionType, TextUnit

    units = [
        TextUnit(RegionType.BODY, "một đoạn văn bản đủ dài để không bị bỏ qua",
                 0, (0, 0, 10, 10)),
    ]

    docs = chunk_units(units, source="SGK_KHTN_7_KNTT", page=121, variant="kntt")

    assert docs[0].metadata["formula_hybrid_status"] == ""


def test_formula_hybrid_status_dedupes_across_body_units():
    from src.etl.layout.chunker import chunk_units
    from src.etl.layout.regions import RegionType, TextUnit

    units = [
        TextUnit(RegionType.BODY, "đoạn một " * 10, 0, (0, 0, 10, 10),
                 formula_hybrid_status=["applied"]),
        TextUnit(RegionType.BODY, "đoạn hai " * 10, 1, (0, 10, 10, 20),
                 formula_hybrid_status=["applied", "unmatched_count"]),
    ]

    docs = chunk_units(units, source="SGK_KHTN_7_KNTT", page=121, variant="kntt")

    assert docs[0].metadata["formula_hybrid_status"] == "applied,unmatched_count"

