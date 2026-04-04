# ISSUE #1: Design and Implement the Solarized 'Unix Guy' UI (Zero-NPM)

## 1. Overview
Implement `rune-ui`, the "Face" (BFF) of the RUNE ecosystem. This component is a **thin interface** to the `rune-api`, providing a modular, observable dashboard with high-fidelity benchmark reports.

## 2. Core Vision
- **Zero NPM:** Strictly avoid JavaScript frameworks and the NPM ecosystem to prevent trojan injections and supply chain hacks.
- **Technology Stack:** Python 3.14 + FastAPI + HTMX + Jinja2 (Auto-escaping).
- **Aesthetic:** "Modern Unix Guy" with a custom **Solarized** theme (Light/Dark) and **Fira Code** typography. Smooth interactions via HTMX server-driven fragments.

## 3. Key Features
### A. Modular Configuration
- Modular interface for configuring Vast.ai, Ollama, and Agent Tracks.
- All configuration logic is fetched from and saved to the `rune-api`.

### B. Observability & Logging
- Streaming log viewer (using SSE/HTMX) for active `rune` jobs.
- Visual dashboard for system health (API, Operator, Jobs).

### C. Benchmark Reports & Costs
- Detailed breakdown of costs: 
    - Cloud (Vast.ai, AWS/GCP/Azure stubs).
    - Local Hardware (TDP, energy rates, amortization).
- **Pre-Flight Spend Alert:** A mandatory modal that warns the user about projected costs *before* execution.
- Performance analytics comparing similar "Scopes" historically.

### D. Persistence
- **S3 (Default):** Enforced for long-term historical report storage.
- **PVC/NFS Fallback:** Supported for local development and test environments.

## 4. Quality Gates (RuneGate)
- **Coverage:** Mandatory 97% minimum (targeting 100%).
- **Security:** Strict CVE blocking (Grype/Trivy threshold 7.0), `bandit`, and `ruff`.
- **Merge Security:** Mandatory `merge-gate` check in CI.

## 5. Tasks
- [ ] Setup FastAPI + Jinja2 + HTMX foundation.
- [ ] Implement the Solarized layout (Zero-NPM Tailwind/CSS).
- [ ] Develop the thin `api_client.py` for `rune-api` communication.
- [ ] Build the Pre-Flight Spend Alert modal.
- [ ] Integrate S3/PVC report fetching.
