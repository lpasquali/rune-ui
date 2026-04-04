import os
from fastapi import FastAPI, Request, Form
import asyncio
from fastapi.responses import HTMLResponse, StreamingResponse

@app.get("/api/jobs/{job_id}/logs")
async def stream_job_logs(request: Request, job_id: str):
    """SSE endpoint to stream event logs from the Brain to the UI."""
    async def event_generator():
        last_event_id = 0
        while True:
            if await request.is_disconnected():
                break
            
            try:
                # Fetch events from the RUNE API
                events_data = await api_client.get_job_status(f"{job_id}/events")
                events = events_data.get("events", [])
                
                # Stream only new events
                if len(events) > last_event_id:
                    for i in range(last_event_id, len(events)):
                        event = events[i]
                        msg = f'<div><span style="color: var(--base01)">[{event["timestamp"]}]</span> <span style="color: var(--yellow)">{event["name"]}</span>: {event.get("message", "")}</div>'
                        yield f"data: {msg}\n\n"
                    last_event_id = len(events)
                
                # Check if job is finished
                job_status = await api_client.get_job_status(job_id)
                if job_status.get("status") in ["succeeded", "failed", "cancelled"]:
                    yield "data: <div><hr><strong>STREAM ENDED</strong></div>\n\n"
                    break
                    
            except Exception as exc:
                yield f"data: <div><span style="color: var(--red)">Log Error: {str(exc)}</span></div>\n\n"
                break
                
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api_client import RuneApiClient

app = FastAPI(title="RUNE UI")
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="app/templates")

# Initialize API client
RUNE_API_URL = os.environ.get("RUNE_API_URL", "http://localhost:8080")
api_client = RuneApiClient(base_url=RUNE_API_URL)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("base.html", {"request": request})

@app.get("/api/status", response_class=HTMLResponse)
async def get_status(request: Request):
    try:
        health = await api_client.get_health()
        status_color = "var(--green)" if health.get("status") == "ok" else "var(--red)"
        return f'<span style="color: {status_color}">API STATUS: {health.get("status", "unknown").upper()}</span>'
    except Exception:
        return '<span style="color: var(--red)">API STATUS: OFFLINE</span>'

@app.get("/benchmarks", response_class=HTMLResponse)
async def get_benchmarks_page(request: Request):
    return templates.TemplateResponse("benchmarks.html", {"request": request})

@app.post("/benchmarks/estimate", response_class=HTMLResponse)
async def get_benchmark_estimate(
    request: Request,
    model: str = Form(...),
    vastai: bool = Form(False),
    max_dph: float = Form(0.0),
    local_hardware: bool = Form(False),
):
    """BFF logic to fetch and display the pre-flight cost estimate."""
    payload = {
        "model": model,
        "vastai": vastai,
        "max_dph": max_dph,
        "local_hardware": local_hardware,
        "local_tdp_watts": 350.0 if local_hardware else 0.0, # Default TDP if local
        "local_energy_rate_kwh": 0.15,
        "estimated_duration_seconds": 3600
    }
    
    try:
        estimate = await api_client.get_estimate(payload)
        return templates.TemplateResponse("estimate_modal.html", {
            "request": request,
            "estimate": estimate
        })
    except Exception as exc:
        return f'<div class="modal" style="border-color: var(--red)"><h3>Estimation Error</h3><p>{str(exc)}</p><button hx-get="/benchmarks" hx-target="#main">Back</button></div>'

@app.post("/api/jobs/submit", response_class=HTMLResponse)
async def submit_benchmark_job(
    request: Request,
    model: str = Form(...),
    vastai: bool = Form(False),
    max_dph: float = Form(0.0),
):
    """BFF logic to submit a job to the RUNE core and show the tracker."""
    payload = {
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
        "ollama_url": None
    }
    
    try:
        job_info = await api_client.submit_job("benchmark", payload)
        job_id = job_info.get("job_id")
        return templates.TemplateResponse("job_tracker.html", {
            "request": request,
            "job_id": job_id
        })
    except Exception as exc:
        return f'<div class="card" style="border-color: var(--red)"><h3>Submission Failed</h3><p>{str(exc)}</p></div>'

@app.get("/api/jobs/{job_id}/status", response_class=HTMLResponse)
async def poll_job_status(request: Request, job_id: str):
    """Poll the RUNE API for job status updates via HTMX."""
    try:
        status_info = await api_client.get_job_status(job_id)
        status = status_info.get("status", "unknown").lower()
        
        # Color based on terminal states
        status_color = "var(--yellow)"
        if status in ["succeeded", "success", "completed"]: status_color = "var(--green)"
        if status in ["failed", "error", "cancelled"]: status_color = "var(--red)"
        
        return f'<div class="card" style="border-left: 5px solid {status_color}"><h3>Job: {job_id}</h3><p>Status: <span style="color: {status_color}">{status.upper()}</span></p><p>{status_info.get("message", "")}</p></div>'
    except Exception as exc:
        return f'<p style="color: var(--red)">Error polling status: {str(exc)}</p>'

@app.get("/config", response_class=HTMLResponse)
async def get_config(request: Request):
    return '<div class="card"><h2>Configuration</h2><p>Manage Vast.ai templates and Ollama endpoints.</p></div>'

@app.get("/reports/{job_id}", response_class=HTMLResponse)
async def view_report(request: Request, job_id: str):
    """BFF logic to fetch and display a specific historical report."""
    try:
        report = await api_client.get_report_content(job_id)
        return templates.TemplateResponse("report_view.html", {
            "request": request,
            "report": report
        })
    except Exception as exc:
        return f'<div class="card" style="border-color: var(--red)"><h3>Report Error</h3><p>{str(exc)}</p></div>'
