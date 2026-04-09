# SPDX-License-Identifier: Apache-2.0
import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import os
from pathlib import Path
import secrets
from typing import Any, AsyncGenerator, Optional

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from rune_ui.api_client import RuneApiClient

log = logging.getLogger(__name__)

app = FastAPI(title="RUNE UI")
BASE_DIR = Path(__file__).parent.resolve()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")

RUNE_API_URL = os.environ.get(
    "RUNE_API_URL",
    os.environ.get("RUNE_API_BASE_URL", "http://localhost:8080"),
)
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


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness probe for Docker/K8s health checks."""
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    return templates.TemplateResponse(request, "base.html")


@app.get("/api/status", response_class=HTMLResponse)
async def get_status(request: Request) -> str:
    try:
        health = await api_client.get_health()
        if health.get("status") == "ok":
            return '<span style="color: var(--green)">API STATUS: ONLINE</span>'
        return '<span style="color: var(--yellow)">API STATUS: NOT CONNECTED</span>'
    except Exception:
        return '<span style="color: var(--yellow)">API STATUS: NOT CONNECTED</span>'


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
    except Exception as exc:
        log.exception("Estimation failed")
        return templates.TemplateResponse(
            request,
            "error_modal.html",
            {
                "title": "Estimation Error",
                "message": f"Unable to compute estimate from {RUNE_API_URL}/v1/estimates.",
                "detail": str(exc) or "Unknown error",
                "help": "Check that the RUNE API is running and reachable, "
                "and that RUNE_API_URL or RUNE_API_BASE_URL is set correctly.",
            },
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


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> Any:
    try:
        reports_data = await api_client.get_reports()
        events = reports_data.get("events", [])
        
        labels = []
        data_points = []
        for ev in events:
            labels.append(ev.get("job_id", "Unknown"))
            data_points.append(ev.get("duration_ms", 0) / 1000)
            
        chart_data = {
            "labels": labels,
            "datasets": [{
                "label": "Duration (s)",
                "data": data_points,
                "backgroundColor": "rgba(99, 102, 241, 0.5)",
                "borderColor": "rgba(99, 102, 241, 1)",
                "borderWidth": 1
            }]
        }
        return templates.TemplateResponse(request, "dashboard.html", {"chart_data": chart_data, "events": events})
    except Exception:
        log.exception("Failed to load dashboard")
        return '<div class="card" style="border-color: var(--red)"><h3>Error</h3><p>Unable to load dashboard.</p></div>'

@app.get("/compare", response_class=HTMLResponse)
async def compare(request: Request) -> Any:
    try:
        reports_data = await api_client.get_reports()
        events = reports_data.get("events", [])
        
        labels = []
        data_points = []
        for ev in events:
            labels.append(ev.get("job_id", "Unknown"))
            data_points.append(ev.get("duration_ms", 0) / 1000)
            
        chart_data = {
            "labels": labels,
            "datasets": [{
                "label": "Duration (s)",
                "data": data_points,
                "backgroundColor": "rgba(52, 211, 153, 0.5)",
                "borderColor": "rgba(52, 211, 153, 1)",
                "borderWidth": 1
            }]
        }
        return templates.TemplateResponse(request, "compare.html", {"chart_data": chart_data, "events": events})
    except Exception:
        log.exception("Failed to load compare")
        return '<div class="card" style="border-color: var(--red)"><h3>Error</h3><p>Unable to load comparison.</p></div>'


@app.get("/config", response_class=HTMLResponse)
async def get_config(request: Request) -> Any:
    """Configuration page: read-only display of backend settings, API status, and models."""
    api_url = RUNE_API_URL
    auth_disabled = os.environ.get("RUNE_API_AUTH_DISABLED", "0") == "1"
    tenant = os.environ.get("RUNE_API_TENANT", "default")

    # Check API connectivity
    api_online = False
    try:
        health = await api_client.get_health()
        api_online = health.get("status") == "ok"
    except Exception:
        pass

    # Fetch available models (best-effort)
    models: list[str] = []
    try:
        catalog = await api_client.get_vastai_models()
        models = catalog.get("models", [])
    except Exception:
        pass
        
    settings = {}
    try:
        settings = await api_client.get_settings()
    except Exception:
        log.exception("Failed to fetch global settings")

    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "api_url": api_url,
            "api_online": api_online,
            "auth_disabled": auth_disabled,
            "tenant": tenant,
            "models": models,
            "settings": settings,
        },
    )

@app.post("/config/profile", response_class=HTMLResponse)
async def switch_profile(request: Request, profile: str = Form(...)) -> Any:
    try:
        await api_client.update_settings({"active_profile": profile})
        return HTMLResponse('<div class="card" style="border-color: var(--green)"><p>Profile switched successfully.</p><button hx-get="/config" hx-target="#main">Refresh</button></div>')
    except Exception as e:
        return HTMLResponse(f'<div class="card" style="border-color: var(--red)"><p>Error: {e}</p></div>')

@app.post("/config/update", response_class=HTMLResponse)
async def update_config(request: Request, backend_type: str = Form(...), backend_url: str = Form(""), model: str = Form(...)) -> Any:
    try:
        payload = {"config": {"backend_type": backend_type, "backend_url": backend_url, "model": model}}
        await api_client.update_settings(payload)
        return HTMLResponse('<div class="card" style="border-color: var(--green)"><p>Settings updated successfully.</p><button hx-get="/config" hx-target="#main">Refresh</button></div>')
    except Exception as e:
        return HTMLResponse(f'<div class="card" style="border-color: var(--red)"><p>Error: {e}</p></div>')

@app.post("/config/new_profile", response_class=HTMLResponse)
async def create_new_profile(request: Request, name: str = Form(...)) -> Any:
    try:
        await api_client.create_profile(name, {})
        return HTMLResponse('<div class="card" style="border-color: var(--green)"><p>Profile created successfully.</p><button hx-get="/config" hx-target="#main">Refresh</button></div>')
    except Exception as e:
        return HTMLResponse(f'<div class="card" style="border-color: var(--red)"><p>Error: {e}</p></div>')


@app.get("/reports", response_class=HTMLResponse)
async def get_reports_page(request: Request) -> Any:
    """Display historical benchmark reports."""
    try:
        reports_data = await api_client.get_reports()
        return templates.TemplateResponse(request, "reports.html", {"reports": reports_data})
    except Exception:
        log.exception("Failed to load reports")
        return '<div class="card" style="border-color: var(--red)"><h3>Reports Error</h3><p>Unable to load reports.</p></div>'


@app.get("/chains/{run_id}", response_class=HTMLResponse)
async def get_chain_page(request: Request, run_id: str) -> Any:
    """Render the multi-agent chain DAG page for `run_id` (Issue #99).

    Server-side rendering is an empty SVG shell; the client JS fetches state
    from `GET /v1/chains/{run_id}/state` and updates the DOM. We pre-fetch the
    initial state here so the page still renders useful content (and the right
    HTTP status) on the first load — 404 if the run is unknown, 502 if the
    backend is unreachable.
    """
    initial_state: Any = None
    error_message: Optional[str] = None
    status_code = 200
    try:
        initial_state = await api_client.get_chain_state(run_id)
    except httpx.HTTPStatusError as exc:
        # Pass through 404 (and other 4xx) from the backend to the client.
        upstream = exc.response.status_code
        status_code = upstream if upstream in (404, 400, 403) else 502
        if upstream == 404:
            error_message = f"Chain run '{run_id}' not found."
        else:
            error_message = f"Upstream error {upstream} fetching chain state."
    except Exception as exc:
        log.exception("Failed to fetch chain state for %s", run_id)
        status_code = 502
        error_message = f"Unable to reach RUNE API at {RUNE_API_URL}: {exc}"

    return templates.TemplateResponse(
        request,
        "chain.html",
        {
            "run_id": run_id,
            "initial_state": initial_state,
            "initial_state_json": json.dumps(initial_state) if initial_state else "null",
            "error_message": error_message,
            "rune_api_url": RUNE_API_URL,
        },
        status_code=status_code,
    )


@app.get("/reports/{job_id}", response_class=HTMLResponse)
async def view_report(request: Request, job_id: str) -> Any:
    """BFF logic to fetch and display a specific historical report."""
    try:
        report = await api_client.get_report_content(job_id)
        return templates.TemplateResponse(request, "report_view.html", {"report": report})
    except Exception:
        log.exception("Failed to load report %s", job_id)
        return '<div class="card" style="border-color: var(--red)"><h3>Report Error</h3><p>Unable to load report.</p></div>'


@app.get("/audits/{run_id}", response_class=HTMLResponse)
async def get_audits_page(request: Request, run_id: str) -> Any:
    """Render the audit artifacts shell for a benchmark run (Issue #100).

    The server only emits the shell (template + CSS + JS). The ``audit-viewer.js``
    module performs the ``GET /v1/audits/{run_id}/artifacts`` fetch client-side
    using ``RUNE_API_URL`` as the base URL, groups artifacts by ``kind``, and
    renders a card per artifact with per-kind inline previews (SLSA JSON, SBOM
    component list, TLA+ pass/fail) plus copy / download controls.

    Unknown runs are handled client-side: the RUNE API returns 404, which the
    JS catches and displays as an error state. This endpoint therefore always
    returns 200 — it is a static shell that needs no backend lookup.
    """
    return templates.TemplateResponse(
        request,
        "audit.html",
        {"run_id": run_id, "api_base_url": RUNE_API_URL},
    )
