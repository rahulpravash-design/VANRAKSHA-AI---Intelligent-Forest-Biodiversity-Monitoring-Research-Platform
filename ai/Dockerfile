# syntax=docker/dockerfile:1
# The standalone AI inference microservice. Only relevant when
# AI_SERVICE_URL is set on the backend; otherwise the backend imports this
# package in-process and this image is unused.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY ai/requirements.txt ai/requirements.txt
RUN pip install -r ai/requirements.txt

COPY ai ai

WORKDIR /app
EXPOSE 8001
ENV PYTHONPATH=/app

CMD ["uvicorn", "ai.service.main:app", "--host", "0.0.0.0", "--port", "8001"]
