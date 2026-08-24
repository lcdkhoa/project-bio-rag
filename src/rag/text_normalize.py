# -*- coding: utf-8 -*-
"""Chuẩn hoá + tách từ cho KÊNH THƯA (BM25). Chỉ dùng ở phía truy vấn và chỉ mục
thưa — **KHÔNG BAO GIỜ** ghi đè chữ đã lưu trong `biology_text` (CẤM #5, nguyên
tắc 1: đoán lại một chỉ số dưới là bịa).

## Vì sao cần một kênh riêng cho công thức

Đo trên chính 16 393 chunk đã index (D-73): chỉ số dưới **không sống sót ở bất kỳ
độ phân giải nào** — hỏng:đúng = CD 256:3, CTST 377:3, KNTT 408:4, và ký tự `₂`
Unicode xuất hiện **0** lần ở cả ba nhà xuất bản. OCR đọc chỉ số dưới thành **dấu
phẩy**: `O₂`→`O,`, `H₂SO₄`→`H,SO,`, `CO₂`→`CO,`. Nên một học sinh gõ `CO2` không
bao giờ khớp từ vựng với trang lưu `CO,` — đúng chỗ đề cương nói BM25 tồn tại để
"không bỏ sót các truy vấn chứa **thuật ngữ khoa học đặc thù**".

## Luật, và vì sao nó KHÔNG phải là bịa

Chỗ dễ sai nhất: đoán chữ số. `SO,` có thể là SO₂ **hoặc** SO₃; `H,SO,` là H₂SO₄
— hai dấu phẩy là hai chữ số **khác nhau**. Viết lại chúng thành chữ số là bịa.

Nên luật ở đây **xoá** chữ số thay vì đoán: một token có dạng công thức sinh ra
**khung** của nó, mỗi vị trí chỉ số dưới thay bằng `#`:

    CO,  ->  co#          CO2  ->  co# + co2
    H,O  ->  h#o          H2O  ->  h#o + h2o
    H,SO, -> h#so#        H2SO4 -> h#so# + h2so4

Cả tài liệu **và** truy vấn đi qua đúng một hàm này, nên phép biến đổi đối xứng.
Nó **có mất mát** — `SO2` và `SO3` cùng ra `so#` — và mất mát đó là **thành thật**:
chữ đã index KHÔNG chứa chữ số, nên thông tin phân biệt SO₂/SO₃ không tồn tại
trong kho để mà giữ.

Token còn đọc được chữ số thì sinh **cả hai** dạng (khung + dạng nguyên văn). Nhờ
vậy trang đọc ĐÚNG (`CO2` → 2 token trùng) vẫn ăn điểm cao hơn trang đọc HỎNG
(`CO,` → 1 token trùng): giữ được độ chính xác ở chỗ thông tin còn, mà vẫn vớt
được recall ở chỗ thông tin đã mất.

## Chỉ số dưới `0` bị loại — bằng phép đo, không phải bằng cảm tính

Quét toàn bộ 1 001 276 token của index: luật ban đầu (cho phép chỉ số `0`) khớp
3 959 token / 715 dạng, trong đó có **`H0C` (82 lần), `KH0A` (58), `TRA0` (14),
`S0`, `I0`, `CaC0`** — đó là chữ tiếng Việt IN HOA bị OCR đọc `Ọ`/`O`→`0`
("KHOA HỌC"). Chỉ số dưới bằng 0 **vô nghĩa trong hoá học**, nên loại nó là một
luật có nguyên tắc chứ không phải vá tạm. Sau khi loại: **3 590 token / 634 dạng
= 0,359%** tổng số token, và mọi ca `H0C`/`KH0A`/`TRA0` biến mất.

**Dương tính giả CÒN LẠI, đã đo và cố ý chấp nhận:** token một chữ cái + dấu phẩy
(`A,` 111 lần, `R,` 105, `B,` 67, `C,` 70, `V,` 55) vừa có thể là biến vật lý có
chỉ số dưới (F₁, F₂ — đề cương nêu `A = Fs`), vừa có thể là nhãn phương án trắc
nghiệm "A, B, C, D". Không tách được hai cái bằng hình dạng token. Chúng được để
nguyên vì **IDF tự chặn thiệt hại**: token nào có mặt khắp nơi thì df cao → IDF
≈ 0 → gần như không cộng điểm. Đây đúng là lập luận đã dùng ở G3 khi chọn IDF
thay cho danh sách stopword (D-49).
"""

import re
import unicodedata
from typing import List

# Đổi giá trị này khi luật chuẩn hoá đổi -> chỉ mục thưa cũ sẽ tự báo lỗi.
NORMALIZER_VERSION = "v3_formula_skeleton_plus_letters"

# Chỉ số dưới: chữ số 1-9, chữ số dưới Unicode ₁-₉, hoặc DẤU PHẨY (OCR - D-73).
# Cố ý KHÔNG có `0` và `₀`: chỉ số dưới 0 vô nghĩa, và cho phép nó thì luật bắt
# nhầm chữ IN HOA tiếng Việt bị OCR sai (đo được: `H0C`, `KH0A`, `TRA0`).
_SUB_CLASS = "1-9₁-₉,"
_GROUP = rf"[A-Z][a-z]?[{_SUB_CLASS}]?"
_FORMULA_RE = re.compile(rf"^(?:{_GROUP})+$")
_SUB_RE = re.compile(rf"[{_SUB_CLASS}]")
# Dấu câu bao quanh một token. KHÔNG có dấu phẩy: dấu phẩy bên trong/cuối token
# chính là chỉ số dưới bị OCR đọc sai, nên cắt nó đi là mất luôn tín hiệu.
_EDGE_PUNCT = ".;:!?()[]{}\"'“”‘’…–—+=/*<>%&|\\"
_SUBSCRIPT_DIGITS = {chr(0x2080 + d): str(d) for d in range(10)}
# Công thức dài quá ngưỡng này gần như chắc chắn là rác OCR, không phải công thức.
MAX_FORMULA_LEN = 12

# Vốn từ ĐÓNG: ký hiệu nguyên tố hoá học. Đây là DỮ LIỆU, không phải heuristic —
# nhóm hai chữ `[A-Z][a-z]` phải nằm trong danh sách này thì token mới được coi
# là công thức. Đo được nó giết đúng lớp dương tính giả đã thấy trên bộ test:
# `Bo,` (tên Bohr + dấu phẩy) -> loại, còn `Na,` `Fe,` `Cu,` `Mg,` `Ca,` `Zn,`
# `Ag,` `Pb,` (đều là nguyên tố thật) vẫn giữ.
_ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al",
    "Si", "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe",
    "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr",
    "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm",
    "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W",
    "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn",
    "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf",
    "Es", "Fm", "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}
# Số La Mã DÀI (>= 2 ký tự) là nhãn mục, không phải công thức: `XIII,` đọc theo
# hình dạng thì là X+I+I+I và lọt luật. Chữ La Mã một ký tự (`I,` `V,` `C,`) thì
# KHÔNG loại được — chúng đồng thời là iodine / vanadium / carbon, và hình dạng
# token không tách được hai nghĩa. Đó là dương tính giả CÒN LẠI, đã đo và chấp
# nhận (IDF chặn thiệt hại).
_ROMAN_RE = re.compile(r"^[IVXLCDM]{2,}$")
_GROUP_SPLIT_RE = re.compile(rf"[A-Z][a-z]?[{_SUB_CLASS}]?")

_WS_RE = re.compile(r"\S+")
_WORD_RE = re.compile(r"[0-9a-zÀ-ỹ]+")


def fold(text: str) -> str:
    """Bỏ dấu + hạ chữ. Xử lý riêng đ/Đ (NFD không tách được hai chữ này).

    Giống hệt `src/test/qa_citation_page.fold` — cố ý trùng, vì cả hai phải nhìn
    corpus theo cùng một cách.
    """
    s = str(text or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def is_formula_token(token: str) -> bool:
    """Token có dạng công thức hoá/lý VÀ có ít nhất một vị trí chỉ số dưới.

    Ba tầng, tầng sau chặn dương tính giả mà tầng trước để lọt:
      1. hình dạng (`_FORMULA_RE`) + có chỉ số dưới;
      2. bỏ chỉ số đi mà ra một số La Mã dài -> nhãn mục, không phải công thức;
      3. mọi nhóm HAI chữ phải là ký hiệu nguyên tố thật.
    """
    if not token or len(token) > MAX_FORMULA_LEN:
        return False
    if not _FORMULA_RE.match(token) or not _SUB_RE.search(token):
        return False
    letters = "".join(c for c in token if c.isalpha())
    if _ROMAN_RE.match(letters):
        return False
    for grp in _GROUP_SPLIT_RE.findall(token):
        sym = "".join(c for c in grp if c.isalpha())
        if len(sym) == 2 and sym not in _ELEMENTS:
            return False
    return True


def formula_tokens(token: str) -> List[str]:
    """Khung công thức (+ dạng nguyên văn nếu chữ số còn đọc được).

    `CO,` -> ['co#'] · `CO2` -> ['co#', 'co2'] · `H,SO,` -> ['h#so#']
    """
    if not is_formula_token(token):
        return []
    skeleton: List[str] = []
    literal: List[str] = []
    has_digit = False
    for ch in token:
        if ch in _SUBSCRIPT_DIGITS:      # ₂ -> 2
            ch = _SUBSCRIPT_DIGITS[ch]
        if ch == ",":
            skeleton.append("#")
            literal.append("#")          # dấu phẩy không mang chữ số nào cả
        elif ch.isdigit():
            skeleton.append("#")
            literal.append(ch)
            has_digit = True
        else:
            skeleton.append(ch.lower())
            literal.append(ch.lower())
    out = ["".join(skeleton)]
    # Dạng CHỮ THUẦN (bỏ hẳn vị trí chỉ số dưới). Cần vì học sinh gõ `CuO` không
    # có chỉ số nào, trong khi trang lưu `CuO,` — không có dạng này thì token
    # `cuo` biến mất khỏi tài liệu và truy vấn `CuO` **tệ đi** so với trước khi
    # có chuẩn hoá. Đo được: `CuO` 6/10 -> 4/10 chunk đúng ở top-10 trước khi
    # thêm dòng này. Lỗi do chính bước chuẩn hoá gây ra, không phải của OCR.
    letters = "".join(c for c in skeleton if c != "#")
    if len(letters) >= 2:
        out.append(letters)
    if has_digit:
        lit = "".join(literal)
        if lit not in out:
            out.append(lit)
    return out


def tokenize(text: str, fold_accents: bool = True,
             formula: bool = True) -> List[str]:
    """Tách từ cho kênh thưa.

    Token dạng công thức đi ĐƯỜNG RIÊNG (chỉ sinh token công thức) — vì tách
    `H,SO,` theo ký tự không phải chữ-số sẽ cho `h`, `so`, làm mất hẳn quan hệ
    giữa hai nhóm. Mọi token khác tách theo ký tự không phải chữ-số.

    `fold_accents=True` bỏ dấu. Lý do phải ĐO chứ không mặc định: OCR làm hỏng
    dấu (chính vì thế G3 phải so khớp trên dạng đã bỏ dấu), nên bỏ dấu **có thể**
    tăng recall; nhưng nó cũng làm từ chức năng đụng từ nội dung
    (`khí`→`khi`, `đo`/`độ`→`do`, `lá`→`la`). BM25 dùng IDF nên tự chặn phần
    đụng đó — nhưng đó là giả thuyết, và bảng đo nằm trong decision log.

    `formula=False` TẮT hẳn kênh công thức — chỉ để ĐO xem kênh đó đáng bao
    nhiêu (before/after), không phải để chạy thật.
    """
    out: List[str] = []
    for raw in _WS_RE.findall(str(text or "")):
        stripped = raw.strip(_EDGE_PUNCT)
        if not stripped:
            continue
        ftoks = formula_tokens(stripped) if formula else []
        if ftoks:
            out.extend(ftoks)
            continue
        piece = fold(stripped) if fold_accents else stripped.lower()
        for w in _WORD_RE.findall(piece):
            if len(w) >= 2 or w.isdigit():
                out.append(w)
    return out
