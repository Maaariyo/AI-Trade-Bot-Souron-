# syntax=docker/dockerfile:1
# Python image for the api and worker services (development).
# Build context: repository root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_SYSTEM_CERTS=1 \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PATH=/opt/venv/bin:$PATH

# Optional extra CA for TLS-intercepting proxies. Compose passes an empty file
# unless EXTRA_CA_CERT_FILE is set; an empty file changes nothing.
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then \
      cat /run/secrets/extra_ca >> /etc/ssl/certs/ca-certificates.crt; \
    fi

RUN pip install --no-cache-dir uv==0.11.32

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

COPY services ./services
COPY db ./db

EXPOSE 8000
CMD ["sh", "-c", "python -m services.migrate && uvicorn services.api.main:app --host 0.0.0.0 --port 8000"]
