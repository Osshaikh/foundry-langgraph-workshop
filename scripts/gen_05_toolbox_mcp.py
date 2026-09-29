"""Generate docs/modules/05-toolbox-mcp.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M5 · MCP tools via Foundry Toolbox",
    "Create a Foundry Toolbox with Web Search and Microsoft Learn MCP tools, then load it from a hosted LangGraph agent.",
    minutes=60,
)

nb.md("""
## Objectives

- Create a Foundry Toolbox named `lgws-m05-toolbox` with `WebSearchToolboxTool` and a Microsoft Learn MCP server.
- List toolbox tools locally with `langchain_azure_ai.tools.AzureAIProjectToolbox`.
- Build a hosted LangGraph agent that loads toolbox tools at startup through an async `create_graph()` factory.
- Reuse the schema sanitizer and consent-aware tool error handler from the Foundry samples.
- Test both a Microsoft Learn MCP question and a web search question, asserting tool calls.

## Toolbox concept

A toolbox exposes one MCP endpoint for one immutable toolbox version. The unversioned consumer endpoint follows the toolbox's `default_version`, so promoting a new version can update agents without changing their code.
""")

nb.bootstrap()

nb.md("## 1. Create a toolbox version")

nb.code(r'''
from azure.ai.projects.models import MCPToolboxTool, WebSearchToolboxTool
from workshop.config import project_client

TOOLBOX_NAME = "lgws-m05-toolbox"
client = project_client()
version = client.toolboxes.create_version(
    TOOLBOX_NAME,
    tools=[
        WebSearchToolboxTool(),
        MCPToolboxTool(
            server_label="mslearn",
            server_url="https://learn.microsoft.com/api/mcp",
            require_approval="never",
        ),
    ],
    description="M5 workshop toolbox: web search plus Microsoft Learn MCP.",
    metadata={"lab": "m05"},
)
client.toolboxes.update(TOOLBOX_NAME, default_version=version.version)
toolbox = client.toolboxes.get(TOOLBOX_NAME)
print("Toolbox:", toolbox.name)
print("Created version:", version.version)
print("Default version:", toolbox.default_version)
''')

nb.md("""
`require_approval="never"` means the runtime may call Microsoft Learn tools without pausing for user approval. If a tool is configured as `always`, your runtime must enforce the approval before calling it; a prompt instruction alone is not enough.
""")

nb.md("## 2. List toolbox tools locally")

nb.code(r'''
import os
from langchain_azure_ai.tools import AzureAIProjectToolbox

os.environ["TOOLBOX_NAME"] = TOOLBOX_NAME
toolbox_loader = AzureAIProjectToolbox(toolbox_name=TOOLBOX_NAME)
tools = await toolbox_loader.get_tools()
tool_names = [tool.name for tool in tools]
print("Loaded tools:")
for name in tool_names:
    print(" -", name)
assert any("search" in name.lower() or "web" in name.lower() for name in tool_names)
assert any("learn" in name.lower() or "docs" in name.lower() or "microsoft" in name.lower() for name in tool_names)
''')

nb.md("## 3. Read the hosted agent")

nb.code(r'''
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m05-toolbox" / "src" / "toolbox-agent"
show_file(src / "main.py")
show_file(src / "langgraph.json")
show_file(AGENTS_DIR / "m05-toolbox" / "azure.yaml")
''')

nb.md("""
The `langgraph.json` entry points at `./main.py:create_graph`. The hosting adapter supports async factories, so the agent can enumerate toolbox tools during startup.

The toolbox endpoint itself is a project resource. No extra Azure RBAC role is required for the agent identity just to call this toolbox; downstream tools may have their own auth requirements. Web Search and the public Microsoft Learn MCP server do not require an additional Azure role here.
""")

nb.md("## 4. Initialise the hosted-agent project")

nb.code(r'''
from workshop.azd import init_agent

agent = init_agent("m05-toolbox", port=8105, env={"TOOLBOX_NAME": TOOLBOX_NAME})
print("Agent project:", agent.project_dir)
''')

nb.md("""
The previous cell that used `AzureAIProjectToolbox` is the local toolbox test: it called the toolbox MCP endpoint and listed tools without deploying.

## 5. Deploy and invoke
""")

nb.code("agent.deploy()")

nb.code(r'''
from workshop.agents import ask

learn = ask(
    agent.agent_name,
    "Use the Microsoft Learn MCP tool to answer: which Python package hosts LangGraph agents as Foundry hosted agents? Cite the Learn source."
)
learn_calls = [item.name for item in learn.output if getattr(item, "type", None) == "function_call"]
print("Microsoft Learn call names:", learn_calls)
assert any("learn" in name.lower() or "docs" in name.lower() or "microsoft" in name.lower() for name in learn_calls), learn_calls
''')

nb.code(r'''
web = ask(
    agent.agent_name,
    "Use web search to find a current page about Azure AI Search and summarize it in one sentence with a source URL."
)
web_calls = [item.name for item in web.output if getattr(item, "type", None) == "function_call"]
print("Web search call names:", web_calls)
assert any("web" in name.lower() or name.lower() == "search" for name in web_calls), web_calls
''')

nb.your_turn(
    """
    Add an `allowed_tools` filter to the Microsoft Learn MCP tool, create a new toolbox version, promote it to default, and re-run the local tool listing.
    """,
    "# Hint: MCPToolboxTool(..., allowed_tools=[...], require_approval='never')",
)

nb.md("""
## Cleanup

The deployed agent `lgws-m05-toolbox` and toolbox `lgws-m05-toolbox` are kept. Toolbox versions are immutable; creating another version and updating `default_version` is the normal way to change available tools.

## Recap

| Concept | What you used |
|---|---|
| Toolbox version | Immutable set of tool definitions |
| Default version | The unversioned MCP consumer endpoint follows this pointer |
| `require_approval` | Runtime contract: `never` can call directly; `always` must pause and ask |
| `AzureAIProjectToolbox` | Loads Foundry Toolbox tools as LangChain tools |
| Async graph factory | Loads tools at hosted-agent startup |

➡️ Next: continue to the next workshop module.
""")

nb.save("docs/modules/05-toolbox-mcp.ipynb")
