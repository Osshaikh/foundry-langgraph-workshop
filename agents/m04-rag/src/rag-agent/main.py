"""M4 · Grounding/RAG with Azure AI Search (Responses protocol)."""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"

SYSTEM_PROMPT = """You are Contoso Outdoor's grounded product and policy assistant.
Always use search_knowledge_base for Contoso facts. Answer only from returned sources.
Cite source doc ids inline in square brackets, for example [policy-returns]. If the sources do not answer, say what is missing.
"""


def _credential() -> DefaultAzureCredential:
    return DefaultAzureCredential(process_timeout=60)


def _project() -> AIProjectClient:
    return AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/"), credential=_credential())


def _build_chat_model() -> ChatOpenAI:
    credential = _credential()
    project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/"), credential=credential)
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    return ChatOpenAI(
        model=deployment,
        base_url=str(project.get_openai_client().base_url),
        api_key=get_bearer_token_provider(credential, _AZURE_AI_SCOPE),
        use_responses_api=True,
        output_version="responses/v1",
    )


def _embed(text: str) -> list[float]:
    deployment = os.environ.get("AZURE_AI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    account_openai_base = project_endpoint.split("/api/projects/", 1)[0] + "/openai/v1/"
    try:
        return (
            _project()
            .get_openai_client(base_url=account_openai_base)
            .embeddings.create(model=deployment, input=text)
            .data[0]
            .embedding
        )
    except Exception as exc:
        logger.warning("Embedding call failed; falling back to keyword-first hybrid search: %s", exc)
        return [0.0] * 3072


@tool
def search_knowledge_base(
    query: Annotated[str, "Natural-language product or policy question."],
    top: Annotated[int, "Maximum number of sources to retrieve."] = 4,
) -> str:
    """Hybrid-search the Contoso Outdoor knowledge base and return cited source snippets."""
    credential = _credential()
    client = SearchClient(
        endpoint=os.environ["SEARCH_ENDPOINT"].rstrip("/"),
        index_name=os.environ.get("SEARCH_INDEX", "lgws-m04-contoso"),
        credential=credential,
    )
    vector = VectorizedQuery(vector=_embed(query), k_nearest_neighbors=top, fields="content_vector")
    results = client.search(
        search_text=query,
        vector_queries=[vector],
        query_type="semantic",
        semantic_configuration_name="contoso-semantic",
        select=["doc_id", "title", "category", "content"],
        top=top,
    )
    docs = []
    for result in results:
        docs.append(
            {
                "doc_id": result["doc_id"],
                "title": result["title"],
                "category": result["category"],
                "content": result["content"],
            }
        )
    return json.dumps(docs, ensure_ascii=False)


graph = create_agent(_build_chat_model(), tools=[search_knowledge_base], system_prompt=SYSTEM_PROMPT)
