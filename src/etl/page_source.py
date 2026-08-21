"""Nguồn trang: trừu tượng hoá "một quyển sách" thành các trang ảnh BGR.

Nguồn thật của corpus hiện tại (đo 2026-08-21) là **một thư mục PNG mỗi quyển**,
một file mỗi trang: `datasources/SGK_KHTN_6_KNTT/page_001.png …`. Không còn PDF
nào trong `datasources/`.

Hai bất biến định hình module này:

1. **Số trong tên file LÀ chỉ số trang của nguồn**, không phải thứ tự enumerate
   thư mục. Nguồn tự đánh số theo trang thật của họ, nên một trang tải bù về sau
   vẫn slot đúng chỗ. Vì vậy `page_numbers()` trả về *số trong tên file* và mọi
   thứ ở tầng trên neo vào nó — tuyệt đối không vào `enumerate(...)`.
2. **Checkpoint khoá theo content hash của TỪNG TRANG**, không phải của cả quyển:
   tải bù 19 trang chỉ re-process 19 trang.

`PdfPageSource` chỉ còn sống cho đường upload PDF ở `src/app/api.py` — corpus
chính không đi qua nó. `PDF_RENDER_DPI` là hằng số của riêng đường legacy đó,
không phải config tinh chỉnh được (`RENDER_DPI` đã bị xoá: nguồn PNG không có
bước render nào để tinh chỉnh).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable, Protocol, Sequence, runtime_checkable

import cv2
import numpy as np

PAGE_FILE = re.compile(r"^page[_-]?(\d+)\.png$", re.IGNORECASE)

# DPI render cho ĐƯỜNG LEGACY (PDF upload) — nguồn PNG không dùng tới.
PDF_RENDER_DPI = 220


class PageSourceError(RuntimeError):
    """Không đọc được trang nguồn — phải dừng ồn ào, không được đoán."""


@runtime_checkable
class PageSource(Protocol):
    """Một quyển sách, truy cập theo SỐ TRANG NGUỒN (số trong tên file)."""

    @property
    def name(self) -> str:
        """Tên hiển thị của quyển (đi vào metadata `source` của chunk)."""

    def page_numbers(self) -> list[int]:
        """Các số trang nguồn có thật, tăng dần. KHÔNG phải range(n)."""

    def load(self, page_number: int) -> np.ndarray:
        """Trang -> mảng HxWx3 BGR uint8 (alpha đã bị bỏ)."""

    def content_hash(self, page_number: int) -> str:
        """Hash nội dung của ĐÚNG trang đó — khoá checkpoint."""


def _imread_bgr(path: Path) -> np.ndarray:
    """Đọc PNG -> BGR uint8. `np.fromfile` để không chết trên path unicode.

    `IMREAD_COLOR` luôn trả 3 kênh BGR: RGBA của nguồn này có alpha = 255 ở mọi
    pixel (đã đo) nên bỏ alpha là mất 0 thông tin.
    """
    raw = np.fromfile(str(path), dtype=np.uint8)
    if raw.size == 0:
        raise PageSourceError(f"file trang rỗng: {path}")
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise PageSourceError(f"không decode được ảnh trang: {path}")
    return image


class PngFolderPageSource:
    """Một thư mục `page_NNN.png` = một quyển."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise PageSourceError(f"không phải thư mục: {self.directory}")
        self._paths: dict[int, Path] = {}
        for path in self.directory.iterdir():
            match = PAGE_FILE.match(path.name)
            if match:
                number = int(match.group(1))
                if number in self._paths:
                    raise PageSourceError(
                        f"hai file cùng số trang {number} trong {self.directory}: "
                        f"{self._paths[number].name} và {path.name}")
                self._paths[number] = path
        if not self._paths:
            raise PageSourceError(f"không có file page_*.png trong {self.directory}")

    @property
    def name(self) -> str:
        return self.directory.name

    def page_numbers(self) -> list[int]:
        return sorted(self._paths)

    def path(self, page_number: int) -> Path:
        try:
            return self._paths[page_number]
        except KeyError:
            raise PageSourceError(
                f"{self.name}: không có trang {page_number}") from None

    def load(self, page_number: int) -> np.ndarray:
        return _imread_bgr(self.path(page_number))

    def content_hash(self, page_number: int) -> str:
        digest = hashlib.md5()
        with self.path(page_number).open("rb") as handle:
            for block in iter(lambda: handle.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()


class PdfPageSource:
    """Một file PDF = một quyển. Chỉ dùng cho đường upload legacy."""

    def __init__(self, pdf_path: str | Path, dpi: int = PDF_RENDER_DPI):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.is_file():
            raise PageSourceError(f"không thấy PDF: {self.pdf_path}")
        self.dpi = dpi
        self._file_hash: str | None = None
        self._n_pages: int | None = None

    @property
    def name(self) -> str:
        return self.pdf_path.name

    def _page_count(self) -> int:
        if self._n_pages is None:
            import fitz
            doc = fitz.open(str(self.pdf_path))
            try:
                self._n_pages = doc.page_count
            finally:
                doc.close()
        return self._n_pages

    def page_numbers(self) -> list[int]:
        # 1-based để cùng hệ với tên file `page_001.png` của nguồn PNG.
        return list(range(1, self._page_count() + 1))

    def load(self, page_number: int) -> np.ndarray:
        import fitz
        doc = fitz.open(str(self.pdf_path))
        try:
            if not 1 <= page_number <= doc.page_count:
                raise PageSourceError(
                    f"{self.name}: không có trang {page_number}")
            pix = doc.load_page(page_number - 1).get_pixmap(dpi=self.dpi)
            arr = np.frombuffer(pix.samples, np.uint8).reshape(
                pix.height, pix.width, pix.n)
            if pix.n == 1:
                return np.repeat(arr, 3, axis=2).copy()
            return arr[:, :, :3][:, :, ::-1].copy()   # RGB(A) -> BGR
        finally:
            doc.close()

    def content_hash(self, page_number: int) -> str:
        if self._file_hash is None:
            digest = hashlib.md5()
            with self.pdf_path.open("rb") as handle:
                for block in iter(lambda: handle.read(65536), b""):
                    digest.update(block)
            self._file_hash = digest.hexdigest()
        # Một PDF = một file, không tách được bytes của từng trang, nên khoá
        # trang = hash(file) + số trang. Vẫn đúng tính chất "đổi nội dung ->
        # đổi khoá", chỉ là hạt to hơn nguồn PNG.
        return hashlib.md5(
            f"{self._file_hash}:{page_number}".encode("utf-8")).hexdigest()


def source_hash(source: PageSource) -> str:
    """Hash tổng của cả quyển = hash của (số trang, hash trang) theo thứ tự.

    Dùng để biết manifest có còn khớp nguồn hay không. Không dùng làm khoá
    checkpoint — khoá đó là per-page.
    """
    digest = hashlib.md5()
    for number in source.page_numbers():
        digest.update(f"{number}:{source.content_hash(number)}|".encode("utf-8"))
    return digest.hexdigest()


def discover_page_sources(data_dir: str | Path) -> list[PageSource]:
    """Mọi quyển trong `data_dir`: thư mục PNG trước, PDF legacy sau.

    Thư mục không có `page_*.png` bị bỏ qua im lặng (ví dụ thư mục phụ trợ) —
    một thư mục PNG hỏng thì `PngFolderPageSource` đã raise từ trong ra.
    """
    root = Path(data_dir)
    out: list[PageSource] = []
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir()):
        if child.is_dir() and any(PAGE_FILE.match(p.name) for p in child.iterdir()):
            out.append(PngFolderPageSource(child))
    out.extend(PdfPageSource(p) for p in sorted(root.glob("*.pdf")))
    return out


def find_page_source(data_dir: str | Path, name: str) -> PageSource:
    """Một quyển theo tên (tên thư mục hoặc tên file PDF)."""
    for source in discover_page_sources(data_dir):
        if source.name == name or Path(source.name).stem == name:
            return source
    raise PageSourceError(f"không thấy quyển '{name}' trong {data_dir}")


def contiguity_gaps(page_numbers: Sequence[int] | Iterable[int]) -> list[int]:
    """Các số trang THIẾU giữa min..max. Rỗng nghĩa là dãy liền mạch."""
    numbers = sorted(set(page_numbers))
    if not numbers:
        return []
    present = set(numbers)
    return [n for n in range(numbers[0], numbers[-1] + 1) if n not in present]


def page_checkpoint_key(source: PageSource, page_number: int) -> str:
    """Khoá của MỘT trang: tên quyển + hash nội dung trang.

    Đây là khoá của cả `processing_status` và id chunk. Vì sao có tên quyển: hash
    trang là duy nhất trong corpus hiện tại (đã md5 toàn bộ 801 file, 0 trùng)
    nhưng dựa vào điều đó là dựa vào một phép đo có thể hết hạn — hai trang giống
    nhau bit-for-bit ở hai quyển sẽ dùng chung id chunk và ghi đè lẫn nhau. Đổi
    tên thư mục nguồn thì khoá đổi -> re-process cả quyển: ồn ào nhưng đúng, hơn
    là im lặng trộn hai quyển.
    """
    return f"{source.name}#{source.content_hash(page_number)}"
