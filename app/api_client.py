import os
import httpx
from typing import Any, Dict, Optional

class RuneApiClient:
    """Thin client to interact with the RUNE core API."""
    
    def __init__(self, base_url: str = "http://localhost:8080", api_token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-Tenant-ID": os.environ.get("RUNE_API_TENANT", "default"),
        }
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"
        elif os.environ.get("RUNE_API_TOKEN"):
            self.headers["Authorization"] = f"Bearer {os.environ.get('RUNE_API_TOKEN')}"

    async def get_health(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/healthz")
            return response.json()

    async def get_vastai_models(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/catalog/vastai-models",
                headers=self.headers
            )
            return response.json()

    async def get_estimate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Request a cost estimate from the RUNE core."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/estimates",
                headers=self.headers,
                json=payload
            )
            return response.json()

    async def submit_job(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a new benchmark or instance job."""
        endpoint = f"/v1/jobs/{kind}"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}{endpoint}",
                headers=self.headers,
                json=payload
            )
            return response.json()

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/jobs/{job_id}",
                headers=self.headers
            )
            return response.json()

    async def get_reports(self) -> Dict[str, Any]:
        """Fetch list of completed reports from S3 or PVC via the Brain."""
        # For now, we fetch succeeded jobs from the JobStore via the API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/metrics/summary",
                headers=self.headers
            )
            return response.json()

    async def get_report_content(self, job_id: str) -> Dict[str, Any]:
        """Fetch full JSON report content for a specific job."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/jobs/{job_id}",
                headers=self.headers
            )
            return response.json()
