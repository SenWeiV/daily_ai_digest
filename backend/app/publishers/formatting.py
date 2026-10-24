"""Format platform copy for readable copy/paste output.

Formatting only inserts paragraph breaks around existing sentence and list boundaries.
It never removes content or changes facts; the validated character budget is checked
against the formatted draft by the normal publisher validation path.
"""

from __future__ import annotations

import re

from app.publishers.validation import CopyDraft


_CJK_BREAK = re.compile(r"([。！？!?])\s*")
_EN_BREAK = re.compile(r"(?<!\.)\.\s+(?=[A-Z0-9#])")
_LIST_BREAK = re.compile(r"\s+(?=(?:[-*•]|\d+[.)])\s+)")


def format_body(platform: str, text: str) -> str:
    """Insert readable paragraph breaks without shortening the body."""
    body = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not body:
        return ""

    body = _LIST_BREAK.sub("\n", body)
    if "\n" not in body:
        body = _CJK_BREAK.sub(r"\1\n\n", body)
        body = _EN_BREAK.sub(".\n\n", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def format_draft(draft: CopyDraft) -> CopyDraft:
    """Return a copy-ready draft with paragraph boundaries made explicit."""
    thread = tuple(format_body("x", part) for part in draft.thread)
    body = "\n\n".join(thread) if thread else format_body(draft.platform, draft.body)
    return CopyDraft(
        platform=draft.platform,
        title=draft.title.strip(),
        body=body,
        hashtags=draft.hashtags,
        thread=thread,
    )
