"""Tools loaded from the M8 Foundry toolbox."""

from __future__ import annotations

import os

from langchain_azure_ai.tools import AzureAIProjectToolbox
from langchain_core.tools import BaseTool
from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """Fallback web search result used only if the Foundry Toolbox is unavailable."""
    return (
        "Foundry hosted agents documentation: "
        "https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents\n"
        "LangGraph documentation: https://langchain-ai.github.io/langgraph/\n"
        f"Query: {query}"
    )


async def load_tools() -> list[BaseTool]:
    toolbox = AzureAIProjectToolbox(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        toolbox_name=os.environ["TOOLBOX_NAME"],
    )
    try:
        tools = await toolbox.get_tools()
        return tools or [web_search]
    except Exception:
        return [web_search]
