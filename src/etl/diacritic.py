"""Conservative Vietnamese diacritic correction for OCR output.

Only rewrites tokens that appear in a curated confusion map. Anything
all-caps, containing digits, or on the science allowlist is left untouched
so chemical formulas / English terms / proper nouns are never damaged.
"""
import re

# Curated map of frequent Tesseract diacritic misreads → correct form.
# Extend as QA surfaces more (keep lowercase keys; matching is case-insensitive
# but preserves the original leading capital).
_CONFUSIONS = {
    "triên": "triển",
    "đât": "đất",
    "tổn": "tồn",     # "tổn tại" -> "tồn tại"  (context-guarded below)
    "giây": "giấy",   # guarded: only when not a time unit context (see note)
    "bảy": "bày",     # "trình bảy" -> "trình bày"
    "môi": "mỗi",
}
# Confusions that are too ambiguous to apply unconditionally -> require a
# preceding trigger word (avoids "giây"=second, "môi"=lip false positives).
_CONTEXT_GUARDED = {
    "giây": {"prev": {"sản", "tờ", "bột"}, "to": "giấy"},
    "tổn":  {"prev": {"vẫn", "còn", "sự"},  "to": "tồn"},
    "môi":  {"prev": {"với", "của"},         "to": "mỗi"},
}
SCIENCE_ALLOWLIST = {"oxygen", "hydrogen", "nitrogen", "sulfuric", "acid",
                     "carbon", "dioxide", "chlorine", "sodium", "iron"}

_TOKEN = re.compile(r"\w+|\W+", re.UNICODE)

def _skip(tok: str) -> bool:
    if any(ch.isdigit() for ch in tok):
        return True
    if tok.isupper() and len(tok) > 1:
        return True
    if tok.lower() in SCIENCE_ALLOWLIST:
        return True
    return False

def _apply_case(src: str, repl: str) -> str:
    return repl.capitalize() if src[:1].isupper() else repl

def fix_diacritics(text: str) -> str:
    toks = _TOKEN.findall(text)
    words = [t for t in toks if t.strip()]  # for prev-word lookups
    out, wi = [], -1
    for t in toks:
        if not t.strip():
            out.append(t); continue
        wi += 1
        low = t.lower()
        if _skip(t):
            out.append(t); continue
        prev = words[wi - 1].lower() if wi > 0 else ""
        if low in _CONTEXT_GUARDED:
            g = _CONTEXT_GUARDED[low]
            out.append(_apply_case(t, g["to"]) if prev in g["prev"] else t)
        elif low in _CONFUSIONS and low not in _CONTEXT_GUARDED:
            out.append(_apply_case(t, _CONFUSIONS[low]))
        else:
            out.append(t)
    return "".join(out)
