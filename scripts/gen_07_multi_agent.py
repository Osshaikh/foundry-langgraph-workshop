"""Generate docs/modules/07-multi-agent.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M7 · Multi-agent orchestration",
    "Use LangGraph to coordinate sequential, routed, and parallel specialist agents inside one hosted agent.",
    minutes=60,
)

nb.md("""
## Objectives

- Build a sequential pipeline: writer → legal reviewer → formatter, with private `draft` state.
- Build a supervisor/router that chooses specialist sub-agents created with `create_agent`.
- Fan out to parallel specialist nodes and fan in to a synthesizer.
- Host the whole supervisor graph as **one** Responses hosted agent and assert two routes.

```
user → router ──┬─ sequential: writer → legal → formatter
                ├─ orders_agent → synthesizer
                ├─ product_expert → synthesizer
                └─ fanout → price/durability/fit → synthesizer
```
""")

nb.bootstrap()

nb.md("## 1. Read the supervisor graph")
nb.code("""
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m07-multi-agent" / "src" / "multi-agent"
show_file(src / "main.py")
show_file(AGENTS_DIR / "m07-multi-agent" / "azure.yaml")
""")

nb.md("## 2. Initialize and run locally")
nb.code("""
from workshop.azd import init_agent, summarize_output

agent = init_agent("m07-multi-agent", port=8107, fresh=True)
agent.run_local(timeout=900)
""")

nb.code("""
order = agent.local_responses("Where is order A123 and can I return it if it is late?")
product = agent.local_responses("Which backpack features matter for a rainy 2-day hike?")
parallel = agent.local_responses("Compare two hiking boots in parallel across cost, durability, and fit.")

for label, response in [("order", order), ("product", product), ("parallel", parallel)]:
    print("\\n---", label, "---")
    summarize_output(response)
    text = str(response["output"]).lower()
    assert "routes_taken" in text

assert "orders_agent" in str(order["output"]).lower()
assert "product_expert" in str(product["output"]).lower()
assert "price_research" in str(parallel["output"]).lower()
""")

nb.code("""
agent.stop_local()
""")

nb.md("## 3. Deploy one hosted supervisor agent")
nb.code("""
agent.deploy()
""")

nb.md("## 4. Invoke hosted and assert routing")
nb.code("""
from workshop.agents import ask

h_order = ask(agent.agent_name, "My order A123 has not arrived. What should I do?")
h_product = ask(agent.agent_name, "What should I look for in a waterproof hiking jacket?")

order_text = h_order.output_text.lower()
product_text = h_product.output_text.lower()
print(order_text)
print(product_text)
assert "orders_agent" in order_text
assert "product_expert" in product_text
""")

nb.md("""
**Expected output:** both hosted responses include a `ROUTES_TAKEN:` line. The assertions prove two different questions took
different specialist routes inside the same hosted agent.
""")

nb.md("""
## Stretch: Agent-to-Agent (A2A) — optional reading

The Foundry samples include `langgraph/a2a`, where one hosted agent publishes an incoming A2A endpoint and another hosted
agent calls it through a Toolbox `a2a_preview` tool. A2A is useful when specialists must be independently deployed,
versioned, or shared across teams. This lab does **not** execute A2A: our orchestration stays inside one LangGraph graph so
the classroom setup remains fast and deterministic.
""")

nb.md("## Cleanup")
nb.code("""
agent.stop_local()
print("Kept deployed agent:", agent.agent_name)
""")

nb.your_turn(
    """
    Add a third routed specialist named `loyalty_agent`. Route questions about points, status, or rewards to it, then add
    one assertion that proves the new route was taken.
    """,
    "# Extend agents/m07-multi-agent/src/multi-agent/main.py and rerun the local cells."
)

nb.md("""
## Recap

| Pattern | Node names |
|---|---|
| Sequential | `writer`, `legal_reviewer`, `formatter` |
| Supervisor/router | `router`, `orders_agent`, `product_expert`, `synthesizer` |
| Parallel fan-out/fan-in | `fanout`, `price_research`, `durability_research`, `fit_research`, `synthesizer` |

➡️ Next: **M8 · Deep research agent** — give an agent planning, web search, sub-agent delegation, and final reports.
""")

nb.save("docs/modules/07-multi-agent.ipynb")

