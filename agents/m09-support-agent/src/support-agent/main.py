"""M9-M12 reusable Contoso Outdoor support agent (Responses protocol)."""

from __future__ import annotations

import json
import os
from typing import Annotated

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

ORDERS = {
    "CO-1001": {
        "customer": "Avery Johnson",
        "item": "TrailMaster 45L Backpack",
        "status": "delivered",
        "delivery_date": "2026-09-21",
        "return_by": "2026-10-21",
        "eligible_for_return": True,
    },
    "CO-1002": {
        "customer": "Mina Patel",
        "item": "SummitShell Rain Jacket",
        "status": "in transit",
        "estimated_delivery": "2026-10-03",
        "eligible_for_return": False,
    },
    "CO-1003": {
        "customer": "Diego Rivera",
        "item": "CampCook Stove Kit",
        "status": "processing",
        "estimated_ship_date": "2026-09-30",
        "eligible_for_return": False,
    },
}

RETURN_POLICIES = {
    "backpack": "Backpacks can be returned within 30 days if clean, undamaged, and with tags attached.",
    "apparel": "Apparel can be returned within 30 days if unworn, unwashed, and with tags attached.",
    "stove": "Fuel-burning stove kits can be returned unused within 30 days; used fuel canisters are never returnable.",
    "default": "Most Contoso Outdoor items can be returned within 30 days if unused and in original packaging.",
}

SYSTEM_PROMPT = """
You are the Contoso Outdoor support agent for a Microsoft Foundry workshop.
Be concise, friendly, and safe. Use tools whenever a customer asks about order
status, returns, or escalation. Never invent order data. If a request includes
PII such as email addresses or credit card numbers, refuse and ask the customer
to remove the sensitive data before continuing.
""".strip()


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _enable_tracing_if_configured() -> None:
    if not (
        os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
        or _truthy(os.getenv("OTEL_AUTO_CONFIGURE_AZURE_MONITOR"))
    ):
        return
    try:
        from langchain_azure_ai.callbacks.tracers import enable_auto_tracing

        enable_auto_tracing(
            connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING") or None,
            project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
            credential=DefaultAzureCredential(),
            enable_content_recording=_truthy(os.getenv("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED")),
            trace_all_langgraph_nodes=_truthy(os.getenv("AZURE_TRACING_ALL_LANGGRAPH_NODES") or "true"),
            auto_configure_azure_monitor=_truthy(os.getenv("OTEL_AUTO_CONFIGURE_AZURE_MONITOR")),
            agent_id="lgws-m09-support-agent",
            provider_name="azure.ai.openai",
        )
    except Exception as exc:  # pragma: no cover - tracing must never break the agent
        print(f"Tracing disabled: {exc.__class__.__name__}: {exc}")


@tool
def lookup_order(
    order_id: Annotated[str, "Contoso order id, for example CO-1001."],
) -> str:
    """Look up Contoso Outdoor order status by order id."""
    order = ORDERS.get(order_id.strip().upper())
    if not order:
        return json.dumps({"found": False, "message": "Order not found. Ask for a valid CO-#### order id."})
    return json.dumps({"found": True, "order_id": order_id.strip().upper(), **order})


@tool
def return_policy(
    category: Annotated[str, "Product category: backpack, apparel, stove, or other."],
) -> str:
    """Return the Contoso Outdoor return policy for a product category."""
    key = category.strip().lower()
    if "pack" in key:
        key = "backpack"
    elif key in {"jacket", "shirt", "pants", "apparel", "clothing"}:
        key = "apparel"
    elif "stove" in key or "fuel" in key:
        key = "stove"
    else:
        key = "default"
    return RETURN_POLICIES[key]


@tool
def create_support_case(
    reason: Annotated[str, "Short reason for human escalation."],
    order_id: Annotated[str | None, "Optional Contoso order id."] = None,
) -> str:
    """Create a simulated support case for a human specialist."""
    suffix = abs(hash((reason, order_id))) % 10000
    return json.dumps({"case_id": f"CS-{suffix:04d}", "reason": reason, "order_id": order_id})


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


_enable_tracing_if_configured()

graph = create_agent(
    _build_chat_model(),
    tools=[lookup_order, return_policy, create_support_case],
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        PIIMiddleware("email", strategy="block", apply_to_input=True),
        PIIMiddleware("credit_card", strategy="block", apply_to_input=True),
    ],
)
