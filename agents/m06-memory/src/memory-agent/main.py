"""M6 · Durable graph state over the Invocations protocol."""

from __future__ import annotations

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = """
You are the M6 memory lab assistant. Keep replies to two short sentences.
If the user shares a name, preference, or project detail, acknowledge it.
On follow-up turns, use the conversation state that LangGraph checkpointing gives you.
""".strip()


@tool
def memory_marker(value: str) -> str:
    """Echo a short fact so the lab can see when tools are available."""
    return f"noted:{value}"


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


graph = create_agent(
    _build_chat_model(),
    tools=[memory_marker],
    system_prompt=SYSTEM_PROMPT,
    checkpointer=FoundryCheckpointSaver(user_isolation=True),
)
