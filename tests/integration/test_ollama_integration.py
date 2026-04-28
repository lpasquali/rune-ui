"""Live checks against Ollama for rune-ui CI (rune-ci python-integration workflow).

Skipped locally unless OLLAMA_TEST_URL is set. In GitHub Actions the
RuneGate/Ollama-Integration job sets OLLAMA_TEST_URL and OLLAMA_TEST_MODEL.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.integration

_OLLAMA_URL = os.environ.get("OLLAMA_TEST_URL", "").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_TEST_MODEL", "tinyllama")


@pytest.fixture(scope="module")
def ollama_url() -> str:
    if not _OLLAMA_URL:
        pytest.skip("OLLAMA_TEST_URL not set — skipping live Ollama integration tests")
    return _OLLAMA_URL


def test_ollama_api_tags_lists_pulled_model(ollama_url: str) -> None:
    """Ensure the CI-pulled model is visible (validates Ollama is up and pull succeeded)."""
    req = urllib.request.Request(f"{ollama_url}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            assert resp.status == 200
            data = json.load(resp)
    except urllib.error.URLError as exc:
        pytest.fail(f"Ollama /api/tags unreachable: {exc}")

    models = data.get("models") or []
    names = [str(m.get("name", "")) for m in models]
    base = _OLLAMA_MODEL.split(":")[0].lower()
    assert any(base in n.lower() for n in names), (
        f"expected model containing {base!r} in Ollama tags; got {names!r}"
    )
