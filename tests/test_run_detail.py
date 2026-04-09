# SPDX-License-Identifier: Apache-2.0
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

@patch("httpx.AsyncClient.stream")
def test_stream_browser_view_success(mock_stream) -> None:
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def mock_stream_ctx(*args, **kwargs):
        class MockResponse:
            status_code = 200
            async def aiter_bytes(self):
                yield b"event: screenshot\n"
                yield b"data: base64img\n\n"
        yield MockResponse()
        
    mock_stream.side_effect = mock_stream_ctx
    
    response = client.get("/api/v1/runs/test-123/browser-stream")
    assert response.status_code == 200
    assert b"data: base64img" in response.content

@patch("httpx.AsyncClient.stream")
def test_stream_browser_view_404(mock_stream) -> None:
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def mock_stream_ctx(*args, **kwargs):
        class MockResponse:
            status_code = 404
        yield MockResponse()
        
    mock_stream.side_effect = mock_stream_ctx
    
    response = client.get("/api/v1/runs/test-123/browser-stream")
    assert response.status_code == 200
    assert b"data: not available" in response.content

@patch("httpx.AsyncClient.stream")
def test_stream_browser_view_error(mock_stream) -> None:
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def mock_stream_ctx(*args, **kwargs):
        raise Exception("Connection failed")
        yield
        
    mock_stream.side_effect = mock_stream_ctx
    
    response = client.get("/api/v1/runs/test-123/browser-stream")
    assert response.status_code == 200
    assert b"event: error" in response.content