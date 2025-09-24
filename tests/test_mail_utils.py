from __future__ import annotations

import pytest

from app.shared.mail_utils import normalize_recipients


@pytest.mark.no_smoke
def test_normalize_recipients_comma_separated():
    envelope, header = normalize_recipients("a@x.com, b@y.com")

    assert envelope == ["a@x.com", "b@y.com"]
    assert header == "a@x.com, b@y.com"


@pytest.mark.no_smoke
def test_normalize_recipients_semicolon_separated():
    envelope, header = normalize_recipients("a@x.com; b@y.com ;")

    assert envelope == ["a@x.com", "b@y.com"]
    assert header == "a@x.com, b@y.com"


@pytest.mark.no_smoke
def test_normalize_recipients_list_dedup_preserves_order():
    envelope, header = normalize_recipients(["A@X.com", "a@x.com", "b@y.com"])

    assert envelope == ["A@X.com", "b@y.com"]
    assert header == "A@X.com, b@y.com"


@pytest.mark.no_smoke
def test_normalize_recipients_drops_invalid(caplog):
    caplog.set_level("WARNING", logger="cbs.mailer")

    envelope, header = normalize_recipients("bad, ok@x.com")

    assert envelope == ["ok@x.com"]
    assert header == "ok@x.com"
    assert any("[MAIL-INVALID-RECIPIENT]" in message for message in caplog.messages)
