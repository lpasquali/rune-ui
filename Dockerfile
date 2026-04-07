# RUNE UI Dockerfile (Zero NPM)
FROM python:3.13-slim-bookworm

# 1. Security: Create non-root user
RUN groupadd -r rune && useradd -r -g rune -u 1000 rune

# 2. Dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 3. Application code
COPY rune_ui/ rune_ui/

# 4. Security: Hardening
RUN chown -R rune:rune /app
USER 1000

# 5. Runtime
EXPOSE 8080
ENTRYPOINT ["python", "-m", "uvicorn", "rune_ui.main:app", "--host", "0.0.0.0", "--port", "8080"]