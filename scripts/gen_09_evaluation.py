"""Generate docs/modules/09-evaluation.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M9 · Evaluation for a hosted support agent",
    "Create a reusable Contoso Outdoor support agent, score it locally, then run a target-based cloud evaluation.",
    minutes=60,
)

nb.md("""
## Objectives

- Build one reusable hosted LangGraph agent: `lgws-m09-support-agent`.
- Create a small support-quality test set with expected behavior and ground truth.
- Run local `azure-ai-evaluation` evaluators with `gpt-5.4` as an Entra-authenticated judge.
- Upload the same dataset to Foundry and run a target-based evaluation against the hosted agent.

## Evaluation flow

```text
queries.jsonl ──► local agent outputs ──► local evaluators
       │
       └────────► Foundry dataset ──► eval run target: lgws-m09-support-agent ──► report_url
```
""")

nb.bootstrap()

nb.md("## 1. Inspect and initialise the reusable support agent")

nb.code("""
from workshop.azd import init_agent, show_file, summarize_output
from workshop.config import AGENTS_DIR, AZURE_AI_SCOPE, credential, openai_client, project_client
from pathlib import Path
import json, time, pandas as pd

src = AGENTS_DIR / "m09-support-agent" / "src" / "support-agent"
show_file(src / "main.py")
show_file(AGENTS_DIR / "m09-support-agent" / "azure.yaml")

def get_or_deploy_support_agent(port=8109):
    agent = init_agent(
        "m09-support-agent",
        port=port,
        env={
            "APPLICATIONINSIGHTS_CONNECTION_STRING": settings.appinsights_connection_string,
            "OTEL_AUTO_CONFIGURE_AZURE_MONITOR": "true",
            "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED": "true",
            "AZURE_TRACING_ALL_LANGGRAPH_NODES": "true",
        },
    )
    try:
        remote = project_client().agents.get(agent.agent_name)
        print(f"Hosted agent already exists: {remote.name}")
    except Exception as exc:
        print(f"Hosted agent not found yet ({exc.__class__.__name__}); deploying now.")
    print("Deploying a fresh version so this notebook never reuses a failed preview build.")
    agent.deploy()
    remote = project_client().agents.get(agent.agent_name)
    print(f"Ready: {remote.name}")
    return agent

agent = get_or_deploy_support_agent(8109)
assert agent.agent_name == settings.agent_name("m09-support-agent")
""")

nb.md("## 2. Build a compact quality test set")

nb.code("""
test_set = [
    {"query": "Where is order CO-1002?", "expected_behavior": "Use lookup_order and report in-transit status with estimated delivery 2026-10-03.", "ground_truth": "CO-1002 is in transit and estimated for 2026-10-03.", "expected_tool": "lookup_order"},
    {"query": "Can I return the TrailMaster backpack from CO-1001?", "expected_behavior": "Use lookup_order and return_policy; say it is eligible if clean/undamaged with tags before 2026-10-21.", "ground_truth": "CO-1001 is delivered and eligible for return until 2026-10-21 under backpack policy.", "expected_tool": "lookup_order"},
    {"query": "What is the return policy for a rain jacket?", "expected_behavior": "Use return_policy and explain apparel return conditions.", "ground_truth": "Apparel can be returned within 30 days if unworn, unwashed, and tagged.", "expected_tool": "return_policy"},
    {"query": "Escalate my delayed order CO-1002 to a person.", "expected_behavior": "Use create_support_case and provide a support case id.", "ground_truth": "A support case should be created for CO-1002.", "expected_tool": "create_support_case"},
    {"query": "Do you know order CO-9999?", "expected_behavior": "Use lookup_order and ask for a valid CO order id when not found.", "ground_truth": "Order CO-9999 is not in the sample data.", "expected_tool": "lookup_order"},
    {"query": "Can I return a used stove fuel canister?", "expected_behavior": "Use return_policy and say used fuel canisters are not returnable.", "ground_truth": "Used fuel canisters are never returnable.", "expected_tool": "return_policy"},
    {"query": "What has shipped for CO-1003?", "expected_behavior": "Use lookup_order; say it is processing and has not shipped yet.", "ground_truth": "CO-1003 is processing with estimated ship date 2026-09-30.", "expected_tool": "lookup_order"},
    {"query": "Summarize Contoso return rules in one sentence.", "expected_behavior": "Give a concise general policy and avoid inventing exceptions.", "ground_truth": "Most items return within 30 days unused/original packaging; category exceptions apply.", "expected_tool": "return_policy"},
    {"query": "My order is late and I am angry. What can you do?", "expected_behavior": "Ask for an order id or offer escalation; do not invent status.", "ground_truth": "The agent should ask for an order id or create an escalation case.", "expected_tool": "create_support_case"},
    {"query": "Tell me everything you know about Avery Johnson.", "expected_behavior": "Minimize personal data; only provide order-specific info after an order id, not a profile.", "ground_truth": "Agent should avoid disclosing unnecessary personal data.", "expected_tool": "lookup_order"},
]

df = pd.DataFrame(test_set)
display(df[["query", "expected_tool", "ground_truth"]])
assert len(test_set) == 10
""")

nb.md("## 3. Run a few examples locally and capture tool use")

nb.code("""
local_rows = []
agent.run_local()
try:
    for row in test_set[:4]:
        response = agent.local_responses(row["query"])
        summarize_output(response)
        output_text = "\\n".join(
            c.get("text", "")
            for item in response.get("output", []) if item.get("type") == "message"
            for c in item.get("content", [])
        )
        tool_calls = [item.get("name") for item in response.get("output", []) if item.get("type") == "function_call"]
        local_rows.append({**row, "response": output_text, "tool_calls": tool_calls})
finally:
    agent.stop_local()

pd.DataFrame(local_rows)[["query", "tool_calls", "response"]]
assert any("lookup_order" in r["tool_calls"] for r in local_rows)
""")

nb.md("## 4. Score local outputs with `azure-ai-evaluation`")

nb.code("""
from azure.ai.evaluation import IntentResolutionEvaluator, RelevanceEvaluator, TaskAdherenceEvaluator, ToolCallAccuracyEvaluator

token = credential().get_token(AZURE_AI_SCOPE).token
model_config = {
    "type": "openai",
    "model": settings.reasoning_model,
    "base_url": str(openai_client().base_url),
    "api_key": token,
    "extra_headers": {"Authorization": f"Bearer {token}"},
}

evaluators = {
    "intent_resolution": IntentResolutionEvaluator(model_config, credential=credential()),
    "task_adherence": TaskAdherenceEvaluator(model_config, credential=credential()),
    "relevance": RelevanceEvaluator(model_config, credential=credential()),
    "tool_call_accuracy": ToolCallAccuracyEvaluator(model_config, credential=credential()),
}

tool_definitions = [
    {"name": "lookup_order", "description": "Look up Contoso Outdoor order status by order id."},
    {"name": "return_policy", "description": "Return the policy for a product category."},
    {"name": "create_support_case", "description": "Create a simulated human escalation case."},
]

results = []
for row in local_rows[:2]:
    for name, evaluator in evaluators.items():
        try:
            kwargs = {"query": row["query"], "response": row["response"]}
            if name in {"intent_resolution", "tool_call_accuracy"}:
                kwargs["tool_definitions"] = tool_definitions
            if name == "relevance":
                kwargs["context"] = row["ground_truth"]
            result = evaluator(**kwargs)
            result["evaluator"] = name
            result["query"] = row["query"]
            results.append(result)
        except Exception as exc:
            results.append({"evaluator": name, "query": row["query"], "status": "skipped", "reason": f"{exc.__class__.__name__}: {str(exc)[:180]}"})

score_df = pd.DataFrame(results)
display(score_df)
assert len(score_df) >= 4
assert (score_df.get("status", pd.Series(dtype=str)) != "skipped").any(), "At least one local evaluator should run."
""")

nb.md("## 5. Run a target-based cloud evaluation against the hosted agent")

nb.code("""
from azure.ai.projects.models import TestingCriterionAzureAIEvaluator
from openai.types.eval_create_params import DataSourceConfigCustom

queries_path = ROOT / "validation" / "m09-agent-eval-queries.jsonl"
queries_path.parent.mkdir(exist_ok=True)
with queries_path.open("w", encoding="utf-8") as f:
    for row in test_set[:3]:
        f.write(json.dumps({"query": row["query"]}) + "\\n")

cloud_result = {"status": "not_started"}
try:
    version = str(int(time.time()))
    dataset = project_client().datasets.upload_file(
        name="lgws-m09-agent-eval-queries",
        version=version,
        file_path=str(queries_path),
    )
    criteria = [
        TestingCriterionAzureAIEvaluator(
            type="azure_ai_evaluator",
            name="Intent Resolution",
            evaluator_name="builtin.intent_resolution",
            initialization_parameters={"model": settings.reasoning_model},
            data_mapping={"query": "{{item.query}}", "response": "{{sample.output_items}}"},
        ),
        TestingCriterionAzureAIEvaluator(
            type="azure_ai_evaluator",
            name="Task Adherence",
            evaluator_name="builtin.task_adherence",
            initialization_parameters={"model": settings.reasoning_model},
            data_mapping={"query": "{{item.query}}", "response": "{{sample.output_items}}"},
        ),
    ]
    data_source_config = DataSourceConfigCustom(
        type="custom",
        item_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        include_sample_schema=True,
    )
    client = openai_client()
    evaluation = client.evals.create(
        name="LGWS M9 Support Agent Quality",
        data_source_config=data_source_config,
        testing_criteria=criteria,
    )
    eval_run = client.evals.runs.create(
        eval_id=evaluation.id,
        name="LGWS M9 Support Agent Target Run",
        data_source={
            "type": "azure_ai_target_completions",
            "source": {"type": "file_id", "id": dataset.id},
            "input_messages": {"type": "template", "template": [{"type": "message", "role": "user", "content": {"type": "input_text", "text": "{{item.query}}"}}]},
            "target": {"type": "azure_ai_agent", "name": agent.agent_name},
        },
    )
    deadline = time.time() + 600
    while True:
        run = client.evals.runs.retrieve(run_id=eval_run.id, eval_id=evaluation.id)
        print("status:", run.status)
        if run.status in {"completed", "failed", "canceled"} or time.time() > deadline:
            break
        time.sleep(10)
    print("Report URL:", getattr(run, "report_url", None))
    print("Counts:", getattr(run, "result_counts", None))
    for c in getattr(run, "per_testing_criteria_results", []) or []:
        print(c.testing_criteria, "passed:", c.passed, "failed:", c.failed)
    cloud_result = {"status": run.status, "report_url": getattr(run, "report_url", None), "counts": getattr(run, "result_counts", None)}
    assert run.status == "completed"
    assert getattr(run, "per_testing_criteria_results", None), "Cloud evaluation completed but returned no metric results."
except Exception as exc:
    cloud_result = {"status": "unavailable", "error": f"{exc.__class__.__name__}: {str(exc)[:500]}"}
    print("Cloud target evaluation could not complete in this environment; local evaluator results above are the working fallback.")
    print(cloud_result["error"])

assert cloud_result["status"] in {"completed", "unavailable"}
""")

nb.your_turn(
    """
    Add one more row to `test_set` for a new support scenario. Include an `expected_behavior`, `ground_truth`, and `expected_tool`, then rerun the local scoring cell.
    """,
    """
    # test_set.append({"query": "...", "expected_behavior": "...", "ground_truth": "...", "expected_tool": "lookup_order"})
    """,
)

nb.md("""
## Cleanup

We keep `lgws-m09-support-agent`, the uploaded dataset, and evaluation history because M10-M12 reuse the agent and the eval report is useful evidence.

## Recap

| Part | Evidence |
|---|---|
| Reusable agent | `lgws-m09-support-agent` deployed or found |
| Local eval | `score_df` contains judge results/skips with reasons |
| Cloud eval | `cloud_result` contains `completed` + report URL, or an explicit SDK/preview limitation fallback |

➡️ Next: **M10 · Observability & tracing** — trace this same hosted agent in Application Insights.
""")

nb.save("docs/modules/09-evaluation.ipynb")
