FROM python@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144

LABEL org.opencontainers.image.source="https://github.com/QWED-AI/qwed-legal"
LABEL org.opencontainers.image.description="QWED Legal Verification Action"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Install dependencies
WORKDIR /app

COPY pyproject.toml README.md ./
COPY qwed_legal/ qwed_legal/
COPY action_entrypoint.py .

RUN pip install --no-cache-dir .

# One-shot action container: no long-running service to monitor, so the
# health check is explicitly disabled (QWED docker-no-healthcheck rule).
HEALTHCHECK NONE

# GitHub Docker container actions must run as the default user (root):
# the runner-provided GITHUB_OUTPUT / GITHUB_WORKSPACE files are not
# writable by a non-root USER. See Dockerfile support in the GitHub
# Actions docs — non-root hardening is therefore intentionally omitted
# here (issue #41 review).

ENTRYPOINT ["python", "/app/action_entrypoint.py"]
