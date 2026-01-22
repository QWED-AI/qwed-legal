FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/QWED-AI/qwed-legal"
LABEL org.opencontainers.image.description="QWED Legal Verification Action"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Install dependencies
WORKDIR /app

COPY pyproject.toml .
COPY qwed_legal/ qwed_legal/
COPY action_entrypoint.py .

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "/app/action_entrypoint.py"]
