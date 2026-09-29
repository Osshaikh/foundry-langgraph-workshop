"""M15 · Capstone: Contoso Outdoor Concierge (Responses protocol).

One hosted LangGraph agent that combines what the workshop built:

* Grounding (M4)        search_knowledge_base over the Azure AI Search index
* Toolbox / MCP (M5)    web search + Microsoft Learn MCP loaded from a Foundry Toolbox (optional)
* Tools (M3)            lookup_order / issue_refund local tools
* Guardrails (M11)      an input-screening node that refuses payment-card numbers
* Human-in-the-loop (M13)  issue_refund pauses for approval via interrupt()
* Memory (M6)           FoundryCheckpointSaver keeps graph state per conversation
* Tracing (M10)         enable_auto_tracing() emits OpenTelemetry GenAI spans
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Annotated, Any, Literal

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver

load_dotenv()
logger = logging.getLogger("capstone")

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"
SENSITIVE_TOOLS = {"issue_refund"}

SYSTEM_PROMPT = """You are the Contoso Outdoor Concierge.
- For Contoso products and policies ALWAYS call search_knowledge_base and cite doc ids in square brackets, e.g. [policy-returns].
- For order questions call lookup_order. Never invent order data.
- To give money back call issue_refund. A manager must approve it; if it is rejected, explain that politely.
- Use web or Microsoft Learn tools only for questions that are not about Contoso.
Keep answers short and friendly."""

# ── Demo order data (replace with your order system) ──────────────────
_ORDERS = {
    "CO-1001": {"customer": "Priya", "item": "Alpine Shelter 2P Tent", "total": 240.0, "status": "delivered",
                "delivered": "2026-09-10"},
    "CO-1002": {"customer": "Diego", "item": "TrailPro 35L Backpack", "total": 159.0, "status": "in transit",
                "delivered": None},
    "CO-1003": {"customer": "Mei", "item": "TrailLite Rain Jacket", "total": 89.0, "status": "delivered",
                "delivered": "2026-08-02"},
}

_CARD_NUMBER = re.compile(r"\b(?:\d[ -]?){13,16}\b")


# ── Model ──────────────────────────────────────────────────────────────
def _credential() -> DefaultAzureCredential:
    return DefaultAzureCredential(process_timeout=60)


def _build_chat_model() -> ChatOpenAI:
    credential = _credential()
    project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/"), credential=credential)
    return ChatOpenAI(
        model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini"),
        base_url=str(project.get_openai_client().base_url),
        api_key=get_bearer_token_provider(credential, _AZURE_AI_SCOPE),
        use_responses_api=True,
        output_version="responses/v1",
    )


# ── Tools ──────────────────────────────────────────────────────────────
def _embed(text: str) -> list[float]:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    account_openai_base = endpoint.split("/api/projects/", 1)[0] + "/openai/v1/"
    project = AIProjectClient(endpoint=endpoint, credential=_credential())
    client = project.get_openai_client(base_url=account_openai_base)
    deployment = os.environ.get("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
    return client.embeddings.create(model=deployment, input=text).data[0].embedding


@tool
def search_knowledge_base(
    query: Annotated[str, "Natural-language product or policy question."],
    top: Annotated[int, "Maximum number of sources to retrieve."] = 4,
) -> str:
    """Hybrid-search the Contoso Outdoor knowledge base and return source snippets with doc ids."""
    from azure.search.documents import SearchClient
    from azure.search.documents.models import VectorizedQuery

    client = SearchClient(
        endpoint=os.environ["SEARCH_ENDPOINT"].rstrip("/"),
        index_name=os.environ.get("SEARCH_INDEX", "lgws-m04-contoso"),
        credential=_credential(),
    )
    results = client.search(
        search_text=query,
        vector_queries=[VectorizedQuery(vector=_embed(query), k_nearest_neighbors=top, fields="content_vector")],
        query_type="semantic",
        semantic_configuration_name="contoso-semantic",
        select=["doc_id", "title", "content"],
        top=top,
    )
    return json.dumps([{"doc_id": r["doc_id"], "title": r["title"], "content": r["content"]} for r in results])


@tool
def lookup_order(order_id: Annotated[str, "Order id such as CO-1001."]) -> str:
    """Look up a Contoso Outdoor order by id."""
    order = _ORDERS.get(order_id.strip().upper())
    return json.dumps({"order_id": order_id.upper(), **order}) if order else f"No order found with id {order_id}."


@tool
def issue_refund(
    order_id: Annotated[str, "Order id to refund."],
    amount: Annotated[float, "Refund amount in USD."],
    reason: Annotated[str, "Short reason for the refund."],
) -> str:
    """Issue a refund for an order. Requires manager approval (the graph pauses before this runs)."""
    order = _ORDERS.get(order_id.strip().upper())
    if not order:
        return f"Refund failed: order {order_id} not found."
    if amount > order["total"]:
        return f"Refund failed: {amount:.2f} exceeds the order total {order['total']:.2f}."
    return json.dumps({"refund_id": f"RF-{order_id.upper()[-4:]}-{int(amount * 100)}", "order_id": order_id.upper(),
                       "amount": amount, "reason": reason, "status": "issued"})


def _sanitize_tool_schema(t: BaseTool) -> None:
    # Some MCP servers publish object schemas without "properties"; OpenAI rejects those.
    schema: Any = t.args_schema if isinstance(t.args_schema, dict) else None
    if schema is not None and schema.get("type") == "object" and "properties" not in schema:
        schema["properties"] = {}


async def _load_toolbox_tools() -> list[BaseTool]:
    name = os.environ.get("TOOLBOX_NAME", "").strip()
    if not name:
        return []
    from langchain_azure_ai.tools import AzureAIProjectToolbox

    try:
        tools = await AzureAIProjectToolbox(toolbox_name=name).get_tools()
    except Exception as exc:  # keep the concierge working even if the toolbox is unavailable
        logger.warning("Toolbox %s unavailable: %s", name, exc)
        return []
    for t in tools:
        _sanitize_tool_schema(t)
        t.handle_tool_error = lambda err: f"Tool error: {err}"
    logger.info("Loaded %d toolbox tool(s): %s", len(tools), [t.name for t in tools])
    return tools


# ── Graph ──────────────────────────────────────────────────────────────
def _last_user_text(state: MessagesState) -> str:
    for message in reversed(state["messages"]):
        if message.type == "human":
            return message.text if hasattr(message, "text") else str(message.content)
    return ""


def _build_graph(model: ChatOpenAI, tools: list[BaseTool]):
    model_with_tools = model.bind_tools(tools)
    tool_node = ToolNode(tools, handle_tool_errors=True)

    def guard(state: MessagesState) -> Command[Literal["agent", "__end__"]]:
        """In-graph guardrail: never let payment card numbers reach the model or the logs."""
        if _CARD_NUMBER.search(_last_user_text(state)):
            refusal = AIMessage(content="For your security, please don't share card numbers here. "
                                        "I can help with your order id instead (for example CO-1001).")
            return Command(update={"messages": [refusal]}, goto=END)
        return Command(goto="agent")

    async def agent(state: MessagesState) -> dict:
        reply = await model_with_tools.ainvoke([SystemMessage(SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [reply]}

    def route(state: MessagesState) -> Literal["approve", "tools", "__end__"]:
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None) or []
        if not calls:
            return END
        return "approve" if any(c["name"] in SENSITIVE_TOOLS for c in calls) else "tools"

    def approve(state: MessagesState) -> Command[Literal["tools", "agent"]]:
        """Pause for a manager decision before any sensitive tool runs."""
        last = state["messages"][-1]
        pending = [c for c in last.tool_calls if c["name"] in SENSITIVE_TOOLS]
        decision = interrupt({"action": "approve_refund", "tool_calls": [
            {"name": c["name"], "args": c["args"]} for c in pending]})
        if isinstance(decision, dict) and decision.get("feedback"):
            # Manager declined with feedback: answer every pending call so the model can respond.
            declined = [ToolMessage(content=f"Refund NOT approved by manager: {decision['feedback']}",
                                    tool_call_id=c["id"]) for c in last.tool_calls]
            return Command(update={"messages": declined}, goto="agent")
        return Command(goto="tools")

    builder = StateGraph(MessagesState)
    builder.add_node("guard", guard)
    builder.add_node("agent", agent)
    builder.add_node("approve", approve)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "guard")
    builder.add_conditional_edges("agent", route, ["approve", "tools", END])
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=FoundryCheckpointSaver(user_isolation=True))


async def create_graph():
    """Factory loaded by the hosting entrypoint (see langgraph.json)."""
    if os.environ.get("ENABLE_TRACING", "true").lower() == "true":
        from langchain_azure_ai.callbacks.tracers import enable_auto_tracing

        enable_auto_tracing()
    tools: list[BaseTool] = [search_knowledge_base, lookup_order, issue_refund]
    tools += await _load_toolbox_tools()
    return _build_graph(_build_chat_model(), tools)
