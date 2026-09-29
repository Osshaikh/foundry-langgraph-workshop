"""Generate docs/modules/03-tools-and-function-calling.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M3 · Tools & function calling",
    "Turn Python functions into tool schemas, inspect local tool calls, then build the ReAct loop by hand with LangGraph.",
    minutes=55,
)

nb.md("""
## Objectives

- Define LangChain tools with `@tool`, docstrings, type hints and a Pydantic `args_schema`.
- Bind tools to a Foundry chat model and inspect `AIMessage.tool_calls` before any tool executes.
- Build the ReAct loop **by hand** with `StateGraph(MessagesState)`, `ToolNode` and `tools_condition`.
- See parallel tool calls and `ToolNode(handle_tool_errors=...)` in action.
- Host the same hand-built graph as a Foundry Hosted Agent and assert the expected tools were called.

## Scenario

Contoso Outdoor support agents often need three facts before replying:

```
customer request → lookup_order + check_inventory + estimate_shipping → grounded answer
```

The fake order, inventory and shipping data are small Python dictionaries so you can focus on the tool-calling mechanics.
""")

nb.bootstrap()

nb.md("## 1. Tool schemas from Python functions")

nb.code(r'''
from typing import Annotated, Literal
from langchain_core.tools import tool
from pydantic import BaseModel, Field

@tool
def lookup_order(order_id: Annotated[str, "Contoso order id such as CO-1001."]) -> str:
    """Look up a Contoso Outdoor order by order id."""
    return "demo order"

class ShippingEstimateInput(BaseModel):
    destination_zip: str = Field(description="US destination ZIP code, e.g. 98101")
    service_level: Literal["ground", "express", "overnight"] = Field(default="ground")

@tool(args_schema=ShippingEstimateInput)
def estimate_shipping(destination_zip: str, service_level: str = "ground") -> str:
    """Estimate Contoso Outdoor delivery time and cost."""
    return "demo estimate"

print("lookup_order schema:")
print(lookup_order.args_schema.model_json_schema())
print("\nestimate_shipping schema:")
print(estimate_shipping.args_schema.model_json_schema())
''')

nb.md("""
`lookup_order` gets its schema from the docstring and type hint. `estimate_shipping` uses a Pydantic model so we can add richer field descriptions and enum constraints.

## 2. Bind tools and inspect tool calls locally

`bind_tools` only asks the model to produce tool calls. It does **not** run tools. That makes it perfect for inspecting the model's proposed calls.
""")

nb.code(r'''
from workshop.config import chat_model

@tool
def check_inventory(sku: Annotated[str, "Product SKU such as SKU-TENT-2P."]) -> str:
    """Check current available inventory and restock date for a SKU."""
    return "demo inventory"

bound = chat_model().bind_tools([lookup_order, check_inventory, estimate_shipping], parallel_tool_calls=True)
expected = {"lookup_order", "check_inventory"}
for attempt in range(3):
    probe = bound.invoke(
        "Call lookup_order for order CO-1002 and check_inventory for SKU-TENT-2P. "
        "Return tool calls, not prose."
    )
    names = {call["name"] for call in probe.tool_calls}
    print("tool_calls:", probe.tool_calls)
    if expected <= names:
        break
assert expected <= names, names
''')

nb.md("""
The model can request more than one tool in the same turn. LangGraph's `ToolNode` executes those calls and appends `ToolMessage` results.

## 3. Read the hosted agent source
""")

nb.code(r'''
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m03-tools" / "src" / "tools-agent"
show_file(src / "main.py")
show_file(src / "langgraph.json")
show_file(AGENTS_DIR / "m03-tools" / "azure.yaml")
''')

nb.md("""
Key lines to notice:

- `_build_chat_model().bind_tools(TOOLS, parallel_tool_calls=True)` asks the model for OpenAI-style tool calls.
- `StateGraph(MessagesState)` stores the running conversation in a `messages` list.
- `tools_condition` routes to `ToolNode` when the last assistant message has tool calls, otherwise ends.
- `ToolNode(..., handle_tool_errors=_tool_error)` converts tool exceptions into tool messages that the model can recover from.

## 4. Visualize the graph
""")

nb.code(r'''
import importlib.util

spec = importlib.util.spec_from_file_location("m03_tools_main", src / "main.py")
m03 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m03)
print(m03.graph.get_graph().draw_mermaid())
''')

nb.md("## 5. Initialise and run locally")

nb.code(r'''
from workshop.azd import init_agent, summarize_output

agent = init_agent("m03-tools", port=8103)
agent.run_local()
''')

nb.code(r'''
question = (
    "For order CO-1002, look up the order, check inventory for SKU-TENT-2P, "
    "and estimate ground shipping to ZIP 10001. Use all needed tools before answering."
)
local = agent.local_responses(question)
summarize_output(local)

def function_call_names(response):
    items = response["output"] if isinstance(response, dict) else [item.model_dump() for item in response.output]
    return [item.get("name", "") for item in items if item.get("type") == "function_call"]

names = set(function_call_names(local))
assert {"lookup_order", "check_inventory", "estimate_shipping"} <= names, names
''')

nb.md("### Tool error handling")

nb.code(r'''
error_demo = agent.local_responses("Try lookup_order for missing order CO-9999, then explain what happened.")
summarize_output(error_demo)
assert "Tool error handled" in str(error_demo["output"])
''')

nb.code("agent.stop_local()")

nb.md("## 6. Deploy and invoke the hosted agent")

nb.code("agent.deploy()")

nb.code(r'''
from workshop.agents import ask

hosted = ask(
    agent.agent_name,
    "For order CO-1001, call lookup_order, check_inventory for SKU-BP-35L, "
    "and estimate express shipping to ZIP 98101."
)
hosted_names = set(function_call_names(hosted))
print("hosted tool calls:", hosted_names)
assert {"lookup_order", "check_inventory", "estimate_shipping"} <= hosted_names, hosted_names
''')

nb.your_turn(
    """
    Add a fourth tool called `recommend_alternative(sku: str)` that suggests an in-stock substitute when inventory is zero. Re-run the local agent and ask about `SKU-PAD-REG`.
    """,
    "# Your code here",
)

nb.md("""
## Cleanup

The local container is stopped above. The deployed agent `lgws-m03-tools` is kept so you can inspect traces in Foundry.

## Recap

| Concept | What you did |
|---|---|
| `@tool` | Converted Python functions into JSON tool schemas |
| Pydantic `args_schema` | Added enum/field metadata for shipping inputs |
| `bind_tools` | Inspected local `tool_calls` before execution |
| `ToolNode` | Executed model-requested tools and handled errors |
| Hosted Agent | Deployed the same hand-built graph to Foundry |

➡️ Next: **M4 · Grounding / RAG with Azure AI Search** — connect a hosted agent to a searchable knowledge base.
""")

nb.save("docs/modules/03-tools-and-function-calling.ipynb")
