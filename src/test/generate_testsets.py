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

## Nhiều câu MỘT lượt gọi, và cái giá của nó (D-75)

Hạn mức/ngày của OpenRouter free tier **chưa đo được** (API không trả header
`x-ratelimit-*`, `/api/v1/key` trả `limit: null` — D-67), nên đường sinh này được
thiết kế để **không phụ thuộc vào việc biết hạn mức**:

* **`QUESTIONS_PER_CALL = 3` câu trên MỘT lượt gọi**, cùng một trang vàng. 12 quyển
  × 25 câu đi từ **300+ lượt gọi xuống ~100**.
* **Ghi từng lô ra CSV NGAY** (append), nên một lần 429 mất tối đa một lượt gọi,
  không mất cả quyển như bản trước (bản trước gom `rows` rồi ghi ở CUỐI quyển).
* **Chạy lại đúng lệnh cũ là tiếp tục**: trang nào đã có trong CSV thì bỏ qua.
* 429 → **lùi rồi thử lại**, hết số lần thì **dừng SẠCH cả lượt chạy** và in ra chỗ
  đã dừng. Không đốt tiếp quyển sau khi đã biết là hết hạn mức.

**CÁI GIÁ, phải ghi vào báo cáo chứ không được giấu:** 3 câu cùng một trang là 3 câu
**tương quan** — trang nào khó truy hồi thì cả 3 cùng trượt. 25 câu từ 9 trang có
sức phân biệt thống kê gần với **9 mẫu độc lập** hơn là 25. Nên `_generation_meta.json`
ghi cả `n_gold_pages`, và báo cáo phải nói rõ số trang vàng, không chỉ số câu.

## Vì sao KHÔNG có mức độ khó "tổng hợp đa ngữ cảnh"

Đề cương (Nội dung 3) đòi ba mức: *trích xuất trực tiếp / suy luận liên kết / tổng
hợp đa ngữ cảnh*. Mức thứ ba **không thể sinh từ một trang** — theo định nghĩa nó
cần câu trả lời trải trên nhiều trang. Bắt LLM sinh nó từ một trang thì nó sẽ hoặc
bịa, hoặc dán nhãn sai cho một câu thực chất là suy luận trong trang. Cả hai đều
tệ hơn là **thiếu và nói ra là thiếu**.

Nên đường này sinh hai mức **thật** (`truc_tiep`, `suy_luan`) và ghi
`missing_difficulty: tong_hop_da_ngu_canh` vào meta. Muốn có mức thứ ba thì phải:
ghép chunk từ **nhiều trang cùng một Bài**, và **`metrics` phải nhận gold là một
TẬP trang** — hiện `make_page_relevance` nhận đúng một trang. Đó là việc riêng,
không nhét vào đây.

## TRUNG THỰC VỀ BỘ TEST NÀY

Câu hỏi và `ground_truth` do **LLM sinh**. Người dùng đã chốt (D-74) là sẽ **duyệt
tay ~50 câu** để ước lượng tỉ lệ gold key sai và công bố kèm mọi bảng số — cho tới
khi đó `human_reviewed` là `false`, và mọi báo cáo dùng số đo từ đây **phải ghi rõ**.
Bộ test là thước đo **tương đối** giữa các cấu hình (ablation), không phải chân lý.

`seed` chỉ cố định **thứ tự chọn trang**. Câu hỏi sinh ở `temperature=0.7` nên
**không** lặp lại nguyên văn giữa hai lượt chạy — đừng đọc `seed` thành "bộ test
tái tạo được từng chữ".

## Chạy

    python src/test/generate_testsets.py --dry-run          # chọn trang, không gọi LLM
    python src/test/generate_testsets.py                    # 25 câu/quyển
    python src/test/generate_testsets.py --book SGK_KHTN_6_KNTT --per-book 30
    # bị 429 giữa đường? chạy LẠI ĐÚNG LỆNH ĐÓ, nó tiếp tục từ chỗ dừng.
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
from src.etl.book.manifest import book_id_from_source_name  # noqa: E402
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
RANDOM_SEED = 42               # cố định THỨ TỰ CHỌN TRANG (không cố định câu hỏi)
# Số câu xin trên MỘT lượt gọi. Đây là cần điều khiển hạn mức: 300+ lượt -> ~100.
# Cái giá là 3 câu chung một trang vàng thì tương quan với nhau (xem docstring).
QUESTIONS_PER_CALL = int(os.getenv("EVAL_QUESTIONS_PER_CALL", "3"))
# Hai mức độ khó SINH ĐƯỢC từ một trang. Mức "tổng hợp đa ngữ cảnh" của đề cương
# KHÔNG sinh được từ một trang — xem docstring, và nó được ghi là còn thiếu.
DIFFICULTY_LEVELS = ("truc_tiep", "suy_luan")
MISSING_DIFFICULTY = "tong_hop_da_ngu_canh"
PHAN_MON_VALUES = ("ly", "hoa", "sinh", "khac")
# Lùi rồi thử lại khi bị 429. Hết dãy này thì DỪNG SẠCH cả lượt chạy.
RATE_LIMIT_BACKOFF_SECONDS = (20, 60)

CSV_FIELDS = [
    "question",
    "ground_truth",
    "source_book",     # == metadata `source` của chunk
    "source_page",     # == metadata `page` (số trang IN)
    "source_page_index",  # == metadata `page_index` (số trong tên file)
    "bai_so",
    # Nhãn Nội dung 3 của đề cương. `khoi`/`bo_sach` suy từ TÊN QUYỂN bằng code
    # (deterministic); `phan_mon`/`do_kho` do LLM gắn trong CÙNG lượt gọi, nên
    # KHÔNG tốn thêm lượt nào — nhưng chúng là nhãn của MODEL, không phải chân lý.
    "phan_mon",
    "do_kho",
    "khoi",
    "bo_sach",
    "n_chunks",
    "text_chars",
]

GEN_PROMPT = """Bạn là giáo viên ra đề môn Khoa học tự nhiên THCS.
Dưới đây là toàn bộ nội dung văn bản mà hệ thống đã trích được từ MỘT trang sách
giáo khoa (đúng văn bản đang nằm trong cơ sở dữ liệu tìm kiếm, có thể còn lỗi OCR).

[NỘI DUNG TRANG]:
{page_text}

Hãy tạo {n} câu hỏi kiểm tra kiến thức mà học sinh trả lời được HOÀN TOÀN chỉ dựa
vào nội dung trang trên, mỗi câu kèm đáp án chuẩn (ground truth) ngắn gọn, chính xác.

Quy tắc:
- Mỗi câu hỏi hỏi một nội dung KHÁC nhau trong trang. Không hỏi lại cùng một chi tiết.
- Câu hỏi cụ thể, rõ ràng, bằng tiếng Việt, KHÔNG tham chiếu "trang này"/"đoạn trên".
- Câu hỏi phải chứa đủ từ khoá để tìm lại được trang, không phụ thuộc ngữ cảnh ngoài.
- Đáp án chỉ lấy từ nội dung trang, KHÔNG bịa thêm.
- "do_kho" của mỗi câu chọn trong: "truc_tiep" (đáp án nằm nguyên văn trong trang),
  "suy_luan" (phải nối hai chi tiết trong CÙNG trang mới trả lời được).
  Cố gắng có ÍT NHẤT MỘT câu mỗi loại.
- "phan_mon" là phân môn của nội dung trang, chọn trong: "ly", "hoa", "sinh",
  hoặc "khac" nếu trang không thuộc riêng phân môn nào (ví dụ bài mở đầu, kĩ năng
  chung). ĐỪNG đoán bừa — không rõ thì ghi "khac".
- Nếu trang chủ yếu là bìa, mục lục, bảng tra, hình trang trí, hoặc chữ quá vụn/lỗi
  OCR nặng không đủ ra câu hỏi tốt -> đặt "answerable": false và để "questions": [].

CHỈ trả về JSON thuần (không markdown), đúng định dạng:
{{"answerable": true, "phan_mon": "sinh", "questions": [
  {{"question": "...", "ground_truth": "...", "do_kho": "truc_tiep"}}
]}}
"""


class QuotaStop(RuntimeError):
    """Hết hạn mức API — dừng SẠCH cả lượt chạy, không đốt tiếp quyển sau."""


def _is_rate_limited(exc: Exception) -> bool:
    """429 / hết hạn mức, nhận theo LỚP trước rồi mới theo chuỗi.

    Nhận theo chuỗi là phương án dự phòng có chủ ý: OpenRouter là proxy nhiều nhà
    cung cấp nên thông điệp lỗi không cố định, và đoán sai theo hướng "coi là hết
    hạn mức" chỉ làm lượt chạy dừng sớm (an toàn), còn đoán sai hướng kia thì đốt
    hết hạn mức trong lúc mọi lượt gọi đều thất bại.
    """
    try:
        from openai import RateLimitError
        if isinstance(exc, RateLimitError):
            return True
    except Exception:
        pass
    text = str(exc).lower()
    return any(k in text for k in ("429", "rate limit", "rate_limit",
                                   "quota", "too many requests"))


def _ask_llm(llm, prompt: str, *, sleeper=time.sleep) -> str:
    """Gọi LLM, lùi rồi thử lại khi bị 429, hết dãy thì raise `QuotaStop`."""
    for attempt, wait in enumerate((*RATE_LIMIT_BACKOFF_SECONDS, None)):
        try:
            resp = llm.invoke(prompt)
            return getattr(resp, "content", resp)
        except Exception as exc:
            if not _is_rate_limited(exc):
                raise
            if wait is None:
                raise QuotaStop(
                    f"bị chặn hạn mức sau {attempt} lần thử lại: {exc}") from exc
            print(f"    ! hạn mức (429) — chờ {wait}s rồi thử lại "
                  f"({attempt + 1}/{len(RATE_LIMIT_BACKOFF_SECONDS)})")
            sleeper(wait)
    raise QuotaStop("không tới được đây")   # pragma: no cover


def book_labels(source_name: str) -> Dict[str, str]:
    """`khoi` + `bo_sach` suy từ TÊN QUYỂN. Không nhận ra thì để RỖNG, không đoán.

    Dùng lại `book_id_from_source_name` thay vì viết regex thứ hai — hai nơi suy ra
    cùng một thứ là hai nguồn sự thật, và đó đúng là bug D-71 đã cắn một lần.
    """
    book_id = book_id_from_source_name(source_name)
    if not book_id.startswith("KHTN") or "-" not in book_id:
        return {"khoi": "", "bo_sach": ""}
    grade, publisher = book_id[len("KHTN"):].split("-", 1)
    return {"khoi": grade, "bo_sach": publisher}


def _rows_in_csv(csv_path: Path) -> tuple:
    """`(số câu đã có, tập page_index đã dùng)` — nền của việc chạy lại là tiếp tục."""
    if not csv_path.exists():
        return 0, set()
    done: set = set()
    count = 0
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            count += 1
            value = (row.get("source_page_index") or "").strip()
            if value.isdigit():
                done.add(int(value))
    return count, done


def _append_rows(csv_path: Path, rows: List[Dict]) -> None:
    """Ghi NGAY từng lô. Một lần 429 vì thế mất tối đa một lượt gọi."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in CSV_FIELDS} for r in rows)


def parse_questions(data: dict, payload: Dict, labels: Dict) -> List[Dict]:
    """JSON của LLM -> các dòng CSV. Câu thiếu trường thì BỎ, không lấp."""
    if not data.get("answerable"):
        return []
    phan_mon = str(data.get("phan_mon", "")).strip().lower()
    if phan_mon not in PHAN_MON_VALUES:
        phan_mon = ""          # ngoài tập đóng -> để rỗng, không đoán
    out: List[Dict] = []
    for item in data.get("questions") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        truth = str(item.get("ground_truth", "")).strip()
        if not question or not truth:
            continue
        do_kho = str(item.get("do_kho", "")).strip().lower()
        if do_kho not in DIFFICULTY_LEVELS:
            do_kho = ""
        out.append({**payload, **labels, "question": question,
                    "ground_truth": truth, "do_kho": do_kho,
                    "phan_mon": phan_mon})
    return out


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
    per_call: int = QUESTIONS_PER_CALL,
) -> Optional[Path]:
    """Sinh câu hỏi cho một quyển. Chạy lại là TIẾP TỤC, không làm lại từ đầu.

    Raise `QuotaStop` khi hết hạn mức — cố ý để nó nổi lên `main()` và dừng cả lượt
    chạy, thay vì đốt tiếp quyển sau khi đã biết là bị chặn.
    """
    csv_path = out_dir / f"{source.name}_testset.csv"
    if overwrite and csv_path.exists() and not dry_run:
        csv_path.unlink()
    have, pages_done = (0, set()) if dry_run else _rows_in_csv(csv_path)
    if have >= per_book and not dry_run:
        print(f"  -> đã có {have}/{per_book} câu trong {csv_path.name}, bỏ qua "
              f"(dùng --overwrite để làm lại).")
        return csv_path
    if have:
        print(f"  -> TIẾP TỤC: đã có {have} câu từ {len(pages_done)} trang.")

    loader = LayoutOCRLoader()
    labels = book_labels(source.name)
    pages = list(source.page_numbers())
    rng = random.Random(seed)
    rng.shuffle(pages)

    made = have
    examined = skipped_short = skipped_role = unanswerable = llm_error = calls = 0
    t0 = time.perf_counter()

    for page_number in pages:
        if made >= per_book:
            break
        # Hạn mức xét theo TRANG ĐÃ XÉT, và trang đã dùng ở lượt trước không tính
        # lại — nếu tính lại thì lần chạy thứ hai sẽ hết hạn mức mà chưa gọi lượt
        # nào, tức việc "chạy lại là tiếp tục" tự vô hiệu.
        if examined >= per_book * CANDIDATE_MULTIPLIER:
            print(f"  !! đã xét {examined} trang mà chỉ được {made}/{per_book} câu "
                  f"-> dừng quyển này, con số thật là {made}.")
            break
        if page_number in pages_done:
            continue
        examined += 1

        payload = _page_payload(loader, source, page_number)
        if payload is None:
            skipped_role += 1
            continue
        if payload["text_chars"] < MIN_PAGE_TEXT_CHARS:
            skipped_short += 1
            continue

        if dry_run:
            # Mỗi trang cho tới `per_call` câu, nên dry-run phải cộng `per_call` —
            # cộng 1 thì nó báo cần gấp 3 số trang thật, tức nói sai chi phí của
            # chính lượt chạy mà nó có nhiệm vụ dự báo. Bắt được khi CHẠY THẬT
            # `--dry-run --per-book 3`: nó xét 4 trang cho 3 câu, trong khi lượt
            # thật chỉ cần 1 trang.
            made += per_call
            print(f"  [{min(made, per_book):>2}/{per_book}] page_{page_number:03d} "
                  f"-> in {payload['source_page']}, Bài {payload['bai_so'] or '?'}, "
                  f"{payload['n_chunks']} chunk, {payload['text_chars']} ký tự")
            continue

        calls += 1
        try:
            raw = _ask_llm(llm, GEN_PROMPT.format(
                page_text=payload["text"][:4000], n=per_call))
            rows = parse_questions(_parse_json(raw), payload, labels)
        except QuotaStop:
            print(f"  !! HẾT HẠN MỨC sau {calls} lượt gọi. Đã lưu {made} câu vào "
                  f"{csv_path.name}. Chạy LẠI ĐÚNG LỆNH NÀY để tiếp tục.")
            raise
        except Exception as exc:
            llm_error += 1
            logger.warning("Sinh câu hỏi lỗi (page_%03d): %s", page_number, exc)
            continue

        if not rows:
            unanswerable += 1
            continue

        rows = rows[:max(1, per_book - made)]
        _append_rows(csv_path, rows)      # GHI NGAY, trước khi gọi lượt tiếp theo
        pages_done.add(page_number)
        made += len(rows)
        print(f"  [{made:>2}/{per_book}] in {payload['source_page']:>3} "
              f"(page_{page_number:03d}) +{len(rows)} câu: "
              f"{rows[0]['question'][:56]}")

    took = time.perf_counter() - t0
    print(f"  xét {examined} trang / {calls} lượt gọi trong {took:.0f}s | "
          f"bỏ vì role/rỗng {skipped_role} | bỏ vì ít chữ {skipped_short} | "
          f"LLM nói không đặt được {unanswerable} | lỗi LLM {llm_error}")

    if dry_run:
        return None
    if not csv_path.exists():
        print(f"  !! không sinh được câu nào cho {source.name}.")
        return None
    if made < per_book:
        print(f"  !! CHỈ được {made}/{per_book} câu — báo cáo phải dùng con số thật này.")
    print(f"  -> {csv_path.name}: {made} câu")
    return csv_path


def _write_meta(out_dir: Path, written: List[Path], args, stopped: str = "") -> Path:
    """Ghi meta SAU MỖI QUYỂN, không phải ở cuối lượt chạy.

    Bản trước chỉ ghi ở cuối, nên một lượt bị 429 giữa đường để lại CSV mà **không
    có** meta — tức có số mà không có câu "chưa ai duyệt" đi kèm. Đó đúng là kiểu
    im lặng nguy hiểm: người đọc sau sẽ tưởng bộ test đã hoàn chỉnh.
    """
    pages: set = set()
    total = 0
    by_level: Dict[str, int] = {}
    by_mon: Dict[str, int] = {}
    for path in written:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                total += 1
                pages.add((row.get("source_book"), row.get("source_page")))
                by_level[row.get("do_kho") or "(rỗng)"] = \
                    by_level.get(row.get("do_kho") or "(rỗng)", 0) + 1
                by_mon[row.get("phan_mon") or "(rỗng)"] = \
                    by_mon.get(row.get("phan_mon") or "(rỗng)", 0) + 1
    meta_path = out_dir / "_generation_meta.json"
    meta_path.write_text(json.dumps({
        "human_reviewed": False,
        "note": ("Câu hỏi + ground_truth do LLM sinh, CHƯA có người duyệt. "
                 "Mọi báo cáo dùng số đo từ bộ test này phải ghi rõ điều đó."),
        "correlated_questions_warning": (
            f"{QUESTIONS_PER_CALL} câu chung MỘT trang vàng nên tương quan với "
            f"nhau: {total} câu chỉ đến từ {len(pages)} trang, sức phân biệt "
            f"thống kê gần với số TRANG hơn số CÂU."),
        "n_questions": total,
        "n_gold_pages": len(pages),
        "by_do_kho": by_level,
        "by_phan_mon": by_mon,
        "missing_difficulty": MISSING_DIFFICULTY,
        "missing_difficulty_reason": (
            "Không sinh được từ MỘT trang (theo định nghĩa cần nhiều trang), và "
            "metrics.make_page_relevance hiện nhận đúng một trang vàng."),
        "questions_per_call": QUESTIONS_PER_CALL,
        "generator_model": os.getenv("EVAL_LLM_MODEL", ""),
        "generator_base_url": os.getenv("EVAL_LLM_BASE_URL", ""),
        "per_book_target": args.per_book,
        "seed": args.seed,
        "seed_scope": "chỉ thứ tự chọn trang; câu hỏi sinh ở temperature 0.7",
        "min_page_text_chars": MIN_PAGE_TEXT_CHARS,
        "skip_printed_pages_before": SKIP_PRINTED_PAGES_BEFORE,
        "stopped_early": stopped,
        "files": sorted(p.name for p in written),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", default="", help="chỉ một quyển, ví dụ SGK_KHTN_6_KNTT")
    ap.add_argument("--per-book", type=int, default=NUM_QUESTIONS_PER_BOOK)
    ap.add_argument("--per-call", type=int, default=QUESTIONS_PER_CALL,
                    help="số câu xin trên MỘT lượt gọi (mặc định %(default)s)")
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

    print(f"{len(sources)} quyển. {args.per_book} câu/quyển, "
          f"{args.per_call} câu/lượt gọi"
          f"{' (DRY RUN, 0 lượt gọi)' if args.dry_run else ''}.\n")

    written: List[Path] = []
    stopped = ""
    for source in sources:
        print(f"== {source.name} ({len(list(source.page_numbers()))} trang) ==")
        try:
            path = generate_for_book(
                source, args.out_dir, llm, args.per_book,
                args.seed, args.dry_run, args.overwrite, args.per_call)
        except QuotaStop as exc:
            stopped = f"{source.name}: {exc}"
            path = args.out_dir / f"{source.name}_testset.csv"
            if path.exists() and path not in written:
                written.append(path)
            print(f"\n!! DỪNG SẠCH cả lượt chạy vì hết hạn mức, không đốt tiếp "
                  f"các quyển sau. Chạy lại đúng lệnh này để tiếp tục.")
            break
        if path:
            written.append(path)
        # Ghi meta sau MỖI quyển: một lượt bị chặn giữa đường vẫn phải để lại câu
        # "chưa ai duyệt" bên cạnh số liệu.
        if not args.dry_run and written:
            _write_meta(args.out_dir, written, args, stopped)
        print()

    if args.dry_run:
        return 0
    if written:
        meta_path = _write_meta(args.out_dir, written, args, stopped)
        print(f"Đã ghi {meta_path.name} (ghi rõ: CHƯA có người duyệt, và "
              f"{args.per_call} câu chung một trang thì tương quan).")
    return 2 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
