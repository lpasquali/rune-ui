import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api_client import RuneApiClient
from unittest.mock import AsyncMock, patch

client = TestClient(app)

def test_index_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "RUNE" in response.text

@patch("app.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_online(mock_health):
    mock_health.return_value = {"status": "ok"}
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "ONLINE" in response.text

@patch("app.api_client.RuneApiClient.get_health", new_callable=AsyncMock)
def test_api_status_offline(mock_health):
    mock_health.side_effect = Exception("offline")
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "OFFLINE" in response.text

def test_benchmarks_page():
    response = client.get("/benchmarks")
    assert response.status_code == 200
    assert "Run Benchmark" in response.text

@patch("app.api_client.RuneApiClient.get_estimate", new_callable=AsyncMock)
def test_cost_estimate_modal(mock_estimate):
    mock_estimate.return_value = {
        "projected_cost_usd": 10.50,
        "cost_driver": "vastai",
        "resource_impact": "medium",
        "local_energy_kwh": 0.0,
        "warning": None
    }
    response = client.post("/benchmarks/estimate", data={"model": "llama3.1:8b", "vastai": "true"})
    assert response.status_code == 200
    assert "PRE-FLIGHT SPEND ALERT" in response.text
    assert "$10.5" in response.text

@patch("app.api_client.RuneApiClient.submit_job", new_callable=AsyncMock)
def test_job_submission(mock_submit):
    mock_submit.return_value = {"job_id": "test-job-123"}
    response = client.post("/api/jobs/submit", data={"model": "llama3.1:8b", "vastai": "true"})
    assert response.status_code == 200
    assert "Benchmark Tracker" in response.text
    assert "test-job-123" in response.text

@patch("app.api_client.RuneApiClient.get_job_status", new_callable=AsyncMock)
def test_job_polling(mock_status):
    mock_status.return_value = {"status": "succeeded", "message": "Done"}
    response = client.get("/api/jobs/test-job-123/status")
    assert response.status_code == 200
    assert "SUCCEEDED" in response.text

@patch("app.api_client.RuneApiClient.get_reports", new_callable=AsyncMock)
def test_reports_page(mock_reports):
    mock_reports.return_value = {"events": [{"timestamp": "now", "job_id": "123", "name": "test"}]}
    response = client.get("/reports")
    assert response.status_code == 200
    assert "Historical Reports" in response.text
    assert "test" in response.text
