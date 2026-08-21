"""Kiểm tra âm tiết tiếng Việt — CHỈ GẮN CỜ, không sửa một ký tự nào.

Bản cũ (`fix_diacritics`) tự *ghi lại* chữ theo một bảng confusion tự soạn. Đo
trên corpus thật: nó sửa được **3 token trên ~6500** (spec §1.2) trong khi có
toàn quyền thay ký tự trong sách giáo khoa. Đổi lấy nguy cơ đó cho 0,05% lợi ích
là sai theo nguyên tắc 5: *bước sửa tự động phải là drop-only hoặc
flag-for-review*. Vì vậy module này chỉ trả về danh sách token đáng ngờ; caller
gắn `needs_review` lên chunk cho người xem.

Cái kiểm được và cái KHÔNG kiểm được — nói rõ để không ai tưởng đây là spellcheck:

* KIỂM ĐƯỢC (cấu trúc chính tả, không cần từ điển):
  - token lẫn chữ với số (`kh6ng`, `1a`) — đo được 0,10–0,15% token, dấu hiệu
    OCR hỏng rất đặc trưng;
  - phụ âm đầu / phụ âm cuối không tồn tại trong tiếng Việt (`nggười`, `honl`);
  - nhiều hơn một dấu thanh trong cùng một âm tiết;
  - âm tiết đóng bởi p/t/c/ch mà **không** mang dấu sắc hoặc nặng — luật chính
    tả thật, nên `mat` (mất dấu của `mát`/`mạt`) bị bắt.
* KHÔNG kiểm được: `chế` -> `ché`. Cả hai đều là âm tiết hợp lệ; phân biệt cần
  từ điển/ngữ cảnh, không có offline. Đây chính là loại lỗi CER 0,0048 đã đo —
  vô hại cho retrieval, và **im lặng sửa nó là điều bị cấm**, nên nó nằm ngoài
  phạm vi và được nói ra thay vì che đi.
"""
from __future__ import annotations

import re
import unicodedata

# Thuật ngữ khoa học / tiếng Anh hay xuất hiện trong SGK KHTN: không phải âm tiết
# tiếng Việt nên không được đem luật tiếng Việt ra soi (giữ như bản cũ để không
# flag nhiễu).
SCIENCE_ALLOWLIST = {
    "oxygen", "hydrogen", "nitrogen", "sulfuric", "acid", "carbon", "dioxide",
    "chlorine", "sodium", "iron", "calcium", "magnesium", "potassium",
    "glucose", "protein", "lipid", "vitamin", "amino", "ribosome", "gene",
    "ampe", "vol", "volt", "watt", "newton", "pascal", "joule",
}

# Viết tắt / đơn vị đo viết thường: không phải âm tiết, đừng soi bằng luật
# tiếng Việt (nếu không "km", "tr." trong MỤC LỤC sẽ ngập cờ).
ABBREVIATION_ALLOWLIST = {
    "km", "kg", "cm", "mm", "dm", "ml", "mg", "ha", "tr", "vd", "cs", "kwh",
    "kw", "mol", "atm", "ppm", "adn", "arn",
}

# Từ phiên âm/ngoại lai viết liền nhiều âm tiết mà KHÔNG có dấu tiếng Việt nào
# ("cacbon", "amoniac", "hidroxit"). Luật âm tiết không áp dụng được cho chúng;
# ngưỡng độ dài giữ lại các âm tiết thật (mọi âm tiết tiếng Việt không dấu vẫn
# đi qua kiểm tra cấu trúc bình thường vì cấu trúc của chúng hợp lệ).
LOANWORD_MIN_LEN = 6

# Chữ cái KHÔNG có trong bảng chữ cái tiếng Việt -> token là từ ngoại lai/kí
# hiệu, bỏ qua (đừng flag nhiễu).
_FOREIGN_LETTERS = set("fjwz")

_ONSETS = {
    "", "b", "c", "ch", "d", "đ", "g", "gh", "gi", "h", "k", "kh", "l", "m",
    "n", "ng", "ngh", "nh", "p", "ph", "qu", "r", "s", "t", "th", "tr", "v",
    "x",
}
_CODAS = {"", "c", "ch", "m", "n", "ng", "nh", "p", "t"}
# Âm tiết đóng bởi các phụ âm tắc này chỉ nhận dấu sắc hoặc nặng.
_STOP_CODAS = {"c", "ch", "p", "t"}

_VOWELS = set("aeiouy") | set("ăâêôơư")   # nguyên âm (kể cả loại có dấu phụ)
_ONSET_FIRST = _VOWELS | {"đ"}            # ký tự mở đầu phần rime hợp lệ

# Dấu thanh Unicode combining: sắc, huyền, ngã, hỏi, nặng.
_TONE_MARKS = {"́": "sac", "̀": "huyen", "̃": "nga",
               "̉": "hoi", "̣": "nang"}
_TONE_OK_WITH_STOP_CODA = {"sac", "nang"}

_ALPHA_TOKEN = re.compile(r"^[^\W\d_]+$", re.UNICODE)
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_HAS_DIGIT = re.compile(r"\d")
_HAS_ALPHA = re.compile(r"[^\W\d_]", re.UNICODE)

MAX_FLAGS_PER_UNIT = 12


def _decompose(token: str) -> tuple[str, list[str]]:
    """Tách token thành (chuỗi không dấu thanh, danh sách tên dấu thanh).

    NFD tách dấu thanh thành combining char, nhưng cũng tách cả dấu phụ của
    ă/â/ê/ô/ơ/ư/đ — nên phải ghép các dấu phụ đó lại (chỉ bóc dấu THANH).
    """
    tones: list[str] = []
    kept: list[str] = []
    for char in unicodedata.normalize("NFD", token):
        if char in _TONE_MARKS:
            tones.append(_TONE_MARKS[char])
        else:
            kept.append(char)
    return unicodedata.normalize("NFC", "".join(kept)), tones


def _split_onset(base: str) -> tuple[str, str]:
    for length in (3, 2, 1):
        if len(base) > length and base[:length] in _ONSETS:
            # "gi"/"qu" là phụ âm đầu, nhưng "gi" trong "gia" và "g" trong "ga"
            # đều hợp lệ; thử dài trước ngắn là đủ vì phần còn lại còn phải qua
            # kiểm tra nguyên âm bên dưới.
            rest = base[length:]
            if rest and rest[0] in _VOWELS:
                return base[:length], rest
    return "", base


def _split_coda(rime: str) -> tuple[str, str]:
    for length in (2, 1):
        if len(rime) > length and rime[-length:] in _CODAS:
            return rime[:-length], rime[-length:]
    return rime, ""


def is_valid_syllable(token: str) -> bool:
    """Token có phải MỘT âm tiết tiếng Việt viết đúng chính tả cấu trúc?

    Chỉ trả lời về CẤU TRÚC (phụ âm đầu / nguyên âm / phụ âm cuối / dấu thanh),
    không về nghĩa — `mát` hợp lệ, `mat` không, `chế` và `ché` đều hợp lệ.
    """
    if not token or not _ALPHA_TOKEN.match(token):
        return False
    base, tones = _decompose(token.lower())
    if len(tones) > 1:
        return False
    onset, rime = _split_onset(base)
    if onset not in _ONSETS or not rime:
        return False
    nucleus, coda = _split_coda(rime)
    if not nucleus or not 1 <= len(nucleus) <= 3:
        return False
    if any(ch not in _VOWELS for ch in nucleus):
        return False
    if coda in _STOP_CODAS and (not tones or tones[0] not in _TONE_OK_WITH_STOP_CODA):
        return False
    return True


def _suspicious(token: str) -> bool:
    if _HAS_DIGIT.search(token) and _HAS_ALPHA.search(token):
        # `kh6ng`, `1a`: chữ lẫn số. Công thức hoá học (CO2, H2O, Fe3O4) và đơn
        # vị (m3) viết HOA phần chữ hoặc là allowlist -> đã bị loại ở dưới.
        return True
    if not _ALPHA_TOKEN.match(token):
        return False
    return not is_valid_syllable(token)


def _skip(token: str) -> bool:
    if len(token) < 2:
        return True
    if token.isupper():
        return True          # CO2, ADN, SGK…
    lowered = token.lower()
    if lowered in SCIENCE_ALLOWLIST:
        return True
    if lowered in ABBREVIATION_ALLOWLIST:
        return True
    if any(ch in _FOREIGN_LETTERS for ch in lowered):
        return True          # từ ngoại lai: luật tiếng Việt không áp dụng
    if (len(token) >= LOANWORD_MIN_LEN and _ALPHA_TOKEN.match(token)
            and token == unicodedata.normalize("NFD", token)
            and lowered.isascii()):
        return True          # từ phiên âm dài, không dấu -> không phải âm tiết
    return False


def diacritic_review_flags(text: str) -> list[str]:
    """Các token đáng ngờ trong `text`. Rỗng = không có gì phải xem lại.

    Không sửa, không xoá, không sắp xếp lại chữ — chỉ liệt kê.
    """
    seen: list[str] = []
    for token in _TOKEN.findall(text or ""):
        if _skip(token) or token in seen:
            continue
        if _suspicious(token):
            seen.append(token)
            if len(seen) >= MAX_FLAGS_PER_UNIT:
                break
    return seen
