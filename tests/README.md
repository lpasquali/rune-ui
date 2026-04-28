# RUNE-UI Test Suite

Tests for the RUNE web dashboard and its interactions with the core API.

## Directory Structure

- **`components/`**: Unit tests for UI views and components: Dashboard, Run Details, Benchmark Wizard, and Interactive Terminal.
- **`integration/`**: Tests for service-level integration: configuration settings sync and LLM backend (Ollama) connectivity.

## Running Tests

Tests are run using `pytest`:

```bash
# Run all UI tests
python -m pytest tests/

# Run components only
python -m pytest tests/components/
```
