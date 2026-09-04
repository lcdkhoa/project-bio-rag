# -*- coding: utf-8 -*-
"""Sinh bộ test 240 câu bằng lấy mẫu ngẫu nhiên trên toàn corpus (D-182).

Thay thế toàn bộ pipeline cũ (generate_testsets.py -> build_testset_240.py ->
build_image_questions.py, D-181 và trước đó): KHÔNG còn ràng buộc "đều theo
quyển" — mỗi câu văn bản/hình được rút ngẫu nhiên từ MỘT chunk/MỘT ảnh cụ thể
trong index, không quan tâm chunk/ảnh đó thuộc quyển nào. Xem thiết kế đầy đủ
(đã qua 4 lượt phản biện) ở
`document/specs/2026-09-03-eval-rebuild-design.md` mục 3.1.

Ba nhóm câu, tỉ lệ KHÔNG cố định (tính từ kích thước thật của index tại thời
điểm chạy, xem `_tinh_n_moi_nhom`):
    - van_ban: rút 1 chunk `biology_text`, LLM soạn câu hỏi bám sát nội dung.
    - hinh: rút 1 doc `biology_image_metadata`, LLM soạn câu hỏi về hình.
    - ngoai_pham_vi: chọn ngẫu nhiên 1 môn học KHÁC (Sử/Địa/...), LLM soạn câu
      hỏi kiến thức phổ thông của môn đó — hệ thống PHẢI trả lời "không biết"
      thay vì bịa (nguyên tắc 1).

Bắt buộc người duyệt tay trước khi coi bộ test là chính thức — `run_eval.py`/
`retrieval_benchmark.py` raise nếu `meta.json` chưa `human_reviewed: true`
(xem `src/test/testset_common.py::require_human_reviewed`).

Chạy:
    python -m src.test.build_testset                       # sinh nháp, seed 42
    python -m src.test.build_testset --n 240 --n-ngoai-pham-vi 30 --seed 42
    python -m src.test.build_testset --mark-reviewed        # xác nhận ĐÃ duyệt tay
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd
from dotenv import load_dotenv

from src.config import PERSIST_DIR, TEXT_COLLECTION_NAME, IMAGE_METADATA_COLLECTION_NAME
from src.test.llm_client import get_eval_llm, is_configured, config_help

load_dotenv()
logger = logging.getLogger(__name__)

OUT_DIR = Path(__file__).resolve().parent / "testset"
DRAFT_CSV = OUT_DIR / "draft.csv"
META_JSON = OUT_DIR / "meta.json"

MIN_CHUNK_CHARS = 200  # tham khảo CHUNK_SIZE=400, không phải số đo mới
CIRCUIT_BREAKER_WINDOW = 20
CIRCUIT_BREAKER_MAX_ERROR_RATE = 0.30

MON_NGOAI_PHAM_VI = [
    "Lịch sử", "Địa lý", "Giáo dục công dân", "Toán", "Ngữ văn",
    "Tiếng Anh", "Tin học", "Thể dục", "Âm nhạc", "Mỹ thuật",
]

GEN_PROMPT_VAN_BAN = """Bạn đang soạn MỘT câu hỏi kiểm tra cho học sinh THCS dựa
trên đúng đoạn văn bản dưới đây (trích từ sách giáo khoa Khoa học tự nhiên).

[ĐOẠN VĂN BẢN]:
{doan}

Yêu cầu:
- Soạn ĐÚNG MỘT câu hỏi tiếng Việt tự nhiên mà câu trả lời nằm TRỌN trong đoạn
  văn bản trên (không cần kiến thức ngoài đoạn này).
- `ground_truth` là câu trả lời chuẩn, DIỄN GIẢI LẠI bằng lời của bạn (không
  chép nguyên văn từng chữ của đoạn).

CHỈ trả JSON thuần (không markdown, không giải thích thêm):
{{"question": "<câu hỏi>", "ground_truth": "<đáp án chuẩn>"}}
"""

GEN_PROMPT_HINH = """Bạn đang soạn MỘT câu hỏi kiểm tra cho học sinh THCS về một
HÌNH trong sách giáo khoa Khoa học tự nhiên. Thông tin bạn có về hình này:

Nhãn hình: {nhan}
Chú thích: {chu_thich}
Chữ trong hình (OCR): {chu_trong_hinh}
Ngữ cảnh quanh hình: {ngu_canh}

Yêu cầu:
- Soạn ĐÚNG MỘT câu hỏi tiếng Việt yêu cầu quan sát/hiểu nội dung hình này
  (ví dụ "Quan sát Hình X.Y, cho biết...").
- `ground_truth` là câu trả lời chuẩn dựa trên thông tin trên.

CHỈ trả JSON thuần (không markdown, không giải thích thêm):
{{"question": "<câu hỏi>", "ground_truth": "<đáp án chuẩn>"}}
"""

GEN_PROMPT_NGOAI_PHAM_VI = """Soạn ĐÚNG MỘT câu hỏi kiến thức phổ thông bậc
THCS thuộc môn {mon} (KHÔNG phải môn Khoa học tự nhiên — Lý/Hoá/Sinh).

CHỈ trả JSON thuần (không markdown, không giải thích thêm):
{{"question": "<câu hỏi>", "ground_truth": "Câu hỏi thuộc môn {mon}, KHÔNG nằm trong 12 quyển SGK Khoa học tự nhiên (Lý-Hoá-Sinh). Hệ thống nên trả lời không tìm thấy thông tin trong sách / không thuộc phạm vi kiến thức, KHÔNG được tự trả lời bằng kiến thức ngoài sách hay bịa đáp án."}}
"""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip().rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _kiem_tra_input(n_total: int, n_ngoai_pham_vi: int) -> None:
    """Chặn input vô lý TRƯỚC khi tính n_con_lai/gọi random.sample.

    Tìm ra ở phản biện lần 2 của spec: để `n_con_lai` âm rồi `random.sample`
    ném `ValueError` khó hiểu tệ hơn một thông báo rõ ràng ở đây.
    """
    if n_ngoai_pham_vi >= n_total or n_ngoai_pham_vi < 0:
        raise SystemExit(
            f"--n-ngoai-pham-vi ({n_ngoai_pham_vi}) phải nhỏ hơn --n ({n_total}) "
            "và không âm.")


def _kiem_tra_du_pool(pool_size: int, n_can: int) -> None:
    """Chặn khi pool đủ điều kiện nhỏ hơn số cần rút — KHÔNG âm thầm hạ n_can.

    Tìm ra ở phản biện lần 2 của spec: hạ n_can rồi dồn phần thiếu sang nhóm
    khác sẽ âm thầm đổi tỉ lệ đã in ở bước tính N.
    """
    if pool_size < n_can:
        # Chữ "pool" viết thường (không phải "Pool") để khớp regex case-sensitive
        # của test_kiem_tra_du_pool_chan_pool_thieu — bug gõ hoa/thường có sẵn
        # trong code mẫu gốc của brief, sửa tại đây để Step 4 "PASS toàn bộ" đúng
        # như brief yêu cầu.
        raise SystemExit(
            f"pool đủ điều kiện chỉ có {pool_size} phần tử, cần rút {n_can} — "
            "không đủ. KHÔNG tự hạ số cần rút; hoặc mở rộng bộ lọc, hoặc giảm "
            "--n.")


def _tinh_n_moi_nhom(n_total: int, n_ngoai_pham_vi: int,
                      n_chunk: int, n_anh: int) -> Dict[str, int]:
    """N cho từng nhóm, tính TẠI THỜI ĐIỂM CHẠY từ kích thước thật của index.

    p_hinh = n_anh / (n_chunk + n_anh); n_hinh = round(n_con_lai * p_hinh).
    """
    n_con_lai = n_total - n_ngoai_pham_vi
    p_hinh = n_anh / (n_chunk + n_anh) if (n_chunk + n_anh) > 0 else 0.0
    n_hinh = round(n_con_lai * p_hinh)
    n_van_ban = n_con_lai - n_hinh
    return {
        "n_van_ban": n_van_ban,
        "n_hinh": n_hinh,
        "n_ngoai_pham_vi": n_ngoai_pham_vi,
        "p_hinh_do_duoc": round(p_hinh, 4),
    }


def _anh_xa_hinh_sang_cot(meta: dict) -> dict:
    """Ánh xạ metadata `biology_image_metadata` sang cột CSV chuẩn.

    QUAN TRỌNG (phản biện lần 4 của spec): collection ảnh dùng khoá
    `pdf_filename`/`page_number`, KHÔNG PHẢI `source`/`page` như bên text. Đọc
    nhầm `metadata.get("source")` sẽ luôn ra None -> cả nhóm hinh bị gán nhầm
    ngoai_pham_vi ở retrieval_benchmark.py. KHÔNG BAO GIỜ đọc `source`/`page`
    ở hàm này.
    """
    return {
        "source_book": str(meta.get("pdf_filename") or ""),
        "source_page": str(meta.get("page_number")) if meta.get("page_number") is not None else "",
        "figure_label": str(meta.get("figure_label") or ""),
    }


def _dem_anh_hop_le(client) -> Dict[str, list]:
    """Đếm/lấy ids ảnh hợp lệ với ĐÚNG MỘT bộ lọc, dùng cho CẢ đếm lẫn lấy mẫu.

    Bộ lọc: is_active=True, review_status not in (rejected, deleted), và có
    figure_label HOẶC crop_text không rỗng. Trước phản biện lần 4, bản nháp
    dùng bộ lọc KHÁC nhau ở bước đếm và bước lấy mẫu (lệch 2,6% trên corpus
    hôm nay) — nay dùng chung một hàm để không thể lệch nữa.
    """
    col = client.get_collection(IMAGE_METADATA_COLLECTION_NAME)
    got = col.get(include=["metadatas"], limit=1_000_000)  # cùng safety cap ablation.py đã dùng
    ids_hop_le = []
    metas_hop_le = {}
    for cid, meta in zip(got["ids"], got["metadatas"]):
        if meta.get("is_active") is False:
            continue
        if str(meta.get("review_status") or "").lower() in {"rejected", "deleted"}:
            continue
        if not (meta.get("figure_label") or meta.get("crop_text")):
            continue
        ids_hop_le.append(cid)
        metas_hop_le[cid] = meta
    return {"ids": ids_hop_le, "metas": metas_hop_le}


def _dem_van_ban_hop_le(client) -> Dict[str, list]:
    """Pool DUY NHẤT cho cả ĐẾM (`n_chunk` của công thức `p_hinh`) lẫn LẤY MẪU
    câu văn bản (lọc theo độ dài, `len(doc) >= MIN_CHUNK_CHARS`).

    SỬA CÓ CHỦ Ý so với bản nháp gốc của spec (2026-09-04, đo trên `database/`
    thật, không phải suy đoán): bản nháp dùng một hàm đếm THÔ riêng
    (`_dem_van_ban_tho`, 16515 chunk không lọc gì) cho `n_chunk`, trong khi
    `n_anh` lại luôn là số ẢNH ĐÃ LỌC (qua `_dem_anh_hop_le`) — bất đối xứng
    có hệ thống. Đo trực tiếp: 16515 chunk thô nhưng chỉ 11444 chunk (69,3%)
    đủ điều kiện lấy mẫu (len>=200 ký tự, 5071/16515 = 30,7% bị loại vì quá
    ngắn) — trong khi phía ảnh chỉ lệch 2,6% (3881 thô vs 3780 hợp lệ, mức
    lệch mà spec đã biết và chấp nhận). Dùng số thô cho text nhưng số lọc cho
    ảnh làm `p_hinh` bị tính THẤP hơn thực tế (~0,186 thay vì ~0,248 nếu đối
    xứng cả hai phía) — hỏng đúng mục tiêu D-182 (nhóm câu Hình từng quá nhỏ
    để chẩn đoán). Nay dùng CHUNG một pool đã lọc cho cả đếm lẫn lấy mẫu ở cả
    hai phía văn bản/ảnh — đối xứng, không thể lệch giữa hai bước như bản
    nháp cũ. ĐỪNG quay lại tách riêng một hàm đếm thô — đó chính là bug đã
    sửa, không phải một lựa chọn thiết kế hợp lệ khác.
    """
    col = client.get_collection(TEXT_COLLECTION_NAME)
    got = col.get(include=["documents", "metadatas"], limit=1_000_000)
    ids_hop_le = []
    docs_hop_le = {}
    metas_hop_le = {}
    for cid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
        if doc and len(doc) >= MIN_CHUNK_CHARS:
            ids_hop_le.append(cid)
            docs_hop_le[cid] = doc
            metas_hop_le[cid] = meta
    return {"ids": ids_hop_le, "docs": docs_hop_le, "metas": metas_hop_le}


class _CauTron:
    """Cửa sổ trượt theo dõi tỉ lệ ITEM sinh THẤT BẠI (không phải lệnh gọi API
    thô) — dừng hẳn script nếu vượt ngưỡng.

    Một ITEM có thể tốn tới 3 lệnh gọi API thật (`_sinh_mot_cau` retry tối đa 3
    lần) trước khi bị tính là 1 lần thất bại ở đây — `ghi_nhan()` được gọi
    ĐÚNG MỘT LẦN mỗi item (thành công hay thất bại), không phải mỗi lệnh gọi
    API. Tên biến `window`/`CIRCUIT_BREAKER_WINDOW=20` nghĩa là "20 ITEM gần
    nhất", KHÔNG phải "20 lệnh gọi API gần nhất" — worst case thực tế có thể
    tốn tới 60 lệnh gọi API trước khi cửa sổ 20 item đầy và có thể dừng.

    Tìm ra ở phản biện lần 4 của spec: không có trần tổng cho cơ chế rút thay
    thế, nếu Groq lỗi hệ thống (đã xảy ra thật, D-173) script có thể đốt rất
    nhiều lệnh gọi trước khi ai đó nhận ra.
    """

    def __init__(self, window: int = CIRCUIT_BREAKER_WINDOW,
                 max_rate: float = CIRCUIT_BREAKER_MAX_ERROR_RATE):
        self._window = window
        self._max_rate = max_rate
        self._ket_qua: deque = deque(maxlen=window)

    def ghi_nhan(self, thanh_cong: bool) -> None:
        """Gọi ĐÚNG MỘT LẦN sau khi một ITEM đã hoàn tất (thành công hoặc hết
        3 lần thử) — xem `_sinh_mot_cau`, không gọi trong vòng lặp retry bên
        trong nó."""
        self._ket_qua.append(thanh_cong)
        if len(self._ket_qua) == self._window:
            ti_le_loi = 1 - (sum(self._ket_qua) / self._window)
            if ti_le_loi > self._max_rate:
                raise SystemExit(
                    f"Tỉ lệ lỗi LLM {ti_le_loi:.0%} vượt ngưỡng "
                    f"{self._max_rate:.0%} trên {self._window} ITEM gần "
                    "nhất -> DỪNG HẲN (fail loudly thay vì âm thầm đốt quota). "
                    "Kiểm tra EVAL_LLM_* trong .env / hạn mức Groq trước khi "
                    "chạy lại.")


def _sinh_mot_cau(llm, prompt: str, cau_tron: _CauTron) -> Optional[dict]:
    """Gọi LLM 1 lần (tối đa 2 thử lại), trả None nếu thất bại cả 3 lần."""
    for lan in range(3):
        try:
            resp = llm.invoke(prompt)
            data = _parse_json(resp.content if hasattr(resp, "content") else str(resp))
            q = str(data.get("question", "")).strip()
            gt = str(data.get("ground_truth", "")).strip()
            if not q or not gt:
                raise ValueError("question/ground_truth rỗng")
            cau_tron.ghi_nhan(True)
            return {"question": q, "ground_truth": gt}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sinh câu lỗi (lần %d/3): %s", lan + 1, exc)
            if lan == 2:
                cau_tron.ghi_nhan(False)
                return None
            time.sleep(2)


def _sinh_van_ban(llm, ids: List[str], docs: Dict[str, str],
                   metas: Dict[str, dict], n_can: int,
                   da_dung: set, cau_tron: _CauTron) -> List[dict]:
    rows = []
    pool = [i for i in ids if i not in da_dung]
    random.shuffle(pool)
    idx = 0
    so_lan_thay = 0
    while len(rows) < n_can:
        if idx >= len(pool):
            raise SystemExit(
                f"Hết pool văn bản (cần {n_can}, đã hết {len(pool)} ứng viên) "
                "trước khi đủ số câu — tỉ lệ lỗi LLM quá cao hoặc pool quá nhỏ.")
        cid = pool[idx]
        idx += 1
        da_dung.add(cid)
        ket_qua = _sinh_mot_cau(llm, GEN_PROMPT_VAN_BAN.format(doan=docs[cid]), cau_tron)
        if ket_qua is None:
            so_lan_thay += 1
            continue
        m = metas[cid]
        rows.append({
            "question": ket_qua["question"], "loai": "van_ban",
            "source_book": str(m.get("source") or ""),
            "source_page": str(m.get("page")) if m.get("page") is not None else "",
            "figure_label": "", "ground_truth": ket_qua["ground_truth"],
        })
    if so_lan_thay:
        print(f"[build_testset] văn bản: đã thay {so_lan_thay} item lỗi LLM")
    return rows


def _sinh_hinh(llm, ids: List[str], metas: Dict[str, dict], n_can: int,
               da_dung: set, cau_tron: _CauTron) -> List[dict]:
    rows = []
    pool = [i for i in ids if i not in da_dung]
    random.shuffle(pool)
    idx = 0
    so_lan_thay = 0
    while len(rows) < n_can:
        if idx >= len(pool):
            raise SystemExit(
                f"Hết pool hình (cần {n_can}, đã hết {len(pool)} ứng viên) "
                "trước khi đủ số câu.")
        cid = pool[idx]
        idx += 1
        da_dung.add(cid)
        m = metas[cid]
        prompt = GEN_PROMPT_HINH.format(
            nhan=m.get("figure_label") or "(không có)",
            chu_thich=m.get("figure_caption") or "(không có)",
            chu_trong_hinh=m.get("crop_text") or "(không có)",
            ngu_canh=(m.get("context_text") or "")[:500] or "(không có)",
        )
        ket_qua = _sinh_mot_cau(llm, prompt, cau_tron)
        if ket_qua is None:
            so_lan_thay += 1
            continue
        cot = _anh_xa_hinh_sang_cot(m)
        rows.append({
            "question": ket_qua["question"], "loai": "hinh",
            **cot, "ground_truth": ket_qua["ground_truth"],
        })
    if so_lan_thay:
        print(f"[build_testset] hình: đã thay {so_lan_thay} item lỗi LLM")
    return rows


def _sinh_ngoai_pham_vi(llm, n_can: int, cau_tron: _CauTron) -> List[dict]:
    rows = []
    while len(rows) < n_can:
        mon = random.choice(MON_NGOAI_PHAM_VI)
        ket_qua = _sinh_mot_cau(llm, GEN_PROMPT_NGOAI_PHAM_VI.format(mon=mon), cau_tron)
        if ket_qua is None:
            continue
        rows.append({
            "question": ket_qua["question"], "loai": "ngoai_pham_vi",
            "source_book": "", "source_page": "", "figure_label": "",
            "ground_truth": ket_qua["ground_truth"],
        })
    return rows


def build(n_total: int, n_ngoai_pham_vi: int, seed: int) -> None:
    import chromadb

    _kiem_tra_input(n_total, n_ngoai_pham_vi)
    random.seed(seed)

    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    # n_chunk và n_van_ban_pool dùng CHUNG một pool đã lọc (sửa D-182, xem
    # docstring `_dem_van_ban_hop_le`) — đối xứng với phía ảnh, nơi n_anh
    # cũng luôn là số ĐÃ LỌC qua `_dem_anh_hop_le`.
    van_ban_pool = _dem_van_ban_hop_le(client)
    hinh_pool = _dem_anh_hop_le(client)
    n_chunk = len(van_ban_pool["ids"])
    n_anh = len(hinh_pool["ids"])

    n = _tinh_n_moi_nhom(n_total, n_ngoai_pham_vi, n_chunk, n_anh)
    print(f"[build_testset] index: {n_chunk} chunk đủ điều kiện lấy mẫu (đã lọc), "
          f"{n_anh} ảnh hợp lệ -> p_hinh={n['p_hinh_do_duoc']}")
    print(f"[build_testset] N mục tiêu: van_ban={n['n_van_ban']} "
          f"hinh={n['n_hinh']} ngoai_pham_vi={n['n_ngoai_pham_vi']} "
          f"(tổng {n['n_van_ban'] + n['n_hinh'] + n['n_ngoai_pham_vi']})")

    _kiem_tra_du_pool(len(van_ban_pool["ids"]), n["n_van_ban"])
    _kiem_tra_du_pool(n_anh, n["n_hinh"])

    if not is_configured():
        raise SystemExit(config_help())
    llm = get_eval_llm(temperature=0.7)
    cau_tron = _CauTron()
    da_dung: set = set()

    rows = []
    rows += _sinh_van_ban(llm, van_ban_pool["ids"], van_ban_pool["docs"],
                           van_ban_pool["metas"], n["n_van_ban"], da_dung, cau_tron)
    rows += _sinh_hinh(llm, hinh_pool["ids"], hinh_pool["metas"],
                        n["n_hinh"], da_dung, cau_tron)
    rows += _sinh_ngoai_pham_vi(llm, n["n_ngoai_pham_vi"], cau_tron)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=[
        "question", "loai", "source_book", "source_page",
        "figure_label", "ground_truth"])
    df.to_csv(DRAFT_CSV, index=False, encoding="utf-8-sig")

    meta = {
        "seed": seed, "n_total": n_total,
        "n_van_ban": n["n_van_ban"], "n_hinh": n["n_hinh"],
        "n_ngoai_pham_vi": n["n_ngoai_pham_vi"],
        "p_hinh_do_duoc": n["p_hinh_do_duoc"],
        "n_chunk_do_duoc": n_chunk, "n_anh_do_duoc": n_anh,
        "tao_luc": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "human_reviewed": False, "reviewed_at": None,
    }
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"[build_testset] đã ghi {DRAFT_CSV} ({len(df)} câu) + {META_JSON}")
    print("[build_testset] BẮT BUỘC duyệt tay trước khi dùng chính thức: "
          "đọc lại draft.csv, sửa câu/ground_truth sai, rồi chạy "
          "`python -m src.test.build_testset --mark-reviewed`")


def mark_reviewed() -> None:
    if not META_JSON.exists():
        raise SystemExit(f"Chưa có {META_JSON} — chạy sinh bộ test trước.")
    meta = json.loads(META_JSON.read_text(encoding="utf-8"))
    print(f"Xác nhận đã đọc và duyệt tay TOÀN BỘ {DRAFT_CSV} "
          f"({meta.get('n_total')} câu)?")
    xac_nhan = input("Gõ 'xac-nhan-da-doc' để tiếp tục: ").strip()
    if xac_nhan != "xac-nhan-da-doc":
        raise SystemExit("Chưa xác nhận — không đổi human_reviewed.")
    meta["human_reviewed"] = True
    meta["reviewed_at"] = datetime.now(timezone(timedelta(hours=7))).isoformat()
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"Đã đánh dấu human_reviewed=true trong {META_JSON}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=240)
    ap.add_argument("--n-ngoai-pham-vi", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mark-reviewed", action="store_true")
    args = ap.parse_args()

    if args.mark_reviewed:
        mark_reviewed()
        return 0
    build(args.n, args.n_ngoai_pham_vi, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
