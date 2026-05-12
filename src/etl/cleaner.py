"""Text cleaning utilities for Vietnamese content."""

import re
import unicodedata


def clean_vietnamese_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = "".join(
        char for char in text
        if not unicodedata.category(char).startswith("C") or char in "\n\t"
    )
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()
