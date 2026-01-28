FROM python:3.12-slim

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install system dependencies for pymssql (FreeTDS) and Azure CLI
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    freetds-dev \
    freetds-bin \
    curl \
    && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock .python-version ./

# Install dependencies with uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY code/ ./code/

# Create necessary directories
RUN mkdir -p data/sites/jsonl

# Expose port for API server (master mode)
EXPOSE 5001

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

# Default to master mode (API server)
# Worker deployments override with: command: [".venv/bin/python", "code/core/worker.py"]
CMD [".venv/bin/python", "code/core/api.py"]
