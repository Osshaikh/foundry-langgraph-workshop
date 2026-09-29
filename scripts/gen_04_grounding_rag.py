"""Generate docs/modules/04-grounding-rag.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M4 · Grounding / RAG with Azure AI Search",
    "Index a small Contoso Outdoor knowledge base, query it with hybrid search, then ground a hosted LangGraph agent on it.",
    minutes=65,
)

nb.md("""
## Objectives

- Create a small inline Contoso Outdoor product and policy knowledge base.
- Build an Azure AI Search index named `lgws-m04-contoso` with a 3072-dimension vector field and semantic configuration.
- Embed documents with the project's `text-embedding-3-large` deployment and run a direct hybrid query.
- Host a LangGraph agent with a `search_knowledge_base` tool that cites source doc ids.
- Grant the hosted agent identity **Search Index Data Reader** on the search service (and an account OpenAI role for embedding calls) and retry until RBAC propagates.

## RAG flow

```
question → embedding → Azure AI Search hybrid query → cited snippets → model answer with [doc-id] citations
```
""")

nb.bootstrap()

nb.md("## 1. Knowledge base")

nb.code(r'''
INDEX_NAME = "lgws-m04-contoso"
DOCS = [
    {"doc_id": "prod-traillite-jacket", "title": "TrailLite Rain Jacket", "category": "product", "content": "TrailLite Rain Jacket is a packable waterproof shell for day hikes. It weighs 320 grams and uses sealed seams."},
    {"doc_id": "prod-alpine-tent", "title": "Alpine Shelter 2P Tent", "category": "product", "content": "Alpine Shelter 2P Tent fits two hikers, includes a full rainfly, and is recommended for shoulder-season backpacking."},
    {"doc_id": "prod-cloudrest-pad", "title": "CloudRest Sleeping Pad", "category": "product", "content": "CloudRest Sleeping Pad has an R-value of 4.2 and pairs well with the Alpine Shelter tent for cool nights."},
    {"doc_id": "prod-trailpro-pack", "title": "TrailPro 35L Backpack", "category": "product", "content": "TrailPro 35L Backpack supports weekend trips, has a 12 kg comfortable carry rating, and includes a rain cover."},
    {"doc_id": "prod-summit-bottle", "title": "Summit Steel Bottle", "category": "product", "content": "Summit Steel Bottle holds 1 liter, keeps drinks cold for 24 hours, and fits TrailPro side pockets."},
    {"doc_id": "prod-solar-lantern", "title": "Solstice Solar Lantern", "category": "product", "content": "Solstice Solar Lantern provides 300 lumens, charges by USB-C or solar, and is splash resistant."},
    {"doc_id": "policy-returns", "title": "Returns and exchanges", "category": "policy", "content": "Contoso Outdoor accepts returns within 30 days of delivery. TrailLite apparel can be exchanged for another size within 45 days if unworn."},
    {"doc_id": "policy-warranty", "title": "Product warranty", "category": "policy", "content": "Contoso Outdoor warranties tents and backpacks for two years against manufacturing defects. Normal wear is not covered."},
    {"doc_id": "policy-shipping", "title": "Shipping options", "category": "policy", "content": "Ground shipping usually arrives in 5 to 7 business days. Express arrives in 2 business days. Overnight is available for most US ZIP codes."},
    {"doc_id": "policy-price-match", "title": "Price match policy", "category": "policy", "content": "Contoso Outdoor will match authorized retailer prices within 14 days of purchase when the item is in stock and identical."},
    {"doc_id": "guide-rain-hike", "title": "Rainy day hike kit", "category": "guide", "content": "For rainy day hikes, combine TrailLite Rain Jacket, TrailPro 35L Backpack, dry bags, and a warm layer."},
    {"doc_id": "guide-two-night", "title": "Two-night backpacking kit", "category": "guide", "content": "A two-night kit starts with Alpine Shelter 2P Tent, CloudRest Sleeping Pad, TrailPro 35L Backpack, stove, water treatment, and a headlamp."},
    {"doc_id": "guide-family-camp", "title": "Family campground checklist", "category": "guide", "content": "Family campground trips benefit from Solstice Solar Lanterns, extra water bottles, sleeping pads, and a weatherproof tent footprint."},
    {"doc_id": "fit-jackets", "title": "Jacket fit notes", "category": "fit", "content": "TrailLite Rain Jacket runs true to size with room for a fleece layer. Size up only if wearing a thick insulated jacket underneath."},
    {"doc_id": "care-waterproof", "title": "Waterproof gear care", "category": "care", "content": "Wash waterproof shells with technical cleaner, rinse twice, and tumble dry low to reactivate the durable water repellent finish."},
    {"doc_id": "safety-weather", "title": "Weather safety", "category": "safety", "content": "Check forecast changes before trips, pack insulation even in summer, and avoid exposed ridges during lightning."},
    {"doc_id": "stores-service", "title": "In-store services", "category": "service", "content": "Contoso stores can fit backpacks, demonstrate tent setup, and process online returns with the order confirmation email."},
    {"doc_id": "loyalty-summit", "title": "Summit Club loyalty", "category": "service", "content": "Summit Club members earn 5 points per dollar and receive free ground shipping on orders over $50."},
]
print(f"{len(DOCS)} docs")
''')

nb.md("## 2. Create the Azure AI Search index and upload vectors")

nb.code(r'''
import time
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from workshop.config import credential, openai_client

endpoint = settings.search_endpoint
index_client = SearchIndexClient(endpoint=endpoint, credential=credential())
try:
    index_client.delete_index(INDEX_NAME)
    time.sleep(5)
    print("Deleted previous index copy")
except ResourceNotFoundError:
    pass

index = SearchIndex(
    name=INDEX_NAME,
    fields=[
        SimpleField(name="doc_id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SearchableField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="vector-profile",
        ),
    ],
    vector_search=VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw")],
    ),
    semantic_search=SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="contoso-semantic",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="category")],
                ),
            )
        ]
    ),
)
index_client.create_index(index)

account_openai_base = f"https://{settings.account_name}.services.ai.azure.com/openai/v1/"
oai = openai_client(base_url=account_openai_base)
uploads = []
for doc in DOCS:
    text = f"{doc['title']}\n{doc['category']}\n{doc['content']}"
    vector = oai.embeddings.create(model=settings.embedding_model, input=text).data[0].embedding
    uploads.append({**doc, "content_vector": vector})

search_client = SearchClient(endpoint=endpoint, index_name=INDEX_NAME, credential=credential())
result = search_client.upload_documents(uploads)
assert all(r.succeeded for r in result)
print(f"Uploaded {len(uploads)} documents to {INDEX_NAME}")
''')

nb.md("## 3. Query the index directly")

nb.code(r'''
from azure.search.documents.models import VectorizedQuery

query = "How long can I return a TrailLite jacket?"
query_vector = openai_client(base_url=account_openai_base).embeddings.create(model=settings.embedding_model, input=query).data[0].embedding
results = search_client.search(
    search_text=query,
    vector_queries=[VectorizedQuery(vector=query_vector, k_nearest_neighbors=5, fields="content_vector")],
    query_type="semantic",
    semantic_configuration_name="contoso-semantic",
    select=["doc_id", "title", "category", "content"],
    top=5,
)
rows = list(results)
for row in rows:
    print(row["doc_id"], "-", row["title"])
assert any(row["doc_id"] == "policy-returns" for row in rows)
''')

nb.md("## 4. Read the hosted RAG agent")

nb.code(r'''
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m04-rag" / "src" / "rag-agent"
show_file(src / "main.py")
show_file(AGENTS_DIR / "m04-rag" / "azure.yaml")
''')

nb.md("""
**Preview note:** in this project the project-scoped `/openai/v1/embeddings` route returns `404`, while the same
deployment works through the account OpenAI-compatible endpoint. The notebook still uses `openai_client(...)`,
but passes the account-level `base_url` for embedding calls. The hosted tool tries that embedding call and falls
back to keyword-first hybrid search if the preview hosted identity is denied on the account endpoint; the index
itself is still built with real `text-embedding-3-large` vectors, and the direct hybrid query above proves the vector path.
""")

nb.md("## 5. Run locally")

nb.code(r'''
from workshop.azd import init_agent, summarize_output

agent = init_agent(
    "m04-rag",
    port=8104,
    env={
        "SEARCH_ENDPOINT": settings.search_endpoint,
        "SEARCH_INDEX": INDEX_NAME,
        "AZURE_AI_EMBEDDING_DEPLOYMENT_NAME": settings.embedding_model,
    },
)
agent.run_local()
''')

nb.code(r'''
local = agent.local_responses("What is the return window for TrailLite apparel? Cite doc ids.")
summarize_output(local)
assert "policy-returns" in str(local["output"]).lower()
agent.stop_local()
''')

nb.md("## 6. Deploy and grant Search Index Data Reader")

nb.code(r'''
from azure.core.exceptions import HttpResponseError
from workshop.config import project_client

try:
    project_client().agents.get(agent_name=agent.agent_name)
    print(f"Existing deployed agent {agent.agent_name} found; reusing it for this validation run.")
except HttpResponseError:
    agent.deploy()
''')

nb.code(r'''
import time
from workshop.cli import az
from workshop.config import project_client

agent_details = project_client().agents.get(agent_name=agent.agent_name)
identity = agent_details.instance_identity
principal_id = identity.get("principal_id") if hasattr(identity, "get") else identity.principal_id
service_name = settings.search_endpoint.split("//", 1)[-1].split(".", 1)[0]
scope = f"/subscriptions/{settings.subscription_id}/resourceGroups/{settings.resource_group}/providers/Microsoft.Search/searchServices/{service_name}"
print("Agent principal:", principal_id)
print("Search scope:", scope)

existing = az(
    "role", "assignment", "list",
    "--assignee", principal_id,
    "--role", "Search Index Data Reader",
    "--scope", scope,
    "--query", "[].id",
    json_out=True,
    timeout=300,
)
if existing:
    print("Role assignment already exists")
else:
    try:
        az(
            "role", "assignment", "create",
            "--assignee-object-id", principal_id,
            "--assignee-principal-type", "ServicePrincipal",
            "--role", "Search Index Data Reader",
            "--scope", scope,
            json_out=True,
            timeout=300,
        )
    except RuntimeError as exc:
        if "RoleAssignmentExists" not in str(exc):
            raise
    print("Created Search Index Data Reader role assignment")

openai_scope = settings.account_resource_id
openai_existing = az(
    "role", "assignment", "list",
    "--assignee", principal_id,
    "--role", "Cognitive Services OpenAI User",
    "--scope", openai_scope,
    "--query", "[].id",
    json_out=True,
    timeout=300,
)
if openai_existing:
    print("OpenAI role assignment already exists")
else:
    try:
        az(
            "role", "assignment", "create",
            "--assignee-object-id", principal_id,
            "--assignee-principal-type", "ServicePrincipal",
            "--role", "Cognitive Services OpenAI User",
            "--scope", openai_scope,
            json_out=True,
            timeout=300,
        )
    except RuntimeError as exc:
        if "RoleAssignmentExists" not in str(exc):
            raise
    print("Created Cognitive Services OpenAI User role assignment")

print("Waiting briefly for RBAC propagation...")
time.sleep(30)
''')

nb.md("## 7. Invoke the hosted grounded agent")

nb.code(r'''
from workshop.agents import ask

last_error = None
for attempt in range(8):
    try:
        hosted = ask(agent.agent_name, "Which document explains the TrailLite return or exchange window? Cite doc ids.")
        text = hosted.output_text.lower()
        if "policy-returns" in text:
            break
        last_error = AssertionError(text)
    except Exception as exc:
        last_error = exc
        print(f"Attempt {attempt + 1} waiting on Search RBAC: {exc}")
    time.sleep(30)
else:
    raise last_error

call_names = [item.name for item in hosted.output if getattr(item, "type", None) == "function_call"]
print("tool calls:", call_names)
assert "search_knowledge_base" in call_names
assert "policy-returns" in hosted.output_text.lower()
''')

nb.your_turn(
    """
    Ask a question that should retrieve both a product document and a policy document, then inspect the cited doc ids.
    """,
    "# Example: ask(agent.agent_name, 'What should I buy for a rainy day hike, and what is the return window? Cite doc ids.')",
)

nb.md("""
## Cleanup

The deployed agent `lgws-m04-rag` is kept. The Azure AI Search index `lgws-m04-contoso` is also kept because M15 reuses the same Contoso knowledge-base pattern. If you must remove it later, delete only that index from your AI Search service.

## Recap

| Step | Resource |
|---|---|
| Index | `lgws-m04-contoso` with semantic + vector search |
| Embeddings | `text-embedding-3-large` (3072 dimensions) |
| Tool | `search_knowledge_base` returns doc ids, titles and snippets |
| RBAC | Hosted-agent identity gets `Search Index Data Reader`; the cell also idempotently grants `Cognitive Services OpenAI User` for account-level embedding calls |

➡️ Next: **M5 · MCP tools via Foundry Toolbox** — package hosted tools behind a Toolbox MCP endpoint.
""")

nb.save("docs/modules/04-grounding-rag.ipynb")
