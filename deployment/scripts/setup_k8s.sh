#!/bin/bash
# Setup Kubernetes infrastructure: cert-manager, KEDA, ALB controller, and Gateway
# This script is idempotent - it skips components that are already installed
set -e

echo "=== Kubernetes Infrastructure Setup ==="

# Check required environment variables
if [ -z "$AZURE_RESOURCE_GROUP" ] || [ -z "$AKS_NAME" ]; then
    echo "Missing required environment variables."
    echo "Required: AZURE_RESOURCE_GROUP, AKS_NAME"
    exit 1
fi

# Get script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Resource Group: $AZURE_RESOURCE_GROUP"
echo "AKS: $AKS_NAME"
echo "Repo Root: $REPO_ROOT"

# Get AKS credentials
echo ""
echo "=== Getting AKS credentials ==="
az aks get-credentials --name "$AKS_NAME" --resource-group "$AZURE_RESOURCE_GROUP" --overwrite-existing

# Install ALB Controller
if ! helm status alb-controller -n azure-alb-system &>/dev/null; then
    echo ""
    echo "=== Installing ALB Controller ==="
    if [ -z "$ALB_CONTROLLER_IDENTITY_CLIENT_ID" ]; then
        echo "Error: ALB_CONTROLLER_IDENTITY_CLIENT_ID is required for ALB controller installation"
        exit 1
    fi
    helm install alb-controller \
        oci://mcr.microsoft.com/application-lb/charts/alb-controller \
        --namespace azure-alb-system --create-namespace \
        --version 1.9.7 \
        --set albController.podIdentity.clientID="$ALB_CONTROLLER_IDENTITY_CLIENT_ID" \
        --wait
else
    echo ""
    echo "=== ALB Controller already installed, skipping ==="
fi

# Install cert-manager
if ! helm status cert-manager -n cert-manager &>/dev/null; then
    echo ""
    echo "=== Installing cert-manager ==="
    helm repo add jetstack https://charts.jetstack.io --force-update
    helm install cert-manager jetstack/cert-manager \
        --namespace cert-manager --create-namespace \
        --version v1.19.2 \
        --set crds.enabled=true \
        --set config.apiVersion="controller.config.cert-manager.io/v1alpha1" \
        --set config.kind="ControllerConfiguration" \
        --set config.enableGatewayAPI=true \
        --wait
else
    echo ""
    echo "=== cert-manager already installed, skipping ==="
fi

# Install Gateway chart
echo ""
echo "=== Installing Gateway ==="
if [ -z "$ALB_SUBNET_ID" ]; then
    echo "Error: ALB_SUBNET_ID is required for Gateway installation"
    exit 1
fi

# Install KEDA (with Azure Workload Identity enabled)
if ! helm status keda -n keda &>/dev/null; then
    echo ""
    echo "=== Installing KEDA ==="
    if [ -z "$KEDA_IDENTITY_CLIENT_ID" ] || [ -z "$AZURE_TENANT_ID" ]; then
        echo "Error: KEDA_IDENTITY_CLIENT_ID and AZURE_TENANT_ID are required for KEDA installation"
        exit 1
    fi
    helm repo add kedacore https://kedacore.github.io/charts --force-update
    helm install keda kedacore/keda \
        --namespace keda --create-namespace \
        --version 2.18.3 \
        --set podIdentity.azureWorkload.enabled=true \
        --set podIdentity.azureWorkload.clientId="$KEDA_IDENTITY_CLIENT_ID" \
        --set podIdentity.azureWorkload.tenantId="$AZURE_TENANT_ID" \
        --wait
else
    echo ""
    echo "=== KEDA already installed, skipping ==="
fi

# Auto-detect TLS secret - if nlweb-tls-secret exists, enable TLS
TLS_SECRET_NAME=""
if kubectl get secret nlweb-tls-secret -n gateway &>/dev/null; then
    TLS_SECRET_NAME="nlweb-tls-secret"
    echo "TLS secret found: $TLS_SECRET_NAME (TLS will be enabled)"
else
    echo "TLS secret not found (HTTP mode)"
fi

helm upgrade --install nlweb-gateway "$REPO_ROOT/helm/gateway" \
    --namespace gateway --create-namespace \
    --set alb.subnetResourceId="$ALB_SUBNET_ID" \
    --set certManager.email="${AZURE_CERT_MANAGER_EMAIL:-admin@nlweb.ai}" \
    --set tlsSecretName="$TLS_SECRET_NAME" \
    --wait

echo ""
echo "=== Kubernetes Infrastructure Setup Complete ==="

# Output status
echo ""
echo "=== Installation Status ==="
helm list -A | grep -E "cert-manager|keda|alb-controller|nlweb-gateway" || true

echo ""
echo "=== Gateway Status ==="
kubectl get gateway -n gateway 2>/dev/null || echo "Gateway resource not yet created"

echo ""
echo "=== IMPORTANT: ALB Provisioning ==="
echo ""
echo "The Azure Application Load Balancer takes approximately 5 minutes to provision."
echo "The Gateway will not have an address until the ALB is ready."
echo ""
echo "Check Gateway status with:"
echo "  kubectl get gateway nlweb-gateway -n gateway"
echo ""
echo "Wait until you see an ADDRESS before proceeding:"
echo "  NAME             CLASS                ADDRESS                              READY"
echo "  nlweb-gateway    azure-alb-external   abc123.eastus.cloudapp.azure.com    True"
echo ""
echo "=== Next Step ==="
echo "Once the Gateway has an ADDRESS, configure DNS and request a TLS certificate:"
echo "  make request-certificate HOSTNAME=<your-domain>"
echo ""
echo "=== Done ==="
