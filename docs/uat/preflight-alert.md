# UAT: Pre-Flight Spend Alert Verification

**Issue:** #10  
**Feature:** Pre-flight spend warning modal that blocks benchmark execution until confirmed.

---

## Overview

Before any benchmark job is submitted to the RUNE API, the UI must display a cost-estimate modal
fetched from `POST /v1/estimates`.  The modal blocks execution — no job is submitted until the
operator explicitly clicks **CONFIRM & RUN**.

---

## Pre-requisites

| Requirement | Value |
|-------------|-------|
| RUNE UI running | `python -m uvicorn app.main:app --reload` |
| RUNE API mock or live | `RUNE_API_URL=http://localhost:8080` |
| Browser | Any modern browser with DevTools |

---

## Test Steps

### TC-01 — Modal appears before any job submission

1. Open the RUNE UI in a browser and navigate to **Benchmarks**.
2. Fill in the benchmark form (model, Vast.ai toggle, max DPH).
3. Click **Evaluate Cost & Proceed**.
4. **Expected:** The **PRE-FLIGHT SPEND ALERT** modal appears overlaid on the page.
5. **Expected:** The modal shows the projected cost (`$X.XX`) sourced from `/v1/estimates`.
6. **Expected:** No benchmark job has been submitted yet (confirm via `GET /v1/jobs` — list unchanged).

### TC-02 — Execution is blocked until confirmation

1. With the modal visible, attempt any other page interaction (click elsewhere, navigate).
2. **Expected:** The overlay prevents interaction with the underlying form.
3. Click **CANCEL** in the modal.
4. **Expected:** The modal closes; no job is submitted.
5. Repeat step 2–3 of TC-01, then click **CONFIRM & RUN**.
6. **Expected:** The Benchmark Tracker panel appears; a new job ID is displayed.
7. **Expected:** `GET /v1/jobs/<job_id>` returns `status: queued` or `running`.

### TC-03 — Real-time cost projection matches `/v1/estimates`

1. Open DevTools → Network tab.
2. Submit the benchmark form.
3. Locate the `POST /benchmarks/estimate` request.
4. Compare the `projected_cost_usd`, `cost_driver`, and `resource_impact` fields in the API
   response with the values shown in the PRE-FLIGHT SPEND ALERT modal.
5. **Expected:** All three fields match exactly.

### TC-04 — Energy consumption line appears only for local hardware

1. Enable **Use Local Hardware (Airgapped)** checkbox and submit.
2. **Expected:** The modal shows an **Energy consumption: X.XX kWh** line.
3. Disable **Use Local Hardware** and re-submit.
4. **Expected:** The energy consumption line is absent.

### TC-05 — Warning banner appears when API returns a warning

1. Configure the RUNE API mock to return `"warning": "GPU memory may be insufficient"`.
2. Submit the benchmark form.
3. **Expected:** The modal shows a highlighted warning line with the text above.

---

## Pass / Fail Criteria

| Test Case | Pass Condition |
|-----------|---------------|
| TC-01 | Modal shown; no job submitted |
| TC-02 | CANCEL dismisses modal without submission; CONFIRM creates a job |
| TC-03 | Modal values match `/v1/estimates` response exactly |
| TC-04 | Energy line conditional on local hardware selection |
| TC-05 | Warning banner present when API returns warning |

---

## Notes

- The pre-flight gate is enforced server-side: `POST /api/jobs/submit` is only reachable through
  the CONFIRM form, which carries hidden fields (`model`, `vastai`, `max_dph`) from the estimate
  step.  There is no way to bypass it via normal UI navigation.
- The estimate is sourced live from `POST /v1/estimates` on every form submission — values are
  never cached between sessions.
