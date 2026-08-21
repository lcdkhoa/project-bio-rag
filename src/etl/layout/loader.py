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
from ..book.manifest import (MANIFEST_DIR, book_id_from_source_name,
                             load_manifest)
from ..image_processor import get_pdf_variant

logger = logging.getLogger(__name__)

SKIP_ROLES = ("cover",)


class ManifestMissing(RuntimeError):
    """Chưa dựng BookManifest cho quyển này — phải chạy --build-manifests trước."""


class LayoutOCRLoader:
    """Đường text duy nhất: một `PageSource`, từng trang một."""

    def __init__(self, manifest_dir=None):
        self.manifest_dir = Path(manifest_dir) if manifest_dir else MANIFEST_DIR
        self._manifests: dict[str, object] = {}
        self._page_meta: dict[str, dict] = {}

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
        regions = segment_page(img, variant)
        units = extract_text_units(img, regions, variant)
        # `bai_so` CÓ trong manifest nhưng KHÔNG đi vào metadata chunk: đo trên
        # corpus thật, spine Bài hiện còn sai nặng (sách 6 dựng được 4 Bài cho
        # ~55 Bài; MỤC LỤC OCR ra 0 entry). Ghi một số Bài chưa chứng minh được
        # vào index là nói điều mình không chứng minh được (nguyên tắc 1) — nên
        # nó ở lại manifest như một giả thuyết có flag, cho người xem.
        return chunk_units(units, source=source.name,
                           page=int(meta["printed_page"]), variant=variant,
                           page_index=int(page_number))

    def load_book(self, source):
        out = []
        for page_number in source.page_numbers():
            try:
                out.extend(self.load_page(source, page_number))
            except Exception as e:
                logger.error(f"[{source.name}] trang {page_number}: {e}")
        return out
