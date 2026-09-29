"""Configuration + client bootstrap shared by every lab.

Every notebook starts with::

    from workshop.config import settings, project_client, chat_model

so the environment is loaded once from ``.env`` at the repo root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO_ROOT / "agents"
AZURE_AI_SCOPE = "https://ai.azure.com/.default"

load_dotenv(REPO_ROOT / ".env", override=False)


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Environment variable {name!r} is not set. Run scripts/provision.ps1 "
            f"(or copy .env.example to .env) and restart the kernel."
        )
    return value or ""


@dataclass(frozen=True)
class Settings:
    subscription_id: str
    resource_group: str
    location: str
    account_name: str
    project_name: str
    project_endpoint: str
    project_resource_id: str
    chat_model: str
    reasoning_model: str
    embedding_model: str
    finetune_base_model: str
    search_endpoint: str
    search_connection: str
    appinsights_connection_string: str
    rai_policy_name: str
    lab_prefix: str

    @property
    def account_resource_id(self) -> str:
        return (
            f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{self.account_name}"
        )

    def agent_name(self, lab: str) -> str:
        """Unique, valid hosted-agent name for a lab, e.g. ``lgws-m02-first-agent``."""
        return f"{self.lab_prefix}-{lab}".lower()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    sub = _env("AZURE_SUBSCRIPTION_ID", required=True)
    rg = _env("AZURE_RESOURCE_GROUP", required=True)
    account = _env("FOUNDRY_ACCOUNT_NAME", required=True)
    project = _env("FOUNDRY_PROJECT_NAME", required=True)
    endpoint = _env(
        "FOUNDRY_PROJECT_ENDPOINT",
        f"https://{account}.services.ai.azure.com/api/projects/{project}",
    ).rstrip("/")
    resource_id = _env(
        "FOUNDRY_PROJECT_RESOURCE_ID",
        f"/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices"
        f"/accounts/{account}/projects/{project}",
    )
    return Settings(
        subscription_id=sub,
        resource_group=rg,
        location=_env("AZURE_LOCATION", "eastus2"),
        account_name=account,
        project_name=project,
        project_endpoint=endpoint,
        project_resource_id=resource_id,
        chat_model=_env("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini"),
        reasoning_model=_env("AZURE_AI_REASONING_DEPLOYMENT_NAME", "gpt-5.4"),
        embedding_model=_env("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large"),
        finetune_base_model=_env("AZURE_AI_FINETUNE_BASE_MODEL", "gpt-4.1-mini"),
        search_endpoint=_env("AZURE_SEARCH_ENDPOINT", ""),
        search_connection=_env("AZURE_SEARCH_CONNECTION_NAME", ""),
        appinsights_connection_string=_env("APPLICATIONINSIGHTS_CONNECTION_STRING", ""),
        rai_policy_name=_env("RAI_POLICY_NAME", "lgws-strict"),
        lab_prefix=_env("LAB_PREFIX", "lgws"),
    )


settings = get_settings()


@lru_cache(maxsize=1)
def credential():
    from azure.identity import DefaultAzureCredential

    # Azure CLI token acquisition can be slow in classroom environments after
    # tenant switches. Give developer credentials enough time while preserving
    # the normal DefaultAzureCredential chain for hosted-agent identities.
    return DefaultAzureCredential(process_timeout=60)


@lru_cache(maxsize=1)
def project_client():
    """The Foundry project client (``azure.ai.projects.AIProjectClient``)."""
    from azure.ai.projects import AIProjectClient

    return AIProjectClient(endpoint=settings.project_endpoint, credential=credential())


def openai_client(agent_name: str | None = None, **kwargs):
    """OpenAI client bound to the project, or to a hosted agent's endpoint.

    Extra keyword arguments are forwarded to ``AIProjectClient.get_openai_client``.
    Labs use this for account-level OpenAI-compatible endpoints, such as
    ``https://<account>.services.ai.azure.com/openai/v1`` for embeddings.
    """
    if agent_name:
        return project_client().get_openai_client(agent_name=agent_name, **kwargs)
    return project_client().get_openai_client(**kwargs)


def chat_model(deployment: str | None = None, **kwargs):
    """LangChain ``ChatOpenAI`` wired to the Foundry project's Responses endpoint.

    This is the exact factory the hosted agents use in their ``main.py``.
    """
    from azure.identity import get_bearer_token_provider
    from langchain_openai import ChatOpenAI

    kwargs.setdefault("use_responses_api", True)
    kwargs.setdefault("output_version", "responses/v1")
    return ChatOpenAI(
        model=deployment or settings.chat_model,
        base_url=str(openai_client().base_url),
        api_key=get_bearer_token_provider(credential(), AZURE_AI_SCOPE),
        **kwargs,
    )
