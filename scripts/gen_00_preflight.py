"""Generate docs/modules/00-preflight.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M0 · Preflight check",
    "Prove your lab machine and Foundry project are ready before M1. Every row should be ✅.",
    minutes=10,
)

nb.md("""
Run this notebook **after** [Setup](../setup.md) (tools installed, `scripts/provision` finished, `.env` written).
It checks everything the labs depend on and tells you how to fix anything that is red.

| Area | What we check |
|---|---|
| Workstation | Python ≥ 3.12, `az`, `azd` ≥ 1.27.1, the `azure.ai.agents` azd extension, `git`, `uv` |
| Sign-in | `az login` works, and `azd` reuses it |
| Configuration | `.env` has every required value |
| Foundry | Project reachable, required model deployments exist, a model answers |
| Optional | Azure AI Search reachable (M4), Application Insights configured (M10) |
""")

nb.bootstrap()

nb.code('''
import json, re, shutil, subprocess, sys
import pandas as pd

results = []

def check(area, name, ok, detail="", fix="", required=True):
    status = "✅" if ok else ("❌" if required else "⚠️")
    results.append({"": status, "Area": area, "Check": name, "Detail": detail, "How to fix": "" if ok else fix})
    return ok

def run(*cmd):
    exe = shutil.which(cmd[0])
    if not exe:
        return 127, ""
    try:
        p = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=180)
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return p.returncode, (p.stdout or "") + (p.stderr or "")

def version_tuple(text):
    m = re.search(r"(\\d+)\\.(\\d+)\\.(\\d+)", text)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
''')

nb.md("## 1. Workstation tools")

nb.code('''
check("Workstation", "Python >= 3.12", sys.version_info >= (3, 12), sys.version.split()[0],
      "Install Python 3.13 and re-run `uv sync`.")

rc, out = run("az", "version", "-o", "json")
az_ver = json.loads(out).get("azure-cli", "0") if rc == 0 else "missing"
check("Workstation", "Azure CLI >= 2.70", rc == 0 and version_tuple(az_ver) >= (2, 70, 0), az_ver,
      "winget install Microsoft.AzureCLI  (macOS: brew install azure-cli)")

rc, out = run("azd", "version")
check("Workstation", "Azure Developer CLI >= 1.27.1", rc == 0 and version_tuple(out) >= (1, 27, 1),
      out.splitlines()[0] if out else "missing", "winget install Microsoft.Azd  (macOS: brew install azd)")

rc, out = run("azd", "ext", "list", "--installed")
has_ext = rc == 0 and "azure.ai.agents" in out
ext_line = next((l for l in out.splitlines() if "azure.ai.agents" in l), "not installed")
check("Workstation", "azd extension azure.ai.agents", has_ext, " ".join(ext_line.split()[:4]),
      "azd ext install azure.ai.agents")

for tool, fix in [("git", "winget install Git.Git"), ("uv", "winget install astral-sh.uv")]:
    rc, out = run(tool, "--version")
    check("Workstation", tool, rc == 0, out.strip().splitlines()[0] if out else "missing", fix)
''')

nb.md("## 2. Sign-in")

nb.code('''
rc, out = run("az", "account", "show", "-o", "json")
acct = json.loads(out) if rc == 0 else {}
check("Sign-in", "az login", rc == 0, acct.get("name", ""), "Run `az login` in a terminal.")
check("Sign-in", "Subscription matches .env", acct.get("id") == settings.subscription_id,
      acct.get("id", ""), "az account set --subscription <AZURE_SUBSCRIPTION_ID from .env>")

rc, out = run("azd", "config", "get", "auth.useAzCliAuth")
check("Sign-in", "azd reuses az login", rc == 0 and "true" in out.lower(), out.strip(),
      "azd config set auth.useAzCliAuth true")
''')

nb.md("## 3. Configuration (`.env`)")

nb.code('''
from dataclasses import asdict
required = ["subscription_id", "resource_group", "account_name", "project_name", "project_endpoint",
            "chat_model", "reasoning_model", "embedding_model"]
optional = ["search_endpoint", "appinsights_connection_string", "rai_policy_name", "finetune_base_model"]
values = asdict(settings)
for key in required:
    check("Config", key, bool(values[key]), str(values[key])[:60], "Re-run scripts/provision or edit .env")
for key in optional:
    check("Config", key, bool(values[key]), str(values[key])[:60], "Needed by later labs; re-run scripts/provision",
          required=False)
''')

nb.md("## 4. Foundry project, models and a live call")

nb.code('''
from workshop.config import project_client, chat_model

try:
    deployments = {d.name: d for d in project_client().deployments.list()}
    check("Foundry", "Project reachable", True, f"{len(deployments)} deployments", "")
except Exception as exc:
    deployments = {}
    check("Foundry", "Project reachable", False, type(exc).__name__,
          "Check FOUNDRY_PROJECT_ENDPOINT and that you have the Foundry User role (wait 5 min after provisioning).")

for name, required_flag in [(settings.chat_model, True), (settings.reasoning_model, True),
                            (settings.embedding_model, True), (settings.finetune_base_model, False)]:
    check("Foundry", f"Deployment `{name}`", name in deployments, "",
          "Re-run scripts/provision (it creates all deployments).", required=required_flag)

try:
    answer = chat_model().invoke("Reply with exactly: Foundry is ready.").text.strip()
    check("Foundry", "Model answers", "ready" in answer.lower(), answer, "")
except Exception as exc:
    check("Foundry", "Model answers", False, str(exc)[:120],
          "401/403 → role not yet propagated or missing Foundry User role; CredentialUnavailable → az login")
''')

nb.md("## 5. Optional services")

nb.code('''
if settings.search_endpoint:
    try:
        from azure.search.documents.indexes import SearchIndexClient
        from workshop.config import credential
        n = len(list(SearchIndexClient(settings.search_endpoint, credential()).list_index_names()))
        check("Optional", "Azure AI Search (M4)", True, f"{n} indexes", "", required=False)
    except Exception as exc:
        check("Optional", "Azure AI Search (M4)", False, type(exc).__name__,
              "Needs Search Index Data Contributor + Search Service Contributor roles.", required=False)
else:
    check("Optional", "Azure AI Search (M4)", False, "not configured", "Set AZURE_SEARCH_ENDPOINT", required=False)

check("Optional", "Application Insights (M10)", bool(settings.appinsights_connection_string),
      "configured" if settings.appinsights_connection_string else "", "Set APPLICATIONINSIGHTS_CONNECTION_STRING",
      required=False)
''')

nb.md("## Summary")

nb.code('''
df = pd.DataFrame(results)
pd.set_option("display.max_colwidth", 80)
display(df)
failed = df[df[""] == "❌"]
if failed.empty:
    print("\\nAll required checks passed. You are ready for M1!")
else:
    print(f"\\n{len(failed)} required check(s) failed. Fix them and re-run this notebook.")
assert failed.empty, "Preflight failed. See the 'How to fix' column."
''')

nb.md("""
**Expected output:** a table of ✅ rows (⚠️ is fine for optional items) and *All required checks passed*.

➡️ Next: **M1 · First inference**
""")

nb.save("docs/modules/00-preflight.ipynb")
