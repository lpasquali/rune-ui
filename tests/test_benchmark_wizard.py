import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from rune_ui.main import app

client = TestClient(app)

@patch("rune_ui.api_client.RuneApiClient.submit_job", new_callable=AsyncMock)
def test_job_submission_agentic(mock_submit: AsyncMock) -> None:
    mock_submit.return_value = {"job_id": "test-job-agentic"}
    response = client.post("/api/jobs/submit", data={
        "kind": "agentic-agent",
        "agent": "cyber:pentestgpt",
        "question": "test",
        "backend_type": "openai",
        "backend_url": "http://x",
        "model": "gpt-4",
        "vastai": "false",
        "max_dph": "0.0"
    })
    assert response.status_code == 200
    assert "test-job-agentic" in response.text
    
    # Verify the payload passed to api_client.submit_job
    mock_submit.assert_called_once()
    args, kwargs = mock_submit.call_args
    assert args[0] == "agentic-agent"
    assert args[1]["agent"] == "cyber:pentestgpt"
    assert args[1]["backend_type"] == "openai"
