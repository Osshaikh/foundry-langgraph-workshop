"""M3 · Tools and function calling (Responses protocol)."""

from __future__ import annotations

import json
import os
from typing import Annotated, Literal

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = """You are Contoso Outdoor's order-support assistant.
Use tools for order, inventory, and shipping facts. Cite order ids, SKUs, and shipping estimates from tool results.
When the user asks for several facts, call all required tools before writing the final answer.
"""

ORDERS = {
    "CO-1001": {
        "customer": "Maya Chen",
        "status": "shipped",
        "items": ["SKU-BP-35L", "SKU-BTL-1L"],
        "destination_zip": "98101",
    },
    "CO-1002": {
        "customer": "Noah Patel",
        "status": "processing",
        "items": ["SKU-TENT-2P", "SKU-PAD-REG"],
        "destination_zip": "10001",
    },
}

INVENTORY = {
    "SKU-BP-35L": {"name": "TrailPro 35L Backpack", "available": 18, "next_restock": "2026-10-06"},
    "SKU-BTL-1L": {"name": "Summit Steel Bottle", "available": 42, "next_restock": "2026-10-03"},
    "SKU-TENT-2P": {"name": "Alpine Shelter 2P Tent", "available": 4, "next_restock": "2026-10-12"},
    "SKU-PAD-REG": {"name": "CloudRest Sleeping Pad", "available": 0, "next_restock": "2026-10-09"},
}


@tool
def lookup_order(order_id: Annotated[str, "Contoso order id such as CO-1001."]) -> str:
    """Look up a Contoso Outdoor order by order id."""
    order = ORDERS.get(order_id.upper())
    if not order:
        raise ValueError(f"Order {order_id} was not found.")
    return json.dumps({"order_id": order_id.upper(), **order})


@tool
def check_inventory(sku: Annotated[str, "Product SKU such as SKU-TENT-2P."]) -> str:
    """Check current available inventory and restock date for a SKU."""
    item = INVENTORY.get(sku.upper())
    if not item:
        raise ValueError(f"SKU {sku} was not found.")
    return json.dumps({"sku": sku.upper(), **item})


class ShippingEstimateInput(BaseModel):
    """Arguments for estimating a shipment."""

    destination_zip: str = Field(description="US destination ZIP code, e.g. 98101")
    service_level: Literal["ground", "express", "overnight"] = Field(
        default="ground", description="Shipping speed to quote."
    )


@tool(args_schema=ShippingEstimateInput)
def estimate_shipping(destination_zip: str, service_level: str = "ground") -> str:
    """Estimate Contoso Outdoor delivery time and cost by ZIP and service level."""
    table = {
        "ground": (5, 7.95),
        "express": (2, 18.50),
        "overnight": (1, 39.00),
    }
    days, cost = table[service_level]
    if destination_zip.startswith("9"):
        days += 1
    return json.dumps(
        {
            "destination_zip": destination_zip,
            "service_level": service_level,
            "estimated_days": days,
            "cost_usd": cost,
        }
    )


TOOLS = [lookup_order, check_inventory, estimate_shipping]


def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    credential = DefaultAzureCredential(process_timeout=60)
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    return ChatOpenAI(
        model=deployment,
        base_url=str(project.get_openai_client().base_url),
        api_key=get_bearer_token_provider(credential, _AZURE_AI_SCOPE),
        use_responses_api=True,
        output_version="responses/v1",
    )


def _tool_error(error: Exception) -> str:
    return f"Tool error handled by ToolNode: {error}"


_model_with_tools = _build_chat_model().bind_tools(TOOLS, parallel_tool_calls=True)


def call_model(state: MessagesState) -> dict:
    """Graph node: ask the model whether to answer or call tools."""
    response = _model_with_tools.invoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
    return {"messages": [response]}


builder = StateGraph(MessagesState)
builder.add_node("assistant", call_model)
builder.add_node("tools", ToolNode(TOOLS, handle_tool_errors=_tool_error))
builder.add_edge(START, "assistant")
builder.add_conditional_edges("assistant", tools_condition, {"tools": "tools", END: END})
builder.add_edge("tools", "assistant")

graph = builder.compile()
