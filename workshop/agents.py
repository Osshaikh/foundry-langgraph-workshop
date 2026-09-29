"""Invoke deployed hosted agents and clean them up (Python SDK)."""

from __future__ import annotations

from .config import openai_client, project_client


def ask(agent_name: str, message: str, *, previous_response_id: str | None = None,
        conversation: str | None = None, show: bool = True, **kwargs):
    """Send one Responses turn to a deployed hosted agent and return the response."""
    client = openai_client(agent_name=agent_name)
    extra = {}
    if previous_response_id:
        extra["previous_response_id"] = previous_response_id
    if conversation:
        extra["conversation"] = conversation
    response = client.responses.create(input=message, **extra, **kwargs)
    if show:
        from .azd import summarize_output

        print(f"[{agent_name}] {response.id}")
        summarize_output(response)
    return response


def list_lab_agents(prefix: str = "lgws-") -> list[str]:
    return sorted(a.name for a in project_client().agents.list() if a.name.startswith(prefix))


def delete_agent(agent_name: str) -> None:
    """Delete a hosted agent and all of its versions."""
    try:
        project_client().agents.delete(agent_name=agent_name)
        print(f"deleted agent {agent_name}")
    except Exception as exc:  # already gone
        print(f"skip {agent_name}: {exc.__class__.__name__}")
