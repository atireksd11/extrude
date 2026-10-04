"""The model seat reports a provider rejection instead of hiding it."""

from io import BytesIO
from unittest.mock import patch
import urllib.error

import pytest

from extrude.harness.client import complete
from extrude.harness.proposal import ProposalError


def test_angle_brackets_around_the_key_are_refused(monkeypatch):
    monkeypatch.setenv("EXTRUDE_MODEL_KEY", "<test-key>")
    monkeypatch.setenv("EXTRUDE_MODEL", "openai/gpt-6-luna")
    with patch("extrude.harness.client.urllib.request.urlopen") as opened:
        with pytest.raises(ProposalError, match="angle brackets") as caught:
            complete("hello", "primary")
    opened.assert_not_called()
    assert caught.value.kind == "tool"


def test_a_provider_rejection_names_the_status(monkeypatch):
    monkeypatch.setenv("EXTRUDE_MODEL_KEY", "test-key")
    monkeypatch.setenv("EXTRUDE_MODEL", "openai/gpt-6-luna")
    monkeypatch.setenv("EXTRUDE_MODEL_URL", "https://openrouter.ai/api/v1/chat/completions")
    error = urllib.error.HTTPError(
        url="https://openrouter.ai/api/v1/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=BytesIO(b'{"error":{"message":"Missing Authentication header"}}'),
    )
    with patch("extrude.harness.client.urllib.request.urlopen", side_effect=error):
        with pytest.raises(ProposalError, match="401: Missing Authentication header") as caught:
            complete("hello", "primary")
    assert caught.value.kind == "tool"
