#!/bin/bash
# Load synthetic schema data into crawler
# Downloads index.json containing site/sitemap pairs and registers each with the crawler API
set -e

echo "=== Loading Synthetic Schema Data ==="

# Validate required variables
if [ -z "$HOSTNAME" ] || [ -z "$SPLIT_NAME" ]; then
    echo "Error: HOSTNAME and SPLIT_NAME are required"
    exit 1
fi

# Configuration
SYNTHETIC_BASE_URL="https://nlwsyntheticschemapublic.z13.web.core.windows.net/ecm0nio5rjdi09mbo8xa0p1c"
INDEX_URL="${SYNTHETIC_BASE_URL}/${SPLIT_NAME}/index.json"
CRAWLER_API_BASE="https://${HOSTNAME}/crawler/api/sites"

echo "Configuration:"
echo "  Index URL: $INDEX_URL"
echo "  Crawler API: $CRAWLER_API_BASE"
echo ""

# Download index.json
echo "=== Downloading index.json ==="
INDEX_JSON=$(curl -sf "$INDEX_URL")
if [ -z "$INDEX_JSON" ]; then
    echo "Error: Failed to download from $INDEX_URL"
    echo "Check that SPLIT_NAME='$SPLIT_NAME' is valid."
    exit 1
fi

TOTAL_COUNT=$(echo "$INDEX_JSON" | jq 'length')
echo "Found $TOTAL_COUNT site(s) to process"
echo ""

# Track results
SUCCESS_COUNT=0
FAILURE_COUNT=0

echo "=== Processing Sites ==="

# Process each site
for i in $(seq 0 $((TOTAL_COUNT - 1))); do
    SITE=$(echo "$INDEX_JSON" | jq -r ".[$i].site")
    SITEMAP_URL=$(echo "$INDEX_JSON" | jq -r ".[$i].sitemap_url")
    ENCODED_SITE=$(echo -n "$SITE" | jq -sRr @uri)

    echo "[$((i + 1))/$TOTAL_COUNT] $SITE"
    echo "  Sitemap: $SITEMAP_URL"

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${CRAWLER_API_BASE}/${ENCODED_SITE}/schema-files" \
        -H "Content-Type: application/json" \
        -d "{\"schema_map_url\": \"$SITEMAP_URL\"}")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
        echo "  Status: SUCCESS"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo "  Status: FAILED (HTTP $HTTP_CODE)"
        echo "  Error: $BODY"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
    fi
    echo ""
done

# Summary
echo "=== Summary ==="
echo "Total: $TOTAL_COUNT | Success: $SUCCESS_COUNT | Failed: $FAILURE_COUNT"

if [ $FAILURE_COUNT -gt 0 ]; then
    exit 1
fi

echo ""
echo "=== Load Complete ==="
