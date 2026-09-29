"""M2 · Your first hosted LangGraph agent (Responses protocol).

The module exports ``graph`` — a compiled LangGraph agent. The Foundry hosting
adapter (``python -m langchain_azure_ai.agents.hosting.run``) reads
``langgraph.json``, imports ``graph`` and serves it on ``/responses``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Annotated

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = (
    "You are Contoso's friendly workshop assistant. Keep answers short and "
    "use your tools for anything involving time or arithmetic."
)


@tool
def get_current_time() -> str:
    """Return the current UTC date and time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
def calculator(
    expression: Annotated[str, "A math expression to evaluate, e.g. '42 * 17'."],
) -> str:
    """Evaluate a simple math expression and return the result."""
    try:
        return str(eval(expression, {"__builtins__": {}}))  # noqa: S307 - demo only
    except Exception as exc:  # pragma: no cover - surfaced to the model
        return f"Error: {exc}"


def _build_chat_model() -> ChatOpenAI:
    # FOUNDRY_PROJECT_ENDPOINT is injected by Foundry when hosted; from .env locally.
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


graph = create_agent(
    _build_chat_model(),
    tools=[get_current_time, calculator],
    system_prompt=SYSTEM_PROMPT,
)
