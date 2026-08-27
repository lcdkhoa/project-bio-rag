"""Layout-aware text loader: một trang nguồn -> các chunk Document đã sạch.

Ba điều khác bản M1 và mỗi điều là một luật của repo:

1. **Không render.** Nguồn là PNG một file/trang (`PageSource`), nên không có
   DPI nào để tinh chỉnh và không có bước preprocess nào chạy trước
   segmentation — dải wipe 6% lề trái của bản cũ đã bị xoá vì đo được là **không
   có con dấu nào** trên nguồn này mà nó thì xoá mất viền info-box, icon và số
   trang lề trái (spec §1.5).
2. **Số trang in lấy từ `BookManifest`, không đoán.** Bản cũ fallback về
   `index + 1` — một lỗi off-by-one im lặng (nguồn thật: `printed_page ==
   filenum − 1`). Không có manifest -> **raise**, không index bừa (CẤM #5).
3. **Trang bìa bị bỏ ở bước chunk, không bị xoá khỏi nguồn**: manifest gắn
   `role="cover"`, loader trả về rỗng (CẤM #4).
"""
import logging
from pathlib import Path

from .segmenter import segment_page
from .text_extract import extract_text_units
from .chunker import chunk_units
from .formula_ocr import get_formula_client
from ..book.manifest import (MANIFEST_DIR, book_id_from_source_name,
                             load_manifest)
from ..image_processor import get_pdf_variant
from ...config import FORMULA_HYBRID_ENABLED

logger = logging.getLogger(__name__)

SKIP_ROLES = ("cover",)

# Spine Bài chỉ được ghi vào metadata chunk khi chính manifest KHÔNG tự tố là nó
# hỏng. Hai flag này nghĩa là "số Bài dựng ra không tin được", và ghi một số Bài
# chưa chứng minh được vào index là nói điều mình không chứng minh được
# (nguyên tắc 1). Đo 2026-08-21: cả 4 quyển đều sạch hai flag này (55/42/47/51
# Bài liền mạch, D-43) nên `bai_so` đi vào index — chặn của D-39 được gỡ, nhưng
# gỡ CÓ ĐIỀU KIỆN chứ không gỡ hẳn: quyển nào hỏng lại thì tự động thôi ghi.
SPINE_UNTRUSTED_FLAGS = ("bai_numbers_not_contiguous", "spine_out_of_order")


class ManifestMissing(RuntimeError):
    """Chưa dựng BookManifest cho quyển này — phải chạy --build-manifests trước."""


class LayoutOCRLoader:
    """Đường text duy nhất: một `PageSource`, từng trang một."""

    def __init__(self, manifest_dir=None):
        self.manifest_dir = Path(manifest_dir) if manifest_dir else MANIFEST_DIR
        self._manifests: dict[str, object] = {}
        self._page_meta: dict[str, dict] = {}
        self._spine_trusted: dict[str, bool] = {}   # cảnh báo một lần/quyển

    def manifest_for(self, source):
        name = source.name
        if name not in self._manifests:
            book_id = book_id_from_source_name(name)
            path = self.manifest_dir / f"{book_id}.json"
            if not path.is_file():
                raise ManifestMissing(
                    f"{name}: không có manifest {path} — chạy "
                    f"`python main.py --build-manifests` trước khi index text")
            manifest = load_manifest(path)
            self._manifests[name] = manifest
            self._page_meta[name] = {
                int(page["page_index"]): page for page in manifest.pages}
        return self._manifests[name]

    def spine_is_trusted(self, source) -> bool:
        if source.name in self._spine_trusted:
            return self._spine_trusted[source.name]
        manifest = self.manifest_for(source)
        bad = [f["kind"] for f in manifest.flags
               if f["kind"] in SPINE_UNTRUSTED_FLAGS]
        if bad:
            logger.warning(
                f"[{source.name}] spine Bài có flag {sorted(set(bad))} -> "
                f"KHÔNG ghi bai_so vào metadata chunk cho quyển này")
        self._spine_trusted[source.name] = not bad
        return not bad

    def page_meta(self, source, page_number: int) -> dict:
        self.manifest_for(source)
        meta = self._page_meta[source.name].get(int(page_number))
        if meta is None:
            raise ManifestMissing(
                f"{source.name}: manifest không có trang {page_number} — "
                f"manifest cũ so với nguồn, dựng lại trước khi index")
        if meta.get("printed_page") is None:
            raise ManifestMissing(
                f"{source.name}: trang {page_number} không có printed_page "
                f"trong manifest — không được đoán số trang")
        return meta

    def load_page(self, source, page_number: int):
        meta = self.page_meta(source, page_number)
        if meta.get("role") in SKIP_ROLES:
            logger.info(
                f"[{source.name}] trang {page_number}: role={meta['role']} "
                f"-> không index (nguồn vẫn giữ nguyên)")
            return []
        variant = get_pdf_variant(source.name)
        img = source.load(page_number)
        regions = segment_page(img, variant, book=source.name)
        formula_client = get_formula_client() if FORMULA_HYBRID_ENABLED else None
        units = extract_text_units(img, regions, variant,
                                   formula_client=formula_client)
        # `bai_so` đi vào metadata chunk CHỈ KHI spine của quyển này sạch flag
        # (xem SPINE_UNTRUSTED_FLAGS). Trước D-43 spine sai nặng nên chỗ này bị
        # chặn cứng; giờ nó là điều kiện đo được, không phải một hằng số niềm tin.
        bai_so = meta.get("bai_so") if self.spine_is_trusted(source) else None
        return chunk_units(units, source=source.name,
                           page=int(meta["printed_page"]), variant=variant,
                           page_index=int(page_number),
                           bai_so=int(bai_so) if bai_so is not None else None)

    def load_book(self, source):
        out = []
        for page_number in source.page_numbers():
            try:
                out.extend(self.load_page(source, page_number))
            except Exception as e:
                logger.error(f"[{source.name}] trang {page_number}: {e}")
        return out
