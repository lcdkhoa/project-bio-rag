"""Đánh giá hệ RAG (Qwen 2.5) theo từng bộ sách + LLM thứ 2 (Gemini) chấm lại.

Luồng cho mỗi câu hỏi trong từng bộ test:
    1. TRUY XUẤT: gọi đúng pipeline thật (HybridRetriever) -> lấy chunk text kèm
       metadata (source, page).
    2. SỐ LIỆU IR (xác định): đối chiếu metadata với (source_book, source_page)
       của câu hỏi -> Precision@k, Recall@k (hit@k), MRR (điểm rank).
       Tính cả mức page-level (nghiêm) và book-level (đo nhiễu chéo sách).
    3. SINH CÂU TRẢ LỜI: ghép context -> prompt -> Qwen 2.5 -> parser (y như API).
    4. LLM THỨ 2 CHẤM LẠI: Gemini 2.5 Flash chấm câu trả lời của Qwen theo
       correctness / faithfulness / relevancy (1-5) so với đáp án chuẩn + context.

Kết quả:
    - testsets/<book>_result.csv  : chi tiết từng câu.
    - evaluation_report.csv       : tổng hợp + XẾP HẠNG 12 sách.
    - evaluation_report.md        : bảng leaderboard dễ đọc.

Chạy (sau khi đã có testsets):
    python src/test/evaluator.py
"""

import os
import sys
import glob
import json
import re
import logging

# Cho phép import package `src`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd
from dotenv import load_dotenv

from src.app.dependencies import AppServices
from src.test.metrics import evaluate_retrieval
from src.test.eval_llm import get_eval_llm, is_configured, config_help

load_dotenv()
logger = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("EVAL_LLM_MODEL", "(chưa cấu hình)")
# Các mức k cho recall "thô" (top-k similarity, BỎ QUA relevance gate) — dùng để
# chứng minh: tăng k thì recall tăng. recall@<max> chính là "trần recall".
RAW_RECALL_KS = (3, 5, 10)

JUDGE_PROMPT = """Bạn là giám khảo chấm chất lượng câu trả lời của một trợ lý AI môn
Khoa học tự nhiên. Hãy chấm KHÁCH QUAN, dựa trên đáp án chuẩn và ngữ cảnh.

[CÂU HỎI]:
{question}

[ĐÁP ÁN CHUẨN (ground truth)]:
{ground_truth}

[NGỮ CẢNH HỆ THỐNG TRUY XUẤT ĐƯỢC]:
{context}

[CÂU TRẢ LỜI CỦA TRỢ LÝ (cần chấm)]:
{answer}

Chấm theo 3 tiêu chí, thang điểm 1-5 (5 là tốt nhất):
- correctness: câu trả lời có ĐÚNG so với đáp án chuẩn không.
- faithfulness: câu trả lời có BÁM SÁT ngữ cảnh, không bịa (hallucination) không.
- relevancy: có trả lời ĐÚNG TRỌNG TÂM câu hỏi không.

CHỈ trả JSON thuần (không markdown):
{{"correctness": <1-5>, "faithfulness": <1-5>, "relevancy": <1-5>, "reasoning": "<ngắn gọn>"}}
"""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def get_answer_and_context(question: str) -> dict:
    """Gọi hệ RAG Qwen 2.5 thật. Trả về answer, contexts, và metadata chunk.

    Tái sử dụng đúng pipeline của API /api/chat:
    HybridRetriever -> ghép context -> prompt -> Qwen 2.5 -> parser.
    """
    services = AppServices.get_instance()

    result = services.hybrid_retriever.search(question)
    text_docs = result.text_docs

    contexts = [d.page_content for d in text_docs if getattr(d, "page_content", None)]
    metas = [getattr(d, "metadata", {}) or {} for d in text_docs]

    if not contexts:
        answer = (
            "Mình tìm thấy hình ảnh liên quan trong cơ sở dữ liệu ảnh."
            if result.image_only_query
            else "Thông tin này không được đề cập trong sách giáo khoa."
        )
        return {"answer": answer, "contexts": contexts, "metas": metas}

    context_str = "\n\n".join(contexts)
    prompt = services.rag.prompt.format(context=context_str, question=question)
    try:
        raw = services.llm.invoke(prompt)
        answer = services.rag.answer_parser.parse(raw)
    except Exception as exc:
        logger.error("Qwen lỗi cho câu hỏi %r: %s", question, exc)
        answer = "Xin lỗi, đã xảy ra lỗi khi tạo câu trả lời."

    return {"answer": answer, "contexts": contexts, "metas": metas}


def raw_recall_at_ks(question: str, src_book: str, src_page: int, ks=RAW_RECALL_KS) -> dict:
    """Recall@k page-level cho nhiều mức k, dùng top-k similarity THÔ (bỏ qua gate).

    Lấy top-max(ks) một lần rồi cắt tiền tố để tính hit@3/5/10 → cho thấy recall
    tăng đơn điệu theo k. recall@<max> chính là 'trần recall' (embedding có tìm
    ra trang vàng không), tách bạch với recall production (bị gate cắt còn ~3).
    """
    from src.test.metrics import make_page_relevance
    services = AppServices.get_instance()
    max_k = max(ks)
    try:
        scored = services.hybrid_retriever.text_db.db.similarity_search_with_score(question, k=max_k)
    except Exception as exc:
        logger.warning("Raw recall lỗi: %s", exc)
        return {f"recall@{k}_raw": float("nan") for k in ks}

    is_rel = make_page_relevance(src_book, src_page)
    ordered_metas = [d.metadata or {} for d, _ in scored]
    out = {}
    for k in ks:
        out[f"recall@{k}_raw"] = 1.0 if any(is_rel(m) for m in ordered_metas[:k]) else 0.0
    return out


# 429 cua OpenRouter o day KHONG phai cap/ngay ma la "temporarily rate-limited
# upstream" - loi TAM THOI cua nha cung cap. Do duoc trong luot 231 cau ngay
# 2026-08-26: 2/231 cau mat diem giam khao chi vi khong he co mot lan thu lai
# nao. Mot o NaN trong cot quyet dinh chat luong dat hon vai giay cho.
JUDGE_RETRIES = 3
JUDGE_BACKOFF_SECONDS = (5, 20, 60)


def _la_loi_tam_thoi(exc: Exception) -> bool:
    """429 / 5xx / timeout = thu lai duoc. Sai API key thi thu lai vo ich."""
    msg = str(exc).lower()
    return any(t in msg for t in ("429", "rate", "timeout", "timed out",
                                  "500", "502", "503", "504", "overload"))


def judge_answer(judge_llm, question: str, ground_truth: str, context: str, answer: str) -> dict:
    import time
    loi_cuoi = None
    for lan in range(JUDGE_RETRIES):
        try:
            resp = judge_llm.invoke(JUDGE_PROMPT.format(
                question=question, ground_truth=ground_truth,
                context=(context or "(không có)")[:6000], answer=answer,
            ))
            data = _parse_json(resp.content if hasattr(resp, "content") else str(resp))
            return {
                "judge_correctness": float(data.get("correctness", 0)),
                "judge_faithfulness": float(data.get("faithfulness", 0)),
                "judge_relevancy": float(data.get("relevancy", 0)),
                "judge_reasoning": str(data.get("reasoning", "")).strip(),
            }
        except Exception as exc:
            loi_cuoi = exc
            if lan == JUDGE_RETRIES - 1 or not _la_loi_tam_thoi(exc):
                break
            cho = JUDGE_BACKOFF_SECONDS[min(lan, len(JUDGE_BACKOFF_SECONDS) - 1)]
            logger.warning("Judge lỗi tạm thời (lần %d/%d), chờ %ds: %s",
                           lan + 1, JUDGE_RETRIES, cho, exc)
            print(f"    judge lỗi tạm thời, thử lại sau {cho}s ({lan + 1}/{JUDGE_RETRIES})")
            time.sleep(cho)
    logger.warning("Judge lỗi: %s", loi_cuoi)
    return {"judge_correctness": float("nan"), "judge_faithfulness": float("nan"),
            "judge_relevancy": float("nan"), "judge_reasoning": f"LỖI: {loi_cuoi}"}


NUM_COLS = [
    "precision_page", "recall_page", "mrr_page",
    "precision_book", "recall_book", "mrr_book",
    *[f"recall@{k}_raw" for k in RAW_RECALL_KS],
    "judge_correctness", "judge_faithfulness", "judge_relevancy",
]


def result_path_for(testset_csv: str) -> str:
    return testset_csv.replace("_testset.csv", "_result.csv")


def book_of(testset_csv: str) -> str:
    return os.path.basename(testset_csv).replace("_testset.csv", "")


def summarize_result(book: str, res_df, luot_chay: str) -> dict:
    """Tong hop mot quyen tu bang ket qua.

    `luot_chay` ghi ro so nay do o LUOT NAO: "moi" = do trong lan chay nay,
    "da_co" = doc lai tu `*_result.csv` co san. Khong duoc tron hai loai ma
    khong noi ra (nguyen tac 5: khong im lang).
    """
    summary = {"book": book, "num_questions": len(res_df), "luot_chay": luot_chay}
    for c in NUM_COLS:
        summary[c] = round(res_df[c].mean(skipna=True), 4) if c in res_df.columns else float("nan")
    return summary


def chon_testsets(csv_files, books=None, bo_qua_da_co=False):
    """Loc danh sach bo test theo `--book` / `--bo-qua-da-co`.

    Tra ve (can_chay, bo_qua). Ten quyen khong khop thi NEM ValueError kem
    danh sach that (D-84: mot co bi bo qua im lang dat hon mot loi on ao).
    """
    co_that = [book_of(p) for p in csv_files]
    if books:
        thieu = [b for b in books if b not in co_that]
        if thieu:
            raise ValueError(
                "Khong co bo test cho: " + ", ".join(thieu)
                + " | 12 quyen that su co: " + ", ".join(co_that)
            )
        csv_files = [p for p in csv_files if book_of(p) in set(books)]
    can_chay, bo_qua = [], []
    for p in csv_files:
        if bo_qua_da_co and os.path.exists(result_path_for(p)):
            bo_qua.append(p)
        else:
            can_chay.append(p)
    return can_chay, bo_qua


def evaluate_book(csv_path: str, judge_llm) -> dict:
    df = pd.read_csv(csv_path)
    book = os.path.basename(csv_path).replace("_testset.csv", "")
    print(f"\n=== Đánh giá: {book} ({len(df)} câu) ===")

    records = []
    for i, row in df.iterrows():
        q = str(row["question"])
        gt = str(row.get("ground_truth", ""))
        src_book = str(row["source_book"])
        src_page = int(row["source_page"])

        rag = get_answer_and_context(q)
        ir = evaluate_retrieval(rag["metas"], src_book, src_page)
        raw_recalls = raw_recall_at_ks(q, src_book, src_page)
        verdict = judge_answer(judge_llm, q, gt, "\n\n".join(rag["contexts"]), rag["answer"])

        retrieved_sources = "; ".join(
            f"{(m.get('source') or '?')}:p{m.get('page')}" for m in rag["metas"]
        )
        records.append({
            "question": q,
            "source_book": src_book,
            "source_page": src_page,
            **ir,
            **raw_recalls,
            "retrieved": retrieved_sources,
            "rag_answer": rag["answer"],
            "ground_truth": gt,
            **verdict,
        })
        print(f"  [{i + 1:>2}/{len(df)}] P_page={ir['precision_page']:.2f} "
              f"R_page={ir['recall_page']:.0f} MRR={ir['mrr_page']:.2f} "
              f"correct={verdict['judge_correctness']:.0f}/5")

    res_df = pd.DataFrame(records)
    res_df.to_csv(result_path_for(csv_path), index=False, encoding="utf-8-sig")
    return summarize_result(book, res_df, luot_chay="moi")


def run_evaluation(testsets_dir: str, report_csv: str, report_md: str,
                   books=None, bo_qua_da_co: bool = False):
    csv_files = sorted(glob.glob(os.path.join(testsets_dir, "*_testset.csv")))
    if not csv_files:
        # Thoát KHÁC 0: từ 2026-08-24 bộ test 4 quyển cũ đã bị chuyển vào
        # `_archive_4books_kntt_offset_minus1/` (gold key theo offset −1, vô
        # hiệu trên index mới), nên "không có bộ test" là trạng thái BÌNH
        # THƯỜNG của một bản clone. Trả None ở đây cho exit code 0, tức một
        # script nối lệnh sẽ tưởng là đã đo xong — cùng loại im lặng đã vá ở
        # `main.py` (D-68).
        print("Không tìm thấy bộ test. Chạy generate_testsets.py trước.")
        return 2

    try:
        can_chay, bo_qua = chon_testsets(csv_files, books, bo_qua_da_co)
    except ValueError as exc:
        print(str(exc))
        return 2
    if bo_qua:
        print("Bỏ qua (đã có *_result.csv): " + ", ".join(book_of(p) for p in bo_qua))
    if not can_chay:
        print("Không còn quyển nào cần chạy.")

    judge_llm = get_eval_llm(temperature=0.0) if can_chay else None

    summaries_by_book = {}
    for csv_path in can_chay:
        try:
            s_book = evaluate_book(csv_path, judge_llm)
            summaries_by_book[s_book["book"]] = s_book
        except Exception as exc:
            import traceback
            print(f"Lỗi khi đánh giá {csv_path}: {exc}")
            traceback.print_exc()

    # Đọc lại kết quả CŨ cho những quyển không chạy ở lượt này, để bảng xếp hạng
    # phủ đủ 12 quyển thay vì im lặng chỉ báo cáo phần vừa chạy. Quyển không có
    # kết quả nào thì bị NÊU TÊN ra, không bị bỏ qua lặng lẽ.
    chua_do = []
    for csv_path in csv_files:
        b = book_of(csv_path)
        if b in summaries_by_book:
            continue
        rp = result_path_for(csv_path)
        if os.path.exists(rp):
            summaries_by_book[b] = summarize_result(
                b, pd.read_csv(rp, encoding="utf-8-sig"), luot_chay="da_co")
        else:
            chua_do.append(b)

    summaries = [summaries_by_book[book_of(p)] for p in csv_files
                 if book_of(p) in summaries_by_book]
    if chua_do:
        print("CHƯA CÓ SỐ (không có *_result.csv): " + ", ".join(chua_do))
    if not summaries:
        return 2

    report = pd.DataFrame(summaries)
    # Điểm tổng hợp để XẾP HẠNG: 50% chất lượng truy xuất + 50% chất lượng trả lời.
    report["retrieval_score"] = report[["recall_page", "mrr_page", "precision_page"]].mean(axis=1)
    report["answer_score"] = (
        report[["judge_correctness", "judge_faithfulness", "judge_relevancy"]].mean(axis=1) / 5.0
    )
    report["overall_score"] = (report["retrieval_score"] + report["answer_score"]) / 2.0
    report = report.sort_values("overall_score", ascending=False).reset_index(drop=True)
    report.insert(0, "rank", report.index + 1)
    report.to_csv(report_csv, index=False, encoding="utf-8-sig")

    # Bảng leaderboard markdown.
    lines = [
        "# Báo cáo đánh giá RAG theo từng bộ sách\n",
        f"Tổng số bộ sách: {len(report)}/{len(csv_files)} | "
        f"Tổng số câu: {int(report['num_questions'].sum())} | "
        f"Judge: {os.getenv('EVAL_LLM_MODEL', '?')} | "
        f"Số câu/sách: {int(report['num_questions'].mean())}\n",
        ("- Đo ở lượt NÀY: " + ", ".join(
            r["book"] for r in summaries if r["luot_chay"] == "moi") + "\n") if any(
            r["luot_chay"] == "moi" for r in summaries) else "",
        ("- Lấy từ `*_result.csv` CÓ SẴN của lượt trước: " + ", ".join(
            r["book"] for r in summaries if r["luot_chay"] == "da_co") + "\n") if any(
            r["luot_chay"] == "da_co" for r in summaries) else "",
        ("- **CHƯA ĐO**: " + ", ".join(chua_do) + "\n") if chua_do else "",
        "## Xếp hạng tổng thể\n",
        "| Hạng | Sách | Overall | Recall@k(page) | MRR(page) | Precision(page) | "
        "Correct/5 | Faithful/5 | Relevancy/5 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in report.iterrows():
        lines.append(
            f"| {int(r['rank'])} | {r['book']} | {r['overall_score']:.3f} | "
            f"{r['recall_page']:.2f} | {r['mrr_page']:.2f} | {r['precision_page']:.2f} | "
            f"{r['judge_correctness']:.2f} | {r['judge_faithfulness']:.2f} | {r['judge_relevancy']:.2f} |"
        )

    # Bảng recall@k: chứng minh tăng k thì recall tăng (top-k thô, bỏ qua gate).
    raw_cols = [f"recall@{k}_raw" for k in RAW_RECALL_KS]
    k_headers = " | ".join(f"Recall@{k}" for k in RAW_RECALL_KS)
    lines += [
        "\n## Recall@k tăng theo k (top-k thô, bỏ qua relevance gate)\n",
        "Cho thấy embedding tìm được trang vàng ở mức nào; tăng k thì recall tăng đơn điệu. "
        f"Recall@{max(RAW_RECALL_KS)} là 'trần recall'. So với **Recall(prod)** (chỉ ~3 chunk sau gate) "
        "để thấy nút thắt nằm ở khâu gate/cắt-k, không phải embedding.\n",
        f"| Sách | {k_headers} | Recall(prod) |",
        "|---|" + "---|" * (len(RAW_RECALL_KS) + 1),
    ]
    for _, r in report.iterrows():
        cells = " | ".join(f"{r[c]:.2f}" for c in raw_cols)
        lines.append(f"| {r['book']} | {cells} | {r['recall_page']:.2f} |")
    # Dòng trung bình toàn bộ sách.
    avg_cells = " | ".join(f"{report[c].mean():.2f}" for c in raw_cols)
    lines.append(f"| **TRUNG BÌNH** | {avg_cells} | {report['recall_page'].mean():.2f} |")

    lines += [
        "\n## Ghi chú số liệu",
        "- **Recall@k(page)** = hit@k: tỷ lệ câu hỏi mà hệ truy xuất đúng trang nguồn (top-k thực tế).",
        "- **MRR(page)** = điểm rank: trung bình 1/thứ-hạng của chunk đúng đầu tiên.",
        "- **Precision(page)** = tỷ lệ chunk truy xuất là đúng trang nguồn.",
        f"- **Recall@{RAW_RECALL_KS}** (top-k thô) đo khả năng embedding tìm thấy trang vàng; "
        "**Recall(prod)** là recall thực tế sau relevance gate (~3 chunk). Khoảng cách giữa hai cái "
        "định lượng phần recall mất đi do khâu rank/cắt-k.",
        "- **Correct/Faithful/Relevancy** do LLM thứ 2 chấm lại câu trả lời của Qwen 2.5, thang 1-5.",
        "- `overall_score = (retrieval_score + answer_score)/2`, dùng để xếp hạng.",
    ]
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nĐã lưu báo cáo: {report_csv}")
    print(f"Đã lưu leaderboard: {report_md}")
    print("\n" + report[["rank", "book", "overall_score", "recall_page",
                          "mrr_page", "judge_correctness"]].to_string(index=False))


if __name__ == "__main__":
    import argparse
    base = os.path.dirname(__file__)
    _ap = argparse.ArgumentParser(description="Đánh giá đầu-cuối, CÓ gọi LLM")
    _ap.add_argument("--testset-dir", default=os.path.join(base, "testsets"),
                     help="mặc định src/test/testsets; dùng src/test/testsets_240 "
                          "cho bộ 240 câu")
    _ap.add_argument("--hau-to", default="",
                     help="hậu tố tên file báo cáo, ví dụ _240 -> "
                          "evaluation_report_240.csv (đừng ghi đè số cũ)")
    _ap.add_argument("--book", action="append", default=None,
                     help="chỉ chạy quyển này (khớp CHÍNH XÁC tên bộ test); lặp lại "
                          "được. Tên không khớp -> thoát 2")
    _ap.add_argument("--bo-qua-da-co", action="store_true",
                     help="bỏ qua quyển đã có *_result.csv (chạy tiếp lượt dở dang)")
    _a = _ap.parse_args()
    TESTSETS_DIR = _a.testset_dir
    REPORT_CSV = os.path.join(base, f"evaluation_report{_a.hau_to}.csv")
    REPORT_MD = os.path.join(base, f"evaluation_report{_a.hau_to}.md")

    # Thiếu cấu hình LLM cũng phải thoát khác 0: nó là "chưa đo được", không
    # phải "đo xong".
    if not is_configured():
        print(config_help())
        raise SystemExit(1)
    raise SystemExit(run_evaluation(TESTSETS_DIR, REPORT_CSV, REPORT_MD,
                                    books=_a.book, bo_qua_da_co=_a.bo_qua_da_co) or 0)
