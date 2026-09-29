# Validation report

Lab notebooks executed top-to-bottom against a live Foundry project.

| Notebook | Result | Duration | Run at | Notes |
|---|---|---|---|---|
| 00-preflight.ipynb | PASS | 175s | 2026-09-29 14:01 |  |
| 01-first-inference.ipynb | PASS | 215s | 2026-09-29 13:12 |  |
| 02-first-hosted-agent.ipynb | PASS | 635s | 2026-09-29 13:28 |  |
| 03-tools-and-function-calling.ipynb | PASS | 1069s | 2026-09-29 14:20 |  |
| 04-grounding-rag.ipynb | PASS | 192s | 2026-09-29 16:56 |  |
| 05-toolbox-mcp.ipynb | PASS | 482s | 2026-09-29 15:44 |  |
| 06-agent-memory.ipynb | PASS | 1098s | 2026-09-29 15:15 |  |
| 07-multi-agent.ipynb | PASS | 424s | 2026-09-29 15:30 |  |
| 08-deep-research.ipynb | PASS (local) | 675s | 2026-09-29 15:20 | Hosted deploy to re-check (see notes) |
| 09-evaluation.ipynb | PASS | 302s | 2026-09-29 15:13 |  |
| 10-observability.ipynb | PASS | 728s | 2026-09-29 15:44 |  |
| 11-guardrails.ipynb | PASS | 342s | 2026-09-29 15:02 |  |
| 12-red-teaming.ipynb | PASS (probe path) | 169s | 2026-09-29 15:06 | Full RedTeam scan to re-check (see notes) |
| 13-hitl-and-rest.ipynb | PASS | 584s | 2026-09-29 14:21 |  |
| 14-fine-tuning.ipynb | PASS | 240s | 2026-09-29 15:40 | Fine-tune job itself ran ~70 min beforehand |
| 15-capstone.ipynb | NOT RUN | - | - | Authored + static checks only |

## Notes and known gaps

Status as of the last validation pass (Foundry project in **West US**, Python 3.13, azd 1.34, `azure.ai.agents` 1.0.0-beta.17).

| Lab | What was proven end to end | Re-check before class |
|---|---|---|
| M0–M3, M5–M7, M9, M11, M13 | Full notebook run: local agent + `azd deploy` + hosted invoke | — |
| M4 Grounding / RAG | Full run passed | Output scrubbing only since the run |
| M8 Deep research | Local agent run passed | **Hosted deploy** hit an intermittent `AzureDeveloperCLICredential` error while 4 builders shared one machine. Re-run `agent.deploy()` once. |
| M10 Observability | Full run passed | App Insights lookup was generalized (no hard-coded names) after the run. Re-run section 4. |
| M12 Red teaming | Agent + manual probe scorecard ran | The worker import path and time budget were fixed after the run, so the **full `RedTeam` scan** (~10–15 min) hasn't been run yet. |
| M14 Fine-tuning | Job succeeded (~70 min, 26K trained tokens); fine-tuned deployment answered through the hosted agent | Fine-tuned deployment **bills hourly**. Delete it after class. |
| M15 Capstone | **Authored and statically checked** (compiles, graph wiring verified offline, all imports resolve) | Not executed yet. Run once end to end after M4 and M5. |

Static checks on every lab: all generators, helpers and agents compile; every notebook is valid nbformat
with no syntax errors; every agent's `requirements.txt` resolves for Linux / Python 3.13 (the hosted runtime).
