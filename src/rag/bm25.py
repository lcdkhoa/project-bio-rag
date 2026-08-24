# -*- coding: utf-8 -*-
"""Chỉ mục THƯA (Okapi BM25) dựng TRÊN chính `biology_text` — không OCR lại.

Đề cương, Nội dung 2: *"Truy xuất lai: kết hợp tìm kiếm theo từ khóa (BM25) và
tìm kiếm ngữ nghĩa dày đặc (dense passage retrieval) để không bỏ sót các truy vấn
chứa thuật ngữ khoa học đặc thù."*

## Ba ràng buộc thiết kế, mỗi cái có lý do đã cắn thật

1. **Khoá là chính `chunk_id` của `biology_text`** (`{page_key}_p{page}_c{index}`).
   Dựng một tập tài liệu riêng với id riêng là tạo **nguồn sự thật thứ hai** —
   đúng loại lỗi của D-71 (`book_id` nối cứng `-KNTT` khiến ba NXB ghi đè manifest
   của nhau, im lặng hoàn toàn, 158 test vẫn xanh).

2. **Chỉ mục thưa là artefact SINH RA ĐƯỢC, và nó tự tố khi cũ hơn index.** Dấu
   vân gồm số chunk **và** digest của toàn bộ chunk id **và**
   `TEXT_EXTRACTION_VERSION` **và** phiên bản bộ chuẩn hoá/tách từ. Lệch bất kỳ
   cái nào -> `SparseIndexStale`. Số chunk một mình là **không đủ**: dựng lại
   index với cùng số chunk nhưng khác nội dung sẽ lọt. Chỉ mục thưa cũ hơn index
   là một cách hỏng **âm thầm** — cùng loại D-52 (image doc mồ côi) và loại
   "rerank tắt âm thầm dưới HF_HUB_OFFLINE=1". Không có fallback "thôi dùng tạm
   bản cũ" (CẤM #6).

3. **`k1`/`b` là tham số lúc TRUY VẤN, không phải lúc dựng.** BM25 rất nhạy với
   hai số này và đề cương đòi chọn bằng số, nên quét `k1 x b` phải rẻ: chỉ mục
   lưu tần suất thô, điểm tính lúc truy vấn. Đây cũng là lý do không dùng
   `rank_bm25` (chưa cài): nó chốt `k1`/`b` lúc khởi tạo nên mỗi ô của bảng quét
   là một lần dựng lại chỉ mục.

Công thức: Okapi BM25 với IDF dạng Lucene
`idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5))`, luôn dương nên một từ có mặt ở
hơn nửa số tài liệu không bao giờ **trừ** điểm (biến thể Robertson gốc thì có).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from scipy import sparse

from .text_normalize import NORMALIZER_VERSION, tokenize

logger = logging.getLogger(__name__)

INDEX_FORMAT_VERSION = "bm25-v1"


class SparseIndexStale(RuntimeError):
    """Chỉ mục thưa không còn khớp index dày. FAIL LOUDLY — không dùng bản cũ."""


class SparseIndexMissing(FileNotFoundError):
    """Chưa dựng chỉ mục thưa. Chạy `python main.py --build-bm25`."""


def chunk_ids_digest(ids: Iterable[str]) -> str:
    """Digest ổn định của TẬP chunk id (không phụ thuộc thứ tự trả về)."""
    h = hashlib.md5()
    for cid in sorted(ids):
        h.update(cid.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


@dataclass(frozen=True)
class SparseFingerprint:
    """Dấu vân của index nguồn tại thời điểm dựng chỉ mục thưa."""

    collection: str
    n_chunks: int
    ids_digest: str
    text_extraction_version: str
    tokenizer: str
    normalizer_version: str
    index_format: str = INDEX_FORMAT_VERSION

    def mismatches(self, other: "SparseFingerprint") -> List[str]:
        out = []
        mine_d, theirs_d = asdict(self), asdict(other)
        for field, mine in mine_d.items():
            theirs = theirs_d[field]
            if mine != theirs:
                out.append(
                    f"{field}: chỉ mục thưa={mine!r} vs index hiện tại={theirs!r}")
        return out


class BM25Index:
    """Ma trận tần suất thưa + tra cứu BM25. `k1`/`b` truyền lúc truy vấn."""

    def __init__(
        self,
        ids: Sequence[str],
        tf: sparse.spmatrix,
        doc_len: np.ndarray,
        vocab: Dict[str, int],
        fingerprint: SparseFingerprint,
    ):
        if tf.shape[0] != len(ids):
            raise ValueError(
                f"tf có {tf.shape[0]} hàng nhưng có {len(ids)} chunk id")
        self.ids = list(ids)
        self.tf = tf.tocsc()
        self.doc_len = np.asarray(doc_len, dtype=np.float64)
        self.vocab = dict(vocab)
        self.fingerprint = fingerprint
        self.avg_len = float(self.doc_len.mean()) if len(self.doc_len) else 0.0
        # df của mỗi từ = số tài liệu chứa nó (không phải tổng tần suất).
        binary = self.tf.copy()
        binary.data = np.ones_like(binary.data)
        # float64 CÓ CHỦ Ý: `tf` lưu float32 cho gọn, nhưng df/idf tính ở float32
        # lệch ~7,5e-8 tương đối so với số tính tay (test
        # `test_bm25_score_khop_so_tinh_tay` bắt được). Nhỏ, nhưng nó là sai số
        # của chính công thức chứ không phải của dữ liệu — và sửa không tốn gì.
        self.df = np.asarray(binary.sum(axis=0), dtype=np.float64).ravel()
        n = float(len(self.ids))
        self.idf = np.log(1.0 + (n - self.df + 0.5) / (self.df + 0.5))

    # --- dựng ------------------------------------------------------------
    @classmethod
    def build(
        cls,
        ids: Sequence[str],
        texts: Sequence[str],
        fingerprint: SparseFingerprint,
        fold_accents: bool = True,
        formula: bool = True,
    ) -> "BM25Index":
        if len(ids) != len(texts):
            raise ValueError(f"{len(ids)} id nhưng {len(texts)} văn bản")
        vocab: Dict[str, int] = {}
        rows: List[int] = []
        cols: List[int] = []
        vals: List[int] = []
        doc_len = np.zeros(len(ids), dtype=np.float64)
        for i, text in enumerate(texts):
            toks = tokenize(text, fold_accents=fold_accents, formula=formula)
            doc_len[i] = len(toks)
            counts: Dict[int, int] = {}
            for t in toks:
                j = vocab.get(t)
                if j is None:
                    j = len(vocab)
                    vocab[t] = j
                counts[j] = counts.get(j, 0) + 1
            for j, c in counts.items():
                rows.append(i)
                cols.append(j)
                vals.append(c)
        tf = sparse.csr_matrix(
            (np.asarray(vals, dtype=np.float32), (rows, cols)),
            shape=(len(ids), max(len(vocab), 1)),
        )
        return cls(ids, tf, doc_len, vocab, fingerprint)

    # --- truy vấn --------------------------------------------------------
    def scores(self, query: str, k1: float, b: float,
               fold_accents: bool = True, formula: bool = True) -> np.ndarray:
        """Điểm BM25 của MỌI tài liệu cho một truy vấn."""
        toks = tokenize(query, fold_accents=fold_accents, formula=formula)
        out = np.zeros(len(self.ids), dtype=np.float64)
        if not toks or self.avg_len <= 0:
            return out
        # Từ lặp trong truy vấn: BM25 cộng một lần cho mỗi lần xuất hiện.
        qcount: Dict[int, int] = {}
        for t in toks:
            j = self.vocab.get(t)
            if j is not None:
                qcount[j] = qcount.get(j, 0) + 1
        norm = k1 * (1.0 - b + b * (self.doc_len / self.avg_len))
        for j, qtf in qcount.items():
            col = self.tf.getcol(j)
            rows = col.indices
            f = col.data.astype(np.float64)
            out[rows] += qtf * self.idf[j] * (f * (k1 + 1.0)) / (f + norm[rows])
        return out

    def search(self, query: str, k: int, k1: float, b: float,
               fold_accents: bool = True,
               formula: bool = True) -> List[Tuple[str, float]]:
        """Top-k `(chunk_id, điểm)`, bỏ hẳn tài liệu điểm 0."""
        if k <= 0:
            return []
        s = self.scores(query, k1=k1, b=b, fold_accents=fold_accents,
                        formula=formula)
        nz = np.flatnonzero(s > 0.0)
        if nz.size == 0:
            return []
        take = nz[np.argsort(-s[nz], kind="stable")[:k]]
        return [(self.ids[i], float(s[i])) for i in take]

    # --- lưu / nạp -------------------------------------------------------
    def save(self, directory) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        sparse.save_npz(str(directory / "bm25_tf.npz"), self.tf.tocsr())
        np.save(str(directory / "bm25_doclen.npy"), self.doc_len)
        (directory / "bm25_meta.json").write_text(
            json.dumps(
                {
                    "fingerprint": asdict(self.fingerprint),
                    "ids": self.ids,
                    "vocab": self.vocab,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.info("Đã lưu chỉ mục thưa: %d chunk, %d từ vựng -> %s",
                    len(self.ids), len(self.vocab), directory)
        return directory

    @classmethod
    def load(cls, directory) -> "BM25Index":
        directory = Path(directory)
        meta_path = directory / "bm25_meta.json"
        if not meta_path.exists():
            raise SparseIndexMissing(
                f"Không có chỉ mục thưa ở {directory}. "
                "Dựng bằng: python main.py --build-bm25"
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        tf = sparse.load_npz(str(directory / "bm25_tf.npz"))
        doc_len = np.load(str(directory / "bm25_doclen.npy"))
        return cls(
            ids=meta["ids"],
            tf=tf,
            doc_len=doc_len,
            vocab=meta["vocab"],
            fingerprint=SparseFingerprint(**meta["fingerprint"]),
        )

    def verify(self, live: SparseFingerprint) -> None:
        """RAISE nếu chỉ mục thưa không còn khớp index dày. Không có fallback."""
        bad = self.fingerprint.mismatches(live)
        if bad:
            raise SparseIndexStale(
                "Chỉ mục thưa CŨ HƠN / KHÁC index dày — từ chối dùng.\n  "
                + "\n  ".join(bad)
                + "\nDựng lại: python main.py --build-bm25"
            )


# --- Đọc dấu vân của index dày ------------------------------------------

def live_fingerprint(collection, tokenizer: str,
                     text_extraction_version: str) -> SparseFingerprint:
    """Dấu vân HIỆN TẠI của `biology_text`. Chỉ đọc id — rẻ (đo ~0,2 s/16 393)."""
    got = collection.get(include=[], limit=1_000_000)
    ids = got.get("ids") or []
    return SparseFingerprint(
        collection=getattr(collection, "name", "?"),
        n_chunks=len(ids),
        ids_digest=chunk_ids_digest(ids),
        text_extraction_version=text_extraction_version,
        tokenizer=tokenizer,
        normalizer_version=NORMALIZER_VERSION,
    )
