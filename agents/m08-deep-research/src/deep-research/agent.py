"""DeepAgents assembly for M8."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from deepagents import SubAgent, create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver

from prompts import RESEARCH_WORKFLOW_INSTRUCTIONS, RESEARCHER_INSTRUCTIONS


def build_agent(model: ChatOpenAI, checkpointer: BaseCheckpointSaver[Any], tools: list[BaseTool]):
    current_date = datetime.now().strftime("%Y-%m-%d")
    research_sub_agent: SubAgent = {
        "name": "research-agent",
        "description": "Research one focused question using web search and return cited findings.",
        "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
        "tools": tools,
    }
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=RESEARCH_WORKFLOW_INSTRUCTIONS,
        subagents=[research_sub_agent],
        middleware=[TodoListMiddleware()],
        checkpointer=checkpointer,
        name="m8-deep-research-agent",
    )
