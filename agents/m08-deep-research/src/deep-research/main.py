"""M8 · Deep research graph loaded by the Foundry LangGraph host."""

from __future__ import annotations

from dotenv import load_dotenv
from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver, ResponsesHostServer

from agent import build_agent
from research_tools import load_tools
from utils import build_chat_model

load_dotenv()


async def create_graph():
    """Async factory used by langgraph.json and the configuration-driven host."""
    tools = await load_tools()
    return build_agent(
        build_chat_model(),
        FoundryCheckpointSaver(user_isolation=True),
        tools,
    )


async def serve_with_host_class(port: int = 8088) -> None:
    """Reference pattern from foundry-samples/responses/11-deep-agents."""
    async with FoundryCheckpointSaver(user_isolation=True) as checkpointer:
        tools = await load_tools()
        agent = build_agent(build_chat_model(), checkpointer, tools)
        await ResponsesHostServer(agent).run_async(port=port)
