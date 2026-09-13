"""Make console output safe for Mandarin on Windows.

Python on Windows encodes stdout using the legacy code page (cp1252 here),
so `print("苹果")` raises UnicodeEncodeError. Every CLI debug entrypoint
calls enable_utf8_output() first so the debug commands work with Mandarin
messages, which is half of what this service handles.

This is deliberately separate from the file-encoding rule: file opens pass
encoding="utf-8" explicitly, but stdout is configured by the interpreter
and has to be re-pointed at runtime.
"""

import sys


def enable_utf8_output() -> None:
    """Switch stdout/stderr to UTF-8. Safe to call more than once.

    Silently does nothing on streams that cannot be reconfigured (for
    example when output is already wrapped by another tool).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            # Stream is detached or not reconfigurable. Printing ASCII still works.
            pass
