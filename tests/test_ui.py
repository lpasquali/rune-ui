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
