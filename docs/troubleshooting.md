# Troubleshooting

Problems new engineers hit most often, with the fix for each. Most are covered by
[M0 · Preflight](modules/00-preflight.ipynb).

## Sign-in and permissions

| Symptom | Cause | Fix |
|---|---|---|
| `DefaultAzureCredential failed to retrieve a token` / `CredentialUnavailableError` | Not signed in, or the token expired | `az login`, then restart the notebook kernel |
| `azd`: *You must be logged into Azure* / `AzureDeveloperCLICredential` error | azd isn't reusing the CLI login | `azd config set auth.useAzCliAuth true` then `azd auth login --check-status` |
| `401 PermissionDenied … lacks the required data action` calling a model | Your user is missing **Foundry User** | Re-run `scripts/provision` (assigns roles), wait ~5 min for propagation |
| `403` on `azd deploy` | Missing **Foundry Project Manager** on the project | As above |
| Hosted agent answers, but its tool fails with `403` on AI Search | The **agent identity** lacks a Search role | Run the role-assignment cell in M4 again, wait 2–5 min |
| Wrong subscription | `az` default subscription differs from `.env` | `az account set --subscription <id>` |

## Local agent (`azd ai agent run`)

| Symptom | Fix |
|---|---|
| `Local agent not ready after …` | The first start installs dependencies (1–3 min). Check `.work/<lab>/<agent>/local-run.log` for the real error |
| `Address already in use` / old answers from a previous lab | A previous host is still bound to the port. `agent.stop_local()` frees it; or re-run the cell, since `run_local()` kills anything on its port first |
| `ModuleNotFoundError` in the local run | Add the package to that agent's `requirements.txt`, then re-run `init_agent(...)` (it syncs sources) and `run_local()` |
| `KeyError: 'FOUNDRY_PROJECT_ENDPOINT'` | Run through `init_agent` / `azd ai agent run` (azd injects it), not `python main.py` directly |

## Deploy (`azd deploy`)

| Symptom | Fix |
|---|---|
| Deploy seems stuck on packaging | A `.venv` is being uploaded. Make sure `src/<agent>/.agentignore` exists (every lab ships one) |
| Version status `failed` | `agent.monitor()` (or `azd ai agent monitor`) shows container logs. Usually a missing dependency or a typo in `requirements.txt` |
| `failed to initialize project … pathspec '*' did not match` | `init` was run inside a git-ignored folder. Use `init_agent()` (it prepares `.work/` correctly) |
| First call after deploy takes ~10 s | Normal **cold start** of a new session sandbox |

## Models and quota

| Symptom | Fix |
|---|---|
| `DeploymentNotFound` | The deployment name in `.env` doesn't exist. Check the portal → *Models + endpoints* |
| `429 Too Many Requests` | Tokens-per-minute quota hit. Wait a minute, or raise capacity on the deployment |
| Provisioning fails with `InsufficientQuota` | Re-run `scripts/provision` with a lower capacity (the script retries once automatically) or pick another region with `-Location swedencentral` |

## Windows specifics

| Symptom | Fix |
|---|---|
| `running scripts is disabled on this system` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `az`/`azd` not found right after installing | Close and reopen the terminal **and** VS Code (PATH refresh) |
| `UnicodeEncodeError: 'charmap' codec` in a script | Use Windows Terminal / PowerShell 7, or `set PYTHONUTF8=1` |
| Notebook can't find the kernel | `uv run python -m ipykernel install --user --name foundry-langgraph-workshop --display-name "Foundry LangGraph Workshop"` and pick it in VS Code |

## Still stuck?

1. Re-run **M0 · Preflight**; it pinpoints most issues.
2. Look at the full error in the notebook output (scroll up past the last line).
3. For a hosted agent: `agent.show()` and `agent.monitor()`.
