# SPDX-License-Identifier: Apache-2.0
#
# Multi-stage image — must match lpasquali/rune-ci/docker/rune-ui-slim.Dockerfile
# (canonical). Change the rune-ci copy first, then mirror here.

FROM python:3.14-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY rune_ui/ rune_ui/

RUN pip install --no-cache-dir pip==26.0 \
 && pip install --no-cache-dir --prefer-binary .

FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/lpasquali/rune-ui"
LABEL org.opencontainers.image.description="RUNE UI — FastAPI web UI for the RUNE ecosystem"
LABEL org.opencontainers.image.licenses="Apache-2.0"

RUN groupadd -r rune && useradd -r -g rune -u 1000 -d /app -s /sbin/nologin rune

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

USER rune

EXPOSE 8080
ENTRYPOINT ["python", "-m", "uvicorn", "rune_ui.main:app", "--host", "0.0.0.0", "--port", "8080"]
