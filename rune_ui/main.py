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


@app.get("/suites", response_class=HTMLResponse)
async def get_suites_page(request: Request) -> Any:
    return templates.TemplateResponse(request, "suites.html")


@app.post("/suites/create", response_class=HTMLResponse)
async def create_suite(
    request: Request,
    agents: str = Form(...),
    models: str = Form(...),
    backend_type: str = Form("ollama"),
    aws: bool = Form(False),
) -> Any:
    # Logic to create the Kubernetes Custom Resource (RuneBenchmarkSuite)
    # This assumes the UI has permission to create CRDs in the cluster
    agent_list = [a.strip() for a in agents.split(",")]
    model_list = [m.strip() for m in models.split(",")]
    
    suite_manifest = {
        "apiVersion": "bench.rune.ai/v1alpha1",
        "kind": "RuneBenchmarkSuite",
        "metadata": {"name": f"suite-{int(time.time())}"},
        "spec": {
            "agents": agent_list,
            "models": model_list,
            "template": {
                "workflow": "agentic-agent",
                "backendType": backend_type,
                "costEstimation": {"aws": aws}
            }
        }
    }
    
    # Send to operator/kube-api or the RUNE core if it proxies k8s
    # For now, we simulate the 'instantiation' success
    return HTMLResponse(f'<div class="card" style="border-color: var(--green)"><h3>Batch Instantiated</h3><p>Created suite with {len(agent_list) * len(model_list)} parallel jobs.</p><button hx-get="/suites" hx-target="#main">Back to Suites</button></div>')


@app.get("/api/suites", response_class=HTMLResponse)
async def get_active_suites(request: Request) -> str:
    # Return a mock or real list of suites
    return '<div class="card"><p>No active suites found. Create one above to start parallel benchmarking.</p></div>'


@app.get("/api/jobs/count", response_class=HTMLResponse)
async def get_active_job_count(request: Request) -> str:
    """Return the raw count of active jobs for the sidebar badge."""
    try:
        reports_data = await api_client.get_reports()
        events = reports_data.get("events", [])
        active = [e for e in events if e.get("status") in ["running", "pending"]]
        return str(len(active))
    except Exception:
        return "0"


@app.get("/api/jobs/active", response_class=HTMLResponse)
async def get_active_job_list(request: Request) -> str:
    """Return HTML cards for all active/pending jobs for the drawer."""
    try:
        reports_data = await api_client.get_reports()
        events = reports_data.get("events", [])
        active = [e for e in events if e.get("status") in ["running", "pending"]]
        
        if not active:
            return '<p style="color: var(--base01); text-align: center; margin-top: 40px;">No active jobs in queue.</p>'
            
        cards = []
        for job in active:
            jid = job.get("job_id", "Unknown")
            status = job.get("status", "unknown")
            cards.append(
                f'<div class="mini-job-card">'
                f'<strong>{jid[:12]}...</strong>'
                f'<div style="display: flex; justify-content: space-between; margin-top: 5px;">'
                f'<span style="color: var(--yellow)">{status.upper()}</span>'
                f'<a href="#" hx-get="/runs/{jid}" hx-target="#main" onclick="toggleDrawer()">Details</a>'
                f'</div></div>'
            )
        return "".join(cards)
    except Exception:
        return '<p style="color: var(--red)">Error fetching queue.</p>'


@app.get("/secrets", response_class=HTMLResponse)
async def get_secrets_page(request: Request) -> Any:
    try:
        secrets = await api_client.get_secrets()
        return templates.TemplateResponse(request, "secrets.html", {"secrets": secrets})
    except Exception:
        log.exception("Failed to load secrets")
        return '<div class="card" style="border-color: var(--red)"><h3>Error</h3><p>Unable to load secrets vault.</p></div>'


@app.post("/secrets/update", response_class=HTMLResponse)
async def update_secret(request: Request, key: str = Form(...), value: str = Form(...)) -> Any:
    try:
        await api_client.update_secret(key, value)
        return HTMLResponse(f'<div class="card" style="border-color: var(--green)"><p>Secret <strong>{key}</strong> updated.</p><button hx-get="/secrets" hx-target="#main">Back to Vault</button></div>')
    except Exception as e:
        return HTMLResponse(f'<div class="card" style="border-color: var(--red)"><p>Update failed: {e}</p></div>')


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


@app.get("/benchmarks/models", response_class=HTMLResponse)
async def get_backend_models_options(
    backend_type: str = "ollama", 
    backend_url: str = ""
) -> str:
    """Fetch model options for a backend and return as HTML <option> tags."""
    try:
        data = await api_client.get_backend_models(backend_type, backend_url)
        models = data.get("models", [])
        if not models:
            return '<option value="">No models found</option>'
        return "".join([f'<option value="{m}">{html.escape(m)}</option>' for m in models])
    except Exception as exc:
        log.error("Failed to fetch models for %s: %s", backend_type, exc)
        return '<option value="">Error fetching models</option>'


@app.post("/benchmarks/estimate", response_class=HTMLResponse)
async def get_benchmark_estimate(
    request: Request,
    kind: str = Form("benchmark"),
    agent: str = Form("sre:k8sgpt"),
    question: str = Form("What is unhealthy in this Kubernetes cluster?"),
    backend_type: str = Form("ollama"),
    backend_url: str = Form(""),
    region: str = Form(""),
    model: str = Form(...),
    vastai: bool = Form(False),
    aws: bool = Form(False),
    gcp: bool = Form(False),
    azure: bool = Form(False),
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
        "region": region,
        "provisioning": provisioning,
        "aws": aws,
        "gcp": gcp,
        "azure": azure,
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
    region: str = Form(""),
    model: str = Form(...),
    vastai: bool = Form(False),
    aws: bool = Form(False),
    gcp: bool = Form(False),
    azure: bool = Form(False),
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
        "region": region,
        "question": question,
        "backend_warmup": True,
        "backend_warmup_timeout": 300,
        "kubeconfig": os.environ.get("RUNE_KUBECONFIG", "~/.kube/config"),
        "backend_url": backend_url if backend_url else None,
        "backend_type": backend_type,
        "aws": aws,
        "gcp": gcp,
        "azure": azure,
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

@app.delete("/api/jobs/{job_id}", response_class=HTMLResponse)
async def delete_job(request: Request, job_id: str) -> str:
    try:
        await api_client.delete_job(job_id)
        return '<div class="card" style="border-left: 5px solid var(--red)"><h3>Job Cancelled</h3><p>Status: <span style="color: var(--red)">CANCELLED</span></p></div>'
    except Exception:
        log.exception("Cancel failed for job %s", job_id)
        return '<p style="color: var(--red)">Error cancelling job.</p>'


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> Any:
    try:
        reports_data = await api_client.get_reports()
        events = reports_data.get("events", [])
        
        labels = []
        cloud_costs = []
        local_costs = []
        for ev in events:
            labels.append(ev.get("job_id", "Unknown"))
            cost = float(ev.get("cost_usd", 0.0) or 0.0)
            if ev.get("backend_type", "cloud") == "local":
                local_costs.append(cost)
                cloud_costs.append(0.0)
            else:
                local_costs.append(0.0)
                cloud_costs.append(cost)
            
        chart_data = {
            "labels": labels,
            "datasets": [
                {
                    "label": "Cloud Execution Cost (USD)",
                    "data": cloud_costs,
                    "backgroundColor": "rgba(52, 211, 153, 0.5)",
                    "borderColor": "rgba(52, 211, 153, 1)",
                    "borderWidth": 1
                },
                {
                    "label": "Local Execution Cost (USD)",
                    "data": local_costs,
                    "backgroundColor": "rgba(99, 102, 241, 0.5)",
                    "borderColor": "rgba(99, 102, 241, 1)",
                    "borderWidth": 1
                }
            ]
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
        
        datasets = []
        tiers = {}
        for ev in events:
            tier = ev.get("tier", "Unknown")
            if tier not in tiers:
                tiers[tier] = []
            cost = float(ev.get("cost_usd", 0.0) or 0.0)
            score = float(ev.get("score", 0.0) or 0.0)
            tiers[tier].append({
                "x": cost,
                "y": score,
                "r": 8,
                "agent": ev.get("agent", "Unknown")
            })

        colors = ["rgba(99, 102, 241, 0.5)", "rgba(52, 211, 153, 0.5)", "rgba(255, 99, 132, 0.5)", "rgba(255, 159, 64, 0.5)"]
        for i, (tier, data) in enumerate(tiers.items()):
            datasets.append({
                "label": f"Tier {tier}",
                "data": data,
                "backgroundColor": colors[i % len(colors)],
                "borderColor": colors[i % len(colors)].replace("0.5", "1"),
                "borderWidth": 1
            })
            
        chart_data = {
            "datasets": datasets
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
    except Exception:
        log.exception("Failed to switch profile")
        return HTMLResponse('<div class="card" style="border-color: var(--red)"><p>Error: Failed to switch profile.</p></div>')

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
    runs_per_period: int = Form(1),
    period_days: int = Form(1),
) -> Any:
    try:
        # Update client to pass new params
        projection = await api_client.get_finops_simulation(
            agent, model, gpu, runs_per_period=runs_per_period, period_days=period_days
        )
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
    except Exception:
        log.exception("FinOps simulation failed")
        return '<div class="card" style="border-color: var(--red)"><h3>Simulation Failed</h3><p>Unable to complete simulation.</p></div>'


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
    except Exception:
        log.exception("Failed to load chain view %s", run_id)
        return '<div class="card" style="border-color: var(--red)"><h3>Error</h3><p>Unable to load chain view.</p></div>'


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

@app.get("/api/reports/{job_id}/export/json", response_class=JSONResponse)
async def export_report_json(job_id: str) -> Any:
    """Export the raw JSON of a benchmark report."""
    try:
        report = await api_client.get_report_content(job_id)
        return JSONResponse(content=report, headers={"Content-Disposition": f'attachment; filename="rune-report-{job_id}.json"'})
    except Exception:
        log.exception("Failed to export report %s", job_id)
        return JSONResponse(status_code=404, content={"error": "Report not found"})

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
            "tokens": tokens.get("total_tokens", 0),
            "result_type": result.get("result_type"),
            "answer": result.get("answer"),
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

        html_str = f'<p>Status: <strong style="color: var(--yellow);">{html.escape(status)}</strong></p>'
        if status not in ["completed", "failed"]:
            escaped_run_id = html.escape(run_id)
            return HTMLResponse(
                content=f'<div hx-get="/runs/{escaped_run_id}/status" hx-trigger="every 2s" hx-swap="outerHTML">{html_str}</div>'
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
            escaped_run_id = html.escape(run_id)
            return f'<div class="card"><p>No pending prompts</p><div hx-get="/runs/{escaped_run_id}/interaction" hx-trigger="every 2s" hx-swap="outerHTML"></div></div>'

        prompt = interaction.get("prompt", "")
        return templates.TemplateResponse(
            request,
            "interaction_form.html",
            {
                "run_id": run_id,
                "prompt": prompt,
            },
        )
    except Exception:
        log.exception("Error polling for prompts for run %s", run_id)
        return '<div class="card" style="border-color: var(--red)"><h3>Error polling for prompts</h3><p>Unable to poll for prompts.</p></div>'


@app.post("/runs/{run_id}/interaction", response_class=HTMLResponse)
async def submit_interaction(request: Request, run_id: str, response: str = Form("")) -> Any:
    """Submit user response to a pending interaction."""
    try:
        await api_client.submit_interaction(run_id, {"response": response})
        return '<div class="card"><p>Response submitted</p></div>'
    except Exception:
        log.exception("Error submitting interaction for run %s", run_id)
        return '<div class="card" style="border-color: var(--red)"><h3>Error</h3><p>Failed to submit response.</p></div>'


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
