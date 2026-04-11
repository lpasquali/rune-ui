# SPDX-License-Identifier: Apache-2.0
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from rune_ui.main import app

client = TestClient(app)

@patch("rune_ui.api_client.RuneApiClient.get_interaction", new_callable=AsyncMock)
def test_poll_interaction_no_prompt(mock_get: AsyncMock) -> None:
    mock_get.return_value = {}
    response = client.get("/runs/test-run/interaction")
    assert response.status_code == 200
    assert "No pending prompts" in response.text
    assert 'hx-get="/runs/test-run/interaction"' in response.text

@patch("rune_ui.api_client.RuneApiClient.get_interaction", new_callable=AsyncMock)
def test_poll_interaction_with_prompt(mock_get: AsyncMock) -> None:
    mock_get.return_value = {"prompt": "Enter value:"}
    response = client.get("/runs/test-run/interaction")
    assert response.status_code == 200
    assert "Enter value:" in response.text
    assert "Your Response:" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_interaction", new_callable=AsyncMock)
def test_poll_interaction_error(mock_get: AsyncMock) -> None:
    mock_get.side_effect = Exception("API error")
    response = client.get("/runs/test-run/interaction")
    assert response.status_code == 200
    assert "Error polling for prompts" in response.text

@patch("rune_ui.api_client.RuneApiClient.submit_interaction", new_callable=AsyncMock)
def test_submit_interaction_success(mock_submit: AsyncMock) -> None:
    response = client.post("/runs/test-run/interaction", data={"response": "my input"})
    assert response.status_code == 200
    assert "Response submitted" in response.text
    mock_submit.assert_called_once_with("test-run", {"response": "my input"})

@patch("rune_ui.api_client.RuneApiClient.submit_interaction", new_callable=AsyncMock)
def test_submit_interaction_error(mock_submit: AsyncMock) -> None:
    mock_submit.side_effect = Exception("Submit failed")
    response = client.post("/runs/test-run/interaction", data={"response": "my input"})
    assert response.status_code == 200
    assert "Failed to submit response" in response.text

def test_interactive_terminal_page() -> None:
    response = client.get("/runs/test-run/terminal")
    assert response.status_code == 200
    assert "Interactive Terminal" in response.text

def test_api_client_interaction_impl() -> None:
    import asyncio
    from rune_ui.api_client import RuneApiClient
    async def _run() -> None:
        class MockResponse:
            def __init__(self, status_code=200, json_data=None):
                self.status_code = status_code
                self._json = json_data or {}
            def raise_for_status(self): pass
            def json(self): return self._json
            
        class MockClient:
            async def __aenter__(self): return self
            async def __aexit__(self, exc_type, exc_val, exc_tb): pass
            async def get(self, url, **kwargs):
                if "404" in url:
                    return MockResponse(404)
                return MockResponse(200, {"prompt": "hi"})
            async def post(self, *args, **kwargs):
                return MockResponse(200, {"ok": True})

        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=MockClient()):
            c = RuneApiClient(base_url="http://x")
            res = await c.get_interaction("123")
            assert res["prompt"] == "hi"
            res_404 = await c.get_interaction("404")
            assert res_404 == {}
            
            res2 = await c.submit_interaction("123", {"response": "yes"})
            assert res2["ok"] is True
            
    asyncio.run(_run())
