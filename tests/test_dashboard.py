from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from rune_ui.main import app

client = TestClient(app)

@patch("rune_ui.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_dashboard_success(mock_get_reports: AsyncMock) -> None:
    mock_get_reports.return_value = {
        "events": [
            {"job_id": "job1", "status": "completed", "duration_ms": 5000}
        ]
    }
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "job1" in response.text
    assert "chart_data" in response.text or "costChart" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_dashboard_error(mock_get_reports: AsyncMock) -> None:
    mock_get_reports.side_effect = Exception("API error")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Unable to load dashboard" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_compare_success(mock_get_reports: AsyncMock) -> None:
    mock_get_reports.return_value = {
        "events": [
            {"job_id": "job2", "status": "failed", "score": 45}
        ]
    }
    response = client.get("/compare")
    assert response.status_code == 200
    assert "Agent Compare" in response.text
    assert "job2" in response.text
    assert "compareChart" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_compare_error(mock_get_reports: AsyncMock) -> None:
    mock_get_reports.side_effect = Exception("API error")
    response = client.get("/compare")
    assert response.status_code == 200
    assert "Unable to load comparison" in response.text