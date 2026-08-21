"""Cổng G3 — TRANG ĐƯỢC TRÍCH DẪN có thực sự chứa câu trả lời hay không.

Repo chưa từng có phép đo này, và nó là thứ đáng đo nhất: với sách giáo khoa, một
citation trỏ sai trang tệ hơn là không trả lời, vì học sinh mở đúng trang đó ra và
không thấy gì.

## G3 đo gì, và KHÔNG đo gì

Với mỗi câu hỏi: chạy **đúng đường retrieval của production** (cùng
`VectorDB.get_retriever` mà `HybridRetriever` dùng, cùng `is_image_only_query` để
định tuyến), lấy `build_citations(text_docs)` — **citation deterministic, không
qua LLM** — rồi với TỪNG trang được trích, đọc lại **văn bản của chính trang đó
trong index** và hỏi: `ground_truth` có nằm trong đó không?

Điểm quan trọng: phép thử **không dùng khoá vàng**. Nó không hỏi "có trích đúng
trang vàng không" (đó là recall, đã có `recall_at_k.py`), mà hỏi "trang đã trích
có chứa câu trả lời không". Một câu hỏi có thể trả lời được từ trang khác trang
vàng và vẫn ĐÚNG. Khoá vàng chỉ được in ra để đối chiếu, không tham gia phán xử.

Ba nhóm kết quả, in riêng — **không gộp** để tránh đọc G3 như chất lượng đầu-cuối:

- `ok`            — có ít nhất một trang được trích chứa câu trả lời;
- `cited_wrong`   — có trích dẫn, nhưng KHÔNG trang nào chứa câu trả lời;
- `no_citation`   — retrieval không trả về gì (không có trích dẫn nào để sai).

    G3 = ok / (ok + cited_wrong)

`no_citation` là lỗi của recall, không phải của citation, nên nó nằm ngoài phân
số — nhưng được in đậm ngay cạnh, vì một G3 = 100% trên 3 câu có trích dẫn là vô
nghĩa.

## Phép so: deterministic trước, LLM chỉ để CỨU và để HIỆU CHỈNH

Chính: bỏ dấu, bỏ dấu câu, so **độ phủ token có trọng số IDF** của `ground_truth`
trong văn bản trang. IDF đo trên chính các trang đang có trong index, **không dùng
danh sách stopword**: phép bỏ dấu (bắt buộc vì OCR sai dấu) làm từ chức năng đụng
từ nội dung — "khí"->"khi", "đo"/"độ"->"do", "lá"->"la", "tai"->"tai", "đá"->"da",
"cân"->"can" — nên một stopword list sẽ xoá đúng những từ quan trọng nhất của sách
KHTN. Đáp án chỉ còn <= 3 token đặc trưng thì đòi CÓ ĐỦ cả ba, vì trúng một phần
trên một cụm ngắn là ngẫu nhiên.

**Giới hạn còn lại, nói thẳng:** bỏ dấu vẫn gộp một số từ khác nghĩa ("sáu" và
"sau" đều thành "sau"), nên với đáp án rất ngắn phép so có thể rộng tay. Đó là lý
do script ĐẾM RIÊNG số phán quyết dựa trên đáp án ngắn và tại sao có `--judge`.

`--coverage-min` mặc định **0,6 là con số CHƯA hiệu chỉnh** — nó phải được đo lại
trên bộ test thật bằng cách chạy `--judge` (LLM đọc trang và trả lời có/không kèm
câu trích dẫn làm bằng) rồi xem hai bên lệch nhau ở đâu. Script in phân bố độ phủ
và bảng đồng thuận deterministic-vs-judge để làm việc đó. Đừng báo cáo G3 như số
chốt trước khi hiệu chỉnh xong.

## Chạy

    python -m src.test.qa_citation_page                 # deterministic, không tốn token
    python -m src.test.qa_citation_page --judge         # thêm LLM cứu các ca bị loại
    python -m src.test.qa_citation_page --book SGK_KHTN_6_KNTT --limit 10 --verbose
    python -m src.test.qa_citation_page --out g3.json

Exit code 1 nếu G3 < ngưỡng (mặc định 0,95) hoặc không có dữ liệu để đo.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)-7s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

G3_THRESHOLD = 0.95
COVERAGE_MIN = 0.60
SHORT_ANSWER_TOKENS = 3
# Token xuất hiện ở hơn nửa số trang thì không mang thông tin phân biệt. Ngưỡng
# này là idf tương ứng với df = N/2, tính ra chứ không gõ tay.
UNINFORMATIVE_IDF = math.log(2.0)


def fold(text: str) -> str:
    """Bỏ dấu + hạ chữ, xử lý riêng đ/Đ (NFD không tách được hai chữ này)."""
    s = str(text or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def tokens_of(text: str) -> List[str]:
    """Token đã bỏ dấu. Giữ chữ số một kí tự ("6 giai đoạn" cần chữ "6")."""
    folded = re.sub(r"[^a-z0-9\s]+", " ", fold(text))
    return [t for t in folded.split() if len(t) >= 2 or t.isdigit()]


def build_idf(page_texts: Sequence[str]) -> Dict[str, float]:
    """IDF đo trên CHÍNH các trang của index — thay cho danh sách stopword gõ tay.

    Vì sao không dùng stopword: phép bỏ dấu (bắt buộc, vì OCR sai dấu) làm từ
    chức năng ĐỤNG với từ nội dung. Trên đúng corpus này: "khí" -> "khi",
    "đo"/"độ" -> "do", "lá" -> "la", "tai" (cái tai) -> "tai", "đá" -> "da",
    "nguyên tử" -> "tu", "cân" -> "can", "nở" -> "no", "băng" -> "bang". Một danh
    sách stopword trên dạng đã bỏ dấu sẽ **xoá chính những từ nội dung quan trọng
    nhất của sách KHTN**. IDF không có vấn đề đó: từ nào có mặt ở khắp nơi thì tự
    mang trọng số ~0, từ nào hiếm thì nặng — tự hiệu chỉnh theo corpus thật.
    """
    n_pages = len(page_texts)
    if n_pages == 0:
        return {}
    df: Counter = Counter()
    for text in page_texts:
        df.update(set(tokens_of(text)))
    return {tok: math.log((n_pages + 1) / (1 + count))
            for tok, count in df.items()}


def _weights(ground_truth: str, idf: Optional[Dict[str, float]]) -> Dict[str, float]:
    toks = set(tokens_of(ground_truth))
    if not toks:
        return {}
    if not idf:
        # Không có index để đo (test đơn vị) -> mọi token nặng bằng nhau.
        return {t: 1.0 for t in toks}
    # Token không có trong index nào = rất đặc trưng: nếu trang không chứa nó thì
    # đó là bằng chứng NGƯỢC, nên cho trọng số cao nhất có thể.
    unseen = max(idf.values()) if idf else 1.0
    return {t: idf.get(t, unseen) for t in toks}


def informative_tokens(
    ground_truth: str, idf: Optional[Dict[str, float]] = None
) -> List[str]:
    weights = _weights(ground_truth, idf)
    if not idf:
        return sorted(weights)
    return sorted(t for t, w in weights.items() if w >= UNINFORMATIVE_IDF)


def coverage(
    ground_truth: str, page_text: str, idf: Optional[Dict[str, float]] = None
) -> Tuple[float, int]:
    """Độ phủ có trọng số IDF, và số token MANG THÔNG TIN của đáp án."""
    weights = _weights(ground_truth, idf)
    if not weights:
        return 0.0, 0
    total = sum(weights.values())
    if total <= 0:
        return 0.0, 0
    page = set(tokens_of(page_text))
    hit = sum(w for tok, w in weights.items() if tok in page)
    informative = informative_tokens(ground_truth, idf)
    return hit / total, len(informative)


def contains_phrase(ground_truth: str, page_text: str) -> bool:
    """Cụm từ của đáp án có nằm NGUYÊN VĂN (đã bỏ dấu) trong trang không.

    Bằng chứng mạnh và không phụ thuộc IDF: OCR sai dấu ("nhiệt ké") vẫn khớp vì
    hai bên đều đã bỏ dấu, nhưng một trang chỉ nhắc "nhiệt độ" thì không khớp.
    """
    needle = " ".join(tokens_of(ground_truth))
    if not needle:
        return False
    return needle in " ".join(tokens_of(page_text))


def page_supports_answer(
    ground_truth: str,
    page_text: str,
    coverage_min: float,
    idf: Optional[Dict[str, float]] = None,
) -> Tuple[bool, float, int]:
    cov, n_informative = coverage(ground_truth, page_text, idf)

    if n_informative == 0:
        # Mọi token của đáp án đều có mặt ở khắp corpus (ví dụ "nhiệt kế" trong
        # một tập trang toàn nói về nhiệt). Độ phủ lúc này vô nghĩa, nên chỉ nhận
        # bằng chứng MẠNH: cụm từ xuất hiện nguyên văn trên trang.
        return contains_phrase(ground_truth, page_text), cov, 0

    if n_informative <= SHORT_ANSWER_TOKENS:
        # Đáp án ngắn ("6 giai đoạn"): trúng một phần là ngẫu nhiên, không phải
        # bằng chứng -> đòi CÓ ĐỦ mọi token đặc trưng, hoặc nguyên cụm từ.
        page = set(tokens_of(page_text))
        need = informative_tokens(ground_truth, idf)
        ok = all(t in page for t in need) or contains_phrase(
            ground_truth, page_text)
        return ok, cov, n_informative

    return cov >= coverage_min, cov, n_informative


# --- Đọc lại văn bản của một trang từ index ---------------------------------

class PageTextIndex:
    """Toàn văn đã index của mỗi (sách, trang in). Nạp MỘT lần rồi tra tại chỗ.

    Nạp cả collection trong một `get()` thay vì query từng trang: vừa nhanh hơn,
    vừa cho luôn tập trang để tính IDF.
    """

    def __init__(self, collection):
        got = collection.get(include=["documents", "metadatas"], limit=1_000_000)
        self._pages: Dict[Tuple[str, int], List[str]] = {}
        for doc, meta in zip(got.get("documents") or [],
                             got.get("metadatas") or []):
            meta = meta or {}
            source, page = meta.get("source"), meta.get("page")
            if source is None or page is None:
                continue
            self._pages.setdefault((str(source), int(page)), []).append(doc or "")

    def text_for(self, source: str, page: int) -> str:
        try:
            key = (str(source), int(page))
        except (TypeError, ValueError):
            return ""
        return "\n\n".join(self._pages.get(key, []))

    def page_texts(self) -> List[str]:
        return ["\n\n".join(v) for v in self._pages.values()]

    def sources(self) -> List[str]:
        return sorted({src for src, _ in self._pages})

    def n_pages(self) -> int:
        return len(self._pages)


# --- Ánh xạ nhãn sách hiển thị -> tên `source` trong metadata ----------------

def build_book_lookup(sources: Sequence[str]) -> Dict[str, str]:
    """`build_citations` trả về nhãn ĐỂ HIỂN THỊ, không phải `source` gốc.

    Muốn đọc lại văn bản của trang được trích thì phải map ngược nhãn đó về
    `source`. Map bằng `format_book_name` của chính module citations, không tự
    đoán quy tắc — nếu nhãn đổi thì map đổi theo.
    """
    from src.rag.citations import format_book_name

    return {format_book_name(s): s for s in sources}


JUDGE_PROMPT = """Bạn là người kiểm tra trích dẫn cho sách giáo khoa.

[CÂU HỎI]: {question}
[ĐÁP ÁN CHUẨN]: {ground_truth}
[TOÀN VĂN TRANG {page} CỦA {book}]:
{page_text}

Hỏi: nội dung trang trên có ĐỦ để rút ra đáp án chuẩn không? Không suy diễn ngoài
trang, không dùng kiến thức riêng. Nếu có, phải trích nguyên văn một đoạn của
trang làm bằng chứng.

CHỈ trả về JSON thuần:
{{"supported": true, "evidence": "trích nguyên văn từ trang"}}
hoặc
{{"supported": false, "evidence": ""}}
"""


def judge_page(llm, question: str, ground_truth: str, book: str, page,
               page_text: str) -> Optional[bool]:
    """LLM đọc trang và trả lời có/không. None nếu gọi lỗi (KHÔNG coi là 'không')."""
    prompt = JUDGE_PROMPT.format(
        question=question, ground_truth=ground_truth, book=book, page=page,
        page_text=page_text[:6000])
    try:
        resp = llm.invoke(prompt)
        raw = str(getattr(resp, "content", resp)).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-zA-Z]*", "", raw).strip().rstrip("`").strip()
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1])
        return bool(data.get("supported"))
    except Exception as exc:
        logger.warning("Judge lỗi: %s", exc)
        return None


def rerank_status() -> str:
    """Rerank có THẬT SỰ đang chạy hay không — in ra, không để nó âm thầm tắt.

    `RERANK_ENABLED=true` nhưng model chưa tải (hoặc `HF_HUB_OFFLINE=1`) thì
    `RerankedRetriever` chỉ log một `warning` mỗi truy vấn rồi rơi về xếp theo
    khoảng cách. Đo xong mà không biết mình đo cấu hình nào là báo cáo sai cấu
    hình — nên cổng G3 tự kiểm và in ra.
    """
    from src.config import RERANK_ENABLED, RERANK_MODEL

    if not RERANK_ENABLED:
        return "TẮT (RERANK_ENABLED=false)"
    try:
        from src.rag.reranker import get_reranker

        scores = get_reranker().score("thử", ["một đoạn văn bản thử"])
        if scores:
            return f"ĐANG CHẠY ({RERANK_MODEL})"
        return (f"BẬT nhưng KHÔNG CHẠY — {RERANK_MODEL} không cho điểm; "
                f"kết quả dưới đây là xếp theo khoảng cách, KHÔNG có cross-encoder")
    except Exception as exc:
        return (f"BẬT nhưng KHÔNG NẠP ĐƯỢC {RERANK_MODEL}: {str(exc)[:120]} "
                f"-> kết quả dưới đây KHÔNG có cross-encoder")


def load_testsets(testset_dir: Path, book: str = "") -> List[Dict]:
    rows = []
    for path in sorted(testset_dir.glob("*_testset.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if book and row.get("source_book") != book:
                    continue
                rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Cổng G3 — độ đúng của trang trích dẫn")
    ap.add_argument("--testset-dir", type=Path,
                    default=Path(__file__).resolve().parent / "testsets")
    ap.add_argument("--book", default="")
    ap.add_argument("--limit", type=int, default=0, help="0 = tất cả")
    ap.add_argument("--coverage-min", type=float, default=COVERAGE_MIN)
    ap.add_argument("--threshold", type=float, default=G3_THRESHOLD)
    ap.add_argument("--judge", action="store_true",
                    help="dùng LLM cứu các ca deterministic loại (và hiệu chỉnh ngưỡng)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows = load_testsets(args.testset_dir, args.book)
    if not rows:
        print(f"Không có bộ test nào trong {args.testset_dir}"
              f"{f' cho {args.book}' if args.book else ''}.\n"
              "Chạy `python src/test/generate_testsets.py` trước.")
        return 1
    if args.limit:
        rows = rows[:args.limit]

    from src.config import RETRIEVER_K
    from src.rag.citations import build_citations
    from src.rag.query_intent import is_image_only_query
    from src.rag.vectorstore import VectorDB

    print(f"Nạp text vector DB ({len(rows)} câu hỏi)...")
    db = VectorDB()
    n_chunks = db.db._collection.count()
    if n_chunks == 0:
        print("!! Collection text RỖNG — chưa chạy ETL. G3 không đo được gì.")
        return 1
    print(f"  {n_chunks} chunk trong index.")
    status = rerank_status()
    print(f"  rerank: {status}")

    # Cùng retriever mà HybridRetriever dùng cho nhánh text -> cùng text_docs.
    retriever = db.get_retriever({"k": RETRIEVER_K})
    index = PageTextIndex(db.db._collection)
    book_lookup = build_book_lookup(index.sources())
    # Trọng số token đo trên chính các trang đang có trong index (không dùng danh
    # sách stopword — xem build_idf để biết vì sao).
    idf = build_idf(index.page_texts())
    print(f"  {index.n_pages()} trang, {len(idf)} token khác nhau (IDF đo tại chỗ).")

    llm = None
    if args.judge:
        from src.test.eval_llm import config_help, get_eval_llm, is_configured
        if not is_configured():
            print(config_help())
            return 1
        llm = get_eval_llm(temperature=0.0)

    results = []
    buckets = Counter()
    judge_agree = Counter()
    short_answers = 0

    for i, row in enumerate(rows, 1):
        question = str(row["question"])
        ground_truth = str(row["ground_truth"])
        gold_book = str(row.get("source_book", ""))
        gold_page = row.get("source_page", "")

        if is_image_only_query(question):
            # Production sẽ không trả text_docs cho câu này -> không có citation.
            buckets["image_only_route"] += 1
            results.append({"question": question, "verdict": "image_only_route"})
            continue

        docs = retriever.invoke(question)
        citations = build_citations(docs)
        if not citations:
            buckets["no_citation"] += 1
            results.append({
                "question": question, "verdict": "no_citation",
                "gold_book": gold_book, "gold_page": gold_page,
            })
            continue

        checked = []
        supported_any = False
        for c in citations:
            source = book_lookup.get(c["book"])
            if source is None:
                # Nhãn hiển thị không map về `source` nào -> lỗi thật, phải ồn.
                raise RuntimeError(
                    f"nhãn sách '{c['book']}' không map về source nào trong index; "
                    f"đã có: {sorted(book_lookup)}")
            page_text = index.text_for(source, c["page"])
            ok, cov, n_tok = page_supports_answer(
                ground_truth, page_text, args.coverage_min, idf)

            judged = None
            if llm is not None and not ok:
                judged = judge_page(llm, question, ground_truth,
                                    c["book"], c["page"], page_text)
                if judged is not None:
                    judge_agree["det_no_judge_yes" if judged else "det_no_judge_no"] += 1

            final = ok or bool(judged)
            supported_any = supported_any or final
            checked.append({
                "book": source, "page": c["page"], "section": c["section"],
                "coverage": round(cov, 3), "informative_tokens": n_tok,
                "deterministic": ok, "judge": judged, "supported": final,
                "page_chars": len(page_text),
            })

        verdict = "ok" if supported_any else "cited_wrong"
        buckets[verdict] += 1
        # Đáp án chỉ 1-3 token nội dung ("nhiệt kế") có thể nằm trên rất nhiều
        # trang, nên một phán quyết "ok" dựa vào nó là bằng chứng YẾU. Đếm ra để
        # người đọc biết G3 đang tựa vào bao nhiêu ca như vậy.
        if checked and checked[0]["informative_tokens"] <= SHORT_ANSWER_TOKENS:
            short_answers += 1
        cited_gold = any(str(c["page"]) == str(gold_page)
                         and c["book"] == gold_book for c in checked)
        results.append({
            "question": question, "ground_truth": ground_truth,
            "gold_book": gold_book, "gold_page": gold_page,
            "verdict": verdict, "cited_gold_page": cited_gold,
            "citations": checked,
        })

        if args.verbose or verdict == "cited_wrong":
            mark = "OK " if verdict == "ok" else "SAI"
            print(f"  [{i}/{len(rows)}] {mark} vàng={gold_book} tr.{gold_page} "
                  f"| trích: " + ", ".join(
                      f"tr.{c['page']}(phủ {c['coverage']:.2f}"
                      + (f", judge={c['judge']}" if c["judge"] is not None else "")
                      + ")" for c in checked))
            if verdict == "cited_wrong":
                print(f"        Q: {question[:100]}")
                print(f"        Đáp án: {ground_truth[:100]}")

    measurable = buckets["ok"] + buckets["cited_wrong"]
    g3 = buckets["ok"] / measurable if measurable else 0.0

    print("\n" + "=" * 70)
    print(f"G3 = {g3:.4f}  ({buckets['ok']}/{measurable} câu CÓ trích dẫn mà trang "
          f"trích chứa được câu trả lời)")
    print(f"  ok           {buckets['ok']}")
    print(f"  cited_wrong  {buckets['cited_wrong']}")
    print(f"  no_citation  {buckets['no_citation']}   <-- NGOÀI phân số G3: đây là "
          f"lỗi recall, không phải lỗi citation")
    if buckets["image_only_route"]:
        print(f"  image_only   {buckets['image_only_route']}   <-- câu bị định "
              f"tuyến sang nhánh ảnh, production không trả text_docs")
    print(f"  tổng câu hỏi {len(rows)}")
    if short_answers:
        print(f"  trong đó {short_answers}/{measurable} câu có đáp án chỉ "
              f"<= {SHORT_ANSWER_TOKENS} token nội dung -> bằng chứng YẾU "
              f"(một cụm ngắn có thể nằm trên nhiều trang)")

    covs = [c["coverage"] for r in results for c in r.get("citations", [])]
    if covs:
        covs_sorted = sorted(covs)
        def q(p):
            return covs_sorted[min(len(covs_sorted) - 1, int(p * len(covs_sorted)))]
        print(f"\nPhân bố độ phủ token trên {len(covs)} (câu, trang được trích): "
              f"p10={q(0.10):.2f} p25={q(0.25):.2f} p50={q(0.50):.2f} "
              f"p75={q(0.75):.2f} p90={q(0.90):.2f}  (ngưỡng đang dùng "
              f"{args.coverage_min})")
    if judge_agree:
        print(f"\nĐồng thuận deterministic-vs-judge trên các ca deterministic LOẠI: "
              f"judge cứu {judge_agree['det_no_judge_yes']}, "
              f"judge cũng loại {judge_agree['det_no_judge_no']}"
              f"  -> ngưỡng {args.coverage_min} "
              f"{'CÓ THỂ quá chặt' if judge_agree['det_no_judge_yes'] else 'chưa thấy quá chặt'}")
    else:
        print("\n(chưa chạy --judge: ngưỡng độ phủ CHƯA được hiệu chỉnh — "
              "đừng báo cáo G3 như số chốt)")

    passed = measurable > 0 and g3 >= args.threshold
    print(f"\nG3 {'PASS' if passed else 'FAIL'} (ngưỡng {args.threshold})")

    if args.out:
        args.out.write_text(json.dumps({
            "g3": round(g3, 4),
            "rerank_status": status,
            "short_answer_verdicts": short_answers,
            "threshold": args.threshold,
            "coverage_min": args.coverage_min,
            "coverage_calibrated_by_judge": bool(judge_agree),
            "buckets": dict(buckets),
            "judge_agreement": dict(judge_agree),
            "n_questions": len(rows),
            "n_chunks_indexed": n_chunks,
            "results": results,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"-> {args.out}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
