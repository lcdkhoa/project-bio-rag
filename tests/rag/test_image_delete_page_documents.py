"""Doc ảnh cũ của một trang phải BỊ XOÁ trước khi ghi bản mới.

Đường text đã có `_delete_page_chunks`; đường ảnh thì không, và đó là một lỗ mồ
côi thật sự: `image_id` là hash của CROP, nên crop đổi thì id đổi và doc cũ không
bị upsert đè mà sống sót. Đo được trên một DB scratch 12 trang: thay nội dung 1
trang làm trang đó có **3** doc ảnh (1 cũ + 2 mới), và crop mồ côi vẫn tra ra
được — học sinh có thể được trả về một hình không còn tồn tại trên trang. Cùng
chuyện đó xảy ra với MỌI trang khi bump `IMAGE_EXTRACTION_VERSION`.

Test dùng collection giả nên không nạp CLIP: nó kiểm HỢP ĐỒNG (xoá trên cả hai
collection, đúng where-clause, không nổ khi rỗng), không kiểm ChromaDB.
"""
from __future__ import annotations

import pytest

from src.rag.image_vectorstore import ImageVectorDB


class FakeCollection:
    def __init__(self, ids=None, raise_on_delete=False):
        self._ids = list(ids or [])
        self.deleted_where = []
        self.raise_on_delete = raise_on_delete

    def get(self, where=None, **kwargs):
        return {"ids": list(self._ids)}

    def delete(self, where=None, ids=None):
        if self.raise_on_delete:
            raise RuntimeError("chroma bực mình")
        self.deleted_where.append(where)


class FakeChroma:
    def __init__(self, collection):
        self._collection = collection


def _db(meta_ids=("a", "b"), raise_on_delete=False):
    db = object.__new__(ImageVectorDB)      # bỏ qua __init__ (nó nạp CLIP)
    db._metadata_chroma = FakeChroma(
        FakeCollection(meta_ids, raise_on_delete))
    db._chroma = FakeChroma(FakeCollection(meta_ids, raise_on_delete))
    return db


def test_deletes_from_both_collections_with_the_same_filter():
    db = _db()
    removed = db.delete_page_documents("SGK_KHTN_6_KNTT", [25])

    assert removed == 2
    expected = {"$and": [{"pdf_filename": {"$eq": "SGK_KHTN_6_KNTT"}},
                         {"page_number": {"$in": [25]}}]}
    assert db._metadata_chroma._collection.deleted_where == [expected]
    assert db._chroma._collection.deleted_where == [expected], \
        "collection visual bị bỏ sót -> crop mồ côi vẫn tra ra được"


def test_page_numbers_are_deduped_and_sorted():
    db = _db()
    db.delete_page_documents("SGK_KHTN_9_KNTT", [31, 20, 31, 20, 25])

    where = db._chroma._collection.deleted_where[0]
    assert where["$and"][1]["page_number"]["$in"] == [20, 25, 31]


def test_empty_page_list_is_a_no_op():
    db = _db()
    assert db.delete_page_documents("SGK_KHTN_6_KNTT", []) == 0
    assert db._chroma._collection.deleted_where == []


def test_delete_failure_is_logged_not_raised():
    """ETL không được sập vì một lỗi xoá; nhưng nó phải log (không im lặng)."""
    db = _db(raise_on_delete=True)
    assert db.delete_page_documents("SGK_KHTN_6_KNTT", [25]) == 2


@pytest.mark.parametrize("pages", [[25], [20, 21, 22]])
def test_string_page_numbers_are_coerced(pages):
    db = _db()
    db.delete_page_documents("SGK_KHTN_6_KNTT", [str(p) for p in pages])
    where = db._chroma._collection.deleted_where[0]
    assert where["$and"][1]["page_number"]["$in"] == pages
