#!/bin/bash
# Deploy application (ask-api, crawler) to AKS
# Infrastructure (cert-manager, KEDA, ALB controller, Gateway) must be installed
# first via setup_k8s.sh
# Images must be built first via build_images.sh
set -e

echo "=== AKS Application Deployment Script ==="

# Check required environment variables
if [ -z "$AZURE_RESOURCE_GROUP" ] || [ -z "$ACR_NAME" ] || [ -z "$AKS_NAME" ]; then
    echo "Missing required environment variables. Run 'azd env refresh' first."
    echo "Required: AZURE_RESOURCE_GROUP, ACR_NAME, AKS_NAME"
    exit 1
fi

# Get script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Resource Group: $AZURE_RESOURCE_GROUP"
echo "ACR: $ACR_NAME"
echo "AKS: $AKS_NAME"
echo "Repo Root: $REPO_ROOT"

# Get image digests (after build, so we get the latest)
echo ""
echo "=== Getting image digests ==="
ASK_API_IMAGE_TAG=$(az acr manifest list-metadata --registry "$ACR_NAME" --name ask-api --query "[?tags[?@=='latest']].digest | [0]" -o tsv 2>/dev/null)
CRAWLER_IMAGE_TAG=$(az acr manifest list-metadata --registry "$ACR_NAME" --name crawler --query "[?tags[?@=='latest']].digest | [0]" -o tsv 2>/dev/null)
echo "Ask API Digest: ${ASK_API_IMAGE_TAG:-latest}"
echo "Crawler Digest: ${CRAWLER_IMAGE_TAG:-latest}"

# Login to ACR (needed for pulling container images)
echo ""
echo "=== Logging into ACR ==="
az acr login --name "$ACR_NAME"

HELM_DIR="$REPO_ROOT/helm/nlweb"
ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
echo "ACR Login Server: $ACR_LOGIN_SERVER"

# Get AKS credentials
echo ""
echo "=== Getting AKS credentials ==="
az aks get-credentials --name "$AKS_NAME" --resource-group "$AZURE_RESOURCE_GROUP" --overwrite-existing

# Verify Gateway is installed
if ! helm status nlweb-gateway -n gateway &>/dev/null; then
    echo ""
    echo "Warning: Gateway not installed. Run 'make setup-k8s' first."
    echo "Continuing with application deployment..."
fi

# Generate Helm values from AZD environment
echo ""
echo "=== Generating Helm values ==="
VALUES_FILE="/tmp/values-generated.yaml"

# Get the Helm values JSON from AZD output
HELM_VALUES_JSON=$(azd env get-values --output json 2>/dev/null | jq -r '.HELM_VALUES_JSON // empty')

if [ -z "$HELM_VALUES_JSON" ]; then
    echo "HELM_VALUES_JSON not found in environment. Generating from individual values..."

    # Build values from individual environment variables
    # Application chart only - Gateway is installed separately via setup_k8s.sh
    cat > "$VALUES_FILE" << EOF
global:
  azure:
    tenantId: "$AZURE_TENANT_ID"
  keyVault:
    name: "$AZURE_KEYVAULT_NAME"
    tenantId: "$AZURE_TENANT_ID"
  containerRegistry:
    server: "$ACR_LOGIN_SERVER"
ask-api:
  enabled: true
  serviceAccount:
    name: "ask-api-sa"
  image:
    tag: "${ASK_API_IMAGE_TAG:-latest}"
  workloadIdentity:
    clientId: "$ASK_API_IDENTITY_CLIENT_ID"
crawler:
  enabled: true
  serviceAccount:
    name: "crawler-sa"
  image:
    tag: "${CRAWLER_IMAGE_TAG:-latest}"
  workloadIdentity:
    clientId: "$CRAWLER_IDENTITY_CLIENT_ID"
    kedaIdentityId: "$KEDA_IDENTITY_CLIENT_ID"
  autoscaling:
    storageAccountName: "$STORAGE_ACCOUNT_NAME"
EOF
else
    echo "$HELM_VALUES_JSON" > "$VALUES_FILE"
fi

echo "Generated values file:"
cat "$VALUES_FILE"

# Update Helm dependencies and install from local chart
echo ""
echo "=== Updating Helm dependencies ==="
helm dependency update "$HELM_DIR"

echo ""
echo "=== Installing Helm chart ==="
helm upgrade --install nlweb "$HELM_DIR" \
    -f "$VALUES_FILE" \
    --wait \
    --timeout 25m

echo ""
echo "=== Helm deployment completed ==="

# Output deployment status
echo ""
echo "=== Deployment Status ==="
helm list -A
echo ""
kubectl get pods -A | grep -E "ask-api|crawler|chat-app" || true

echo ""
echo "=== Application Deployment Complete ==="

# Get Gateway FQDN and TLS status
GATEWAY_FQDN=$(kubectl get gateway nlweb-gateway -n gateway -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)
TLS_ENABLED=$(kubectl get gateway nlweb-gateway -n gateway -o jsonpath='{.spec.listeners[?(@.name=="https")].name}' 2>/dev/null)

if [ -n "$GATEWAY_FQDN" ]; then
    echo ""
    echo "Gateway FQDN: $GATEWAY_FQDN"

    if [ -n "$TLS_ENABLED" ]; then
        echo ""
        echo "Visit your application at: https://$GATEWAY_FQDN"
    else
        echo ""
        echo "Visit your application at: http://$GATEWAY_FQDN"
        echo ""
        echo "=== Next Steps: Enable TLS ==="
        echo ""
        echo "Option 1: Request a certificate for the Azure FQDN"
        echo "  make request-certificate HOSTNAME=$GATEWAY_FQDN"
        echo ""
        echo "Option 2: Use your own domain"
        echo "  1. Create a CNAME record pointing your domain to: $GATEWAY_FQDN"
        echo "  2. Request a certificate: make request-certificate HOSTNAME=<your-domain>"
        echo ""
        echo "After requesting, check status with: make check-certificate"
        echo "Once ready, enable TLS with: make enable-tls ENV_NAME=<env>"
    fi
else
    echo ""
    echo "Gateway FQDN not yet available. Check status with:"
    echo "  kubectl get gateway nlweb-gateway -n gateway"
fi

echo ""
echo "=== Done ==="
