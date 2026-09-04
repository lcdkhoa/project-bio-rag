"""Đánh giá hệ RAG (Qwen 2.5) đầu-cuối + LLM thứ 2 (Groq) chấm lại câu trả lời.

D-181 (2026-09-03, chỉ đạo CBHD, xem document/decision_log.html): bỏ hẳn 9 cột
IR/xếp hạng theo TỪNG QUYỂN (precision_page, recall_page, mrr_page, precision_book,
recall_book, mrr_book, retrieval_score, answer_score, overall_score) và mọi logic
tổng hợp/xếp hạng theo quyển. Precision/Recall/F1@K với K=3/5/10/20 trên 4 phương
pháp truy vấn (keyword/dense/truyền thống/đề xuất) nay sống hẳn trong
`src/test/retrieval_benchmark.py` (đã gộp thêm `recall_at_k.py`) — module này
KHÔNG còn tính số liệu truy xuất xác định nữa, tránh hai nơi cùng tính lại cùng
một thứ.

Luồng cho mỗi câu hỏi trong bộ test (MỘT file `src/test/testset/draft.csv`, D-182):
    1. SINH CÂU TRẢ LỜI: gọi đúng pipeline thật (HybridRetriever -> prompt ->
       Qwen 2.5 -> parser, y như API /api/chat).
    2. LLM THỨ 2 CHẤM LẠI: giám khảo Groq chấm câu trả lời của Qwen theo
       correctness / faithfulness / relevancy (1-5) so với đáp án chuẩn + context.
       Cách tính GIỮ NGUYÊN từ trước D-181 — chỉ đổi TRỤC tổng hợp bên dưới.

Trục tổng hợp = LOẠI câu hỏi (`loai`): văn bản / hình / ngoài-phạm-vi — KHÔNG
theo quyển/môn (CBHD: tách theo quyển làm vector DB "rời rạc").
    - "van_ban" / "hinh": xem `src/test/testset/draft.csv`.
    - "ngoai_pham_vi": 30 câu hỏi thuộc môn KHÁC (Sử/Địa/GDCD/Toán/Văn/Anh/...),
      không có trang vàng — `ground_truth` mô tả kỳ vọng hệ thống trả lời không
      biết/không có trong sách thay vì bịa (nguyên tắc 1).

Kết quả:
    - eval_result.csv : chi tiết từng câu (đã bỏ 9 cột IR).
    - eval_report.csv : tổng hợp theo LOẠI câu hỏi.
    - eval_report.md  : bảng dễ đọc theo LOẠI câu hỏi.

Chạy (sau khi bộ test đã người duyệt tay — `human_reviewed=true` trong
`src/test/testset/meta.json`):
    python -m src.test.run_eval
"""

import os
import sys
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
from src.test.llm_client import get_eval_llm, is_configured, config_help

load_dotenv()
logger = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("EVAL_LLM_MODEL", "(chưa cấu hình)")

# Ba loại câu hỏi hợp lệ theo cột `loai` của testset (D-181). Một giá trị
# thiếu/lạ KHÔNG được lặng lẽ gộp vào một trong ba loại này — xem
# `_loai_cau_hoi`.
LOAI_HOP_LE = ("van_ban", "hinh", "ngoai_pham_vi")
LOAI_KHONG_RO = "khong_ro"

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
    HybridRetriever -> ghép context -> prompt -> Qwen 2.5 -> parser. Với câu hỏi
    "ngoài phạm vi" (không có trang vàng) hay câu hỏi bị định tuyến CHỈ-CẦN-ẢNH
    (`is_image_only_query`, D-88), luồng này chạy y hệt — hệ thống PHẢI tự nhận ra
    không có ngữ cảnh phù hợp, không được bịa khi câu hỏi thuộc môn khác.
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


# 429 cua OpenRouter o day KHONG phai cap/ngay ma la "temporarily rate-limited
# upstream" - loi TAM THOI cua nha cung cap. Do duoc trong luot 231 cau ngay
# 2026-08-26: 2/231 cau mat diem giam khao chi vi khong he co mot lan thu lai
# nao. Mot o NaN trong cot quyet dinh chat luong dat hon vai giay cho.
JUDGE_RETRIES = 3
JUDGE_BACKOFF_SECONDS = (5, 20, 60)


def _la_loi_tam_thoi(exc: Exception) -> bool:
    """429 / 5xx / timeout / JSON hong = thu lai duoc. Sai API key thi thu lai vo ich."""
    if isinstance(exc, json.JSONDecodeError):
        return True
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
            # JSON hong o temperature=0.0 thi cung mot model se sinh lai y het
            # loi cu (deterministic) - phai xoay sang model KHAC trong pool thi
            # thu lai moi co y nghia. Khong co pool (chi 1 model) thi bo qua,
            # van thu lai sau backoff (khong hai, du khong chac giup).
            if isinstance(exc, json.JSONDecodeError) and hasattr(judge_llm, "force_rotate"):
                judge_llm.force_rotate()
            logger.warning("Judge lỗi tạm thời (lần %d/%d), chờ %ds: %s",
                           lan + 1, JUDGE_RETRIES, cho, exc)
            print(f"    judge lỗi tạm thời, thử lại sau {cho}s ({lan + 1}/{JUDGE_RETRIES})")
            time.sleep(cho)
    logger.warning("Judge lỗi: %s", loi_cuoi)
    return {"judge_correctness": float("nan"), "judge_faithfulness": float("nan"),
            "judge_relevancy": float("nan"), "judge_reasoning": f"LỖI: {loi_cuoi}"}


# Chỉ còn 3 cột LLM chấm — 9 cột IR/xếp hạng theo quyển đã bị bỏ (D-181).
NUM_COLS = ["judge_correctness", "judge_faithfulness", "judge_relevancy"]


def _loai_cau_hoi(value) -> str:
    """Chuẩn hoá một giá trị `loai` về 1 trong 3 loại hợp lệ.

    Giá trị thiếu/rỗng/lạ -> `khong_ro`, KHÔNG bị lặng lẽ gộp vào văn bản/hình/
    ngoài-phạm-vi (nguyên tắc 5: fail loudly, không đoán).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return LOAI_KHONG_RO
    v = str(value).strip().lower()
    return v if v in LOAI_HOP_LE else LOAI_KHONG_RO


def evaluate_all(csv_path: str, judge_llm) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    print(f"\n=== Đánh giá: {len(df)} câu ===")

    records = []
    for i, row in df.iterrows():
        q = str(row["question"])
        gt = str(row.get("ground_truth", ""))
        src_book = row.get("source_book")
        src_book = None if pd.isna(src_book) else str(src_book)
        src_page_raw = row.get("source_page")
        try:
            src_page = None if pd.isna(src_page_raw) else int(src_page_raw)
        except (TypeError, ValueError):
            src_page = None
        loai = _loai_cau_hoi(row.get("loai"))

        rag = get_answer_and_context(q)
        verdict = judge_answer(judge_llm, q, gt, "\n\n".join(rag["contexts"]), rag["answer"])

        retrieved_sources = "; ".join(
            f"{(m.get('source') or '?')}:p{m.get('page')}" for m in rag["metas"]
        )
        records.append({
            "question": q, "loai": loai, "source_book": src_book,
            "source_page": src_page, "retrieved": retrieved_sources,
            "rag_answer": rag["answer"], "ground_truth": gt, **verdict,
        })
        print(f"  [{i + 1:>3}/{len(df)}] loai={loai:<13} "
              f"correct={verdict['judge_correctness']:.0f}/5 "
              f"faithful={verdict['judge_faithfulness']:.0f}/5 "
              f"relevancy={verdict['judge_relevancy']:.0f}/5")

    return pd.DataFrame(records)


def aggregate_by_loai(all_records: pd.DataFrame) -> pd.DataFrame:
    """Tổng hợp theo LOẠI câu hỏi — copy nguyên văn evaluator.py, chỉ đổi tên
    cột nguon_cau_hoi -> loai (khớp schema draft.csv mới)."""
    cot_ra = ["loai_cau_hoi", "num_questions", *NUM_COLS]
    if all_records.empty:
        return pd.DataFrame(columns=cot_ra)

    df = all_records.copy()
    df["loai"] = df["loai"].map(_loai_cau_hoi)
    g = df.groupby("loai", dropna=False)
    out = g.agg(
        num_questions=("question", "count"),
        judge_correctness=("judge_correctness", "mean"),
        judge_faithfulness=("judge_faithfulness", "mean"),
        judge_relevancy=("judge_relevancy", "mean"),
    ).reset_index().rename(columns={"loai": "loai_cau_hoi"})
    for c in NUM_COLS:
        out[c] = out[c].round(4)

    thu_tu = {"van_ban": 0, "hinh": 1, "ngoai_pham_vi": 2, LOAI_KHONG_RO: 3}
    out["_thu_tu"] = out["loai_cau_hoi"].map(thu_tu).fillna(9)
    out = out.sort_values("_thu_tu").drop(columns="_thu_tu").reset_index(drop=True)
    return out[cot_ra]


TEN_LOAI_HIEN_THI = {
    "van_ban": "Văn bản",
    "hinh": "Hình",
    "ngoai_pham_vi": "Ngoài phạm vi",
    LOAI_KHONG_RO: "Không rõ loại",
}


if __name__ == "__main__":
    import argparse
    from src.test.testset_common import (DRAFT_CSV, META_JSON,
                                          duong_dan_output,
                                          require_human_reviewed)

    _ap = argparse.ArgumentParser(description="Đánh giá đầu-cuối, CÓ gọi LLM")
    _ap.add_argument("--testset-csv", default=str(DRAFT_CSV))
    _ap.add_argument("--allow-draft", action="store_true")
    _a = _ap.parse_args()

    require_human_reviewed(META_JSON, allow_draft=_a.allow_draft)

    if not is_configured():
        print(config_help())
        raise SystemExit(1)

    judge_llm = get_eval_llm(temperature=0.0)
    all_records = evaluate_all(_a.testset_csv, judge_llm)

    result_csv = duong_dan_output("eval_result.csv", _a.allow_draft)
    all_records.to_csv(result_csv, index=False, encoding="utf-8-sig")

    report = aggregate_by_loai(all_records)
    report_csv = duong_dan_output("eval_report.csv", _a.allow_draft)
    report_md = duong_dan_output("eval_report.md", _a.allow_draft)
    report.to_csv(report_csv, index=False, encoding="utf-8-sig")

    lines = ["# Báo cáo đánh giá RAG theo LOẠI câu hỏi\n",
             f"Tổng số câu: {len(all_records)} | "
             f"Judge: {os.getenv('EVAL_LLM_MODEL', '?')}\n",
             "## Tổng hợp theo loại câu hỏi\n",
             "| Loại | Số câu | Correct/5 | Faithful/5 | Relevancy/5 |",
             "|---|---|---|---|---|"]
    for _, r in report.iterrows():
        ten_hien_thi = TEN_LOAI_HIEN_THI.get(r["loai_cau_hoi"], r["loai_cau_hoi"])
        lines.append(
            f"| {ten_hien_thi} | {int(r['num_questions'])} | "
            f"{r['judge_correctness']:.2f} | {r['judge_faithfulness']:.2f} | "
            f"{r['judge_relevancy']:.2f} |")
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nĐã lưu: {result_csv}, {report_csv}, {report_md}")
    print("\n" + report.to_string(index=False))
