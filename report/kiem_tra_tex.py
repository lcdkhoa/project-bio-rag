# -*- coding: utf-8 -*-
"""Kiểm tra tĩnh nguồn LaTeX của báo cáo — vì máy này KHÔNG có trình biên dịch.

Không có `pdflatex` nghĩa là mọi lỗi build chỉ lộ ra trên máy khác, sau khi đã
commit. Script này bắt trước bốn lớp lỗi phổ biến nhất mà không cần biên dịch:

1. `\\ref{...}` trỏ vào nhãn không tồn tại (LaTeX in `??` chứ không báo lỗi).
2. `\\cite{...}` trỏ vào khoá không có trong `references.bib`.
3. Lệnh cần gói mà gói chưa được nạp (`\\ce` cần `mhchem`, `\\multirow` cần
   `multirow`, ...).
4. Ký tự điều khiển lọt vào file — cách hỏng đặc trưng khi vá `.tex` bằng script
   Python mà quên dùng chuỗi thô: `\\allowbreak` chứa `\\a` (BEL) và `\\textbf`
   chứa `\\t` (TAB), Python sẽ âm thầm dịch chúng thành ký tự điều khiển.

    python report/kiem_tra_tex.py

Thoát khác 0 khi có lỗi, để dùng được trong một lệnh nối.
"""
from __future__ import annotations

import glob
import io
import re
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent / "tex_source"
BIB = GOC / "src" / "references.bib"

# Lệnh -> gói phải nạp. Chỉ liệt kê thứ ĐÃ dùng trong báo cáo này, không liệt kê
# cho đủ: một danh sách dài mà sai sẽ sinh cảnh báo giả và bị bỏ qua.
LENH_CAN_GOI = {
    r"\ce": "mhchem",
    r"\multirow": "multirow",
    r"\toprule": "booktabs",
    r"\includegraphics": "graphicx",
    r"\subcaption": "subcaption",
    r"\begin{tikzpicture}": "tikz",
    r"\makecell": "makecell",
    # `\dfrac` KHÔNG phải LaTeX lõi, khác với `\frac` — dễ tưởng nhầm.
    r"\dfrac": "amsmath",
    r"\begin{align}": "amsmath",
}


# Số / cụm từ của BÁO CÁO CHUYÊN ĐỀ CŨ không được phép còn trong bản mới.
# Mỗi mục: (chuỗi bị cấm, lý do + giá trị thay thế). Danh sách này là hàng rào
# cuối cùng trước khi in: một con số cũ sống sót thì không làm hỏng build, không
# ai thấy, và nó nói dối bằng một con số trông rất chính xác.
SO_CU_BI_CAM = [
    ("2.319", "trang: nay là 2 387 trang nội dung / 2 399 trang trên đĩa"),
    ("13.754", "chunk văn bản: nay là 16 393"),
    ("2.408", "vector hình: nay là 3 881 (đo 2026-08-26, đủ 12 quyển)"),
    ("3.880", "vector hình: 3 880 là số đo TRƯỚC lượt dựng lại KNTT; nay 3 881"),
    ("16.162", "tổng vector: nay là 20 274"),
    ("20.273", "tổng vector: sai 1 vì lấy 3 880 hình; nay là 20 274"),
    ("120 câu", "bộ kiểm thử: nay là 240 câu (192 văn bản + 48 hình), chốt D-172"),
    # 231/238 câu là các số TRUNG GIAN của bộ câu hỏi trước khi D-172 chốt 240
    # (192 văn bản + 48 hình, đều 20 câu/quyển, 80 câu/NXB). Cấm dạng "231 câu"/
    # "238 câu" (không cấm bare "231"/"238" — chuỗi đó khớp cả vào những số
    # KHÔNG liên quan như "1.231" ở Bảng~\ref{tab:corpus}, sinh cảnh báo giả).
    ("231 câu", "bộ kiểm thử: 231 là số TRUNG GIAN (trước D-170/D-172); số chốt là 240"),
    ("238 câu", "bộ kiểm thử: 238 là số TRUNG GIAN (trước D-172); số chốt là 240"),
    ("39 câu hình", "phần hình: 39 là số TRƯỚC khi người duyệt giữ lại 2 khung từng bị coi hỏng (D-170); số chốt là 48"),
    ("MiniLM-L12-v2 (384", "mô hình nhúng: nay là bge-m3, 1024 chiều"),
    ("A100", "môi trường: ETL chạy CPU, không GPU"),
    ("MiMo-v2.5-pro", "LLM giám khảo nay là Groq (4 model xoay vòng, D-173)"),
    ("stealth/ox-alpha", "LLM giám khảo: OpenRouter hết free (D-163); nay là Groq (4 model xoay vòng, D-173)"),
    ("BÁO CÁO CHUYÊN ĐỀ", "loại báo cáo: nay là ĐỒ ÁN TỐT NGHIỆP"),
    ("báo cáo chuyên đề tốt nghiệp", "loại báo cáo: nay là ĐỒ ÁN TỐT NGHIỆP"),
    # Hai cách gọi sai loại tài liệu mà bản lint cũ KHÔNG bắt, vì nó chỉ chặn
    # đúng cụm "BÁO CÁO CHUYÊN ĐỀ". Cả hai đều còn sống trong front matter
    # (`hoi_dong.tex` gọi là "khoá luận" ở tiêu đề và "chuyên đề" ở mục lục).
    ("CHUYÊN ĐỀ TỐT NGHIỆP", "loại tài liệu: ĐỒ ÁN TỐT NGHIỆP"),
    ("KHÓA LUẬN TỐT NGHIỆP", "loại tài liệu: ĐỒ ÁN TỐT NGHIỆP"),
    ("khóa luận tốt nghiệp", "loại tài liệu: đồ án tốt nghiệp"),
    ("MÔN SINH HỌC", "tên đề tài theo đề cương đã ký là môn KHOA HỌC TỰ NHIÊN"),
    # Ba khẳng định SAI SỰ THẬT, không phải số cũ — nhưng cùng một hàng rào:
    # chúng nói dối về những việc CHƯA HỀ XẢY RA, nên nguy hiểm hơn một số sai.
    ("giáo viên bộ môn", "CHƯA có giáo viên nào đánh giá — xem CLAUDE.md, D-129"),
    ("Vintern-1B để mô tả", "captioner TẮT (D-47), visual_caption_vi = 0/3 881"),
    ("chú thích tiếng Việt do Vintern-1B sinh",
     "captioner TẮT (D-47), trường này rỗng trên toàn kho"),
]

# Chỗ được phép nhắc lại số cũ vì đang NÓI VỀ nó (so sánh với bản trước).
# Phải là một dòng nêu rõ đó là số cũ, không phải một dòng dùng nó làm số thật.
DAU_MIEN_TRU = "% SO-CU-CO-Y"


def _doc_tex():
    return sorted(glob.glob(str(GOC / "src" / "**" / "*.tex"), recursive=True))


def kiem_tra() -> list[str]:
    loi: list[str] = []
    tex = _doc_tex()
    cls = GOC / "src" / "thesis.cls"
    nguon = {p: io.open(p, encoding="utf-8").read() for p in tex}
    cls_txt = io.open(cls, encoding="utf-8").read() if cls.exists() else ""
    tat_ca = "\n".join(nguon.values())

    # 1) ref vs label
    nhan = set(re.findall(r"\\label\{([^}]+)\}", tat_ca))
    for p, s in nguon.items():
        for r in re.findall(r"\\(?:ref|autoref|eqref|nameref)\{([^}]+)\}", s):
            if r not in nhan:
                loi.append(f"[ref] {Path(p).name}: \\ref{{{r}}} không có \\label")

    # 2) cite vs bib
    if BIB.exists():
        khoa = set(re.findall(r"@\w+\{([^,]+),", io.open(BIB, encoding="utf-8").read()))
        for p, s in nguon.items():
            for c in re.findall(r"\\cite\w*\{([^}]+)\}", s):
                for k in (x.strip() for x in c.split(",")):
                    if k and k not in khoa:
                        loi.append(f"[cite] {Path(p).name}: \\cite{{{k}}} không có trong references.bib")

    # 3) lệnh cần gói
    da_nap = cls_txt + tat_ca
    for lenh, goi in LENH_CAN_GOI.items():
        if lenh in tat_ca and goi not in da_nap:
            loi.append(f"[goi] dùng {lenh} nhưng chưa nạp gói {goi}")

    # 4) số của báo cáo cũ còn sót
    for p, txt in nguon.items():
        for dong_so, dong in enumerate(txt.splitlines(), 1):
            if DAU_MIEN_TRU in dong:
                continue
            for xau, ly_do in SO_CU_BI_CAM:
                if xau in dong:
                    loi.append(f"[socu] {Path(p).name}:{dong_so}: còn {xau!r} "
                               f"-- {ly_do}. Cố ý giữ thì thêm '{DAU_MIEN_TRU}' "
                               f"vào cuối dòng.")

    # 5) ký tự điều khiển
    for p, s in nguon.items():
        xau = sorted({c for c in s if ord(c) < 32 and c not in "\n\r\t"})
        if xau:
            ma = ", ".join(f"0x{ord(c):02x}" for c in xau)
            loi.append(f"[ctrl] {Path(p).name}: có ký tự điều khiển {ma} "
                       f"(dấu hiệu vá .tex bằng chuỗi Python không phải chuỗi thô)")

    return loi


def main() -> int:
    if not GOC.exists():
        print(f"Không thấy {GOC} — chưa có source .tex?")
        return 2
    loi = kiem_tra()
    n = len(_doc_tex())
    if loi:
        print(f"KIỂM TRA TEX: {len(loi)} vấn đề trên {n} file\n")
        for x in loi:
            print("  " + x)
        return 1
    print(f"KIỂM TRA TEX: sạch ({n} file .tex)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
