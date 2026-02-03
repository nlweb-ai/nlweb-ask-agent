#!/bin/bash
# Build Docker images via ACR Tasks
set -e

echo "=== Building Images via ACR Tasks ==="

if [ -z "$ACR_NAME" ]; then
    echo "Error: ACR_NAME is required"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "ACR: $ACR_NAME"
echo "Repo Root: $REPO_ROOT"

echo ""
echo "=== Building ask-api image ==="
az acr build \
    --registry "$ACR_NAME" \
    --image ask-api:latest \
    --file "$REPO_ROOT/ask_api/Dockerfile" \
    "$REPO_ROOT/ask_api"
sleep 5
echo ""
echo "=== Building crawler image ==="
az acr build \
    --registry "$ACR_NAME" \
    --image crawler:latest \
    --file "$REPO_ROOT/crawler/Dockerfile" \
    "$REPO_ROOT/crawler"
sleep 5
echo ""
echo "=== Building chat-app image ==="
az acr build \
    --registry "$ACR_NAME" \
    --image chat-app:latest \
    --file "$REPO_ROOT/chat-app/Dockerfile" \
    "$REPO_ROOT/chat-app"

echo ""
echo "=== Build Complete ==="
echo ""
echo "=== Next Step ==="
echo "Deploy the application:"
echo "  make install-nlweb ENV_NAME=<env>"
