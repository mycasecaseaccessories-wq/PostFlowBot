"""Deterministic per-route text transformations for repost payloads."""
from __future__ import annotations

import re
from collections.abc import Iterable

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\bt\.me/\S+")
_USERNAME_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{5,}")
_SPACE_RE = re.compile(r"[ \t]{2,}")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def transform_text(
    text: str | None, *, remove_usernames: bool = False,
    remove_links: bool = False, remove_keywords: str | Iterable[str] | None = None,
) -> str:
    """Apply only the transformations enabled on one RepostRule.

    Keyword values are comma/newline separated when supplied as a string.
    Matching is case-insensitive and literal (not interpreted as regex).
    """
    value = text or ""
    if remove_usernames:
        value = _USERNAME_RE.sub("", value)
    if remove_links:
        value = _URL_RE.sub("", value)
    if isinstance(remove_keywords, str):
        keywords = [part.strip() for part in re.split(r"[,\n]", remove_keywords)]
    else:
        keywords = [str(part).strip() for part in (remove_keywords or ())]
    for keyword in sorted((k for k in keywords if k), key=len, reverse=True):
        value = re.sub(re.escape(keyword), "", value, flags=re.IGNORECASE)
    value = _SPACE_RE.sub(" ", value)
    value = _BLANK_LINES_RE.sub("\n\n", value)
    return "\n".join(line.strip() for line in value.splitlines()).strip()
