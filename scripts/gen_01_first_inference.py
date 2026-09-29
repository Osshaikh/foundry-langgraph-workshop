"""Generate docs/modules/01-first-inference.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M1 · First inference with LangChain on Foundry",
    "Call a Foundry model from LangChain — the same model client every hosted agent in this workshop uses.",
    minutes=30,
)

nb.md("""
## Objectives

- Authenticate to your Foundry project with **`DefaultAzureCredential`** (your `az login`) — no keys.
- Call a deployed model with the raw **OpenAI Responses API** exposed by the project.
- Wrap the same endpoint in LangChain's **`ChatOpenAI`** — the building block of every LangGraph agent.
- Stream tokens, keep a multi-turn history and get **structured output** back as a Pydantic object.

## How it fits together

```
your code ──► ChatOpenAI (LangChain) ──► https://<account>.services.ai.azure.com/api/projects/<project>/openai/v1/responses
                         ▲                                   │
       Entra ID bearer token (scope https://ai.azure.com/.default)   ──► model deployment (gpt-5.4-mini)
```

The project exposes an **OpenAI-compatible `/openai/v1`** endpoint. Pointing LangChain at it with an
Entra ID token provider means *no API keys ever live in your code* — the same pattern the hosted agents
use when they run inside Foundry with their own managed identity.
""")

nb.bootstrap()

nb.md("""
## 1. The Foundry project client

`AIProjectClient` is the entry point to everything in the project: agents, toolboxes, evaluations,
connections, datasets… `get_openai_client()` returns an `openai.OpenAI` client already pointed at the
project's `/openai/v1` endpoint and authenticated with your identity.
""")

nb.code("""
from workshop.config import project_client, openai_client

project = project_client()
oai = openai_client()
print("OpenAI base URL:", oai.base_url)

resp = oai.responses.create(
    model=settings.chat_model,
    input="In one sentence, what is Microsoft Foundry?",
)
print(resp.output_text)
""")

nb.md("""
**Expected output:** the project's `/openai/v1/` URL and a one-sentence description of Foundry.

> 💡 A `401`/`403` here means your identity is missing the **Foundry User** role on the project;
> a `CredentialUnavailableError` means you need to run `az login`.

## 2. The same model through LangChain

`workshop.config.chat_model()` builds a `ChatOpenAI` exactly like the hosted agents do:
""")

nb.code("""
import inspect
from workshop.config import chat_model
print(inspect.getsource(chat_model))
""")

nb.code("""
llm = chat_model()
reply = llm.invoke("Give me three short tips for writing good agent instructions.")
print(reply.text)
""")

nb.md("""
`use_responses_api=True` routes LangChain through the **Responses API** (instead of Chat Completions).
Hosted agents use it because it returns `response.id`s that Foundry's tracing and conversation features understand.

## 3. Streaming
""")

nb.code("""
for chunk in llm.stream("Count from 1 to 5, one number per line."):
    print(chunk.text, end="", flush=True)
print()
""")

nb.md("## 4. Multi-turn conversation\n\nChat models are stateless — *you* send the history each turn. (LangGraph will manage this for us from M2 onwards.)")

nb.code("""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

history = [
    SystemMessage("You are a concise assistant for Contoso Outdoor, a hiking-gear retailer."),
    HumanMessage("My name is Priya and I'm planning a 3-day hike in the Alps."),
]
first = llm.invoke(history)
history.append(AIMessage(first.text))
history.append(HumanMessage("What is my name and where am I going? Answer in one line."))
print(llm.invoke(history).text)
""")

nb.md("""
**Expected output:** the model recalls *Priya* and *the Alps*.

## 5. Structured output

Agents often need machine-readable answers. `with_structured_output` binds a Pydantic schema and
returns a validated object.
""")

nb.code("""
from pydantic import BaseModel, Field

class GearItem(BaseModel):
    name: str
    reason: str = Field(description="Why it is needed, max 12 words")

class PackingList(BaseModel):
    trip: str
    items: list[GearItem]

structured = chat_model().with_structured_output(PackingList)
plan = structured.invoke("Packing list with exactly 4 items for a rainy 2-day hike in Scotland.")
print(plan.trip)
for item in plan.items:
    print(f" - {item.name}: {item.reason}")
assert len(plan.items) == 4
""")

nb.md("""
## 6. Choosing a model

Your project has several deployments. Swap them by name — the code does not change.
""")

nb.code("""
for deployment in [settings.chat_model, settings.reasoning_model]:
    answer = chat_model(deployment).invoke("Reply with just your model family name.")
    print(f"{deployment:>15} -> {answer.text.strip()}")
""")

nb.your_turn(
    """
    1. Add a `budget_usd: int` field to `PackingList` and ask for a budget-conscious list.
    2. Stream a response from the **reasoning** model (`settings.reasoning_model`) and compare latency.
    """,
    """
    # Your code here
    """,
)

nb.md("""
## Recap

- The project endpoint is OpenAI-compatible; `DefaultAzureCredential` + a bearer-token provider is all you need.
- `ChatOpenAI(base_url=…/openai/v1, api_key=<token provider>, use_responses_api=True)` is **the** model client used by every hosted agent in this workshop.

➡️ Next: **M2 · Your first hosted agent** — wrap this model in a LangGraph agent and deploy it to Foundry.
""")

nb.save("docs/modules/01-first-inference.ipynb")
