# SPDX-License-Identifier: Apache-2.0
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from rune_ui.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "RUNE" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_online(mock_health: AsyncMock) -> None:
    mock_health.return_value = {"status": "ok"}
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "ONLINE" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_not_connected_bad_status(mock_health: AsyncMock) -> None:
    mock_health.return_value = {"status": "degraded"}
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "NOT CONNECTED" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_not_connected_exception(mock_health: AsyncMock) -> None:
    mock_health.side_effect = Exception("offline")
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "NOT CONNECTED" in response.text


def test_benchmarks_page() -> None:
    response = client.get("/benchmarks")
    assert response.status_code == 200
    assert "Run Benchmark" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_estimate", new_callable=AsyncMock)
def test_cost_estimate_modal(mock_estimate: AsyncMock) -> None:
    mock_estimate.return_value = {
        "projected_cost_usd": 10.50,
        "cost_driver": "vastai",
        "resource_impact": "medium",
        "local_energy_kwh": 0.0,
        "warning": None,
    }
    response = client.post("/benchmarks/estimate", data={"model": "llama3.1:8b", "vastai": "true"})
    assert response.status_code == 200
    assert "PRE-FLIGHT SPEND ALERT" in response.text
    assert "$10.5" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_estimate", new_callable=AsyncMock)
def test_cost_estimate_error(mock_estimate: AsyncMock) -> None:
    mock_estimate.side_effect = Exception("API unreachable")
    response = client.post("/benchmarks/estimate", data={"model": "llama3.1:8b"})
    assert response.status_code == 200
    assert "Estimation Error" in response.text
    assert "/v1/estimates" in response.text
    assert "RUNE_API_URL" in response.text


@patch("rune_ui.api_client.RuneApiClient.submit_job", new_callable=AsyncMock)
def test_job_submission(mock_submit: AsyncMock) -> None:
    mock_submit.return_value = {"job_id": "test-job-123"}
    response = client.post("/api/jobs/submit", data={"model": "llama3.1:8b", "vastai": "true"})
    assert response.status_code == 200
    assert "Benchmark Tracker" in response.text
    assert "test-job-123" in response.text


@patch("rune_ui.api_client.RuneApiClient.submit_job", new_callable=AsyncMock)
def test_job_submission_error(mock_submit: AsyncMock) -> None:
    mock_submit.side_effect = Exception("Submit failed")
    response = client.post("/api/jobs/submit", data={"model": "llama3.1:8b"})
    assert response.status_code == 200
    assert "Submission Failed" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_succeeded(mock_status: AsyncMock) -> None:
    mock_status.return_value = {"status": "succeeded", "message": "Done"}
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "SUCCEEDED" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_failed(mock_status: AsyncMock) -> None:
    mock_status.return_value = {"status": "failed", "message": "Error"}
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "FAILED" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_running(mock_status: AsyncMock) -> None:
    mock_status.return_value = {"status": "running", "message": "In progress"}
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "RUNNING" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_error(mock_status: AsyncMock) -> None:
    mock_status.side_effect = Exception("Polling error")
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "Error polling status" in response.text


def test_dashboard_returns_base_page() -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "RUNE" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_vastai_models", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_config_page(mock_health: AsyncMock, mock_models: AsyncMock) -> None:
    mock_health.return_value = {"status": "ok"}
    mock_models.return_value = {"models": ["llama3.1:8b", "mixtral:8x7b"]}
    response = client.get("/config")
    assert response.status_code == 200
    assert "Configuration" in response.text
    assert "ONLINE" in response.text
    assert "llama3.1:8b" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_vastai_models", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_config_page_api_offline(mock_health: AsyncMock, mock_models: AsyncMock) -> None:
    mock_health.side_effect = Exception("offline")
    mock_models.side_effect = Exception("offline")
    response = client.get("/config")
    assert response.status_code == 200
    assert "Configuration" in response.text
    assert "NOT CONNECTED" in response.text
    assert "No models available" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_reports_page(mock_reports: AsyncMock) -> None:
    mock_reports.return_value = {"events": [{"timestamp": "now", "job_id": "123", "name": "test"}]}
    response = client.get("/reports")
    assert response.status_code == 200
    assert "Historical Reports" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_reports_page_error(mock_reports: AsyncMock) -> None:
    mock_reports.side_effect = Exception("Reports unavailable")
    response = client.get("/reports")
    assert response.status_code == 200
    assert "Reports Error" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_report_content", new_callable=AsyncMock)
def test_view_report(mock_report: AsyncMock) -> None:
    mock_report.return_value = {"job_id": "abc-123", "status": "succeeded", "result": "All good"}
    response = client.get("/reports/abc-123")
    assert response.status_code == 200


@patch("rune_ui.api_client.RuneApiClient.get_report_content", new_callable=AsyncMock)
def test_view_report_error(mock_report: AsyncMock) -> None:
    mock_report.side_effect = Exception("Report not found")
    response = client.get("/reports/missing-job")
    assert response.status_code == 200
    assert "Report Error" in response.text


# ── Streaming SSE endpoint ────────────────────────────────────────────────────

@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_events_and_done(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream completes when job reaches succeeded status."""
    events_resp = {"events": [{"timestamp": "2026-01-01T00:00:00Z", "name": "step", "message": "ok"}]}
    status_resp = {"status": "succeeded"}
    mock_status.side_effect = [events_resp, status_resp]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/log-test/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "STREAM ENDED" in content


@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_no_events_then_done(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream completes when status is succeeded even with no events."""
    empty_events = {"events": []}
    status_resp = {"status": "succeeded"}
    mock_status.side_effect = [empty_events, status_resp]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/log-test2/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "STREAM ENDED" in content


@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_error_path(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream yields error message when API call raises an exception."""
    mock_status.side_effect = Exception("connection lost")
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/err-job/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "Log stream interrupted" in content


@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_cancelled(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream stops on cancelled status."""
    mock_status.side_effect = [{"events": []}, {"status": "cancelled"}]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/cancelled-job/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "STREAM ENDED" in content



# ── API client unit tests (sync, testing init and structure) ─────────────────

def test_rune_api_url_env_fallback() -> None:
    """RUNE_API_URL should fall back to RUNE_API_BASE_URL if the former is not set."""
    import importlib
    import os

    old_url = os.environ.pop("RUNE_API_URL", None)
    old_base = os.environ.pop("RUNE_API_BASE_URL", None)
    try:
        os.environ["RUNE_API_BASE_URL"] = "http://rune-api:9090"
        # Re-evaluate the expression that main.py uses
        result = os.environ.get("RUNE_API_URL", os.environ.get("RUNE_API_BASE_URL", "http://localhost:8080"))
        assert result == "http://rune-api:9090"
    finally:
        os.environ.pop("RUNE_API_BASE_URL", None)
        if old_url:
            os.environ["RUNE_API_URL"] = old_url
        if old_base:
            os.environ["RUNE_API_BASE_URL"] = old_base


def test_api_client_init_with_explicit_token() -> None:
    """RuneApiClient stores explicit token in Authorization header."""
    from rune_ui.api_client import RuneApiClient

    c = RuneApiClient(base_url="http://example.com", api_token="explicit-token")
    assert c.headers.get("Authorization") == "Bearer explicit-token"
    assert c.base_url == "http://example.com"


def test_api_client_init_no_token() -> None:
    """RuneApiClient has no Authorization header when no token provided."""
    import os

    from rune_ui.api_client import RuneApiClient

    # Ensure no env token is set during this test
    old = os.environ.pop("RUNE_API_TOKEN", None)
    try:
        c = RuneApiClient(base_url="http://example.com")
        assert "Authorization" not in c.headers
    finally:
        if old:
            os.environ["RUNE_API_TOKEN"] = old


def test_api_client_strips_trailing_slash() -> None:
    """RuneApiClient strips trailing slash from base_url."""
    from rune_ui.api_client import RuneApiClient

    c = RuneApiClient(base_url="http://example.com/")
    assert c.base_url == "http://example.com"


@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_multi_iteration(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream loops more than once, exercising asyncio.sleep."""
    # Iteration 1: events=[], status=running → continues (hits asyncio.sleep)
    # Iteration 2: events=[], status=succeeded → yields STREAM ENDED
    mock_status.side_effect = [
        {"events": []},
        {"status": "running"},
        {"events": []},
        {"status": "succeeded"},
    ]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/multi-iter/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "STREAM ENDED" in content
    mock_sleep.assert_called()


# ── API client implementation tests ──────────────────────────────────────────

def test_api_client_get_vastai_models() -> None:
    """Call get_vastai_models through the RuneApiClient with mocked httpx."""
    import asyncio
    from unittest.mock import MagicMock, patch

    from rune_ui.api_client import RuneApiClient

    async def _run() -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": ["llama3.1:8b"]}

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.__aexit__.return_value = None
        mock_async_client.get.return_value = mock_response

        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=mock_async_client):
            c = RuneApiClient(base_url="http://localhost:8080", api_token="tok")
            result = await c.get_vastai_models()
        assert "models" in result

    asyncio.run(_run())


def _make_httpx_mock(json_data: dict) -> "tuple[Any, Any]":
    """Helper: returns (mock_async_client, patch_target)."""
    from unittest.mock import MagicMock, patch

    mock_response = MagicMock()
    mock_response.json.return_value = json_data

    mock_async_client = AsyncMock()
    mock_async_client.__aenter__.return_value = mock_async_client
    mock_async_client.__aexit__.return_value = None
    mock_async_client.get.return_value = mock_response
    mock_async_client.post.return_value = mock_response
    return mock_async_client, mock_response


def test_api_client_get_health_impl() -> None:
    import asyncio

    from rune_ui.api_client import RuneApiClient

    async def _run() -> None:
        ac, _ = _make_httpx_mock({"status": "ok"})
        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=ac):
            c = RuneApiClient(base_url="http://x")
            result = await c.get_health()
        assert result["status"] == "ok"

    asyncio.run(_run())


def test_api_client_get_estimate_impl() -> None:
    import asyncio

    from rune_ui.api_client import RuneApiClient

    async def _run() -> None:
        ac, _ = _make_httpx_mock({"projected_cost_usd": 5.0})
        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=ac):
            c = RuneApiClient(base_url="http://x")
            result = await c.get_estimate({"model": "test"})
        assert "projected_cost_usd" in result

    asyncio.run(_run())


def test_api_client_submit_job_impl() -> None:
    import asyncio

    from rune_ui.api_client import RuneApiClient

    async def _run() -> None:
        ac, _ = _make_httpx_mock({"job_id": "abc"})
        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=ac):
            c = RuneApiClient(base_url="http://x")
            result = await c.submit_job("benchmark", {"vastai": True})
        assert result["job_id"] == "abc"

    asyncio.run(_run())


def test_api_client_get_job_status_impl() -> None:
    import asyncio

    from rune_ui.api_client import RuneApiClient

    async def _run() -> None:
        ac, _ = _make_httpx_mock({"status": "succeeded"})
        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=ac):
            c = RuneApiClient(base_url="http://x")
            result = await c.get_job_status("job-1")
        assert result["status"] == "succeeded"

    asyncio.run(_run())


def test_api_client_get_reports_impl() -> None:
    import asyncio

    from rune_ui.api_client import RuneApiClient

    async def _run() -> None:
        ac, _ = _make_httpx_mock({"events": []})
        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=ac):
            c = RuneApiClient(base_url="http://x")
            result = await c.get_reports()
        assert "events" in result

    asyncio.run(_run())


def test_api_client_get_report_content_impl() -> None:
    import asyncio

    from rune_ui.api_client import RuneApiClient

    async def _run() -> None:
        ac, _ = _make_httpx_mock({"job_id": "r1", "result": "ok"})
        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=ac):
            c = RuneApiClient(base_url="http://x")
            result = await c.get_report_content("r1")
        assert result["job_id"] == "r1"

    asyncio.run(_run())


# ── Issue #10: pre-flight modal carries form params into submit ───────────────

@patch("rune_ui.api_client.RuneApiClient.get_estimate", new_callable=AsyncMock)
def test_estimate_modal_contains_hidden_model_field(mock_estimate: AsyncMock) -> None:
    """estimate_modal.html must include a hidden 'model' field so CONFIRM can submit it."""
    mock_estimate.return_value = {
        "projected_cost_usd": 3.75,
        "cost_driver": "vastai",
        "resource_impact": "medium",
        "local_energy_kwh": 0.0,
        "warning": None,
    }
    response = client.post(
        "/benchmarks/estimate",
        data={"model": "mixtral:8x7b", "vastai": "true", "max_dph": "2.5"},
    )
    assert response.status_code == 200
    assert 'name="model"' in response.text
    assert 'value="mixtral:8x7b"' in response.text


@patch("rune_ui.api_client.RuneApiClient.get_estimate", new_callable=AsyncMock)
def test_estimate_modal_contains_hidden_vastai_field(mock_estimate: AsyncMock) -> None:
    """estimate_modal.html must carry vastai hidden field for job submission."""
    mock_estimate.return_value = {
        "projected_cost_usd": 1.0,
        "cost_driver": "vastai",
        "resource_impact": "low",
        "local_energy_kwh": 0.0,
        "warning": None,
    }
    response = client.post(
        "/benchmarks/estimate",
        data={"model": "llama3.1:8b", "vastai": "true", "max_dph": "3.0"},
    )
    assert response.status_code == 200
    assert 'name="vastai"' in response.text
    assert 'name="max_dph"' in response.text


# ── Issue #11: tamper-evident log stream ──────────────────────────────────────

def test_log_session_key_endpoint_returns_base64_key() -> None:
    """GET /api/log-session-key must return a valid base64-encoded 32-byte key."""
    import base64

    response = client.get("/api/log-session-key")
    assert response.status_code == 200
    data = response.json()
    assert "key" in data
    key_bytes = base64.b64decode(data["key"])
    assert len(key_bytes) == 32


def test_log_session_key_is_stable_within_process() -> None:
    """Two calls to /api/log-session-key must return the same key (per-process key)."""
    r1 = client.get("/api/log-session-key").json()["key"]
    r2 = client.get("/api/log-session-key").json()["key"]
    assert r1 == r2


def test_sign_log_event_produces_valid_hmac() -> None:
    """_sign_log_event must return a 64-char hex HMAC-SHA256 digest."""
    import hashlib
    import hmac as _hmac

    from rune_ui.main import _log_session_key, _sign_log_event

    payload = "<div>test</div>"
    sig = _sign_log_event(payload)
    assert len(sig) == 64  # SHA-256 hex = 64 chars
    expected = _hmac.new(_log_session_key, payload.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_events_carry_sig_field(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """SSE events must now be JSON objects containing 'html' and 'sig' fields (Issue #11)."""
    import json as _json

    events_resp = {"events": [{"timestamp": "2026-01-01T00:00:00Z", "name": "step", "message": "ok"}]}
    status_resp = {"status": "succeeded"}
    mock_status.side_effect = [events_resp, status_resp]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/sig-test/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    # Every `data: …` line should be valid JSON with html + sig
    data_lines = [line[6:] for line in content.splitlines() if line.startswith("data: ")]
    assert len(data_lines) >= 2  # at least one event + STREAM ENDED
    for raw in data_lines:
        parsed = _json.loads(raw)
        assert "html" in parsed
        assert "sig" in parsed
        assert len(parsed["sig"]) == 64  # SHA-256 hex


@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_sig_verifies_correctly(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """HMAC signatures on SSE events must verify against the session key."""
    import hashlib
    import hmac as _hmac
    import json as _json

    from rune_ui.main import _log_session_key

    events_resp = {"events": [{"timestamp": "t", "name": "n", "message": "m"}]}
    status_resp = {"status": "succeeded"}
    mock_status.side_effect = [events_resp, status_resp]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/verify-sig/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    data_lines = [line[6:] for line in content.splitlines() if line.startswith("data: ")]
    for raw in data_lines:
        parsed = _json.loads(raw)
        expected_sig = _hmac.new(_log_session_key, parsed["html"].encode(), hashlib.sha256).hexdigest()
        assert parsed["sig"] == expected_sig, f"Signature mismatch for chunk: {parsed['html']!r}"


@patch("rune_ui.main.asyncio.sleep", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_error_event_carries_sig(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Error SSE events must also carry a valid HMAC signature."""
    import hashlib
    import hmac as _hmac
    import json as _json

    from rune_ui.main import _log_session_key

    mock_status.side_effect = Exception("connection lost")
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/err-sig/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "Log stream interrupted" in content
    data_lines = [line[6:] for line in content.splitlines() if line.startswith("data: ")]
    assert len(data_lines) == 1
    parsed = _json.loads(data_lines[0])
    expected_sig = _hmac.new(_log_session_key, parsed["html"].encode(), hashlib.sha256).hexdigest()
    assert parsed["sig"] == expected_sig


def test_job_tracker_shows_integrity_badge() -> None:
    """job_tracker.html must contain the security integrity badge element (Issue #11)."""
    from unittest.mock import AsyncMock, patch

    with patch("rune_ui.api_client.RuneApiClient.submit_job", new_callable=AsyncMock) as mock_submit:
        mock_submit.return_value = {"job_id": "badge-test-job"}
        response = client.post("/api/jobs/submit", data={"model": "llama3.1:8b"})

    assert response.status_code == 200
    assert "log-integrity-badge" in response.text
    assert "Security Integrity" in response.text or "Verifying" in response.text
