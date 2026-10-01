FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy monorepo shared packages and requirements
COPY pyproject.toml /app/
COPY packages/shared /app/packages/shared
COPY services/risk_guard /app/services/risk_guard
COPY services/engine /app/services/engine
COPY services/execution /app/services/execution
COPY services/api /app/services/api

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx

EXPOSE 8000

CMD ["uvicorn", "services.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
