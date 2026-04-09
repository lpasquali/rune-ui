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

    async def get_chain_state(self, run_id: str) -> Dict[str, Any]:
        """Fetch DAG state for a multi-agent chain run (Issue #99).

        Returns the full state document `{run_id, nodes[], edges[], overall_status}`
        served by `GET /v1/chains/{run_id}/state`. Raises `httpx.HTTPStatusError`
        on non-2xx responses so callers can distinguish 404 (unknown run) from
        transport errors.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/chains/{run_id}/state",
                headers=self.headers,
            )
            response.raise_for_status()
            return dict(response.json())

    async def get_interaction(self, job_id: str) -> Dict[str, Any]:
        """Fetch pending manual interaction prompt."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/runs/{job_id}/interaction",
                headers=self.headers,
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            return dict(response.json())

    async def submit_interaction(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a response to a pending manual interaction."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/runs/{job_id}/interaction",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
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
