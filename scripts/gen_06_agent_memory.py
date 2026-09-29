"""Generate docs/modules/06-agent-memory.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M6 · Agent memory",
    "Compare Responses conversation history, durable LangGraph checkpoints, and long-term Foundry Memory.",
    minutes=75,
)

nb.md("""
## Objectives

- Explain the two short-term conversation models for Foundry Hosted Agents.
- Create an explicit Responses **conversation** and pass its ID to a hosted agent.
- Run an **Invocations** hosted agent that persists LangGraph state with `FoundryCheckpointSaver`.
- Add long-term user preferences with Foundry Memory, with a safe fallback if the preview is unavailable.

## Concepts

| Layer | Who owns it? | Identifier | Best for |
|---|---|---|---|
| Responses, no checkpointer | Foundry platform | `previous_response_id` or `conversation.id` | normal chat history |
| LangGraph checkpointer | your graph | `agent_session_id` / hosted session | durable graph state, interrupts, files |
| Foundry Memory | project memory store | stable `scope` such as user ID | cross-session preferences |

For Invocations, the v1 REST route is
`{project_endpoint}/agents/{name}/endpoint/protocols/invocations?api-version=v1`. The platform routes Invocations
session affinity from the `agent_session_id` query parameter; the lab helper also sends `x-agent-session-id` so the
container can see the same value.
""")

nb.bootstrap()

nb.md("## 1. Read the two M6 agents")
nb.code("""
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

show_file(AGENTS_DIR / "m06-memory-responses" / "src" / "memory-responses" / "main.py")
show_file(AGENTS_DIR / "m06-memory" / "src" / "memory-agent" / "main.py")
show_file(AGENTS_DIR / "m06-memory" / "azure.yaml")
""")

nb.md("""
The Responses agent intentionally has **no checkpointer**. Its follow-up context comes from the hosted Responses
platform. The Invocations agent uses `FoundryCheckpointSaver(user_isolation=True)`, so LangGraph state is saved in
Foundry's hosted-agent storage and keyed by the agent session.
""")

nb.md("## 2. Part A — platform conversation IDs")
nb.code("""
from workshop.azd import init_agent

responses_agent = init_agent("m06-memory-responses", port=8116, fresh=True)
responses_agent.deploy()
print("Responses agent:", responses_agent.agent_name)
""")

nb.code("""
from workshop.agents import ask
from workshop.config import openai_client

agent_oai = openai_client(agent_name=responses_agent.agent_name)
conversation = agent_oai.conversations.create()
conversation_id = conversation.id
print("conversation id:", conversation_id)

turn1 = ask(
    responses_agent.agent_name,
    "My workshop codename is Kestrel. Reply that you will remember it.",
    conversation=conversation_id,
)
turn2 = ask(
    responses_agent.agent_name,
    "What is my workshop codename?",
    conversation=conversation_id,
)
print(turn2.output_text)
assert "kestrel" in turn2.output_text.lower()
""")

nb.md("""
**Expected output:** the cell prints a `conv_...` ID and the second hosted turn recalls **Kestrel** even though we did not
send `previous_response_id`. That is platform-managed Responses history.
""")

nb.md("## 3. Part B — durable Invocations graph state")
nb.code("""
inv_agent = init_agent("m06-memory", port=8106, fresh=True)
print("Invocations agent:", inv_agent.agent_name)
""")

nb.code("""
inv_agent.run_local(timeout=900)
local_a, local_session = inv_agent.local_invocations("My trail snack is dried mango.")
print("local session:", local_session)
print(local_a)
local_b, local_session_b = inv_agent.local_invocations("What trail snack did I mention?", session_id=local_session)
print("local session reused:", local_session_b)
print(local_b)
assert "mango" in str(local_b).lower()
""")

nb.code("""
inv_agent.stop_local()
""")

nb.code("""
inv_agent.deploy()
remote_a, remote_session = inv_agent.remote_invocations("My project color is teal.")
print("remote session:", remote_session)
print(remote_a)
remote_b, remote_session_b = inv_agent.remote_invocations("What is my project color?", session_id=remote_session)
print("remote session reused:", remote_session_b)
print(remote_b)
assert "teal" in str(remote_b).lower()
""")

nb.md("""
**Expected output:** local and hosted Invocations calls both reuse the same session ID and recall the earlier fact. This is
LangGraph state, not Responses platform conversation history.
""")

nb.md("## 4. Part C — long-term Foundry Memory")
nb.code("""
from azure.core.exceptions import ResourceNotFoundError
from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_azure_ai.chat_history import AzureAIMemoryChatMessageHistory
from langchain_azure_ai.retrievers import AzureAIMemoryRetriever
from langgraph.graph import START, StateGraph, MessagesState
from workshop.config import credential, project_client, settings, chat_model
import time

def as_text(value):
    if isinstance(value, list):
        return " ".join(
            item.get("text", str(item)) if isinstance(item, dict) else str(item)
            for item in value
        )
    return str(value)

store_name = "lgws-m06-memory"
user_scope = "m06-lab-user"
MEMORY_MODE = "foundry"
client = project_client()
try:
    try:
        client.beta.memory_stores.get(store_name)
        print("Memory store exists:", store_name)
    except ResourceNotFoundError:
        definition = MemoryStoreDefaultDefinition(
            chat_model=settings.chat_model,
            embedding_model=settings.embedding_model,
            options=MemoryStoreDefaultOptions(user_profile_enabled=True, chat_summary_enabled=True),
        )
        client.beta.memory_stores.create(
            name=store_name,
            description="M6 workshop long-term memory store",
            definition=definition,
        )
        print("Created memory store:", store_name)
except Exception as exc:
    MEMORY_MODE = "fallback"
    print("Foundry Memory preview unavailable here; using LangGraph-style fallback:", type(exc).__name__, str(exc)[:300])

if MEMORY_MODE == "foundry":
    try:
        hist_a = AzureAIMemoryChatMessageHistory(
            project_endpoint=settings.project_endpoint,
            credential=credential(),
            store_name=store_name,
            scope=user_scope,
            base_history=InMemoryChatMessageHistory(),
            update_delay=0,
        )
        hist_a.add_user_message("Please remember: I prefer dark roast coffee and budget hostels.")
        hist_a.add_ai_message("Noted: dark roast coffee and budget hostels.")
        print("Seeded session A; waiting briefly for memory extraction...")
        time.sleep(45)

        retriever = AzureAIMemoryRetriever(
            project_endpoint=settings.project_endpoint,
            credential=credential(),
            store_name=store_name,
            scope=user_scope,
            k=5,
        )

        def recall_node(state: MessagesState):
            query = state["messages"][-1].content
            docs = retriever.invoke(query)
            memory_text = "\\\\n".join(d.page_content for d in docs) or "No memory found."
            response = chat_model().invoke([
                SystemMessage(content="Use the retrieved long-term memory if relevant."),
                SystemMessage(content=f"Memories:\\\\n{memory_text}"),
                *state["messages"],
            ])
            return {"messages": [response]}

        graph = StateGraph(MessagesState)
        graph.add_node("recall", recall_node)
        graph.add_edge(START, "recall")
        memory_graph = graph.compile()
        recalled = memory_graph.invoke({"messages": [HumanMessage(content="What coffee and lodging do I prefer?")]})
        answer = as_text(recalled["messages"][-1].content)
        print(answer)
        if "dark" not in answer.lower() or "hostel" not in answer.lower():
            raise RuntimeError("Memory extraction did not return the seeded preferences yet.")
    except Exception as exc:
        MEMORY_MODE = "fallback"
        print("Switching to fallback long-term memory pattern:", type(exc).__name__, str(exc)[:300])

if MEMORY_MODE == "fallback":
    long_term = {user_scope: "Prefers dark roast coffee and budget hostels."}
    def fallback_recall_node(state: MessagesState):
        response = chat_model().invoke([
            SystemMessage(content="Use this long-term memory: " + long_term[user_scope]),
            *state["messages"],
        ])
        return {"messages": [response]}
    graph = StateGraph(MessagesState)
    graph.add_node("recall", fallback_recall_node)
    graph.add_edge(START, "recall")
    recalled = graph.compile().invoke({"messages": [HumanMessage(content="What coffee and lodging do I prefer?")]})
    answer = as_text(recalled["messages"][-1].content)
    print(answer)
    assert "dark" in answer.lower() and "hostel" in answer.lower()

print("memory mode:", MEMORY_MODE)
""")

nb.md("## Cleanup")
nb.code("""
inv_agent.stop_local()
if 'MEMORY_MODE' in globals() and MEMORY_MODE == "foundry":
    try:
        result = project_client().beta.memory_stores.delete_scope(name="lgws-m06-memory", scope="m06-lab-user")
        print("Deleted M6 memory scope:", getattr(result, "deleted_count", "ok"))
    except Exception as exc:
        print("Memory scope cleanup skipped:", type(exc).__name__, str(exc)[:200])
print("Kept deployed agents:", responses_agent.agent_name, inv_agent.agent_name)
""")

nb.your_turn(
    """
    Create a second conversation ID for the Responses agent and prove it does **not** know Kestrel until you reuse the original ID.
    Then create a new Invocations session and compare it with the session you reused above.
    """,
    "# Try a fresh conversation or fresh Invocations session here."
)

nb.md("""
## Recap

| Pattern | Demonstrated by | Kept? |
|---|---|---|
| Responses platform history | `lgws-m06-memory-responses` + `conversation.id` | agent kept |
| Durable graph state | `lgws-m06-memory` + `FoundryCheckpointSaver` | agent kept |
| Long-term memory | Foundry Memory store `lgws-m06-memory` or fallback | test scope deleted |

➡️ Next: **M7 · Multi-agent orchestration** — route work across specialist LangGraph agents.
""")

nb.save("docs/modules/06-agent-memory.ipynb")
