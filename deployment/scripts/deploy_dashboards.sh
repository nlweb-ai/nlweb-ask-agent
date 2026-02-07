#!/bin/bash
# Deploy Grafana dashboards to Azure Managed Grafana
#
# Usage:
#   GRAFANA_NAME=<name> AZURE_RESOURCE_GROUP=<rg> ./deploy_dashboards.sh
#
# Each dashboard JSON must include a stable "uid" inside the "dashboard" object.
# The script upserts by uid (create --overwrite) and removes any older duplicates
# that share the same title but have a different uid.
#
# Requires: az CLI with grafana extension, jq

set -euo pipefail

GRAFANA_NAME="${GRAFANA_NAME:?Error: GRAFANA_NAME is required}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:?Error: AZURE_RESOURCE_GROUP is required}"

DASHBOARD_DIR="$(cd "$(dirname "$0")/../dashboards" && pwd)"

echo "Deploying dashboards from: $DASHBOARD_DIR"
echo "Grafana instance: $GRAFANA_NAME (resource group: $RESOURCE_GROUP)"

# Fetch the full list of dashboards once for duplicate cleanup
existing_dashboards=$(az grafana dashboard list \
    --name "$GRAFANA_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    -o json 2>/dev/null || echo "[]")

for dashboard_file in "$DASHBOARD_DIR"/*.json; do
    dashboard_name=$(basename "$dashboard_file" .json)
    target_uid=$(jq -r '.dashboard.uid // empty' "$dashboard_file")
    target_title=$(jq -r '.dashboard.title // empty' "$dashboard_file")

    if [[ -z "$target_uid" ]]; then
        echo "  SKIP $dashboard_name: missing .dashboard.uid in JSON"
        continue
    fi

    # Delete duplicates: same title, different uid
    dup_uids=$(echo "$existing_dashboards" | \
        jq -r --arg title "$target_title" --arg uid "$target_uid" \
        '.[] | select(.title == $title and .uid != $uid) | .uid')

    for dup_uid in $dup_uids; do
        echo "  Removing duplicate: $target_title (uid=$dup_uid)"
        az grafana dashboard delete \
            --name "$GRAFANA_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --dashboard "$dup_uid" \
            --output none 2>/dev/null || true
    done

    # Upsert the dashboard by uid
    echo "  Deploying: $dashboard_name (uid=$target_uid)"
    az grafana dashboard create \
        --name "$GRAFANA_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --definition "$dashboard_file" \
        --overwrite true \
        --output none

    echo "  Done: $dashboard_name"
done

echo "All dashboards deployed successfully."

# Print Grafana URL
GRAFANA_URL=$(az grafana show --name "$GRAFANA_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.endpoint" -o tsv 2>/dev/null)
if [[ -n "$GRAFANA_URL" ]]; then
    echo ""
    echo "Grafana: $GRAFANA_URL"
fi
