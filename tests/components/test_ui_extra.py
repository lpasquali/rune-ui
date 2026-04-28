# SPDX-License-Identifier: Apache-2.0
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from rune_ui.main import app

client = TestClient(app)

@patch("rune_ui.api_client.RuneApiClient.get_finops_simulation", new_callable=AsyncMock)
def test_simulate_finops(mock_simulate: AsyncMock) -> None:
    mock_simulate.return_value = {
        "total_cost_usd": 10.0,
        "confidence": 0.9,
        "gpu_cost_usd": 5.0,
        "token_cost_usd": 5.0,
        "historical_match": True
    }
    response = client.post("/finops/simulate", data={"agent": "holmes", "model": "m1", "gpu": "g1"})
    assert response.status_code == 200
    assert "Simulation Results" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_finops_simulation", new_callable=AsyncMock)
def test_simulate_finops_error(mock_simulate: AsyncMock) -> None:
    mock_simulate.side_effect = Exception("Simulation error")
    response = client.post("/finops/simulate", data={"agent": "holmes", "model": "m1", "gpu": "g1"})
    assert response.status_code == 200
    assert "Simulation Failed" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_chain_state", new_callable=AsyncMock)
def test_get_chain_view(mock_chain: AsyncMock) -> None:
    mock_chain.return_value = {"overall_status": "success", "nodes": [], "edges": []}
    response = client.get("/chains/run123")
    assert response.status_code == 200
    assert "run123" in response.text

@patch("rune_ui.api_client.RuneApiClient.get_chain_state", new_callable=AsyncMock)
def test_get_chain_view_error(mock_chain: AsyncMock) -> None:
    mock_chain.side_effect = Exception("Chain error")
    response = client.get("/chains/run123")
    assert response.status_code == 200
    assert "Error" in response.text

def test_finops_page():
    response = client.get("/finops")
    assert response.status_code == 200
    assert "FinOps" in response.text
