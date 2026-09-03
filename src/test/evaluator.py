"""Đánh giá hệ RAG (Qwen 2.5) đầu-cuối + LLM thứ 2 (Groq) chấm lại câu trả lời.

D-181 (2026-09-03, chỉ đạo CBHD, xem document/decision_log.html): bỏ hẳn 9 cột
IR/xếp hạng theo TỪNG QUYỂN (precision_page, recall_page, mrr_page, precision_book,
recall_book, mrr_book, retrieval_score, answer_score, overall_score) và mọi logic
tổng hợp/xếp hạng theo quyển. Precision/Recall/F1@K với K=3/5/10/20 trên 4 phương
pháp truy vấn (keyword/dense/truyền thống/đề xuất) nay sống hẳn trong
`src/test/ablation.py` (đã gộp thêm `recall_at_k.py`) — module này KHÔNG còn tính
số liệu truy xuất xác định nữa, tránh hai nơi cùng tính lại cùng một thứ.

Luồng cho mỗi câu hỏi trong từng bộ test:
    1. SINH CÂU TRẢ LỜI: gọi đúng pipeline thật (HybridRetriever -> prompt ->
       Qwen 2.5 -> parser, y như API /api/chat).
    2. LLM THỨ 2 CHẤM LẠI: giám khảo Groq chấm câu trả lời của Qwen theo
       correctness / faithfulness / relevancy (1-5) so với đáp án chuẩn + context.
       Cách tính GIỮ NGUYÊN từ trước D-181 — chỉ đổi TRỤC tổng hợp bên dưới.

Trục tổng hợp = LOẠI câu hỏi (`nguon_cau_hoi`): văn bản / hình / ngoài-phạm-vi —
KHÔNG theo quyển/môn (CBHD: tách theo quyển làm vector DB "rời rạc").
    - "van_ban" / "hinh": xem `src/test/testsets_240/`.
    - "ngoai_pham_vi": 30 câu hỏi thuộc môn KHÁC (Sử/Địa/GDCD/Toán/Văn/Anh/...),
      không có trang vàng — `ground_truth` mô tả kỳ vọng hệ thống trả lời không
      biết/không có trong sách thay vì bịa (nguyên tắc 1).

Kết quả:
    - <testset>_result.csv        : chi tiết từng câu (đã bỏ 9 cột IR).
    - evaluation_report<hậu tố>.csv : tổng hợp theo LOẠI câu hỏi.
    - evaluation_report<hậu tố>.md  : bảng dễ đọc theo LOẠI câu hỏi.

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
from src.test.eval_llm import get_eval_llm, is_configured, config_help

load_dotenv()
logger = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("EVAL_LLM_MODEL", "(chưa cấu hình)")

# Ba loại câu hỏi hợp lệ theo cột `nguon_cau_hoi` của testset (D-181). Một giá
# trị thiếu/lạ KHÔNG được lặng lẽ gộp vào một trong ba loại này — xem
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
    """Chuẩn hoá một giá trị `nguon_cau_hoi` về 1 trong 3 loại hợp lệ.

    Giá trị thiếu/rỗng/lạ -> `khong_ro`, KHÔNG bị lặng lẽ gộp vào văn bản/hình/
    ngoài-phạm-vi (nguyên tắc 5: fail loudly, không đoán). Đây là chỗ mọi
    *_result.csv CŨ (trước D-181, không có cột `nguon_cau_hoi`) sẽ rơi vào, cho
    tới khi được chạy lại.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return LOAI_KHONG_RO
    v = str(value).strip().lower()
    return v if v in LOAI_HOP_LE else LOAI_KHONG_RO


def result_path_for(testset_csv: str) -> str:
    return testset_csv.replace("_testset.csv", "_result.csv")


def book_of(testset_csv: str) -> str:
    return os.path.basename(testset_csv).replace("_testset.csv", "")


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


def evaluate_book(csv_path: str, judge_llm) -> pd.DataFrame:
    """Chạy RAG + giám khảo cho một tệp testset, trả DataFrame KẾT QUẢ TỪNG CÂU.

    Không còn tổng hợp/xếp hạng theo quyển ở đây (D-181) — chỉ ghi kết quả từng
    câu ra `<testset>_result.csv`; việc gộp theo LOẠI câu hỏi làm ở
    `aggregate_by_loai`, sau khi đã đọc lại TẤT CẢ các tệp *_result.csv.
    """
    df = pd.read_csv(csv_path)
    ten = book_of(csv_path)
    print(f"\n=== Đánh giá: {ten} ({len(df)} câu) ===")

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
            # Câu "ngoài phạm vi" (D-181) không có trang vàng — cố ép int một
            # ô rỗng/NaN sẽ ném, nên giữ None thay vì đoán số trang.
            src_page = None
        loai = _loai_cau_hoi(row.get("nguon_cau_hoi"))

        rag = get_answer_and_context(q)
        verdict = judge_answer(judge_llm, q, gt, "\n\n".join(rag["contexts"]), rag["answer"])

        retrieved_sources = "; ".join(
            f"{(m.get('source') or '?')}:p{m.get('page')}" for m in rag["metas"]
        )
        records.append({
            "question": q,
            "nguon_cau_hoi": loai,
            "source_book": src_book,
            "source_page": src_page,
            "retrieved": retrieved_sources,
            "rag_answer": rag["answer"],
            "ground_truth": gt,
            **verdict,
        })
        print(f"  [{i + 1:>2}/{len(df)}] loai={loai:<13} "
              f"correct={verdict['judge_correctness']:.0f}/5 "
              f"faithful={verdict['judge_faithfulness']:.0f}/5 "
              f"relevancy={verdict['judge_relevancy']:.0f}/5")

    res_df = pd.DataFrame(records)
    res_df.to_csv(result_path_for(csv_path), index=False, encoding="utf-8-sig")
    return res_df


def _doc_ket_qua_cu(csv_path: str) -> pd.DataFrame:
    """Đọc `<testset>_result.csv` có sẵn (không chạy lại lượt này).

    Bản CŨ (trước D-181) không có cột `nguon_cau_hoi` — khôi phục nó bằng cách
    nối lại với chính testset CSV theo `question` (nguồn sự thật của nhãn loại
    câu hỏi), thay vì để mọi câu cũ rơi hết vào `khong_ro` một cách oan uổng.
    Câu hỏi trùng chữ trong cùng testset (hiếm) thì giữ khớp ĐẦU TIÊN — không
    nhân bản hàng.
    """
    rp = result_path_for(csv_path)
    res = pd.read_csv(rp, encoding="utf-8-sig")
    if "nguon_cau_hoi" not in res.columns:
        try:
            ts = pd.read_csv(csv_path)[["question", "nguon_cau_hoi"]]
            ts = ts.drop_duplicates(subset="question", keep="first")
            res = res.merge(ts, on="question", how="left")
        except Exception as exc:
            logger.warning("Không khôi phục được nguon_cau_hoi cho %s: %s", rp, exc)
            res["nguon_cau_hoi"] = None
    return res


def aggregate_by_loai(all_records: pd.DataFrame) -> pd.DataFrame:
    """Tổng hợp theo LOẠI câu hỏi (văn bản/hình/ngoài-phạm-vi) — trục do CBHD chỉ
    định (D-181), thay cho xếp hạng theo quyển.

    3 chỉ số LLM chấm GIỮ NGUYÊN cách tính (mean, skipna) — chỉ đổi trục gộp.
    Loại `khong_ro` (thiếu/lạ) được báo cáo NHƯ MỘT NHÓM RIÊNG, không bị trộn
    vào văn bản/hình/ngoài-phạm-vi.
    """
    cot_ra = ["loai_cau_hoi", "num_questions", *NUM_COLS]
    if all_records.empty:
        return pd.DataFrame(columns=cot_ra)

    df = all_records.copy()
    df["nguon_cau_hoi"] = df["nguon_cau_hoi"].map(_loai_cau_hoi)
    g = df.groupby("nguon_cau_hoi", dropna=False)
    out = g.agg(
        num_questions=("question", "count"),
        judge_correctness=("judge_correctness", "mean"),
        judge_faithfulness=("judge_faithfulness", "mean"),
        judge_relevancy=("judge_relevancy", "mean"),
    ).reset_index().rename(columns={"nguon_cau_hoi": "loai_cau_hoi"})
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
    LOAI_KHONG_RO: "Không rõ loại (dữ liệu cũ trước D-181)",
}


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

    ok_books = set()
    for csv_path in can_chay:
        try:
            evaluate_book(csv_path, judge_llm)
            ok_books.add(book_of(csv_path))
        except Exception as exc:
            import traceback
            print(f"Lỗi khi đánh giá {csv_path}: {exc}")
            traceback.print_exc()

    # Đọc lại TẤT CẢ *_result.csv hiện có (vừa chạy + có sẵn từ lượt trước) để
    # gộp theo LOẠI câu hỏi trên toàn bộ dữ liệu, không chỉ phần vừa chạy. Tệp
    # nào không có *_result.csv nào cả thì bị NÊU TÊN, không bị bỏ qua lặng lẽ.
    frames = []
    chua_do = []
    luot_theo_ten = {}
    for csv_path in csv_files:
        ten = book_of(csv_path)
        if os.path.exists(result_path_for(csv_path)):
            df_r = _doc_ket_qua_cu(csv_path)
            luot = "moi" if ten in ok_books else "da_co"
            df_r["_ten_testset"] = ten
            frames.append(df_r)
            luot_theo_ten[ten] = luot
        else:
            chua_do.append(ten)
    if chua_do:
        print("CHƯA CÓ SỐ (không có *_result.csv): " + ", ".join(chua_do))
    if not frames:
        return 2

    tat_ca = pd.concat(frames, ignore_index=True, sort=False)
    report = aggregate_by_loai(tat_ca)
    report.to_csv(report_csv, index=False, encoding="utf-8-sig")

    tong_cau = int(tat_ca.shape[0])
    lines = [
        "# Báo cáo đánh giá RAG theo LOẠI câu hỏi (D-181)\n",
        f"Tổng số câu: {tong_cau} | Judge: {os.getenv('EVAL_LLM_MODEL', '?')}\n",
        ("- Tệp đo ở lượt NÀY: " + ", ".join(sorted(ok_books)) + "\n") if ok_books else "",
        ("- Tệp lấy từ *_result.csv CÓ SẴN: " + ", ".join(
            sorted(t for t, l in luot_theo_ten.items() if l == "da_co")) + "\n")
            if any(l == "da_co" for l in luot_theo_ten.values()) else "",
        ("- **CHƯA ĐO**: " + ", ".join(chua_do) + "\n") if chua_do else "",
        "## Tổng hợp theo loại câu hỏi\n",
        "| Loại | Số câu | Correct/5 | Faithful/5 | Relevancy/5 |",
        "|---|---|---|---|---|",
    ]
    for _, r in report.iterrows():
        ten_hien_thi = TEN_LOAI_HIEN_THI.get(r["loai_cau_hoi"], r["loai_cau_hoi"])
        lines.append(
            f"| {ten_hien_thi} | {int(r['num_questions'])} | "
            f"{r['judge_correctness']:.2f} | {r['judge_faithfulness']:.2f} | "
            f"{r['judge_relevancy']:.2f} |"
        )
    lines += [
        "\n## Ghi chú số liệu",
        "- Trục tổng hợp là LOẠI câu hỏi (văn bản/hình/ngoài-phạm-vi), KHÔNG theo "
        "quyển/môn (CBHD, D-181) — bỏ 9 cột IR + xếp hạng theo quyển "
        "(precision/recall/mrr page & book, retrieval_score, answer_score, "
        "overall_score). Precision/Recall/F1@K (K=3/5/10/20) theo 4 phương pháp "
        "truy vấn (keyword/dense/truyền thống/đề xuất) tính riêng trong `ablation.py`.",
        "- Nhóm **Hình**: câu hỏi bị `is_image_only_query()` định tuyến bỏ qua "
        "truy xuất văn bản theo đúng thiết kế (D-88) — không phải lỗi.",
        "- Nhóm **Ngoài phạm vi**: không có trang vàng (`source_page` trống) — 30 "
        "câu thuộc môn KHÁC (Sử/Địa/GDCD/Toán/Văn/Anh/...), không phải câu KHTN "
        "thiếu nội dung. `ground_truth` mô tả kỳ vọng hệ thống trả lời không biết/"
        "không có trong sách; 3 chỉ số giám khảo đo GIÁN TIẾP việc từ chối đúng "
        "hay không (không có chỉ số riêng cho việc này — quyết định D-181).",
        "- Nhóm **Không rõ loại**: `*_result.csv` từ TRƯỚC D-181 không khôi phục "
        "được `nguon_cau_hoi` (testset gốc không còn/câu hỏi không khớp) — chạy "
        "lại tệp đó để có nhãn đúng.",
        "- **Correct/Faithful/Relevancy** do LLM thứ 2 chấm lại câu trả lời, thang "
        "1-5 — cách tính GIỮ NGUYÊN từ trước D-181.",
    ]
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nĐã lưu báo cáo: {report_csv}")
    print(f"Đã lưu leaderboard: {report_md}")
    print("\n" + report.to_string(index=False))


if __name__ == "__main__":
    import argparse
    base = os.path.dirname(__file__)
    _ap = argparse.ArgumentParser(description="Đánh giá đầu-cuối, CÓ gọi LLM")
    _ap.add_argument("--testset-dir", default=os.path.join(base, "testsets"),
                     help="mặc định src/test/testsets; dùng src/test/testsets_240 "
                          "cho bộ 240 câu (+30 ngoài-phạm-vi nếu có, D-181)")
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
