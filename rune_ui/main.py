# SPDX-License-Identifier: Apache-2.0
import asyncio
import base64
import hashlib
import hmac
import html
import httpx
import json
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Any, AsyncGenerator

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
    kind: str = Form("benchmark"),
    agent: str = Form("sre:k8sgpt"),
    question: str = Form("What is unhealthy in this Kubernetes cluster?"),
    backend_type: str = Form("ollama"),
    backend_url: str = Form(""),
    model: str = Form(...),
    vastai: bool = Form(False),
    max_dph: float = Form(0.0),
    local_hardware: bool = Form(False),
) -> Any:
    """BFF logic to fetch and display the pre-flight cost estimate."""
    provisioning = None
    if vastai:
        provisioning = {
            "vastai": {
                "template_hash": os.environ.get("RUNE_VASTAI_TEMPLATE", "c166c11f035d3a97871a23bd32ca6aba"),
                "min_dph": 0.0,
                "max_dph": max_dph,
                "reliability": 0.99,
            }
        }

    payload: dict[str, Any] = {
        "model": model,
        "provisioning": provisioning,
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
            {
                "estimate": estimate, 
                "kind": kind,
                "agent": agent,
                "question": question,
                "backend_type": backend_type,
                "backend_url": backend_url,
                "model": model, 
                "vastai": vastai, 
                "max_dph": max_dph,
                "local_hardware": local_hardware
            },
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
    kind: str = Form("benchmark"),
    agent: str = Form("sre:k8sgpt"),
    question: str = Form("What is unhealthy in this Kubernetes cluster?"),
    backend_type: str = Form("ollama"),
    backend_url: str = Form(""),
    model: str = Form(...),
    vastai: bool = Form(False),
    max_dph: float = Form(0.0),
) -> Any:
    """BFF logic to submit a job to the RUNE core and show the tracker."""
    provisioning = None
    if vastai:
        provisioning = {
            "vastai": {
                "template_hash": os.environ.get("RUNE_VASTAI_TEMPLATE", "c166c11f035d3a97871a23bd32ca6aba"),
                "min_dph": 0.0,
                "max_dph": max_dph,
                "reliability": 0.99,
                "stop_instance": True,
            }
        }

    payload: dict[str, Any] = {
        "provisioning": provisioning,
        "model": model,
        "question": question,
        "backend_warmup": True,
        "backend_warmup_timeout": 300,
        "kubeconfig": os.environ.get("RUNE_KUBECONFIG", "~/.kube/config"),
        "backend_url": backend_url if backend_url else None,
        "backend_type": backend_type,
    }
    
    if kind == "agentic-agent":
        payload["agent"] = agent

    try:
        job_info = await api_client.submit_job(kind, payload)
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


@app.get("/finops", response_class=HTMLResponse)
async def get_finops_page(request: Request) -> Any:
    return templates.TemplateResponse(request, "finops.html")


@app.post("/finops/simulate", response_class=HTMLResponse)
async def simulate_finops(
    request: Request,
    agent: str = Form("holmes"),
    model: str = Form("llama3.1:8b"),
    gpu: str = Form("rtx4090"),
) -> Any:
    try:
        projection = await api_client.get_finops_simulation(agent, model, gpu)
        return templates.TemplateResponse(
            request,
            "finops_results.html",
            {
                "projection": projection,
                "agent": agent,
                "model": model,
                "gpu": gpu,
            },
        )
    except Exception as exc:
        log.exception("FinOps simulation failed")
        return f'<div class="card" style="border-color: var(--red)"><h3>Simulation Failed</h3><p>{exc}</p></div>'


@app.get("/chains/{run_id}", response_class=HTMLResponse)
async def get_chain_view(request: Request, run_id: str) -> Any:
    try:
        chain_state = await api_client.get_chain_state(run_id)
        return templates.TemplateResponse(
            request,
            "chain_detail.html",
            {
                "run_id": run_id,
                "state": chain_state,
                "now_ts": time.time(),
            },
        )
    except Exception as exc:
        log.exception("Failed to load chain view %s", run_id)
        return f'<div class="card" style="border-color: var(--red)"><h3>Error</h3><p>{exc}</p></div>'


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

@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail_view(request: Request, run_id: str) -> Any:
    try:
        data = await api_client.get_job_status(run_id)
        result = data.get("result", {})
        metadata = result.get("metadata", {})
        telemetry = result.get("telemetry", {})
        tokens = result.get("token_usage", {})
        
        run_info = {
            "id": data.get("job_id", run_id),
            "status": data.get("status", "unknown"),
            "agent": metadata.get("agent_name", "Unknown Agent"),
            "tier": metadata.get("tier", "Unknown"),
            "score": result.get("score"),
            "duration_ms": telemetry.get("duration_ms", 0),
            "cost_usd": telemetry.get("cost_usd", "0.00"),
            "tokens": tokens.get("total_tokens", 0)
        }
        return templates.TemplateResponse(request, "run_detail.html", {"run": run_info})
    except Exception:
        log.exception("Failed to load run detail %s", run_id)
        return '<div class="card" style="border-color: var(--red)"><h3>Error</h3><p>Unable to load run details.</p></div>'

@app.get("/runs/{run_id}/status", response_class=HTMLResponse)
async def get_run_status(request: Request, run_id: str) -> Any:
    try:
        data = await api_client.get_job_status(run_id)
        status = data.get("status", "unknown")
        
        html_str = f'<p>Status: <strong style="color: var(--yellow);">{status}</strong></p>'
        if status not in ["completed", "failed"]:
            return HTMLResponse(
                content=f'<div hx-get="/runs/{run_id}/status" hx-trigger="every 2s" hx-swap="outerHTML">{html_str}</div>'
            )
        else:
            return HTMLResponse(content=f'<div>{html_str}</div>')
    except Exception:
        return HTMLResponse(content='<p>Status: <strong style="color: var(--red);">error</strong></p>')

@app.get("/api/v1/runs/{run_id}/trace")
async def stream_run_trace(run_id: str) -> StreamingResponse:
    async def proxy_generator():
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("GET", f"{api_client.base_url}/v1/runs/{run_id}/trace", headers=api_client.headers) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except Exception:
                log.exception("Failed to proxy stream for %s", run_id)
                yield b"event: error\ndata: proxy error\n\n"
    return StreamingResponse(proxy_generator(), media_type="text/event-stream")

@app.get("/api/v1/runs/{run_id}/browser-stream")
async def stream_browser_view(run_id: str) -> StreamingResponse:
    async def proxy_generator():
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("GET", f"{api_client.base_url}/v1/runs/{run_id}/browser-stream", headers=api_client.headers) as response:
                    if response.status_code == 404:
                        yield b"event: error\ndata: not available\n\n"
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except Exception:
                log.exception("Failed to proxy browser stream for %s", run_id)
                yield b"event: error\ndata: proxy error\n\n"
    return StreamingResponse(proxy_generator(), media_type="text/event-stream")


@app.get("/runs/{run_id}/interaction", response_class=HTMLResponse)
async def get_interaction(request: Request, run_id: str) -> Any:
    """Poll for pending interaction/prompt from the run."""
    try:
        interaction = await api_client.get_interaction(run_id)
        if not interaction:
            return '<div class="card"><p>No pending prompts</p><div hx-get="/runs/' + run_id + '/interaction" hx-trigger="every 2s" hx-swap="outerHTML"></div></div>'

        prompt = interaction.get("prompt", "")
        return templates.TemplateResponse(
            request,
            "interaction_form.html",
            {
                "run_id": run_id,
                "prompt": prompt,
            },
        )
    except Exception as exc:
        log.exception("Error polling for prompts for run %s", run_id)
        return f'<div class="card" style="border-color: var(--red)"><h3>Error polling for prompts</h3><p>{exc}</p></div>'


@app.post("/runs/{run_id}/interaction", response_class=HTMLResponse)
async def submit_interaction(request: Request, run_id: str, response: str = Form("")) -> Any:
    """Submit user response to a pending interaction."""
    try:
        result = await api_client.submit_interaction(run_id, {"response": response})
        return f'<div class="card"><p>Response submitted</p></div>'
    except Exception as exc:
        log.exception("Error submitting interaction for run %s", run_id)
        return f'<div class="card" style="border-color: var(--red)"><h3>Error: {exc}</h3></div>'


@app.get("/runs/{run_id}/terminal", response_class=HTMLResponse)
async def get_interactive_terminal(request: Request, run_id: str) -> Any:
    """Display the interactive terminal page for a run."""
    return templates.TemplateResponse(
        request,
        "interactive_terminal.html",
        {
            "run_id": run_id,
        },
    )
