# One Dockerfile, two targets: `api` (FastAPI + solver, also serves the planner page at /)
# and `ui` (nginx on 8501 in front of the API, tuned for server-sent events).

FROM python:3.11-slim AS api
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --require-hashes -r requirements.lock
COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY .env.example ./
# Non-root, uid 1000 so the bind-mounted ./data stays writable on Linux hosts.
RUN useradd --uid 1000 --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM nginxinc/nginx-unprivileged:1.27-alpine AS ui
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8501
