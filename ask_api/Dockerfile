FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install system dependencies for Azure CLI
RUN apt-get update && apt-get install -y \
    curl \
    && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy all necessary files
COPY pyproject.toml uv.lock .python-version config.yaml run_server.py ./
COPY packages/ packages/

RUN uv sync --frozen

# Expose port 8000 (standard port, Azure will map to 80/443)
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    NLWEB_CONFIG_DIR=/app

# Add entrypoint script to pre-warm Azure credentials (fixes race condition on macOS Docker)
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

# Standard Docker pattern: Use CMD with full command
# Azure App Service will respect this if no startup command is configured
CMD [".venv/bin/python", "run_server.py"]
