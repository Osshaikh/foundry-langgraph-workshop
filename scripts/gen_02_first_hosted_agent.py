"""Generate docs/modules/02-first-hosted-agent.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M2 · Your first hosted LangGraph agent",
    "Build a LangGraph agent, run it locally with the Foundry agent server, then deploy it as a Foundry Hosted Agent.",
    minutes=45,
)

nb.md("""
## Objectives

- Build a tool-using agent with LangChain's `create_agent` (a compiled **LangGraph** graph).
- Understand the **hosted-agent project layout**: `azure.yaml`, `main.py`, `langgraph.json`, `requirements.txt`.
- Run it locally with **`azd ai agent run`** and call its OpenAI-compatible **`/responses`** endpoint.
- Deploy it with **`azd deploy`** and invoke the hosted version with the Python SDK — including multi-turn.

## What is a hosted agent?

A **Foundry Hosted Agent** is *your* agent code (any framework — here LangGraph) that Foundry runs for
you in a per-session, VM-isolated sandbox. Foundry handles packaging, identity, scaling to zero, conversation
storage, tracing and the public endpoint. You bring a graph; the
[`langchain_azure_ai.agents.hosting`](https://learn.microsoft.com/azure/foundry/how-to/develop/langchain-hosted-agents)
adapter turns it into a server that speaks Foundry's **Responses** protocol.

```
agents/m02-first-agent/
├── azure.yaml                 ← azd manifest: agent name, runtime, protocol, env, CPU/memory
└── src/first-agent/
    ├── main.py                ← exports `graph` (your LangGraph agent)
    ├── langgraph.json         ← tells the host which graph to serve
    ├── requirements.txt       ← pinned deps installed by Foundry's remote build
    └── .agentignore           ← keeps .venv etc. out of the upload
```
""")

nb.bootstrap()

nb.md("## 1. Read the agent code")

nb.code("""
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m02-first-agent" / "src" / "first-agent"
show_file(src / "main.py")
show_file(src / "langgraph.json")
""")

nb.md("""
Key points:

- `create_agent(model, tools, system_prompt)` returns a **compiled LangGraph** implementing the ReAct loop
  (model → tool calls → model → … → answer).
- Tools are plain Python functions decorated with `@tool`; the docstring and type hints become the tool schema.
- The module-level `graph` object is what `langgraph.json` points to.
- `FOUNDRY_PROJECT_ENDPOINT` is **injected by Foundry** at runtime; locally it comes from your azd environment.

## 2. The deployment manifest
""")

nb.code("""
show_file(AGENTS_DIR / "m02-first-agent" / "azure.yaml")
""")

nb.md("""
| Field | Meaning |
|---|---|
| `host: azure.ai.agent`, `kind: hosted` | a Foundry **hosted** agent service |
| `codeConfiguration.runtime` / `entryPoint` | Foundry builds your source on `python_3_13` and starts the LangGraph host |
| `startupCommand` | what `azd ai agent run` executes locally |
| `protocols` | `responses` → OpenAI-compatible `/responses` endpoint |
| `env` | environment variables passed to the container |
| `container.resources` | CPU / memory **per session** |

## 3. Initialise the azd project against your Foundry project

`init_agent` runs `azd ai agent init --no-prompt` with your project's resource ID and model deployment.
It creates a working copy under `.work/m02-first-agent/` (git-ignored) with its own azd environment.
""")

nb.code("""
from workshop.azd import init_agent

agent = init_agent("m02-first-agent", port=8088)
print("Agent name:", agent.agent_name)
""")

nb.md("""
## 4. Run it locally

`azd ai agent run` creates a virtual environment, installs `requirements.txt` and starts the host on
`http://localhost:8088`. The first start takes 1–2 minutes (dependency install).
""")

nb.code("""
agent.run_local()
""")

nb.code("""
from workshop.azd import summarize_output

r1 = agent.local_responses("What time is it right now, and what is 42 * 17?")
print("response id:", r1["id"])
summarize_output(r1)
""")

nb.md("""
**Expected output:** two tool calls (`get_current_time`, `calculator`), their results, and a final message with the time and **714**.

### Multi-turn with `previous_response_id`

The host stores each response, so the next turn only needs the previous response's ID:
""")

nb.code("""
r2 = agent.local_responses("Add 100 to that result.", previous_response_id=r1["id"])
summarize_output(r2)
assert "814" in str(r2["output"])
""")

nb.code("""
agent.stop_local()
""")

nb.md("""
## 5. Deploy to Foundry

`azd deploy` zips `src/first-agent`, uploads it, lets Foundry **build the dependencies remotely**, creates a
new **agent version** and waits until it is `active` (~2 minutes).
""")

nb.code("""
agent.deploy()
""")

nb.md("""
## 6. Invoke the hosted agent

### With the Python SDK

`project.get_openai_client(agent_name=...)` returns an OpenAI client bound to **your agent's endpoint** —
the same `responses.create` call, but now the model, tools and loop run inside Foundry.
""")

nb.code("""
from workshop.agents import ask

h1 = ask(agent.agent_name, "What is 1234 * 5678? Use your calculator.")
h2 = ask(agent.agent_name, "Now divide that by 2.", previous_response_id=h1.id)
print("\\nFinal:", h2.output_text)
""")

nb.md("""
**Expected output:** `7006652` then `3503326`. The first call after a deploy can take ~10 s (cold start of the session sandbox).

### With azd
""")

nb.code("""
agent.invoke("Say hello to the workshop in five words.")
""")

nb.md("""
### In the portal

Open [ai.azure.com](https://ai.azure.com) → your project → **Agents**. Find `lgws-m02-first-agent`,
open the **Playground**, and chat with it. The **Traces** tab shows each model and tool span.
""")

nb.your_turn(
    """
    1. Add a third tool `convert_currency(amount: float, rate: float) -> str` to `agents/m02-first-agent/src/first-agent/main.py`.
    2. Re-run the **init** cell (it syncs your edited source), then `agent.run_local()` and test it.
    3. `agent.deploy()` again — notice a **new version** of the same agent is created.
    """,
)

nb.md("""
## Recap

| Step | Command |
|---|---|
| Scaffold against a project | `azd ai agent init -m azure.yaml --project-id … --model-deployment …` |
| Run locally | `azd ai agent run` → `POST http://localhost:8088/responses` |
| Deploy | `azd deploy` |
| Invoke | `azd ai agent invoke …` or `project.get_openai_client(agent_name=…).responses.create(...)` |

➡️ Next: **M3 · Tools & function calling** — build the ReAct loop yourself with `StateGraph`.
""")

nb.save("docs/modules/02-first-hosted-agent.ipynb")
