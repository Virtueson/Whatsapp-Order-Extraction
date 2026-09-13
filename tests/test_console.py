import sys

from app.console import enable_utf8_output


def test_stdout_encoding_becomes_utf8():
    enable_utf8_output()
    assert sys.stdout.encoding.lower().replace("-", "") == "utf8"


def test_calling_twice_is_safe():
    enable_utf8_output()
    enable_utf8_output()
    assert sys.stdout.encoding.lower().replace("-", "") == "utf8"


def test_does_not_raise_on_a_stream_without_reconfigure(monkeypatch):
    class DumbStream:
        """Stands in for a stream that another tool has already wrapped."""

    monkeypatch.setattr(sys, "stdout", DumbStream())
    monkeypatch.setattr(sys, "stderr", DumbStream())
    enable_utf8_output()  # must not raise
