#!/bin/bash
set -e

if [ -n "$AZURE_CLIENT_ID" ]; then
    echo "Logging in to Azure with managed identity..."
    az login --identity --client-id "$AZURE_CLIENT_ID" --allow-no-subscriptions -o none 2>&1 || true
    az account set --subscription "$AZURE_SUBSCRIPTION_ID" 2>&1 || true
    echo "Azure login complete"
fi

exec python run_server.py