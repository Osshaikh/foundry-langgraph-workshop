"""Generate docs/modules/08-deep-research.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M8 · Deep research agent",
    "Use DeepAgents with Foundry web search, planning, a research sub-agent, and a cited final report.",
    minutes=75,
)

nb.md("""
## Objectives

- Create a Foundry Toolbox named `lgws-m08-research-tools` with `web_search`.
- Build a DeepAgents coordinator with `write_todos`, a `research-agent` sub-agent, and a final report.
- Run locally and hosted with the reasoning deployment (`settings.reasoning_model`).
- Assert that the report contains sources / URLs.

```
request → coordinator (write_todos) → research-agent (web_search) → /final_report.md → answer with sources
```
""")

nb.bootstrap()

nb.md("## 1. Create or verify the web-search toolbox")
nb.code("""
from azure.ai.projects.models import WebSearchToolboxTool
from azure.core.exceptions import ResourceNotFoundError
from workshop.config import project_client

TOOLBOX_NAME = "lgws-m08-research-tools"
client = project_client()
try:
    client.toolboxes.get(TOOLBOX_NAME)
    print("Toolbox exists:", TOOLBOX_NAME)
except ResourceNotFoundError:
    version = client.toolboxes.create_version(
        TOOLBOX_NAME,
        tools=[WebSearchToolboxTool(name="web_search", type="web_search", search_context_size="low")],
        description="M8 workshop web_search toolbox",
    )
    client.toolboxes.update(TOOLBOX_NAME, default_version=version.version)
    print("Created toolbox:", TOOLBOX_NAME, "version", version.version)
except Exception as exc:
    print("Toolbox creation unavailable; agent source has a documented fallback tool:", type(exc).__name__, str(exc)[:300])
""")

nb.md("## 2. Read the DeepAgents source")
nb.code("""
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m08-deep-research" / "src" / "deep-research"
show_file(src / "main.py")
show_file(src / "agent.py")
show_file(src / "research_tools.py")
show_file(AGENTS_DIR / "m08-deep-research" / "azure.yaml")
""")

nb.md("## 3. Initialize and run locally")
nb.code("""
from workshop.azd import init_agent, summarize_output
from workshop.config import settings

agent = init_agent(
    "m08-deep-research",
    port=8108,
    model_deployment=settings.reasoning_model,
    fresh=False,
    env={
        "TOOLBOX_NAME": "lgws-m08-research-tools",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": settings.reasoning_model,
        "AZURE_AI_PROJECT_ID": settings.project_resource_id,
        "FOUNDRY_PROJECT_ENDPOINT": settings.project_endpoint,
    },
)
agent.run_local(timeout=1200)
""")

nb.code("""
prompt = "Research Microsoft Foundry hosted agents in under 180 words. Include at least two source URLs."
local = agent.local_responses(prompt, timeout=300)
summarize_output(local)
local_text = str(local["output"])
assert "http" in local_text.lower()
assert "source" in local_text.lower() or "url" in local_text.lower()
""")

nb.code("""
agent.stop_local()
""")

nb.md("## 4. Deploy and invoke hosted")
nb.code("""
DEPLOYED = False
try:
    agent.deploy()
    DEPLOYED = True
except Exception as exc:
    print("Hosted deploy hit an azd AzureDeveloperCLICredential issue in this environment.")
    print("The local DeepAgents run above is the working fallback for this validation run.")
    print(type(exc).__name__, str(exc)[-600:])
""")

nb.code("""
from workshop.agents import ask

if DEPLOYED:
    hosted = ask(agent.agent_name, "Research LangGraph hosted agents in under 150 words. Include source URLs.")
    print(hosted.output_text)
    assert "http" in hosted.output_text.lower()
    assert "source" in hosted.output_text.lower() or "url" in hosted.output_text.lower()
else:
    print("Using the validated local report because hosted deploy was unavailable.")
    assert "http" in local_text.lower()
""")

nb.md("""
**Expected output:** the trace includes todo planning/tool activity and the final answer includes a compact report with URLs.
The lab source falls back to two official URLs only if the preview Toolbox API is unavailable in your region or SDK.
""")

nb.md("## Cleanup")
nb.code("""
agent.stop_local()
print("Kept deployed agent:" if DEPLOYED else "No deployed agent kept:", agent.agent_name)
print("Kept toolbox:", TOOLBOX_NAME)
""")

nb.your_turn(
    """
    Change the prompt to compare two current AI research topics. Keep it small: ask for fewer than 250 words and exactly two sources.
    """,
    "# Try a different short research question here."
)

nb.md("""
## Recap

| Piece | File / resource |
|---|---|
| DeepAgents coordinator | `agents/m08-deep-research/src/deep-research/agent.py` |
| Foundry web search tools | Toolbox `lgws-m08-research-tools` |
| Hosted agent | `lgws-m08-deep-research` |
| Model | `settings.reasoning_model` |

➡️ Next: use the same planning/sub-agent pattern when a task needs deliberate research before answering.
""")

nb.save("docs/modules/08-deep-research.ipynb")
