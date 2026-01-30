#!/bin/bash
set -e

# Pre-warm Azure credentials if .azure directory is mounted (local dev)
# This prevents race conditions when multiple threads try to read the token cache
if [ -d "/root/.azure" ] && command -v az &> /dev/null; then
    echo "Pre-warming Azure credentials..."
    # Attempt to get a token - this loads and caches the credential
    az account get-access-token --resource https://management.azure.com/ > /dev/null 2>&1 || true
    echo "Azure credential pre-warm complete"
fi

# Execute the original command
exec "$@"
