from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "RUNE" in response.text


@patch("app.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_online(mock_health: AsyncMock) -> None:
    mock_health.return_value = {"status": "ok"}
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "ONLINE" in response.text


@patch("app.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_degraded(mock_health: AsyncMock) -> None:
    mock_health.return_value = {"status": "degraded"}
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "DEGRADED" in response.text


@patch("app.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_offline(mock_health: AsyncMock) -> None:
    mock_health.side_effect = Exception("offline")
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "OFFLINE" in response.text


def test_benchmarks_page() -> None:
    response = client.get("/benchmarks")
    assert response.status_code == 200
    assert "Run Benchmark" in response.text


@patch("app.api_client.RuneApiClient.get_estimate", new_callable=AsyncMock)
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


@patch("app.api_client.RuneApiClient.get_estimate", new_callable=AsyncMock)
def test_cost_estimate_error(mock_estimate: AsyncMock) -> None:
    mock_estimate.side_effect = Exception("API unreachable")
    response = client.post("/benchmarks/estimate", data={"model": "llama3.1:8b"})
    assert response.status_code == 200
    assert "Estimation Error" in response.text


@patch("app.api_client.RuneApiClient.submit_job", new_callable=AsyncMock)
def test_job_submission(mock_submit: AsyncMock) -> None:
    mock_submit.return_value = {"job_id": "test-job-123"}
    response = client.post("/api/jobs/submit", data={"model": "llama3.1:8b", "vastai": "true"})
    assert response.status_code == 200
    assert "Benchmark Tracker" in response.text
    assert "test-job-123" in response.text


@patch("app.api_client.RuneApiClient.submit_job", new_callable=AsyncMock)
def test_job_submission_error(mock_submit: AsyncMock) -> None:
    mock_submit.side_effect = Exception("Submit failed")
    response = client.post("/api/jobs/submit", data={"model": "llama3.1:8b"})
    assert response.status_code == 200
    assert "Submission Failed" in response.text


@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_succeeded(mock_status: AsyncMock) -> None:
    mock_status.return_value = {"status": "succeeded", "message": "Done"}
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "SUCCEEDED" in response.text


@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_failed(mock_status: AsyncMock) -> None:
    mock_status.return_value = {"status": "failed", "message": "Error"}
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "FAILED" in response.text


@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_running(mock_status: AsyncMock) -> None:
    mock_status.return_value = {"status": "running", "message": "In progress"}
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "RUNNING" in response.text


@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling_error(mock_status: AsyncMock) -> None:
    mock_status.side_effect = Exception("Polling error")
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "Error polling status" in response.text


def test_config_page() -> None:
    response = client.get("/config")
    assert response.status_code == 200
    assert "Configuration" in response.text


@patch("app.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_reports_page(mock_reports: AsyncMock) -> None:
    mock_reports.return_value = {"events": [{"timestamp": "now", "job_id": "123", "name": "test"}]}
    response = client.get("/reports")
    assert response.status_code == 200
    assert "Historical Reports" in response.text


@patch("app.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_reports_page_error(mock_reports: AsyncMock) -> None:
    mock_reports.side_effect = Exception("Reports unavailable")
    response = client.get("/reports")
    assert response.status_code == 200
    assert "Reports Error" in response.text


@patch("app.api_client.RuneApiClient.get_report_content", new_callable=AsyncMock)
def test_view_report(mock_report: AsyncMock) -> None:
    mock_report.return_value = {"job_id": "abc-123", "status": "succeeded", "result": "All good"}
    response = client.get("/reports/abc-123")
    assert response.status_code == 200


@patch("app.api_client.RuneApiClient.get_report_content", new_callable=AsyncMock)
def test_view_report_error(mock_report: AsyncMock) -> None:
    mock_report.side_effect = Exception("Report not found")
    response = client.get("/reports/missing-job")
    assert response.status_code == 200
    assert "Report Error" in response.text


# ── Streaming SSE endpoint ────────────────────────────────────────────────────

@patch("app.main.asyncio.sleep", new_callable=AsyncMock)
@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_events_and_done(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream completes when job reaches succeeded status."""
    events_resp = {"events": [{"timestamp": "2026-01-01T00:00:00Z", "name": "step", "message": "ok"}]}
    status_resp = {"status": "succeeded"}
    mock_status.side_effect = [events_resp, status_resp]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/log-test/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "STREAM ENDED" in content


@patch("app.main.asyncio.sleep", new_callable=AsyncMock)
@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_no_events_then_done(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream completes when status is succeeded even with no events."""
    empty_events = {"events": []}
    status_resp = {"status": "succeeded"}
    mock_status.side_effect = [empty_events, status_resp]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/log-test2/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "STREAM ENDED" in content


@patch("app.main.asyncio.sleep", new_callable=AsyncMock)
@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_error_path(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream yields error message when API call raises an exception."""
    mock_status.side_effect = Exception("connection lost")
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/err-job/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "Log Error" in content


@patch("app.main.asyncio.sleep", new_callable=AsyncMock)
@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_stream_job_logs_cancelled(mock_status: AsyncMock, mock_sleep: AsyncMock) -> None:
    """Stream stops on cancelled status."""
    mock_status.side_effect = [{"events": []}, {"status": "cancelled"}]
    mock_sleep.return_value = None

    with client.stream("GET", "/api/jobs/cancelled-job/logs") as response:
        content = b"".join(response.iter_bytes()).decode()

    assert "STREAM ENDED" in content



# ── API client unit tests (sync, testing init and structure) ─────────────────

def test_api_client_init_with_explicit_token() -> None:
    """RuneApiClient stores explicit token in Authorization header."""
    from app.api_client import RuneApiClient

    c = RuneApiClient(base_url="http://example.com", api_token="explicit-token")
    assert c.headers.get("Authorization") == "Bearer explicit-token"
    assert c.base_url == "http://example.com"


def test_api_client_init_no_token() -> None:
    """RuneApiClient has no Authorization header when no token provided."""
    import os

    from app.api_client import RuneApiClient

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
    from app.api_client import RuneApiClient

    c = RuneApiClient(base_url="http://example.com/")
    assert c.base_url == "http://example.com"


@patch("app.main.asyncio.sleep", new_callable=AsyncMock)
@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
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

    from app.api_client import RuneApiClient

    async def _run() -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": ["llama3.1:8b"]}

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__.return_value = mock_async_client
        mock_async_client.__aexit__.return_value = None
        mock_async_client.get.return_value = mock_response

        with patch("app.api_client.httpx.AsyncClient", return_value=mock_async_client):
            c = RuneApiClient(base_url="http://localhost:8080", api_token="tok")
            result = await c.get_vastai_models()
        assert "models" in result

    asyncio.run(_run())
