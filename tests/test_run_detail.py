# SPDX-License-Identifier: Apache-2.0
from urllib.parse import quote

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from rune_ui.main import app

client = TestClient(app)

@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_run_detail_view_success(mock_get_status: AsyncMock) -> None:
    mock_get_status.return_value = {
        "job_id": "test-123",
        "status": "completed",
        "result": {
            "score": 85,
            "metadata": {"agent_name": "TestAgent", "tier": 1},
            "telemetry": {"duration_ms": 1000, "cost_usd": "0.01"},
            "token_usage": {"total_tokens": 100}
        }
    }
    response = client.get("/runs/test-123")
    assert response.status_code == 200
    assert "TestAgent" in response.text
    assert "85" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_run_detail_view_error(mock_get_status: AsyncMock) -> None:
    mock_get_status.side_effect = Exception("API error")
    response = client.get("/runs/test-123")
    assert response.status_code == 200
    assert "Unable to load run details" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_run_status_polling_in_progress(mock_get_status: AsyncMock) -> None:
    mock_get_status.return_value = {"status": "running"}
    response = client.get("/runs/test-123/status")
    assert response.status_code == 200
    assert "running" in response.text
    assert "hx-get" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_run_status_polling_completed(mock_get_status: AsyncMock) -> None:
    mock_get_status.return_value = {"status": "completed"}
    response = client.get("/runs/test-123/status")
    assert response.status_code == 200
    assert "completed" in response.text
    assert "hx-get" not in response.text

@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_run_status_polling_error(mock_get_status: AsyncMock) -> None:
    mock_get_status.side_effect = Exception("API error")
    response = client.get("/runs/test-123/status")
    assert response.status_code == 200
    assert "error" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_run_status_escapes_reflected_status(mock_get_status: AsyncMock) -> None:
    mock_get_status.return_value = {
        "status": 'running<img src=x onerror=alert(1)>',
    }
    response = client.get("/runs/test-123/status")
    assert response.status_code == 200
    assert "<img " not in response.text
    assert "&lt;img" in response.text


@patch("rune_ui.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_run_status_escapes_run_id_in_poll_url(mock_get_status: AsyncMock) -> None:
    """Run IDs with '/' are ambiguous in paths; this covers quote + attr safety."""
    mock_get_status.return_value = {"status": "running"}
    run_id = 'x"><img src=x onerror=1'
    path = f"/runs/{quote(run_id, safe='')}/status"
    response = client.get(path)
    assert response.status_code == 200
    encoded = quote(run_id, safe="")
    assert f'hx-get="/runs/{encoded}/status"' in response.text

@patch("httpx.AsyncClient.stream")
def test_stream_run_trace_success(mock_stream) -> None:
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def mock_stream_ctx(*args, **kwargs):
        class MockResponse:
            async def aiter_bytes(self):
                yield b"event: message\n"
                yield b"data: test\n\n"
        yield MockResponse()
        
    mock_stream.side_effect = mock_stream_ctx
    
    response = client.get("/api/v1/runs/test-123/trace")
    assert response.status_code == 200
    assert b"data: test" in response.content

@patch("httpx.AsyncClient.stream")
def test_stream_run_trace_error(mock_stream) -> None:
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def mock_stream_ctx(*args, **kwargs):
        raise Exception("Connection failed")
        yield
        
    mock_stream.side_effect = mock_stream_ctx
    
    response = client.get("/api/v1/runs/test-123/trace")
    assert response.status_code == 200
    assert b"event: error" in response.content