#!/usr/bin/env bash
set -euo pipefail
ALIAS=""
LOCATION="eastus2"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --alias|-a) ALIAS="$2"; shift 2 ;;
    --location|-l) LOCATION="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ ! "$ALIAS" =~ ^[a-z0-9]{3,8}$ ]]; then echo "Usage: $0 --alias <3-8 lowercase letters/numbers> [--location eastus2]" >&2; exit 2; fi
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_FILE="$REPO_ROOT/infra/main.bicep"
ENV_FILE="$REPO_ROOT/.env"
step(){ printf '\n==> %s\n' "$1"; }
ok(){ printf '\033[32mâœ“ %s\033[0m\n' "$1"; }
require(){ command -v "$1" >/dev/null 2>&1 || { echo "Required command '$1' was not found. Run scripts/install-tools.sh first." >&2; exit 1; }; }
deploy(){
  local mini="$1" reasoning="$2" embedding="$3" ft="$4" name="lgws-$ALIAS-$(date +%Y%m%d%H%M%S)"
  az deployment sub create --name "$name" --location "$LOCATION" --template-file "$TEMPLATE_FILE" \
    --parameters alias="$ALIAS" location="$LOCATION" principalId="$PRINCIPAL_ID" principalType=User \
    gpt54MiniCapacity="$mini" gpt54Capacity="$reasoning" embeddingCapacity="$embedding" gpt41MiniCapacity="$ft" -o json
}
echo "Microsoft Foundry: LangGraph Hosted Agents Workshop provisioning"
echo "Estimated time: 10-15 minutes. This script creates fixed lab resources and writes .env."
require az; require azd
step "Checking Azure CLI sign-in"
if ! az account show -o none >/dev/null 2>&1; then az login -o none; fi
SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
SUBSCRIPTION_NAME="$(az account show --query name -o tsv)"
ok "Using subscription $SUBSCRIPTION_NAME ($SUBSCRIPTION_ID)"
step "Configuring Azure Developer CLI"
azd config set auth.useAzCliAuth true >/dev/null
if ! azd ext list 2>/dev/null | grep -q 'azure\.ai\.agents'; then azd ext install azure.ai.agents; fi
ok "azd auth.useAzCliAuth=true and azure.ai.agents extension present"
step "Registering Azure resource providers"
for provider in Microsoft.CognitiveServices Microsoft.Search Microsoft.ContainerRegistry Microsoft.OperationalInsights Microsoft.Insights; do
  echo "Registering $provider ..."; az provider register --namespace "$provider" --wait -o none
done
ok "Resource providers registered"
step "Reading signed-in user object id"
PRINCIPAL_ID="$(az ad signed-in-user show --query id -o tsv)"
ok "Principal id: $PRINCIPAL_ID"
step "Deploying workshop infrastructure"
set +e
RESULT="$(deploy 250 150 150 100 2>&1)"
STATUS=$?
set -e
if [[ $STATUS -ne 0 ]]; then
  if grep -Eiq 'quota|capacity|insufficient|limit' <<<"$RESULT"; then
    echo "Quota/capacity error detected. Retrying once with half-size model capacities..."
    RESULT="$(deploy 125 75 75 50)"
  else
    echo "$RESULT" >&2; exit $STATUS
  fi
fi
ok "Azure resources deployed"
step "Writing .env at the repository root"
RESULT_JSON="$RESULT" python - "$ENV_FILE" <<'PY'
import json, os, sys
result=json.loads(os.environ["RESULT_JSON"])
out=result["properties"]["outputs"]
keys=[
 ("AZURE_SUBSCRIPTION_ID","azureSubscriptionId"),
 ("AZURE_RESOURCE_GROUP","azureResourceGroup"),
 ("AZURE_LOCATION","azureLocation"),
 ("FOUNDRY_ACCOUNT_NAME","foundryAccountName"),
 ("FOUNDRY_PROJECT_NAME","foundryProjectName"),
 ("FOUNDRY_PROJECT_ENDPOINT","foundryProjectEndpoint"),
 ("FOUNDRY_PROJECT_RESOURCE_ID","foundryProjectResourceId"),
 ("AZURE_AI_MODEL_DEPLOYMENT_NAME","azureAiModelDeploymentName"),
 ("AZURE_AI_REASONING_DEPLOYMENT_NAME","azureAiReasoningDeploymentName"),
 ("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME","azureAiEmbeddingDeploymentName"),
 ("AZURE_AI_FINETUNE_BASE_MODEL","azureAiFinetuneBaseModel"),
 ("AZURE_SEARCH_ENDPOINT","azureSearchEndpoint"),
 ("AZURE_SEARCH_CONNECTION_NAME","azureSearchConnectionName"),
 ("APPLICATIONINSIGHTS_CONNECTION_STRING","applicationInsightsConnectionString"),
 ("RAI_POLICY_NAME","raiPolicyName"),
 ("LAB_PREFIX","labPrefix"),
]
with open(sys.argv[1], "w", encoding="utf-8") as f:
    for env_key, output_key in keys:
        f.write(f"{env_key}={out[output_key]['value']}\n")
PY
ok "Wrote $ENV_FILE"
echo
printf '\033[32mProvisioning complete\033[0m\n'
echo "Resource group: $(RESULT_JSON="$RESULT" python -c 'import json, os; print(json.loads(os.environ["RESULT_JSON"])["properties"]["outputs"]["azureResourceGroup"]["value"])')"
echo "Foundry project: $(RESULT_JSON="$RESULT" python -c 'import json, os; print(json.loads(os.environ["RESULT_JSON"])["properties"]["outputs"]["foundryProjectEndpoint"]["value"])')"
echo "Next: uv sync --extra docs, then open 00-preflight."
