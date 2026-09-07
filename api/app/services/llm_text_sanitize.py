"""Sanitize LLM output that leaks native tool-call markup into plain text.

Zhipu GLM / DeepSeek occasionally emit internal DSML / tool-call syntax as
ordinary ``content`` instead of structured ``tool_calls``, e.g.::

    <|DSML|tool_calls>
      <|DSML|invoke name="search_literatureDB">
        <|DSML|parameter name="query" string="true">MYB60</|DSML|parameter>
      </|DSML|invoke>
    </|DSML|tool_calls>

Variants seen in the wild:
  - ASCII pipes ``|`` or fullwidth ``｜`` (U+FF5C)
  - **Double pipes** ``||`` (e.g. ``<||DSML||parameter …>``) — critical
  - Optional spaces: ``<| DSML | tool_calls>`` / ``< || DSML || parameter>``
  - Invoke / parameter blocks without a wrapping ``tool_calls`` envelope
  - Truncated / unclosed blocks at end of stream

When such text is rendered with Markdown it shows up as a broken DSML blob.
This module strips those blocks so users never see them.
"""

from __future__ import annotations

import re
from typing import Optional

# Normalize fullwidth / lookalike pipes to ASCII before matching.
_PIPE_TRANSLATE = str.maketrans({
    "\uff5c": "|",  # FULLWIDTH VERTICAL LINE ｜
    "\u2223": "|",  # DIVIDES ∣
    "\u2502": "|",  # BOX DRAWINGS LIGHT VERTICAL │
    "\uffe8": "|",  # HALFWIDTH FORMS LIGHT VERTICAL
})

# One or more pipes (single or double). Keep this simple — avoid
# nested optional quantifiers that can ReDoS under pathological input.
_PIPES = r"\|+"

# Complete closed DSML tool-call envelope.
_DSML_BLOCK_RE = re.compile(
    rf"<\s*{_PIPES}\s*DSML\s*{_PIPES}\s*tool_calls\s*>"
    rf".*?"
    rf"<\s*/\s*{_PIPES}\s*DSML\s*{_PIPES}\s*tool_calls\s*>",
    re.DOTALL | re.IGNORECASE,
)

# Standalone invoke block (sometimes without the tool_calls wrapper).
_DSML_INVOKE_BLOCK_RE = re.compile(
    rf"<\s*{_PIPES}\s*DSML\s*{_PIPES}\s*invoke\b[^>]*>"
    rf".*?"
    rf"<\s*/\s*{_PIPES}\s*DSML\s*{_PIPES}\s*invoke\s*>",
    re.DOTALL | re.IGNORECASE,
)

# Standalone parameter block — the fragment users saw in chat.
_DSML_PARAMETER_BLOCK_RE = re.compile(
    rf"<\s*{_PIPES}\s*DSML\s*{_PIPES}\s*parameter\b[^>]*>"
    rf".*?"
    rf"<\s*/\s*{_PIPES}\s*DSML\s*{_PIPES}\s*parameter\s*>",
    re.DOTALL | re.IGNORECASE,
)

# Any remaining orphan open/close DSML tag (tool_calls / invoke / parameter / …).
_DSML_TAG_RE = re.compile(
    rf"<\s*/?\s*{_PIPES}\s*DSML\b[^>]*>",
    re.IGNORECASE,
)

# Start of a DSML region — used by the stream filter to hold back output.
_DSML_START_RE = re.compile(
    rf"<\s*{_PIPES}\s*DSML\b",
    re.IGNORECASE,
)

# Loose "DSML next to pipes" marker (covers broken / spaced-out forms).
_DSML_PIPE_MARKER_RE = re.compile(
    rf"(?:<\s*{_PIPES}\s*DSML)|(?:{_PIPES}\s*DSML)|(?:DSML\s*{_PIPES})",
    re.IGNORECASE,
)


def _normalize_pipes(text: str) -> str:
    return text.translate(_PIPE_TRANSLATE) if text else text


# Leftover "thinking out loud" that usually precedes a leaked tool call, e.g.
# "Now let me search the literature database…". After DSML is stripped these
# orphan sentences look like the final answer — they are not.
_TOOL_NARRATION_RE = re.compile(
    r"(?:"
    r"(?:^|\n)\s*(?:Now\s+)?(?:Let\s+me|I'll|I\s+will|I\s+am\s+going\s+to)\s+"
    r"(?:also\s+)?(?:search|check|call|look\s+up|query|fetch|retrieve|use|try|"
    r"run|invoke|ask)\b[^\n]*"
    r"|"
    r"(?:^|\n)\s*(?:让我|我来|我再|接下来(?:我)?(?:将|会)?)\s*"
    r"(?:也)?(?:搜索|查询|检索|调用|查一下|看一下|获取)[^\n]*"
    r")",
    re.IGNORECASE,
)


def strip_tool_call_narration(text: str) -> str:
    """Remove orphan tool-call preamble sentences left after DSML stripping."""
    if not text:
        return text
    cleaned = _TOOL_NARRATION_RE.sub("", text)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def sanitize_assistant_text(text: str) -> str:
    """Full cleanup for user-visible assistant text (DSML + narration)."""
    return strip_tool_call_narration(strip_dsml_markup(text or "")).strip()


def answer_is_insufficient(text: str, *, min_chars: int = 80) -> bool:
    """True when filtered final text is empty or only a tool-call preamble."""
    t = (text or "").strip()
    if len(t) < min_chars:
        return True
    # Still looks like a single "let me …" intent line.
    if _TOOL_NARRATION_RE.fullmatch(t):
        return True
    return False


def strip_dsml_markup(text: str) -> str:
    """Remove complete (and leftover orphan) DSML tool-call markup from text."""
    if not text:
        return text
    keep_leading_ws = text[: len(text) - len(text.lstrip(" \t"))]
    keep_trailing_nl = text.endswith("\n")

    cleaned = _normalize_pipes(text)
    cleaned = _DSML_BLOCK_RE.sub("", cleaned)
    cleaned = _DSML_INVOKE_BLOCK_RE.sub("", cleaned)
    cleaned = _DSML_PARAMETER_BLOCK_RE.sub("", cleaned)

    # Unclosed / incomplete opener (e.g. `<||DSML||parameter …>payload` with no
    # close tag): cut from the opener so the payload never reaches the UI.
    m = _DSML_START_RE.search(cleaned)
    if m:
        cleaned = cleaned[: m.start()]
    else:
        cleaned = _DSML_TAG_RE.sub("", cleaned)
        m2 = _DSML_PIPE_MARKER_RE.search(cleaned)
        if m2:
            cleaned = cleaned[: m2.start()]
        elif re.search(r"\bDSML\b", cleaned, re.I):
            # Last resort: drop any line that still mentions DSML markup roles.
            cleaned = "\n".join(
                line
                for line in cleaned.split("\n")
                if not re.search(
                    r"\bDSML\b.*\b(tool_calls|invoke|parameter)\b"
                    r"|\b(tool_calls|invoke|parameter)\b.*\bDSML\b",
                    line,
                    re.I,
                )
            )

    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip(" \t")
    if keep_trailing_nl and cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    return keep_leading_ws + cleaned if cleaned else cleaned


class DsmlStreamFilter:
    """Streaming-safe filter: hold back partial / in-progress DSML regions.

    Usage::

        filt = DsmlStreamFilter()
        for chunk in stream:
            safe = filt.feed(chunk)
            if safe:
                yield safe
        tail = filt.flush()
        if tail:
            yield tail
    """

    # Trailing prefixes that might still grow into a DSML opener. Checked
    # against the *normalized* buffer tail.
    _OPEN_PREFIXES = (
        "<",
        "<|",
        "<||",
        "<|||",
        "<|D",
        "<||D",
        "<|DS",
        "<||DS",
        "<|DSM",
        "<||DSM",
        "<|DSML",
        "<||DSML",
        "<|DSML|",
        "<||DSML|",
        "<||DSML||",
        "< |",
        "< ||",
        "< | ",
        "< || ",
        "< | |",
        "< || ||",
        "< | | ",
        "< | | D",
        "< | | DS",
        "< | | DSM",
        "< | | DSML",
        "< || || D",
        "< || || DS",
        "< || || DSM",
        "< || || DSML",
    )

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        normalized = _normalize_pipes(self._buf)

        # Drop any complete blocks already present.
        cleaned = _DSML_BLOCK_RE.sub("", normalized)
        cleaned = _DSML_INVOKE_BLOCK_RE.sub("", cleaned)
        cleaned = _DSML_PARAMETER_BLOCK_RE.sub("", cleaned)

        # If an open DSML region started but hasn't fully closed, hold it.
        m = _DSML_START_RE.search(cleaned)
        if m:
            head = _DSML_TAG_RE.sub("", cleaned[: m.start()])
            self._buf = cleaned[m.start() :]
            return head

        # Hold back a trailing prefix that might still grow into a DSML opener.
        hold_from: Optional[int] = None
        last_lt = cleaned.rfind("<")
        if last_lt >= 0:
            tail = cleaned[last_lt:]
            if (
                tail in self._OPEN_PREFIXES
                or (
                    tail.startswith("<")
                    and ">" not in tail
                    and len(tail) < 64
                    and re.match(r"^<\s*\|*\s*D?S?M?L?", tail, re.I)
                )
            ):
                hold_from = last_lt

        if hold_from is not None:
            emit, self._buf = cleaned[:hold_from], cleaned[hold_from:]
            return emit

        # No DSML in flight — emit cleaned text (orphan tags scrubbed).
        self._buf = ""
        return _DSML_TAG_RE.sub("", cleaned)

    def flush(self) -> str:
        leftover = self._buf
        self._buf = ""
        if not leftover:
            return ""
        return sanitize_assistant_text(leftover)
