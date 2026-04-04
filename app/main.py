import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api_client import RuneApiClient

log = logging.getLogger(__name__)

app = FastAPI(title="RUNE UI")
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="app/templates")

RUNE_API_URL = os.environ.get("RUNE_API_URL", "http://localhost:8080")
api_client = RuneApiClient(base_url=RUNE_API_URL)

# Per-process HMAC key used to sign SSE log chunks (Issue #11).
_log_session_key: bytes = secrets.token_bytes(32)


def _sign_log_event(payload: str) -> str:
    """Return the hex-encoded HMAC-SHA256 signature for a log event payload."""
    return hmac.new(_log_session_key, payload.encode(), hashlib.sha256).hexdigest()


@app.get("/api/log-session-key")
async def get_log_session_key() -> JSONResponse:
    """Return the base64-encoded HMAC-SHA256 session key for client-side log verification."""
    return JSONResponse({"key": base64.b64encode(_log_session_key).decode()})


@app.get("/api/jobs/{job_id}/logs")
async def stream_job_logs(request: Request, job_id: str) -> StreamingResponse:
    """SSE endpoint to stream HMAC-signed event logs from the Brain to the UI (Issue #11)."""

    async def event_generator() -> AsyncGenerator[str, None]:
        last_event_id = 0
        while True:
            if await request.is_disconnected():  # pragma: no cover
                break  # pragma: no cover

            try:
                events_data = await api_client.get_job_status(f"{job_id}/events")
                events = events_data.get("events", [])

                if len(events) > last_event_id:
                    for i in range(last_event_id, len(events)):
                        event = events[i]
                        ts = html.escape(str(event.get("timestamp", "")))
                        name = html.escape(str(event.get("name", "")))
                        msg = (
                            f'<div><span style="color: var(--base01)">[{ts}]</span>'
                            f' <span style="color: var(--yellow)">{name}</span>:'
                            f' {html.escape(str(event.get("message", "")))}</div>'
                        )
                        sig = _sign_log_event(msg)
                        yield f"data: {json.dumps({'html': msg, 'sig': sig, 'seq': i})}\n\n"
                    last_event_id = len(events)

                job_status = await api_client.get_job_status(job_id)
                if job_status.get("status") in ["succeeded", "failed", "cancelled"]:
                    end_msg = "<div><hr><strong>STREAM ENDED</strong></div>"
                    sig = _sign_log_event(end_msg)
                    yield f"data: {json.dumps({'html': end_msg, 'sig': sig, 'seq': last_event_id})}\n\n"
                    break

            except Exception:
                log.exception("Error streaming logs for job %s", job_id)
                err_msg = '<div><span style="color: var(--red)">Log stream interrupted.</span></div>'
                sig = _sign_log_event(err_msg)
                yield f"data: {json.dumps({'html': err_msg, 'sig': sig, 'seq': -1})}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    return templates.TemplateResponse(request, "base.html")


@app.get("/api/status", response_class=HTMLResponse)
async def get_status(request: Request) -> str:
    try:
        health = await api_client.get_health()
        if health.get("status") == "ok":
            return '<span style="color: var(--green)">API STATUS: ONLINE</span>'
        return '<span style="color: var(--red)">API STATUS: DEGRADED</span>'
    except Exception:
        return '<span style="color: var(--red)">API STATUS: OFFLINE</span>'


@app.get("/benchmarks", response_class=HTMLResponse)
async def get_benchmarks_page(request: Request) -> Any:
    return templates.TemplateResponse(request, "benchmarks.html")


@app.post("/benchmarks/estimate", response_class=HTMLResponse)
async def get_benchmark_estimate(
    request: Request,
    model: str = Form(...),
    vastai: bool = Form(False),
    max_dph: float = Form(0.0),
    local_hardware: bool = Form(False),
) -> Any:
    """BFF logic to fetch and display the pre-flight cost estimate."""
    payload: dict[str, Any] = {
        "model": model,
        "vastai": vastai,
        "max_dph": max_dph,
        "local_hardware": local_hardware,
        "local_tdp_watts": 350.0 if local_hardware else 0.0,
        "local_energy_rate_kwh": 0.15,
        "estimated_duration_seconds": 3600,
    }

    try:
        estimate = await api_client.get_estimate(payload)
        return templates.TemplateResponse(
            request,
            "estimate_modal.html",
            {"estimate": estimate, "model": model, "vastai": vastai, "max_dph": max_dph},
        )
    except Exception:
        log.exception("Estimation failed")
        return (
            '<div class="modal" style="border-color: var(--red)">'
            "<h3>Estimation Error</h3><p>Unable to compute estimate. Please try again.</p>"
            '<button hx-get="/benchmarks" hx-target="#main">Back</button></div>'
        )


@app.post("/api/jobs/submit", response_class=HTMLResponse)
async def submit_benchmark_job(
    request: Request,
    model: str = Form(...),
    vastai: bool = Form(False),
    max_dph: float = Form(0.0),
) -> Any:
    """BFF logic to submit a job to the RUNE core and show the tracker."""
    payload: dict[str, Any] = {
        "vastai": vastai,
        "max_dph": max_dph,
        "model": model,
        "template_hash": os.environ.get("RUNE_VASTAI_TEMPLATE", "c166c11f035d3a97871a23bd32ca6aba"),
        "min_dph": 0.0,
        "reliability": 0.99,
        "question": "What is unhealthy in this Kubernetes cluster?",
        "ollama_warmup": True,
        "ollama_warmup_timeout": 300,
        "kubeconfig": os.environ.get("RUNE_KUBECONFIG", "~/.kube/config"),
        "vastai_stop_instance": True,
        "ollama_url": None,
    }

    try:
        job_info = await api_client.submit_job("benchmark", payload)
        job_id = job_info.get("job_id")
        return templates.TemplateResponse(request, "job_tracker.html", {"job_id": job_id})
    except Exception:
        log.exception("Job submission failed")
        return '<div class="card" style="border-color: var(--red)"><h3>Submission Failed</h3><p>Could not submit job. Please try again.</p></div>'


@app.get("/api/jobs/{job_id}/status", response_class=HTMLResponse)
async def poll_job_status(request: Request, job_id: str) -> str:
    """Poll the RUNE API for job status updates via HTMX."""
    try:
        status_info = await api_client.get_job_status(job_id)
        status = status_info.get("status", "unknown").lower()

        status_color = "var(--yellow)"
        if status in ["succeeded", "success", "completed"]:
            status_color = "var(--green)"
        if status in ["failed", "error", "cancelled"]:
            status_color = "var(--red)"

        safe_jid = html.escape(job_id)
        safe_status = html.escape(status.upper())
        safe_msg = html.escape(str(status_info.get("message", "")))
        return (
            f'<div class="card" style="border-left: 5px solid {status_color}">'
            f"<h3>Job: {safe_jid}</h3>"
            f'<p>Status: <span style="color: {status_color}">{safe_status}</span></p>'
            f"<p>{safe_msg}</p></div>"
        )
    except Exception:
        log.exception("Polling failed for job %s", job_id)
        return '<p style="color: var(--red)">Error polling status. Please retry.</p>'


@app.get("/config", response_class=HTMLResponse)
async def get_config(request: Request) -> str:
    return '<div class="card"><h2>Configuration</h2><p>Manage Vast.ai templates and Ollama endpoints.</p></div>'


@app.get("/reports", response_class=HTMLResponse)
async def get_reports_page(request: Request) -> Any:
    """Display historical benchmark reports."""
    try:
        reports_data = await api_client.get_reports()
        return templates.TemplateResponse(request, "reports.html", {"reports": reports_data})
    except Exception:
        log.exception("Failed to load reports")
        return '<div class="card" style="border-color: var(--red)"><h3>Reports Error</h3><p>Unable to load reports.</p></div>'


@app.get("/reports/{job_id}", response_class=HTMLResponse)
async def view_report(request: Request, job_id: str) -> Any:
    """BFF logic to fetch and display a specific historical report."""
    try:
        report = await api_client.get_report_content(job_id)
        return templates.TemplateResponse(request, "report_view.html", {"report": report})
    except Exception:
        log.exception("Failed to load report %s", job_id)
        return '<div class="card" style="border-color: var(--red)"><h3>Report Error</h3><p>Unable to load report.</p></div>'
