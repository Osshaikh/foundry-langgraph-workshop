"""M6 · Responses agent with platform-managed conversation history."""

from __future__ import annotations

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"
SYSTEM_PROMPT = """
You are the M6 short-term memory demo. You do not use a LangGraph checkpointer.
When the platform provides prior conversation turns, use them to answer follow-up questions.
Keep answers concise.
""".strip()


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


graph = create_agent(_build_chat_model(), tools=[], system_prompt=SYSTEM_PROMPT)
