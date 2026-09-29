"""M13 · Human-in-the-loop refund and discount proposal agent.

The graph drafts a Contoso Outdoor customer-care proposal, pauses with
``interrupt()``, and resumes on approve, revise, or reject decisions from the
Responses protocol host. Checkpoints are scoped by the conversation id.
"""

from __future__ import annotations

import os
from typing import Annotated

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

_DRAFT_PROMPT = """You are a Contoso Outdoor customer-care escalation specialist.
Draft a manager-review proposal for a refund, replacement, loyalty discount, or
combination. Use a concise business tone and include:
- customer situation
- proposed action and dollar/percent amounts when available
- policy rationale
- customer-facing response text
- manager approval checklist
If revision feedback is provided, incorporate it and produce a new draft.
Only the final approved draft should be sent as an assistant message."""


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    draft: str
    revision_history: list[dict[str, str]]


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


def _build_graph(model: ChatOpenAI):
    async def draft(state: State) -> dict[str, str]:
        request = state["messages"][0].content
        history = state.get("revision_history", [])
        msgs: list[BaseMessage] = [
            SystemMessage(content=_DRAFT_PROMPT),
            HumanMessage(content=f"Manager approval request:\n{request}"),
        ]
        for revision in history:
            msgs.append(AIMessage(content=revision["draft"]))
            msgs.append(HumanMessage(content=f"Manager revision feedback: {revision['feedback']}"))
        result = await model.ainvoke(msgs)
        return {"draft": str(result.content)}

    def await_approval(state: State) -> Command:
        resume = interrupt({"draft": state["draft"]})
        if isinstance(resume, dict) and resume.get("feedback"):
            next_history = state.get("revision_history", []) + [
                {"draft": state["draft"], "feedback": str(resume["feedback"])}
            ]
            return Command(update={"revision_history": next_history}, goto="draft")
        return Command(update={"messages": [AIMessage(content=state["draft"])]}, goto=END)

    builder = StateGraph(State)
    builder.add_node("draft", draft)
    builder.add_node("await_approval", await_approval)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "await_approval")
    return builder.compile(checkpointer=FoundryCheckpointSaver(user_isolation=True))


def create_graph():
    return _build_graph(_build_chat_model())
