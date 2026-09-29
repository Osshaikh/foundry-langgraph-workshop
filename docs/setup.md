# Workshop setup

This guide prepares your lab workstation and creates the fixed Azure resources for **Microsoft Foundry: LangGraph Hosted Agents Workshop**. You do not need to choose SKUs, names, or networking settings; the provisioning script creates the standard lab environment and writes `.env`.

!!! tip "Classroom assumptions"
    Each attendee uses a demo Azure subscription where they are **Owner**. Resource names include your short alias, for example `rg-lgws-ada`.

## 0. What you need

| Requirement | Recommended | Minimum | Why |
|---|---:|---:|---|
| RAM | 16 GB | 8 GB | VS Code, notebooks, SDKs, and optional Docker |
| Disk | 20 GB free | 12 GB free | Python environment, docs tooling, optional containers |
| Permissions | Local admin | Local admin | Tool installation |
| Azure | Demo subscription Owner | Demo subscription Owner | Provisioning and RBAC assignment |

## 1. Install tools

| Tool | Version | Windows winget | macOS brew | Used for |
|---|---|---|---|---|
| Git | Current | `winget install Git.Git` | `brew install git` | Clone the repo |
| Python | 3.13 | `winget install Python.Python.3.13` | `brew install python@3.13` | Notebooks and validation |
| uv | Current | `winget install astral-sh.uv` | `brew install uv` | Python dependency sync |
| Azure CLI | >= 2.70 | `winget install Microsoft.AzureCLI` | `brew install azure-cli` | Azure login and deployments |
| Azure Developer CLI | >= 1.27.1 | `winget install Microsoft.Azd` | `brew install azure-developer-cli` | Hosted-agent deployment |
| PowerShell | 7.x | `winget install Microsoft.PowerShell` | `brew install powershell` | Windows-friendly scripts |
| VS Code | Current | `winget install Microsoft.VisualStudioCode` | `brew install --cask visual-studio-code` | Labs and notebooks |
| Docker Desktop | Optional | `winget install Docker.DockerDesktop` | `brew install --cask docker` | Optional container-mode deploys |
| Node.js | Optional LTS 22 | `winget install OpenJS.NodeJS.LTS` | `brew install node@22` | Optional MCP/tool labs |

VS Code extensions installed by the script:

- `ms-python.python`
- `ms-toolsai.jupyter`
- `ms-windows-ai-studio.windows-ai-studio` (Foundry Toolkit)
- `ms-azuretools.vscode-bicep`
- `ms-azuretools.vscode-docker`

=== "Windows"

    ```powershell
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
    .\scripts\install-tools.ps1
    # Optional extras:
    .\scripts\install-tools.ps1 -IncludeDocker -IncludeNode
    ```

=== "macOS"

    ```bash
    ./scripts/install-tools.sh
    # Optional extras:
    ./scripts/install-tools.sh --include-docker --include-node
    ```

=== "Linux"

    ```bash
    ./scripts/install-tools.sh
    ```

## 2. Sign in

```bash
az login
az account show -o table
azd config set auth.useAzCliAuth true
azd auth login --check-status
azd ext install azure.ai.agents
```

The key setting is `azd config set auth.useAzCliAuth true`; it makes `azd` reuse your Azure CLI login during the labs.

## 3. Get the code

```bash
git clone https://github.com/Osshaikh/foundry-langgraph-workshop.git
cd foundry-langgraph-workshop
uv sync --extra docs
uv run python -m ipykernel install --user --name foundry-langgraph-workshop --display-name "Foundry LangGraph Workshop"
```

## 4. Provision Azure

Pick a short lowercase alias, 3-8 characters, such as your initials. The script creates everything with fixed names and writes `.env`.

=== "Windows"

    ```powershell
    .\scripts\provision.ps1 -Alias <alias>
    ```

=== "macOS / Linux"

    ```bash
    ./scripts/provision.sh --alias <alias>
    ```

Estimated time: **10-15 minutes**.

### What gets created

| Resource | Name | SKU / settings | Used by labs |
|---|---|---|---|
| Resource group | `rg-lgws-<alias>` | Container for all resources | All labs |
| Foundry account | `aif-lgws-<alias>` | AI Services `S0`, public access, project management enabled | Hosted agents, inference, evaluation |
| Foundry project | `proj-lgws` | System-assigned identity | All hosted-agent labs |
| Chat deployment | `gpt-5.4-mini` | GlobalStandard, default capacity 250 | Most inference labs |
| Reasoning deployment | `gpt-5.4` | GlobalStandard, default capacity 150 | Reasoning labs |
| Embedding deployment | `text-embedding-3-large` | GlobalStandard, default capacity 150 | RAG labs |
| Fine-tune base | `gpt-4.1-mini` | GlobalStandard, default capacity 100 | Later fine-tuning lab |
| Azure AI Search | `srch-lgws-<alias>` | Basic, semantic ranker free, Entra or API key auth | RAG and indexing labs |
| Log Analytics | `log-lgws-<alias>` | PerGB2018, 30-day retention | Observability |
| Application Insights | `appi-lgws-<alias>` | Workspace-based | Tracing and evaluation |
| Container Registry | `acrlgws<alias>` | Standard, admin disabled | Optional container-mode deploys |
| RAI policy | `lgws-strict` | Blocking, low threshold filters | Guardrails lab |

!!! tip "Quota note"
    If model quota is tight, the provisioning scripts automatically retry once with half-size model capacities. If the retry still fails, ask your instructor for a different demo subscription or a region with quota.

### Rough cost guide

Approximate list prices (USD, pay-as-you-go) for a two-day class. Verify current prices in the
[Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) for your region.

| Item | Approx. cost | Notes |
|---|---:|---|
| Azure AI Search **Basic** | ~$2.50 / day | Fixed while the service exists |
| Container Registry **Standard** | ~$0.70 / day | Fixed; only used for optional container deploys |
| Log Analytics + App Insights | < $1 / day | Pay per GB ingested; workshop traces are small |
| Model tokens (all labs) | ~$2–10 per attendee | Pay per token; M8 deep research and M9/M12 evals use the most |
| Hosted-agent sessions | < $1 per attendee | CPU + memory only while a session is active (0.5 vCPU / 1 GiB) |
| Fine-tuning (M14) | ~$5–15 training + hourly hosting | The fine-tuned **deployment bills per hour**. Delete it at the end of M14 |
| **Typical total** | **~$15–30 per attendee** | Run **teardown** when the class ends |

!!! warning "Delete when done"
    Search, ACR and a fine-tuned deployment keep billing while they exist. `teardown` removes everything.

## 5. Verify

=== "Windows"

    ```powershell
    .\scripts\preflight.ps1
    ```

=== "macOS / Linux"

    ```bash
    ./scripts/preflight.sh
    ```

Then open [`docs/modules/00-preflight.ipynb`](modules/00-preflight.ipynb) in VS Code, select the
**Foundry LangGraph Workshop** kernel and **Run All**. Every required row should be ✅.

!!! note "Docker is optional"
    The labs deploy hosted agents with **code deploy**: Foundry builds your Python dependencies in the
    cloud. Docker Desktop is only needed if you choose container-mode deploys.

## 6. Clean up

=== "Windows"

    ```powershell
    .\scripts\teardown.ps1 -Alias <alias>
    ```

=== "macOS / Linux"

    ```bash
    ./scripts/teardown.sh --alias <alias>
    ```

The teardown deletes `rg-lgws-<alias>` and purges the soft-deleted Foundry account so the name can be reused.

## Common problems

!!! warning "`az` is not on PATH after install"
    Restart your terminal, then run `az --version` again.

!!! warning "Quota errors"
    Re-run provisioning; it retries with lower model capacities. If it still fails, use another demo subscription or ask your instructor.

!!! warning "403 or authorization errors"
    Role assignments can take about 5 minutes to propagate. Wait, then run the preflight script again.

!!! warning "Windows execution policy"
    Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry the PowerShell script.
