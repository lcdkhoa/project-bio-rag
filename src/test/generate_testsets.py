"""Sinh bộ test đánh giá RAG cho corpus 4 quyển KNTT (PNG-per-page).

## Vì sao phải viết lại (bản cũ đo ra 0 cho mọi metric)

Bản trước duyệt `DATA_DIR/*.pdf` — corpus nay là **4 thư mục PNG**, nên nó tìm
thấy **0 sách**. Nhưng lỗi nặng hơn nằm ở KHOÁ VÀNG, và nó âm thầm:

- `source_book` ghi `"SGK KHTN 6 KNTT.pdf"`, còn metadata chunk ghi
  `"SGK_KHTN_6_KNTT"` -> `metrics.make_page_relevance` so `source` không bao giờ
  khớp;
- `source_page` ghi **số trong tên file** (`page_013` -> 13), còn metadata `page`
  là **số trang IN** (= số trong tên file − 1 trên corpus này, D-33) -> lệch 1.

Khoá `source_book` sai một mình đã đủ làm **mọi** Precision/Recall/MRR bằng 0, mà
không có lỗi nào được raise. Còn khoá trang lệch 1 thì bị `PAGE_TOLERANCE = 1`
(cũ) **che đi**: phép so vẫn trả True nên không ai phát hiện — dung sai đó nay đã
đặt về 0 vì chunk không bao giờ vắt qua hai trang (xem `metrics.py`).

Nên bản này **không tự dựng khoá vàng nữa**: nó lấy thẳng
`source` / `page` / `page_index` **từ metadata của chunk thật** do
`LayoutOCRLoader` sinh ra — cùng một đường code đưa dữ liệu vào index. Khoá khớp
**bởi cấu tạo**, không phải bởi quy ước hai bên tự nhớ.

Kèm theo: câu hỏi được sinh từ **đúng văn bản đã được index** (ghép các chunk của
trang), không phải từ một lần `image_to_string` riêng với psm mặc định. Trước đây
hai văn bản đó khác nhau, nên bộ test đo lệch so với thứ hệ thống thực sự có.

## TRUNG THỰC VỀ BỘ TEST NÀY

Câu hỏi và `ground_truth` do **LLM sinh, CHƯA có người duyệt** (người dùng đã
quyết định không duyệt tay — xem `document/specs/`). Mọi báo cáo dùng số đo từ
đây **phải ghi rõ điều đó**. Bộ test là thước đo tương đối giữa các cấu hình
(ablation), không phải chân lý về chất lượng.

## Chạy

    python src/test/generate_testsets.py --dry-run          # chọn trang, không gọi LLM
    python src/test/generate_testsets.py                    # 25 câu/quyển
    python src/test/generate_testsets.py --book SGK_KHTN_6_KNTT --per-book 30
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # đảm bảo in được tiếng Việt trên console Windows
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.config import DATA_DIR  # noqa: E402
from src.etl.layout.loader import LayoutOCRLoader  # noqa: E402
from src.etl.page_source import discover_page_sources  # noqa: E402
from src.test.eval_llm import config_help, get_eval_llm, is_configured  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ----- Tham số sinh test -----------------------------------------------------
# 25 câu/quyển (100 câu) là sàn: với 40 câu, chênh recall ±0,05 nằm trong nhiễu.
NUM_QUESTIONS_PER_BOOK = int(os.getenv("EVAL_QUESTIONS_PER_BOOK", "25"))
# Bỏ phần đầu sách theo SỐ TRANG IN (bìa, mục lục, lời nói đầu). Vai `cover`
# đã bị manifest loại sẵn; ngưỡng này chỉ để tránh MỤC LỤC.
SKIP_PRINTED_PAGES_BEFORE = 10
MIN_PAGE_TEXT_CHARS = 600      # trang phải đủ chữ mới đặt được câu hỏi
CANDIDATE_MULTIPLIER = 3       # xét gấp 3 số câu cần, đủ dư cho trang bị loại
RANDOM_SEED = 42               # cố định để bộ test lặp lại được

CSV_FIELDS = [
    "question",
    "ground_truth",
    "source_book",     # == metadata `source` của chunk
    "source_page",     # == metadata `page` (số trang IN)
    "source_page_index",  # == metadata `page_index` (số trong tên file)
    "bai_so",
    "n_chunks",
    "text_chars",
]

GEN_PROMPT = """Bạn là giáo viên ra đề môn Khoa học tự nhiên THCS.
Dưới đây là toàn bộ nội dung văn bản mà hệ thống đã trích được từ MỘT trang sách
giáo khoa (đúng văn bản đang nằm trong cơ sở dữ liệu tìm kiếm, có thể còn lỗi OCR).

[NỘI DUNG TRANG]:
{page_text}

Hãy tạo MỘT câu hỏi kiểm tra kiến thức mà học sinh trả lời được HOÀN TOÀN chỉ dựa
vào nội dung trang trên, kèm đáp án chuẩn (ground truth) ngắn gọn, chính xác.

Quy tắc:
- Câu hỏi cụ thể, rõ ràng, bằng tiếng Việt, KHÔNG tham chiếu "trang này"/"đoạn trên".
- Câu hỏi phải chứa đủ từ khoá để tìm lại được trang, không phụ thuộc ngữ cảnh ngoài.
- Đáp án chỉ lấy từ nội dung trang, KHÔNG bịa thêm.
- Nếu trang chủ yếu là bìa, mục lục, bảng tra, hình trang trí, hoặc chữ quá vụn/lỗi
  OCR nặng không đủ ra một câu hỏi tốt -> đặt "answerable": false.

CHỈ trả về JSON thuần (không markdown), đúng định dạng:
{{"answerable": true, "question": "...", "ground_truth": "..."}}
"""


def _parse_json(text: str) -> dict:
    """Bóc JSON từ output LLM (có thể bọc ```json ... ```)."""
    import re

    text = str(text).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def _page_payload(loader: LayoutOCRLoader, source, page_number: int) -> Optional[Dict]:
    """Trả về text + KHOÁ VÀNG lấy từ metadata chunk thật, hoặc None nếu bỏ qua.

    Khoá vàng KHÔNG được suy ra ở đây. `page` / `source` / `page_index` đọc
    thẳng từ chunk, nên nếu ETL đổi cách đánh số thì bộ test đổi theo, không lệch
    âm thầm.
    """
    chunks = loader.load_page(source, page_number)
    if not chunks:
        return None

    meta = chunks[0].metadata or {}
    printed = meta.get("page")
    book = meta.get("source")
    if book is None or printed is None:
        # LayoutOCRLoader lẽ ra đã raise ManifestMissing trước khi tới đây;
        # nếu vẫn thiếu thì đây là lỗi thật, không được lặng lẽ bỏ qua.
        raise ValueError(
            f"chunk của {source.name} trang {page_number} thiếu source/page: {meta}")

    if int(printed) < SKIP_PRINTED_PAGES_BEFORE:
        return None

    text = "\n\n".join(c.page_content for c in chunks).strip()
    if len(text) < MIN_PAGE_TEXT_CHARS:
        return None

    return {
        "text": text,
        "source_book": book,
        "source_page": int(printed),
        "source_page_index": int(meta.get("page_index", page_number)),
        "bai_so": meta.get("bai_so", ""),
        "n_chunks": len(chunks),
        "text_chars": len(text),
    }


def generate_for_book(
    source,
    out_dir: Path,
    llm,
    per_book: int,
    seed: int,
    dry_run: bool,
    overwrite: bool,
) -> Optional[Path]:
    csv_path = out_dir / f"{source.name}_testset.csv"
    if csv_path.exists() and not overwrite and not dry_run:
        print(f"  -> đã có {csv_path.name}, bỏ qua (dùng --overwrite để ghi lại).")
        return csv_path

    loader = LayoutOCRLoader()
    pages = list(source.page_numbers())
    rng = random.Random(seed)
    rng.shuffle(pages)

    rows: List[Dict] = []
    examined = skipped_short = skipped_role = unanswerable = llm_error = 0
    t0 = time.perf_counter()

    for page_number in pages:
        if len(rows) >= per_book:
            break
        if examined >= per_book * CANDIDATE_MULTIPLIER:
            break
        examined += 1

        payload = _page_payload(loader, source, page_number)
        if payload is None:
            skipped_role += 1
            continue
        if payload["text_chars"] < MIN_PAGE_TEXT_CHARS:
            skipped_short += 1
            continue

        if dry_run:
            rows.append({**payload, "question": "", "ground_truth": ""})
            print(f"  [{len(rows):>2}/{per_book}] page_{page_number:03d} "
                  f"-> in {payload['source_page']}, Bài {payload['bai_so'] or '?'}, "
                  f"{payload['n_chunks']} chunk, {payload['text_chars']} ký tự")
            continue

        try:
            resp = llm.invoke(GEN_PROMPT.format(page_text=payload["text"][:4000]))
            data = _parse_json(getattr(resp, "content", resp))
        except Exception as exc:
            llm_error += 1
            logger.warning("Sinh câu hỏi lỗi (page_%03d): %s", page_number, exc)
            continue

        if not (data.get("answerable") and data.get("question") and data.get("ground_truth")):
            unanswerable += 1
            continue

        rows.append({
            **payload,
            "question": str(data["question"]).strip(),
            "ground_truth": str(data["ground_truth"]).strip(),
        })
        print(f"  [{len(rows):>2}/{per_book}] in {payload['source_page']:>3} "
              f"(page_{page_number:03d}): {rows[-1]['question'][:66]}")

    took = time.perf_counter() - t0
    print(f"  xét {examined} trang trong {took:.0f}s | bỏ vì role/rỗng {skipped_role} "
          f"| bỏ vì ít chữ {skipped_short} | LLM nói không đặt được {unanswerable} "
          f"| lỗi LLM {llm_error}")

    if dry_run:
        return None
    if not rows:
        print(f"  !! không sinh được câu nào cho {source.name}.")
        return None
    if len(rows) < per_book:
        # Nói ra, không lặng lẽ trả ít hơn yêu cầu.
        print(f"  !! CHỈ được {len(rows)}/{per_book} câu — báo cáo phải dùng con số thật này.")

    out_dir.mkdir(parents=True, exist_ok=True)
    # utf-8-sig (có BOM) để Excel hiển thị đúng tiếng Việt.
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in CSV_FIELDS} for r in rows)
    print(f"  -> đã lưu {len(rows)} câu: {csv_path.name}")
    return csv_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", default="", help="chỉ một quyển, ví dụ SGK_KHTN_6_KNTT")
    ap.add_argument("--per-book", type=int, default=NUM_QUESTIONS_PER_BOOK)
    ap.add_argument("--seed", type=int, default=RANDOM_SEED)
    ap.add_argument("--out-dir", type=Path,
                    default=Path(__file__).resolve().parent / "testsets")
    ap.add_argument("--dry-run", action="store_true",
                    help="chỉ chọn trang + in thống kê, KHÔNG gọi LLM, KHÔNG ghi file")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    sources = discover_page_sources(DATA_DIR)
    if args.book:
        sources = [s for s in sources if s.name == args.book]
    if not sources:
        print(f"Không tìm thấy sách nào trong {DATA_DIR}"
              + (f" khớp --book {args.book}" if args.book else ""))
        return 1

    llm = None
    if not args.dry_run:
        if not is_configured():
            print(config_help())
            return 1
        llm = get_eval_llm(temperature=0.7)

    print(f"{len(sources)} quyển. {args.per_book} câu/quyển"
          f"{' (DRY RUN)' if args.dry_run else ''}.\n")

    written = []
    for source in sources:
        print(f"== {source.name} ({len(list(source.page_numbers()))} trang) ==")
        path = generate_for_book(
            source, args.out_dir, llm, args.per_book,
            args.seed, args.dry_run, args.overwrite)
        if path:
            written.append(path)
        print()

    if written:
        meta_path = args.out_dir / "_generation_meta.json"
        meta_path.write_text(json.dumps({
            "human_reviewed": False,
            "note": ("Câu hỏi + ground_truth do LLM sinh, CHƯA có người duyệt. "
                     "Mọi báo cáo dùng số đo từ bộ test này phải ghi rõ điều đó."),
            "generator_model": os.getenv("EVAL_LLM_MODEL", ""),
            "generator_base_url": os.getenv("EVAL_LLM_BASE_URL", ""),
            "per_book_target": args.per_book,
            "seed": args.seed,
            "min_page_text_chars": MIN_PAGE_TEXT_CHARS,
            "skip_printed_pages_before": SKIP_PRINTED_PAGES_BEFORE,
            "files": [p.name for p in written],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã ghi {meta_path.name} (ghi rõ: CHƯA có người duyệt).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
