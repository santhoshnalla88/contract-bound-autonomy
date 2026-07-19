FROM python:3.12-slim

# Build deps for packages that may need compilation (psycopg, chromadb onnx, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

# Install dependencies + package (better layer caching).
COPY pyproject.toml README.md ./
COPY core/ core/
COPY apps/ apps/
COPY examples/ examples/
RUN pip install -U pip setuptools wheel && pip install -e .

# Runtime assets.
COPY knowledge/ knowledge/
COPY migrations/ migrations/
COPY alembic.ini ./

EXPOSE 8000

# Default command runs the API; the worker service overrides it in docker-compose.
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
