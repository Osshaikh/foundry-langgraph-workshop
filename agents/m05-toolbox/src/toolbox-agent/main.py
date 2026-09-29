"""M5 · Foundry Toolbox tools loaded by a LangGraph hosted agent."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_azure_ai.tools import AzureAIProjectToolbox

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = """You are a research assistant with Foundry Toolbox tools.
Use Microsoft Learn tools for Microsoft documentation questions. Use web search for current general web questions.
When tool results include URLs or titles, include a short Sources section. Do not invent citations.
"""


def _build_chat_model() -> ChatOpenAI:
    credential = DefaultAzureCredential(process_timeout=60)
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    return ChatOpenAI(
        model=deployment,
        base_url=str(project.get_openai_client().base_url),
        api_key=get_bearer_token_provider(credential, _AZURE_AI_SCOPE),
        use_responses_api=True,
        output_version="responses/v1",
    )


_CONSENT_ERROR_CODE = -32006
_CONSENT_HOST = "consent.azure-apim.net"


def _contains_consent_host(text: str) -> bool:
    for token in re.findall(r"https?://[^\s'\"<>]+", text):
        host = urlparse(token).hostname
        if host and (host == _CONSENT_HOST or host.endswith(f".{_CONSENT_HOST}")):
            return True
    return False


def _extract_consent_url(text: str) -> str | None:
    for candidate in re.findall(r"https?://[^\s)>\]\"']+", text):
        if urlparse(candidate).hostname == _CONSENT_HOST:
            return candidate
    return None


def _is_consent_error(exc: BaseException) -> bool:
    error_data = getattr(exc, "error", None)
    if error_data is not None and getattr(error_data, "code", None) == _CONSENT_ERROR_CODE:
        return True
    if _contains_consent_host(str(exc)):
        return True
    sub_exceptions = getattr(exc, "exceptions", None)
    if sub_exceptions:
        return any(_is_consent_error(sub) for sub in sub_exceptions)
    return False


def _consent_url_from_exception(exc: BaseException) -> str:
    error_data = getattr(exc, "error", None)
    if error_data is not None and getattr(error_data, "code", None) == _CONSENT_ERROR_CODE:
        message = getattr(error_data, "message", str(exc))
        return _extract_consent_url(message) or message
    url = _extract_consent_url(str(exc))
    if url:
        return url
    sub_exceptions = getattr(exc, "exceptions", None)
    if sub_exceptions:
        for sub in sub_exceptions:
            nested = _consent_url_from_exception(sub)
            if nested:
                return nested
    return str(exc)


def _consent_aware_error_handler(error: Exception) -> str:
    if _is_consent_error(error):
        url = _consent_url_from_exception(error)
        return "OAuth consent required. Open this URL in a browser, then retry: " + url
    return f"Tool error: {error}"


def _sanitize_tool_schema(tool: BaseTool) -> None:
    schema: Any = tool.args_schema if isinstance(tool.args_schema, dict) else None
    if schema is None:
        return
    if schema.get("type") == "object" and "properties" not in schema:
        schema["properties"] = {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    if required and not props:
        schema["properties"] = {field_name: {"type": "string"} for field_name in required}


async def _load_toolbox_tools() -> list[BaseTool]:
    toolbox = AzureAIProjectToolbox(toolbox_name=os.environ["TOOLBOX_NAME"])
    tools = await toolbox.get_tools()
    for tool in tools:
        _sanitize_tool_schema(tool)
        tool.handle_tool_error = _consent_aware_error_handler
        logger.info("Loaded toolbox tool: %s", tool.name)
    return tools


async def create_graph():
    """Factory used by langgraph.json so toolbox tools are loaded during startup."""
    tools = await _load_toolbox_tools()
    return create_agent(_build_chat_model(), tools=tools, system_prompt=SYSTEM_PROMPT)
