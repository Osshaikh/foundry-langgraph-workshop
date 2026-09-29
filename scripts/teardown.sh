#!/usr/bin/env bash
set -euo pipefail
ALIAS=""; LOCATION="eastus2"; FORCE="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --alias|-a) ALIAS="$2"; shift 2 ;;
    --location|-l) LOCATION="$2"; shift 2 ;;
    --force|-f) FORCE="true"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ ! "$ALIAS" =~ ^[a-z0-9]{3,8}$ ]]; then echo "Usage: $0 --alias <3-8 lowercase letters/numbers> [--location eastus2] [--force]" >&2; exit 2; fi
RG="rg-lgws-$ALIAS"; ACCOUNT="aif-lgws-$ALIAS"
if [[ "$FORCE" != "true" ]]; then
  read -r -p "Delete resource group '$RG' and purge Foundry account '$ACCOUNT'? Type DELETE to continue: " CONFIRM
  [[ "$CONFIRM" == "DELETE" ]] || { echo "Cancelled."; exit 0; }
fi
echo "Starting resource group deletion: $RG"
az group delete -n "$RG" --yes --no-wait
echo "Waiting for resource group deletion before purge (this can take several minutes)..."
az group wait --name "$RG" --deleted
echo "Purging soft-deleted Cognitive Services account: $ACCOUNT"
az cognitiveservices account purge --location "$LOCATION" --resource-group "$RG" --name "$ACCOUNT" -o none
echo "Cleanup requested."
