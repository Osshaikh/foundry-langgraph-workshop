## Notes and known gaps

Status as of the last validation pass (Foundry project in **West US**, Python 3.13, azd 1.34, `azure.ai.agents` 1.0.0-beta.17).

| Lab | What was proven end to end | Re-check before class |
|---|---|---|
| M0–M3, M5–M7, M9, M11, M13 | Full notebook run: local agent + `azd deploy` + hosted invoke | — |
| M4 Grounding / RAG | Full run passed | Output scrubbing only since the run |
| M8 Deep research | Local agent run passed | **Hosted deploy** hit an intermittent `AzureDeveloperCLICredential` error while 4 builders shared one machine. Re-run `agent.deploy()` once. |
| M10 Observability | Full run passed | App Insights lookup was generalized (no hard-coded names) after the run. Re-run section 4. |
| M12 Red teaming | Agent + manual probe scorecard ran | The worker import path and time budget were fixed after the run, so the **full `RedTeam` scan** (~10–15 min) hasn't been run yet. |
| M14 Fine-tuning | Job succeeded (~70 min, 26K trained tokens); fine-tuned deployment answered through the hosted agent | Fine-tuned deployment uses **Developer Tier**: no hosting fee, auto-deleted after 24 h. Re-deploy it from the job before re-running the swap step. |
| M15 Capstone | **Authored and statically checked** (compiles, graph wiring verified offline, all imports resolve) | Not executed yet. Run once end to end after M4 and M5. |

Static checks on every lab: all generators, helpers and agents compile; every notebook is valid nbformat
with no syntax errors; every agent's `requirements.txt` resolves for Linux / Python 3.13 (the hosted runtime).
