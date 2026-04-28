# SPDX-License-Identifier: Apache-2.0
import os
from typing import Any, Dict, Optional

import httpx


class RuneApiClient:
    """Thin client to interact with the RUNE core API."""

    def __init__(self, base_url: str = "http://localhost:8080", api_token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.headers: Dict[str, str] = {
            "X-Tenant-ID": os.environ.get("RUNE_API_TENANT", "default"),
        }
        token = api_token or os.environ.get("RUNE_API_TOKEN", "")
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def get_secrets(self) -> Dict[str, Any]:
        """Fetch current active secret names (masked)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/settings/secrets",
                headers=self.headers,
            )
            return dict(response.json())

    async def update_secret(self, key: str, value: str) -> Dict[str, Any]:
        """Update a specific secret."""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.base_url}/v1/settings/secrets",
                headers=self.headers,
                json={"key": key, "value": value},
            )
            return dict(response.json())

    async def get_health(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/healthz")
            response.raise_for_status()
            return dict(response.json())

    async def get_vastai_models(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/catalog/vastai-models",
                headers=self.headers,
            )
            return dict(response.json())

    async def get_backend_models(self, backend_type: str, backend_url: str = "") -> Dict[str, Any]:
        """Fetch available models for a specific backend type and URL."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/llm/models",
                headers=self.headers,
                params={"backend_type": backend_type, "backend_url": backend_url},
            )
            response.raise_for_status()
            return dict(response.json())

    async def get_estimate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Request a cost estimate from the RUNE core."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/estimates",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            return dict(response.json())

    async def submit_job(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a new benchmark or instance job."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/jobs/{kind}",
                headers=self.headers,
                json=payload,
            )
            return dict(response.json())

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/jobs/{job_id}",
                headers=self.headers,
            )
            return dict(response.json())

    async def delete_job(self, job_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/v1/jobs/{job_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return dict(response.json())

    async def get_reports(self) -> Dict[str, Any]:
        """Fetch list of completed reports from the Brain."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/metrics/summary",
                headers=self.headers,
            )
            return dict(response.json())

    async def get_report_content(self, job_id: str) -> Dict[str, Any]:
        """Fetch full JSON report content for a specific job."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/jobs/{job_id}",
                headers=self.headers,
            )
            return dict(response.json())

    async def get_settings(self) -> Dict[str, Any]:
        """Fetch global settings."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/settings",
                headers=self.headers,
            )
            return dict(response.json())

    async def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update global settings."""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.base_url}/v1/settings",
                headers=self.headers,
                json=payload,
            )
            return dict(response.json())

    async def create_profile(self, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new profile."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/settings/profiles",
                headers=self.headers,
                json={"name": name, "config": config},
            )
            return dict(response.json())

    async def get_finops_simulation(
        self, agent: str, model: str, gpu: str, runs_per_period: int = 1, period_days: int = 1
    ) -> Dict[str, Any]:
        """Fetch cost projection simulation with period scaling."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/finops/simulate",
                headers=self.headers,
                params={
                    "agent": agent, 
                    "model": model, 
                    "gpu": gpu,
                    "runs_per_period": runs_per_period,
                    "period_days": period_days
                },
            )
            response.raise_for_status()
            return dict(response.json())

    async def get_chain_state(self, run_id: str) -> Dict[str, Any]:
        """Fetch multi-agent chain state."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/chains/{run_id}/state",
                headers=self.headers,
            )
            response.raise_for_status()
            return dict(response.json())

    async def get_interaction(self, run_id: str) -> Dict[str, Any]:
        """Fetch pending interaction/prompt for a run."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/runs/{run_id}/interaction",
                headers=self.headers,
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return dict(response.json())

    async def submit_interaction(self, run_id: str, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit user response to a pending interaction."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/runs/{run_id}/interaction",
                headers=self.headers,
                json=response_data,
            )
            response.raise_for_status()
            return dict(response.json())
