"""M7 · Multi-agent orchestration patterns in one LangGraph hosted agent."""

from __future__ import annotations

import operator
import os
from typing import Annotated, Literal

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"


class RouteDecision(BaseModel):
    """Structured router decision."""

    route: Literal["sequential", "orders_agent", "product_expert", "parallel"] = Field(
        description="Best next workflow for the user's request."
    )
    reason: str


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    draft: str
    route: str
    reason: str
    routes_taken: Annotated[list[str], operator.add]
    parallel_notes: Annotated[list[str], operator.add]


def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    return ChatOpenAI(
        model=deployment,
        base_url=str(project.get_openai_client().base_url),
        api_key=get_bearer_token_provider(credential, _AZURE_AI_SCOPE),
        use_responses_api=True,
        output_version="responses/v1",
    )


def _text(state: State) -> str:
    return str(state["messages"][-1].content)


def create_graph():
    model = _build_chat_model()
    orders_agent = create_agent(
        model,
        tools=[],
        system_prompt="You are an orders specialist. Help with order status, returns, and shipping. Keep it brief.",
    )
    product_expert = create_agent(
        model,
        tools=[],
        system_prompt="You are a product expert for outdoor gear. Recommend products and explain tradeoffs briefly.",
    )

    async def route_question(state: State) -> dict:
        question = _text(state)
        lower = question.lower()
        if "slogan" in lower or "campaign" in lower:
            decision = RouteDecision(route="sequential", reason="marketing copy needs writer/legal/formatter")
        elif "compare" in lower or "parallel" in lower:
            decision = RouteDecision(route="parallel", reason="independent specialists can work in parallel")
        else:
            structured = model.with_structured_output(RouteDecision)
            try:
                decision = await structured.ainvoke(
                    [
                        SystemMessage(
                            "Route customer questions. Use orders_agent for order, shipping, return, invoice, tracking. "
                            "Use product_expert for gear, sizing, materials, recommendations. Use sequential for slogans/campaigns. "
                            "Use parallel for explicit comparisons."
                        ),
                        HumanMessage(question),
                    ]
                )
            except Exception:
                decision = RouteDecision(route="product_expert", reason="fallback route")
            if any(word in lower for word in ["order", "shipping", "return", "tracking", "invoice"]):
                decision.route = "orders_agent"
            elif any(word in lower for word in ["boot", "jacket", "tent", "backpack", "product", "gear", "size"]):
                decision.route = "product_expert"
        return {"route": decision.route, "reason": decision.reason, "routes_taken": ["router:" + decision.route]}

    def pick_route(state: State) -> str:
        return state["route"]

    async def writer(state: State) -> dict:
        result = await model.ainvoke([SystemMessage("Write one legally safe draft slogan."), HumanMessage(_text(state))])
        return {"draft": result.content, "routes_taken": ["writer"]}

    async def legal_reviewer(state: State) -> dict:
        result = await model.ainvoke([SystemMessage("Review this slogan for legal/compliance risk. Revise if needed."), HumanMessage(state["draft"])])
        return {"draft": result.content, "routes_taken": ["legal_reviewer"]}

    async def formatter(state: State) -> dict:
        result = await model.ainvoke([SystemMessage("Format the slogan as a polished terminal-friendly answer."), HumanMessage(state["draft"])])
        route_line = "ROUTES_TAKEN: " + " -> ".join([*state.get("routes_taken", []), "formatter"])
        return {"messages": [AIMessage(content=f"{result.content}\n\n{route_line}")], "routes_taken": ["formatter"]}

    async def orders_node(state: State) -> dict:
        result = await orders_agent.ainvoke({"messages": [HumanMessage(_text(state))]})
        return {"draft": result["messages"][-1].content, "routes_taken": ["orders_agent"]}

    async def product_node(state: State) -> dict:
        result = await product_expert.ainvoke({"messages": [HumanMessage(_text(state))]})
        return {"draft": result["messages"][-1].content, "routes_taken": ["product_expert"]}

    async def synthesizer(state: State) -> dict:
        notes = "\n".join(state.get("parallel_notes", [])) or state.get("draft", "")
        result = await model.ainvoke([
            SystemMessage("Synthesize the specialist result into a concise final customer answer."),
            HumanMessage(notes),
        ])
        route_line = "ROUTES_TAKEN: " + " -> ".join([*state.get("routes_taken", []), "synthesizer"])
        return {"messages": [AIMessage(content=f"{result.content}\n\n{route_line}")], "routes_taken": ["synthesizer"]}

    async def price_research(state: State) -> dict:
        return {"parallel_notes": ["pricing analyst: choose the lower total cost if durability is similar."], "routes_taken": ["price_research"]}

    async def durability_research(state: State) -> dict:
        return {"parallel_notes": ["durability analyst: prioritize weatherproof materials and repairability."], "routes_taken": ["durability_research"]}

    async def fit_research(state: State) -> dict:
        return {"parallel_notes": ["fit analyst: ask for foot width, pack weight, and trip length before final sizing."], "routes_taken": ["fit_research"]}

    builder = StateGraph(State)
    builder.add_node("router", route_question)
    builder.add_node("writer", writer)
    builder.add_node("legal_reviewer", legal_reviewer)
    builder.add_node("formatter", formatter)
    builder.add_node("orders_agent", orders_node)
    builder.add_node("product_expert", product_node)
    builder.add_node("synthesizer", synthesizer)
    builder.add_node("fanout", lambda state: {"routes_taken": ["fanout"]})
    builder.add_node("price_research", price_research)
    builder.add_node("durability_research", durability_research)
    builder.add_node("fit_research", fit_research)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        pick_route,
        {
            "sequential": "writer",
            "orders_agent": "orders_agent",
            "product_expert": "product_expert",
            "parallel": "fanout",
        },
    )
    builder.add_edge("writer", "legal_reviewer")
    builder.add_edge("legal_reviewer", "formatter")
    builder.add_edge("formatter", END)
    builder.add_edge("orders_agent", "synthesizer")
    builder.add_edge("product_expert", "synthesizer")
    builder.add_edge("fanout", "price_research")
    builder.add_edge("fanout", "durability_research")
    builder.add_edge("fanout", "fit_research")
    builder.add_edge("price_research", "synthesizer")
    builder.add_edge("durability_research", "synthesizer")
    builder.add_edge("fit_research", "synthesizer")
    builder.add_edge("synthesizer", END)
    return builder.compile()


graph = create_graph()
