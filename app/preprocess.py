"""Text cleaning. Pure functions - no I/O, no network, fully testable.

The single most important rule: newlines are PRESERVED. In list-form
messages the newline is the item delimiter, and flattening it destroys
the strongest structural signal we have.

Debug:  python -m app.preprocess "Fish fillet-5ctn"
"""

import re
import sys
import unicodedata

# Whitespace-ish characters that should become a plain space.
_SPACE_LIKE = "\t\u00a0\u3000\u2002\u2003\u2009"

# Invisible characters that should be deleted outright.
_ZERO_WIDTH = "\u200b\u200c\u200d\ufeff"

_MULTI_SPACE = re.compile(r" {2,}")

# CJK Unified Ideographs - enough to detect Mandarin for logging purposes.
_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_LATIN = re.compile(r"[A-Za-z]")


def preprocess(text: str, max_chars: int = 4000) -> str:
    """Normalize a raw WhatsApp message for the LLM.

    Rules, in order:
      1. Unicode NFKC normalize   (full-width 5 -> 5, full-width comma -> ,)
      2. CRLF and bare CR -> LF
      3. tab / NBSP / ideographic space -> space; zero-width chars removed
      4. collapse runs of spaces -> one space
      5. strip each line
      6. drop empty lines
      7. truncate at max_chars
    """
    if not text:
        return ""

    s = unicodedata.normalize("NFKC", text)

    s = s.replace("\r\n", "\n").replace("\r", "\n")

    for ch in _ZERO_WIDTH:
        s = s.replace(ch, "")
    for ch in _SPACE_LIKE:
        s = s.replace(ch, " ")

    lines = []
    for line in s.split("\n"):
        line = _MULTI_SPACE.sub(" ", line).strip()
        if line:
            lines.append(line)

    s = "\n".join(lines)

    if len(s) > max_chars:
        s = s[:max_chars]

    return s


def detect_script(text: str) -> str:
    """Which writing systems the message uses. For the log only.

    Returns "latin", "cjk", "latin+cjk", or "none".

    This is deliberately NOT language identification. It reports scripts
    because that is all a character-range check can honestly tell you: a
    Malay message is Latin script, not English, and "我要5箱Milo" is a Chinese
    message that happens to contain a brand name. Nothing in the pipeline
    branches on this value - the LLM handles every language from one prompt.
    """
    if not text:
        return "none"
    has_cjk = bool(_CJK.search(text))
    has_latin = bool(_LATIN.search(text))
    if has_cjk and has_latin:
        return "latin+cjk"
    if has_cjk:
        return "cjk"
    if has_latin:
        return "latin"
    return "none"


if __name__ == "__main__":
    from app.console import enable_utf8_output

    enable_utf8_output()
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    cleaned = preprocess(raw)
    print("--- RAW ---")
    print(repr(raw))
    print("--- PREPROCESSED (repr, so you can see the newlines) ---")
    print(repr(cleaned))
    print("--- PREPROCESSED (readable) ---")
    print(cleaned)
    print("--- SCRIPT ---")
    print(detect_script(cleaned))
