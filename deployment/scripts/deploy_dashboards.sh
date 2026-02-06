#!/bin/bash
# Deploy Grafana dashboards to Azure Managed Grafana
#
# Usage:
#   GRAFANA_NAME=<name> AZURE_RESOURCE_GROUP=<rg> ./deploy_dashboards.sh
#
# Requires: az CLI with grafana extension

set -euo pipefail

GRAFANA_NAME="${GRAFANA_NAME:?Error: GRAFANA_NAME is required}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:?Error: AZURE_RESOURCE_GROUP is required}"

DASHBOARD_DIR="$(cd "$(dirname "$0")/../dashboards" && pwd)"

echo "Deploying dashboards from: $DASHBOARD_DIR"
echo "Grafana instance: $GRAFANA_NAME (resource group: $RESOURCE_GROUP)"

for dashboard_file in "$DASHBOARD_DIR"/*.json; do
    dashboard_name=$(basename "$dashboard_file" .json)
    echo "  Deploying: $dashboard_name"

    az grafana dashboard import \
        --name "$GRAFANA_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --definition @"$dashboard_file" \
        --overwrite true \
        --output none

    echo "  Done: $dashboard_name"
done

echo "All dashboards deployed successfully."
