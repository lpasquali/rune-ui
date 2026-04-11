from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from rune_ui.main import app

client = TestClient(app)

@patch("rune_ui.api_client.RuneApiClient.get_settings", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
@patch("rune_ui.api_client.RuneApiClient.get_vastai_models", new_callable=AsyncMock)
def test_config_page_with_settings(mock_models, mock_health, mock_settings):
    mock_health.return_value = {"status": "ok"}
    mock_models.return_value = {"models": ["m1", "m2"]}
    mock_settings.return_value = {
        "active_profile": "default",
        "profiles": ["default", "test"],
        "config": {"backend_type": "ollama", "backend_url": "http://x", "model": "m1"}
    }
    
    response = client.get("/config")
    assert response.status_code == 200
    assert "Global Settings Dashboard" in response.text
    assert "default" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_settings", new_callable=AsyncMock)
def test_config_page_settings_error(mock_settings):
    mock_settings.side_effect = Exception("API error")
    response = client.get("/config")
    assert response.status_code == 200
    assert "Settings not available" in response.text

@patch("rune_ui.api_client.RuneApiClient.update_settings", new_callable=AsyncMock)
def test_switch_profile_success(mock_update):
    response = client.post("/config/profile", data={"profile": "test"})
    assert response.status_code == 200
    assert "Profile switched successfully" in response.text
    mock_update.assert_called_once_with({"active_profile": "test"})

@patch("rune_ui.api_client.RuneApiClient.update_settings", new_callable=AsyncMock)
def test_switch_profile_error(mock_update):
    mock_update.side_effect = Exception("API error")
    response = client.post("/config/profile", data={"profile": "test"})
    assert response.status_code == 200
    assert "Error: API error" in response.text

@patch("rune_ui.api_client.RuneApiClient.update_settings", new_callable=AsyncMock)
def test_update_config_success(mock_update):
    response = client.post("/config/update", data={"backend_type": "openai", "backend_url": "url", "model": "gpt-4"})
    assert response.status_code == 200
    assert "Settings updated successfully" in response.text
    mock_update.assert_called_once_with({"config": {"backend_type": "openai", "backend_url": "url", "model": "gpt-4"}})

@patch("rune_ui.api_client.RuneApiClient.update_settings", new_callable=AsyncMock)
def test_update_config_error(mock_update):
    mock_update.side_effect = Exception("API error")
    response = client.post("/config/update", data={"backend_type": "openai", "backend_url": "url", "model": "gpt-4"})
    assert response.status_code == 200
    assert "Error: API error" in response.text

@patch("rune_ui.api_client.RuneApiClient.create_profile", new_callable=AsyncMock)
def test_create_new_profile_success(mock_create):
    response = client.post("/config/new_profile", data={"name": "newprof"})
    assert response.status_code == 200
    assert "Profile created successfully" in response.text
    mock_create.assert_called_once_with("newprof", {})

@patch("rune_ui.api_client.RuneApiClient.create_profile", new_callable=AsyncMock)
def test_create_new_profile_error(mock_create):
    mock_create.side_effect = Exception("API error")
    response = client.post("/config/new_profile", data={"name": "newprof"})
    assert response.status_code == 200
    assert "Error: API error" in response.text

def test_api_client_update_settings_impl() -> None:
    import asyncio
    from rune_ui.api_client import RuneApiClient
    async def _run() -> None:
        class MockResponse:
            def json(self): return {"ok": True}
        class MockClient:
            async def __aenter__(self): return self
            async def __aexit__(self, exc_type, exc_val, exc_tb): pass
            async def put(self, *args, **kwargs): return MockResponse()
            async def post(self, *args, **kwargs): return MockResponse()

        with patch("rune_ui.api_client.httpx.AsyncClient", return_value=MockClient()):
            c = RuneApiClient(base_url="http://x")
            res = await c.update_settings({"active_profile": "x"})
            assert res["ok"] is True
            res2 = await c.create_profile("name", {})
            assert res2["ok"] is True
    asyncio.run(_run())
