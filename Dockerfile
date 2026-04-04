# RUNE UI Dockerfile (Zero NPM)
FROM python:3.12-slim-bookworm

# 1. Security: Create non-root user
RUN groupadd -r rune && useradd -r -g rune -u 1000 rune

# 2. Dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Application code
COPY app/ app/
COPY static/ static/

# 4. Security: Hardening
RUN chown -R rune:rune /app
USER 1000

# 5. Runtime
EXPOSE 8080
ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
