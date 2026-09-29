# Microsoft Foundry: LangGraph Hosted Agents Workshop

A hands-on, two-day workshop for AI engineers: build agents with **LangGraph** and run them as
**Microsoft Foundry Hosted Agents**. It covers tools, RAG, MCP toolboxes, memory, multi-agent, deep
research, evaluation, tracing, guardrails, red teaming, human-in-the-loop and fine-tuning (labs M0–M15).

Every lab is a Jupyter notebook that is **executed end-to-end against a live Foundry project** before
release. See [`validation/validation-report.md`](validation/validation-report.md).

## Quick start (attendees)

```powershell
# 1. Tools (Windows; macOS/Linux: scripts/install-tools.sh)
./scripts/install-tools.ps1

# 2. Code + Python environment
git clone https://github.com/Osshaikh/foundry-langgraph-workshop.git
cd foundry-langgraph-workshop
uv sync --extra docs
uv run python -m ipykernel install --user --name foundry-langgraph-workshop --display-name "Foundry LangGraph Workshop"

# 3. Azure (creates everything in your lab subscription and writes .env)
az login
./scripts/provision.ps1 -Alias <your-initials>

# 4. Verify, then open docs/modules/00-preflight.ipynb in VS Code
./scripts/preflight.ps1
```

Full instructions: [`docs/setup.md`](docs/setup.md). Clean up afterwards with `./scripts/teardown.ps1`.

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | The workshop site (MkDocs Material): setup, concepts, platform primer, lab notebooks |
| `docs/modules/NN-*.ipynb` | Lab notebooks (generated from `scripts/gen_NN_*.py`, then executed) |
| `agents/mNN-*/` | One azd-ready hosted agent per lab (`azure.yaml` + `src/<agent>/main.py`, …) |
| `workshop/` | Helpers imported by notebooks (`config`, `azd`, `agents`, …) |
| `infra/` | Bicep for the lab environment (Foundry, models, AI Search, App Insights, ACR, RBAC, RAI policy) |
| `scripts/` | `install-tools`, `provision`, `preflight`, `teardown`, notebook generators, `validate.py` |

## Build and publish the site

```bash
uv run mkdocs serve             # preview at http://127.0.0.1:8000
uv run mkdocs build --strict    # check for broken links/pages
uv run mkdocs gh-deploy --force # build locally and push to the gh-pages branch (GitHub Pages)
```

Live site: https://osshaikh.github.io/foundry-langgraph-workshop/

## Maintainers: regenerate and re-validate labs

```bash
uv run python scripts/gen_02_first_hosted_agent.py     # regenerate one notebook
uv run python scripts/validate.py 02                   # execute it against your project
uv run python scripts/validate.py                      # execute all labs
uv run python scripts/cleanup.py                       # remove lab agents/toolboxes/indexes
```

## Credits

Structure inspired by [monuminu/foundry-workshop](https://monuminu.github.io/foundry-workshop/).
Hosted-agent patterns adapted from
[microsoft-foundry/foundry-samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/langgraph).
