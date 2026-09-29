#!/usr/bin/env bash
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
FAIL=0
rows=()
add(){ local check="$1" status="$2" fix="$3" required="${4:-true}"; rows+=("$check|$status|$fix"); [[ "$status" == FAIL && "$required" == true ]] && FAIL=$((FAIL+1)); }
has(){ command -v "$1" >/dev/null 2>&1; }
minver(){ python - "$1" "$2" <<'PY'
import re, sys
def parts(v):
    m=re.search(r'\d+(?:\.\d+)+', v or '')
    return [int(x) for x in m.group(0).split('.')] if m else []
a=parts(sys.argv[1]); b=parts(sys.argv[2])
n=max(len(a), len(b)); a += [0]*(n-len(a)); b += [0]*(n-len(b))
sys.exit(0 if a >= b else 1)
PY
}
pyv="$(python3 --version 2>/dev/null || python --version 2>/dev/null || true)"; minver "$pyv" 3.12 && add 'python >= 3.12' PASS '' || add 'python >= 3.12' FAIL 'Install Python 3.13.'
has uv && add 'uv installed' PASS '' || add 'uv installed' FAIL 'Install uv.'
has git && add 'git installed' PASS '' || add 'git installed' FAIL 'Install Git.'
azv="$(az version --query '"azure-cli"' -o tsv 2>/dev/null || true)"; minver "$azv" 2.70 && add 'az >= 2.70' PASS '' || add 'az >= 2.70' FAIL 'Install/update Azure CLI.'
azdv="$(azd version 2>/dev/null | head -n1 || true)"; minver "$azdv" 1.27.1 && add 'azd >= 1.27.1' PASS '' || add 'azd >= 1.27.1' FAIL 'Install/update azd.'
azd ext list 2>/dev/null | grep -q 'azure\.ai\.agents' && add 'azd ext azure.ai.agents' PASS '' || add 'azd ext azure.ai.agents' FAIL 'azd ext install azure.ai.agents.'
az bicep version >/dev/null 2>&1 && add 'az bicep available' PASS '' || add 'az bicep available' FAIL 'az bicep install.'
az account show -o none >/dev/null 2>&1 && add 'az account show' PASS '' || add 'az account show' FAIL 'az login.'
azd auth login --check-status >/dev/null 2>&1 && add 'azd auth login --check-status' PASS '' || add 'azd auth login --check-status' FAIL 'azd config set auth.useAzCliAuth true.'
declare -A envmap=(); if [[ -f "$ENV_FILE" ]]; then while IFS='=' read -r k v; do [[ "$k" =~ ^#|^$ ]] && continue; envmap[$k]="$v"; done < "$ENV_FILE"; fi
required=(AZURE_SUBSCRIPTION_ID AZURE_RESOURCE_GROUP AZURE_LOCATION FOUNDRY_ACCOUNT_NAME FOUNDRY_PROJECT_NAME FOUNDRY_PROJECT_ENDPOINT FOUNDRY_PROJECT_RESOURCE_ID AZURE_AI_MODEL_DEPLOYMENT_NAME AZURE_AI_REASONING_DEPLOYMENT_NAME AZURE_AI_EMBEDDING_DEPLOYMENT_NAME AZURE_AI_FINETUNE_BASE_MODEL AZURE_SEARCH_ENDPOINT AZURE_SEARCH_CONNECTION_NAME APPLICATIONINSIGHTS_CONNECTION_STRING RAI_POLICY_NAME LAB_PREFIX)
missing=(); for k in "${required[@]}"; do [[ -z "${envmap[$k]:-}" ]] && missing+=("$k"); done
[[ -f "$ENV_FILE" && ${#missing[@]} -eq 0 ]] && add '.env required keys' PASS '' || add '.env required keys' FAIL "Run provision. Missing: ${missing[*]}"
if [[ ${#missing[@]} -eq 0 ]]; then
  deployments="$(az cognitiveservices account deployment list -g "${envmap[AZURE_RESOURCE_GROUP]}" -n "${envmap[FOUNDRY_ACCOUNT_NAME]}" --query '[].name' -o tsv 2>/dev/null || true)"
  miss=(); for d in "${envmap[AZURE_AI_MODEL_DEPLOYMENT_NAME]}" "${envmap[AZURE_AI_REASONING_DEPLOYMENT_NAME]}" "${envmap[AZURE_AI_EMBEDDING_DEPLOYMENT_NAME]}" "${envmap[AZURE_AI_FINETUNE_BASE_MODEL]}"; do grep -qx "$d" <<<"$deployments" || miss+=("$d"); done
  [[ ${#miss[@]} -eq 0 ]] && add 'required model deployments exist' PASS '' || add 'required model deployments exist' FAIL "Missing: ${miss[*]}"
  az rest --method get --url "${envmap[AZURE_SEARCH_ENDPOINT]}/indexes?api-version=2024-07-01" --resource https://search.azure.com -o none >/dev/null 2>&1 && add 'Azure AI Search reachable' PASS '' || add 'Azure AI Search reachable' FAIL 'Wait for RBAC propagation.'
  me="$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)"; roles="$(az role assignment list --assignee "$me" --scope "${envmap[FOUNDRY_PROJECT_RESOURCE_ID]}" --query '[].roleDefinitionName' -o tsv 2>/dev/null || true)"
  grep -q Foundry <<<"$roles" && add 'user roles on Foundry project' PASS '' false || add 'user roles on Foundry project' WARN 'Wait 5 minutes for role propagation.' false
  (cd "$REPO_ROOT" && printf "%s\n" "from workshop.config import chat_model" "print(chat_model().invoke('Reply with the single word pong.').content)" | uv run python - >/dev/null 2>&1) && add 'Foundry Responses smoke test' PASS '' || add 'Foundry Responses smoke test' FAIL 'Verify .env, role propagation, and deployments.'
fi
printf '\n%-38s %-6s %s\n' Check Status Fix
for r in "${rows[@]}"; do IFS='|' read -r c s f <<<"$r"; [[ "$s" == PASS ]] && f=''; printf '%-38s %-6s %s\n' "$c" "$s" "$f"; done
exit $FAIL
