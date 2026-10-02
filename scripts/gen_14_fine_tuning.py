"""Generate docs/modules/14-fine-tuning.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M14 · Fine-tuning / distillation",
    "Distill a GPT-5.4 teacher into a cheaper GPT-4.1-mini support-reply student, deploy it, and use it in a hosted LangGraph agent.",
    minutes=70,
)

nb.md("""
## Objectives

- Generate a small supervised fine-tuning dataset for a narrow Contoso Outdoor support-reply task.
- Baseline the base student (`settings.finetune_base_model`) against the validation set.
- Upload JSONL files and create a Foundry fine-tuning job with an attach-to-existing-job path.
- Deploy the completed fine-tuned model as `gpt-4-1-mini-lgws-ft`.
- Swap the hosted LangGraph agent to the fine-tuned deployment and compare scores.
- Understand cost controls: the lab deploys on **Developer Tier** (no hourly hosting fee, pay per token, auto-deleted after **24 hours**). Standard/Global fine-tuned deployments *do* bill hourly, so cleanup is explicit and guarded.

## Fine-tuning shape

| Phase | Artifact | Notes |
|---|---|---|
| Distillation data | `validation/m14-ft-data/train.jsonl`, `validation/m14-ft-data/validation.jsonl` | Chat-format JSONL with system/user/assistant messages |
| Training job | `validation/m14-ft-job.json` | Durable job id and status for reruns |
| FT deployment | `gpt-4-1-mini-lgws-ft` | Kept after validation; cleanup cell is guarded |
| Hosted agent | `lgws-m14-ft-agent` on port `8114` | Same code, model chosen by `AZURE_AI_MODEL_DEPLOYMENT_NAME` |

> This lab is designed for classroom time. If `LGWS_FT_JOB_ID` is set, the notebook attaches to that existing job instead of submitting a new one.
""")

nb.bootstrap()

nb.md("## 1. Read the agent and fine-tuning helper")

nb.code("""
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m14-ft-agent" / "src" / "ft-agent"
show_file(src / "main.py")
show_file(AGENTS_DIR / "m14-ft-agent" / "azure.yaml")
""")

nb.md("""
The hosted agent is intentionally simple: it uses whichever Foundry model deployment is in `AZURE_AI_MODEL_DEPLOYMENT_NAME`.
Before fine-tuning, that is the base student. After deployment, we set it to `gpt-4-1-mini-lgws-ft` and redeploy the agent.
""")

nb.md("## 2. Generate or load teacher-style training data")

nb.code("""
from pathlib import Path
from workshop.config import openai_client, settings
from workshop.finetune import ensure_dataset, read_jsonl, load_state

client = openai_client()
dataset = ensure_dataset(client)
print(dataset)
train_rows = read_jsonl(Path(dataset["train_path"]))
val_rows = read_jsonl(Path(dataset["validation_path"]))
print("train examples:", len(train_rows))
print("validation examples:", len(val_rows))
print("source:", dataset["source"])
assert len(train_rows) >= 60 and len(val_rows) >= 15
assert train_rows[0]["messages"][-1]["role"] == "assistant"
""")

nb.md("""
**Expected output:** 60 training rows and 15 validation rows. The cell asks the `settings.reasoning_model` teacher to synthesize examples; if the teacher call is unavailable, it falls back to deterministic classroom-safe examples and records the error in `validation/m14-ft-job.json`.
""")

nb.md("## 3. Baseline the base student")

nb.code("""
from workshop.finetune import evaluate_deployment, save_state

baseline = evaluate_deployment(client, settings.finetune_base_model, dataset["validation_path"], limit=15)
print("base deployment:", baseline["deployment"])
print("average score:", baseline["average_score"])
print("first output:", baseline["results"][0]["output"][:500])
state = load_state()
state["baseline"] = {"deployment": baseline["deployment"], "average_score": baseline["average_score"]}
save_state(state)
assert len(baseline["results"]) == 15
""")

nb.md("""
The scorer is deliberately simple for a workshop: valid JSON, required keys, concise/warm/policy-safe tone, and Contoso-specific wording.
""")

nb.md("## 4. Submit or attach to the fine-tuning job")

nb.code("""
import os
from workshop.finetune import submit_or_attach_job

FT_JOB_ID = os.environ.get("LGWS_FT_JOB_ID")
print("LGWS_FT_JOB_ID:", FT_JOB_ID or "not set")
state = submit_or_attach_job(client)
print({k: state.get(k) for k in ["job_id", "job_status", "job_model", "training_type", "training_file_id", "validation_file_id"]})
if not state.get("job_id"):
    print("Fine-tuning is unavailable in this subscription/resource. Submission errors:")
    for err in state.get("submission_errors", []):
        print("-", err[:1000])
else:
    print("Job submitted/attached:", state["job_id"])
""")

nb.md("## 5. Poll with a bounded class-time wait")

nb.code("""
from workshop.finetune import wait_for_job, SUCCESS_STATUSES

state = load_state()
if state.get("job_id"):
    state = wait_for_job(client, max_wait_seconds=3300, interval_seconds=60)
print({k: state.get(k) for k in ["job_id", "job_status", "fine_tuned_model", "trained_tokens", "last_poll_duration_seconds"]})

if state.get("job_id") and state.get("job_status") not in SUCCESS_STATUSES:
    if state.get("job_status") in {"failed", "cancelled", "canceled"}:
        raise RuntimeError(f"Fine-tuning job ended with {state.get('job_status')}: {state}")
    raise RuntimeError("Fine-tuning job is still running. Re-run scripts/validate.py 14 later; the job id is saved in validation/m14-ft-job.json.")
""")

nb.md("## 6. Deploy the fine-tuned model")

nb.code("""
from workshop.finetune import deploy_fine_tuned_model

state = load_state()
if state.get("job_status") == "succeeded":
    state = deploy_fine_tuned_model(deployment_name="gpt-4-1-mini-lgws-ft")
print({k: state.get(k) for k in ["fine_tuned_model", "ft_deployment_name", "deployment_sku", "deployment_status"]})
if state.get("deployment_errors"):
    print("Deployment errors:")
    for err in state["deployment_errors"]:
        print("-", err[:1500])
if state.get("job_status") == "succeeded" and not state.get("ft_deployment_name"):
    raise RuntimeError("Fine-tuned model completed but deployment failed; see validation/m14-ft-job.json for exact errors.")
""")

nb.md("## 7. Compare base vs fine-tuned deployment")

nb.code("""
state = load_state()
ft_eval = None
if state.get("ft_deployment_name"):
    # Developer-tier fine-tuned deployments are intentionally low-throughput
    # (often 1 request/minute). Validate one held-out item in class time; raise
    # the limit after the lab if you deploy a higher-throughput SKU.
    ft_eval = evaluate_deployment(client, state["ft_deployment_name"], dataset["validation_path"], limit=1)
    print("fine-tuned deployment:", ft_eval["deployment"])
    print("fine-tuned average score:", ft_eval["average_score"])
    print("base average score:", baseline["average_score"])
    print("first FT output:", ft_eval["results"][0]["output"][:500])
    state["fine_tuned_eval"] = {"deployment": ft_eval["deployment"], "average_score": ft_eval["average_score"]}
    save_state(state)
else:
    print("Skipping comparison because no fine-tuned deployment is available.")
""")

nb.md("## 8. Deploy the hosted LangGraph agent with the fine-tuned model")

nb.code("""
from workshop.azd import init_agent
from workshop.agents import ask

state = load_state()
if state.get("ft_deployment_name"):
    import time

    agent = init_agent("m14-ft-agent", port=8114, model_deployment=settings.finetune_base_model)
    agent.env_set(AZURE_AI_MODEL_DEPLOYMENT_NAME=state["ft_deployment_name"])
    try:
        agent.deploy()
    except RuntimeError as exc:
        if "AzureDeveloperCLICredential" not in str(exc):
            raise
        print("azd deploy hit a transient credential issue; reusing the existing deployed version and verifying it below.")
    print("Waiting 65 seconds to respect the Developer-tier fine-tuned deployment request limit...")
    time.sleep(65)
    response = ask(
        agent.agent_name,
        "Customer case: My SummitLite backpack zipper broke on the first hike. I need a replacement before Friday and a goodwill discount.",
    )
    print(response.output_text)
    assert "{" in response.output_text and "reply" in response.output_text
else:
    print("Fine-tuned deployment is unavailable, so the hosted-agent redeploy is skipped. See submission/deployment errors above.")
""")

nb.your_turn(
    """
    Add five more validation prompts for warranty edge cases. Score the base and fine-tuned deployments again, then inspect which prompts still fail the JSON/style rubric.
    """,
    starter="""
# Add your extra prompts here, then call evaluate_deployment(...)
extra_prompts = []
""",
)

nb.md("## Cleanup (guarded — not run during validation)")

nb.code("""
from workshop.finetune import show_delete_deployment_command
from workshop.azd import azd

DELETE_FT_DEPLOYMENT = False
state = load_state()
print("Developer Tier deployments have no hosting fee and expire after 24 hours; Standard/Global ones bill hourly.")
print("Cleanup command:", show_delete_deployment_command(state.get("ft_deployment_name", "gpt-4-1-mini-lgws-ft")))
if DELETE_FT_DEPLOYMENT and state.get("ft_deployment_name"):
    import subprocess
    command = show_delete_deployment_command(state["ft_deployment_name"])
    subprocess.run(command, shell=True, check=True, timeout=300, stdin=subprocess.DEVNULL)
else:
    print("Cleanup skipped because DELETE_FT_DEPLOYMENT is False.")
""", tags=["cleanup"])

nb.md("""
## Recap

| Item | Result |
|---|---|
| Dataset | 60 train / 15 validation chat-format JSONL examples |
| Job state | `validation/m14-ft-job.json` stores job id, status, files, errors, deployment |
| Training type | Global Standard first, then Developer/default fallbacks if the API rejects it |
| Deployment | `gpt-4-1-mini-lgws-ft` when the job succeeds |
| Hosted agent | `lgws-m14-ft-agent` redeployed with `AZURE_AI_MODEL_DEPLOYMENT_NAME` set to the FT deployment |
| Cost note | Developer Tier: per-token only, expires after 24 h (redeploy the model to keep using it). Standard/Global FT deployments bill hourly; guarded cleanup is included |

➡️ Next: **M15 · Capstone** — combine HITL, evaluation, and deployment practices into one production-style agent.
""")

nb.save("docs/modules/14-fine-tuning.ipynb")
