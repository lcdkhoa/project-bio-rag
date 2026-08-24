# -*- coding: utf-8 -*-
"""`--book` phải lọc được CẢ BA đường ETL, không chỉ `--build-manifests`.

Vì sao đây là một test chứ không phải một dòng sửa: trước bản vá này
`main.py` nối `--book` vào duy nhất `--build-manifests`, nên
`python main.py --image-only --book SGK_KHTN_6_KNTT` **im lặng bỏ qua** cờ
`--book` và chạy cả 12 quyển ≈ 6 giờ — trong đó 8 quyển CD/CTST đã đo được là
kênh pill đọc 0 nhãn (D-65). Một cờ bị bỏ qua âm thầm là đúng loại lỗi nguyên
tắc 5 cấm.

Và cách hỏng thứ hai, tệ hơn: một tên quyển viết sai (`SGK_KHTN_6_KNT`) lọc ra
**0 quyển** rồi báo "pipeline completed" với exit code 0. Nên tên không khớp
phải THOÁT KHÁC 0.

Fake dùng lại nguyên bộ của `test_run_etl_checkpoint` — phần thật duy nhất vẫn
là các file PNG nhỏ trên đĩa.
"""
import cv2
import numpy as np
import pytest

import main
import src.etl as etl_pkg
import src.rag.image_vectorstore as ivs_mod
import src.rag.vectorstore as vs_mod

from .test_run_etl_checkpoint import (
    NEW_VERSION,
    FakeImageProcessor,
    FakeImageVDB,
    FakeLayoutLoader,
    FakeOCRLoader,
    FakeStatus,
    FakeTextVDB,
)

BOOKS = ("SGK_KHTN_6_KNTT", "SGK_KHTN_7_KNTT")
PAGES = (1, 2)


def _write_page(folder, number, tint):
    image = np.full((40, 30, 3), 255, dtype=np.uint8)
    image[0, 0] = tint
    cv2.imwrite(str(folder / f"page_{number:03d}.png"), image)


class Env:
    def __init__(self, data_dir, text_vdbs):
        self.data_dir = data_dir
        self._text_vdbs = text_vdbs

    @property
    def image_books(self):
        return sorted({c["source"] for p in FakeImageProcessor.instances
                       for c in p.calls})

    @property
    def text_books(self):
        return sorted({d.metadata["source"] for vdb in self._text_vdbs
                       for d in vdb.db.added})


@pytest.fixture
def env(tmp_path, monkeypatch):
    FakeLayoutLoader.instances.clear()
    FakeOCRLoader.instances.clear()
    FakeImageProcessor.instances.clear()

    data_dir = tmp_path / "datasources"
    for book in BOOKS:
        folder = data_dir / book
        folder.mkdir(parents=True)
        for number in PAGES:
            _write_page(folder, number, (number, 1, 2))

    monkeypatch.setattr(main, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(main, "PERSIST_DIR", tmp_path / "db")
    monkeypatch.setattr(main, "IMAGES_DIR", tmp_path / "db" / "images")
    monkeypatch.setattr(main, "PROCESSED_FILES_LOG", tmp_path / "pf.txt")
    monkeypatch.setattr(main, "PROCESSED_IMAGES_LOG", tmp_path / "pi.txt")

    monkeypatch.setattr(etl_pkg, "ProcessingStatus", FakeStatus)
    monkeypatch.setattr(etl_pkg, "LayoutOCRLoader", FakeLayoutLoader,
                        raising=False)
    monkeypatch.setattr(etl_pkg, "RobustOCRLoader", FakeOCRLoader)
    monkeypatch.setattr(
        etl_pkg, "make_image_processor",
        lambda filename, status_tracker=None: FakeImageProcessor(NEW_VERSION),
    )

    text_vdbs = []

    def _text_vdb():
        vdb = FakeTextVDB()
        text_vdbs.append(vdb)
        return vdb

    monkeypatch.setattr(vs_mod, "VectorDB", _text_vdb)
    monkeypatch.setattr(ivs_mod, "ImageVectorDB", FakeImageVDB)

    return Env(data_dir, text_vdbs)


def test_image_only_book_filter_touches_only_that_book(env):
    main.run_etl_image_only(book_name="SGK_KHTN_7_KNTT")

    assert env.image_books == ["SGK_KHTN_7_KNTT"]


def test_image_only_without_filter_touches_every_book(env):
    main.run_etl_image_only()

    assert env.image_books == list(BOOKS)


def test_text_only_book_filter_touches_only_that_book(env):
    main.run_etl_text_only(book_name="SGK_KHTN_6_KNTT")

    assert env.text_books == ["SGK_KHTN_6_KNTT"]


def test_etl_book_filter_touches_only_that_book(env):
    main.run_etl(book_name="SGK_KHTN_7_KNTT")

    assert env.image_books == ["SGK_KHTN_7_KNTT"]
    assert env.text_books == ["SGK_KHTN_7_KNTT"]


@pytest.mark.parametrize("runner", ["run_etl_image_only", "run_etl_text_only",
                                    "run_etl"])
def test_unknown_book_exits_nonzero_and_does_nothing(env, runner):
    with pytest.raises(SystemExit) as excinfo:
        getattr(main, runner)(book_name="SGK_KHTN_6_KNT")

    assert excinfo.value.code == 2
    assert env.image_books == []
    assert env.text_books == []
