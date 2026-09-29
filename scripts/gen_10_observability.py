"""Generate docs/modules/10-observability.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M10 · Observability and tracing",
    "Enable GenAI OpenTelemetry tracing for the support agent and query spans from Application Insights.",
    minutes=60,
)

nb.md("""
## Objectives

- Reuse `lgws-m09-support-agent` and keep each notebook independently runnable.
- Enable LangChain/LangGraph OpenTelemetry tracing with Azure Monitor export.
- Invoke the hosted agent several times to create model and tool spans.
- Query Application Insights through `azure-monitor-query` and inspect `agent.monitor()` output.

```text
hosted agent ──► OpenTelemetry spans ──► Application Insights workspace ──► KQL table
```
""")

nb.bootstrap()

nb.md("## 1. Get or deploy the traced support agent")

nb.code("""
from workshop.azd import init_agent
from workshop.agents import ask
from workshop.config import project_client, credential
import json, shutil, subprocess, time, pandas as pd

agent = init_agent(
    "m09-support-agent",
    port=8110,
    env={
        "APPLICATIONINSIGHTS_CONNECTION_STRING": settings.appinsights_connection_string,
        "OTEL_AUTO_CONFIGURE_AZURE_MONITOR": "true",
        "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED": "true",
        "AZURE_TRACING_ALL_LANGGRAPH_NODES": "true",
    },
)
try:
    project_client().agents.get(agent.agent_name)
    print("Found hosted agent", agent.agent_name)
except Exception:
    print("Agent missing; deploying the reusable M9 support agent.")
    agent.deploy()
    project_client().agents.get(agent.agent_name)
""")

nb.md("## 2. Review the tracing code and manifest settings")

nb.code("""
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

show_file(AGENTS_DIR / "m09-support-agent" / "src" / "support-agent" / "main.py")
show_file(AGENTS_DIR / "m09-support-agent" / "azure.yaml")
""")

nb.md("## 3. Invoke the hosted agent to generate spans")

nb.code("""
prompts = [
    "Where is order CO-1002?",
    "What is the return policy for a rain jacket?",
    "Please escalate order CO-1002 because it is late.",
]
responses = []
for prompt in prompts:
    try:
        r = ask(agent.agent_name, prompt)
    except Exception as exc:
        if "agent_version_failed" not in str(exc):
            raise
        print("Latest agent version failed provisioning; deploying a fresh version and retrying.")
        agent.deploy()
        r = ask(agent.agent_name, prompt)
    responses.append(r.id)
    print("created response", r.id)
    time.sleep(3)
assert len(responses) == 3
""")

nb.md("## 4. Resolve the Log Analytics workspace behind Application Insights")

nb.code("""
def az_json(*args, timeout=120):
    completed = subprocess.run(
        [shutil.which("az") or "az", *args, "-o", "json"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout)[-2000:])
    return json.loads(completed.stdout or "{}")

workspace_id = None
appinsights_resource_id = ""
try:
    # Find the App Insights component whose ApplicationId matches the connection string in .env.
    app_id = dict(p.split("=", 1) for p in settings.appinsights_connection_string.split(";") if "=" in p).get("ApplicationId")
    components = az_json("monitor", "app-insights", "component", "show", "--resource-group", settings.resource_group)
    components = components if isinstance(components, list) else [components]
    component = next((c for c in components if c.get("appId") == app_id), components[0] if components else {})
    appinsights_resource_id = component.get("id", "")
    workspace_resource_id = component.get("workspaceResourceId")
    print("App Insights:", component.get("name"), "workspace:", workspace_resource_id)
    if workspace_resource_id:
        workspace = az_json("resource", "show", "--ids", workspace_resource_id)
        workspace_id = workspace["properties"]["customerId"]
        print("Workspace customer id:", workspace_id)
except Exception as exc:
    print("Workspace lookup failed:", exc)
    print("Falling back to resource-scope log query:", appinsights_resource_id)

assert workspace_id or appinsights_resource_id
""")

nb.md("## 5. Query GenAI spans with retry for ingestion delay")

nb.code("""
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from datetime import timedelta

query = r'''
union isfuzzy=true dependencies, traces, AppDependencies, AppTraces
| extend ts = todatetime(coalesce(column_ifexists("TimeGenerated", datetime(null)), column_ifexists("timestamp", datetime(null))))
| where ts > ago(30m)
| extend props = coalesce(column_ifexists("Properties", dynamic(null)), column_ifexists("customDimensions", dynamic(null)))
| extend props_text = tostring(props)
| extend operation = extract(@'"gen_ai\\.operation\\.name"\\s*:\\s*"([^"]+)"', 1, props_text),
         model = extract(@'"gen_ai\\.request\\.model"\\s*:\\s*"([^"]+)"', 1, props_text),
         input_tokens = extract(@'"gen_ai\\.usage\\.input_tokens"\\s*:\\s*"?([^",}]+)"?', 1, props_text),
         output_tokens = extract(@'"gen_ai\\.usage\\.output_tokens"\\s*:\\s*"?([^",}]+)"?', 1, props_text),
         duration_ms = tostring(coalesce(column_ifexists("DurationMs", real(null)), column_ifexists("duration", real(null)))),
         message = tostring(coalesce(column_ifexists("Message", ""), column_ifexists("message", ""), column_ifexists("Name", ""), column_ifexists("name", "")))
| where operation != "" or message has "gen_ai" or message has "lookup_order" or message has "return_policy"
| project TimeGenerated=ts, operation, model, input_tokens, output_tokens, duration_ms, message
| order by TimeGenerated desc
| take 20
'''

client = LogsQueryClient(credential())
span_rows = []
for attempt in range(20):
    try:
        if workspace_id:
            result = client.query_workspace(workspace_id, query, timespan=timedelta(minutes=30))
        else:
            result = client.query_resource(appinsights_resource_id, query, timespan=timedelta(minutes=30))
    except Exception as exc:
        print("Log query failed; check table names/permissions in this environment:", str(exc)[:500])
        break
    if result.status == LogsQueryStatus.SUCCESS:
        table = result.tables[0] if result.tables else None
        if table and table.rows:
            span_rows = [dict(zip(table.columns, row)) for row in table.rows]
            break
    print(f"No spans yet (attempt {attempt + 1}/20); waiting 30 seconds for ingestion...")
    time.sleep(30)

if span_rows:
    display(pd.DataFrame(span_rows))
else:
    print("No GenAI rows arrived during the retry window. Check the Foundry portal Traces tab and Application Insights Agents view.")

assert span_rows is not None
""")

nb.md("## 6. Inspect hosted-agent logs with `azd ai agent monitor`")

nb.code("""
monitor_output = agent.monitor(tail=80)
print(monitor_output[-2000:])
assert isinstance(monitor_output, str)
""")

nb.your_turn(
    """
    Change the KQL `take 20` to `take 50`, rerun the query, and group spans by `operation` to compare model calls vs. tool execution.
    """,
    """
    # pd.DataFrame(span_rows).groupby("operation").size()
    """,
)

nb.md("""
## Cleanup

Nothing is deleted. We keep the agent and traces so later labs can compare guardrail and red-team behavior in the Foundry portal **Traces** tab.

## Recap

| Signal | Where to inspect |
|---|---|
| Local/hosted logs | `agent.monitor()` |
| OpenTelemetry spans | Application Insights `AppDependencies` / `AppTraces` |
| Visual trace tree | Foundry portal → Agent → **Traces** |

➡️ Next: **M11 · Guardrails** — attach the strict RAI policy and add an in-graph PII guardrail.
""")

nb.save("docs/modules/10-observability.ipynb")
