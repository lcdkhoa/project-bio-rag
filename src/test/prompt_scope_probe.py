# -*- coding: utf-8 -*-
"""Before/after cho MỘT thay đổi: dòng system nói "Sinh học" -> "Khoa học tự nhiên".

Vì sao cần script chứ không chỉ một test chuỗi: đổi chuỗi rồi tuyên bố "đã cải
thiện" là đúng loại khẳng định không có bằng chứng mà nguyên tắc 2 cấm. Test
`tests/rag/test_chain_prompt_scope.py` chỉ khoá lại PHẠM VI; script này chạy LLM
thật trên câu Vật lí và câu Hoá học rồi in **cả hai** câu trả lời cạnh nhau, để
người đọc tự thấy có đổi gì hay không.

Chạy:  python -m src.test.prompt_scope_probe
Đắt: 4 lượt sinh của Qwen2.5-3B trên CPU (không GPU trên máy dev).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.config import RETRIEVER_K  # noqa: E402
from src.rag.chain import BiologyRAG  # noqa: E402
from src.rag.multimodal_context import build_context  # noqa: E402

CU = "Bạn là trợ lý AI môn Sinh học THCS."
MOI = ("Bạn là trợ lý AI môn Khoa học tự nhiên (Vật lí – Hoá học – Sinh học) "
       "bậc THCS.")

# Hai câu lấy từ chính bộ test 300 câu, nhãn `phan_mon` = ly / hoa.
CAU_HOI = [
    ("ly", "Khi lắp pin vào đèn pin và bật công tắc, bóng đèn pin phát ra "
           "ánh sáng là nhờ có năng lượng dự trữ ở đâu?"),
    ("hoa", "Hạt nhân nguyên tử được tạo thành từ những loại hạt nào?"),
]


def main() -> int:
    from src.rag.llm import get_hf_llm
    from src.rag.vectorstore import VectorDB

    rag = BiologyRAG(None)
    mau_moi = rag.prompt.template
    if MOI not in mau_moi:
        raise RuntimeError(
            f"Prompt hiện tại không chứa dòng system MỚI — script này so sai "
            f"cặp. Prompt đang là: {mau_moi[:120]!r}")
    mau_cu = mau_moi.replace(MOI, CU)

    retriever = VectorDB().get_retriever({"k": RETRIEVER_K})
    llm = get_hf_llm()
    parse = rag.answer_parser.parse

    for phan_mon, cau in CAU_HOI:
        docs = retriever.invoke(cau)
        ngu_canh = build_context(docs, [], multimodal=False)
        trang = ", ".join(
            f"{d.metadata.get('source')} tr.{d.metadata.get('page')}"
            for d in docs)
        print("=" * 78)
        print(f"[{phan_mon}] {cau}")
        print(f"ngữ cảnh: {trang}  ({len(ngu_canh)} ký tự)")
        for ten, mau in (("TRƯỚC (Sinh học)", mau_cu),
                         ("SAU  (KHTN)", mau_moi)):
            prompt = mau.format(context=ngu_canh, question=cau)
            print(f"\n--- {ten} ---")
            print(parse(str(llm.invoke(prompt))))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
