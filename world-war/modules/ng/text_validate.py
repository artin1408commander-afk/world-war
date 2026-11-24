"""Persian-aware validation for laws and statements."""
from __future__ import annotations

import re
from collections import Counter

_URL_RE = re.compile(
    r"(https?://|www\.|t\.me/|ble\.ir/|@\w{4,})",
    re.IGNORECASE,
)
_REPEAT_RE = re.compile(r"(.)\1{5,}")
_LATIN_SPAM_RE = re.compile(r"[A-Za-z]{20,}")


def _has_meaningful_persian(text: str, min_letters: int = 4) -> bool:
    letters = re.findall(r"[\u0600-\u06FF]", text or "")
    return len(letters) >= min_letters


def _char_diversity_ok(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) < 8:
        return True
    counts = Counter(compact)
    most = counts.most_common(1)[0][1]
    return (most / max(1, len(compact))) < 0.55


def validate_law_title(title: str) -> str:
    t = (title or "").strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) < 4:
        raise ValueError("عنوان قانون خیلی کوتاه است (حداقل ۴ کاراکتر).")
    if len(t) > 80:
        raise ValueError("عنوان قانون حداکثر ۸۰ کاراکتر است.")
    if not _has_meaningful_persian(t, 3):
        raise ValueError("عنوان قانون باید شامل متن فارسی معنادار باشد.")
    if _REPEAT_RE.search(t) or not _char_diversity_ok(t):
        raise ValueError("عنوان قانون نامعتبر یا اسپم به‌نظر می‌رسد.")
    if _URL_RE.search(t):
        raise ValueError("لینک یا نام‌کاربری در عنوان قانون مجاز نیست.")
    return t


def validate_law_body(body: str) -> str:
    b = (body or "").strip()
    if len(b) < 10:
        raise ValueError("متن قانون خیلی کوتاه است.")
    if len(b) > 2000:
        raise ValueError("متن قانون حداکثر ۲۰۰۰ کاراکتر است.")
    if not _has_meaningful_persian(b, 6):
        raise ValueError("متن قانون باید فارسی و معنادار باشد.")
    if _REPEAT_RE.search(b) or not _char_diversity_ok(b):
        raise ValueError("متن قانون نامعتبر یا اسپم به‌نظر می‌رسد.")
    if _URL_RE.search(b) or _LATIN_SPAM_RE.search(b):
        raise ValueError("لینک یا متن مشکوک در قانون مجاز نیست.")
    return b


def validate_statement(body: str) -> str:
    b = (body or "").strip()
    if len(b) < 3:
        raise ValueError("متن بیانیه خیلی کوتاه است.")
    if len(b) > 2500:
        raise ValueError("متن بیانیه حداکثر ۲۵۰۰ کاراکتر است.")
    if _URL_RE.search(b):
        raise ValueError("لینک، آدرس وب یا نام‌کاربری در بیانیه مجاز نیست.")
    if _REPEAT_RE.search(b) and not _has_meaningful_persian(b, 8):
        raise ValueError("متن بیانیه نامعتبر یا اسپم به‌نظر می‌رسد.")
    if not _char_diversity_ok(b):
        raise ValueError("متن بیانیه بیش از حد تکراری است.")
    # short statements allowed if they have some letters
    if len(b) < 20 and not _has_meaningful_persian(b, 2):
        raise ValueError("بیانیه باید متن قابل فهم داشته باشد.")
    return b
