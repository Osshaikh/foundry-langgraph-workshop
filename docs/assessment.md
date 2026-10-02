# Post-workshop assessment

This assessment checks that you can **explain** the core ideas behind applied AI agents and **build**
production-shaped agents on Microsoft Foundry. It has two parts:

| Part | Format | Time | Measures |
|---|---|---|---|
| **Knowledge test** (Parts A–E) | 75 questions in Microsoft Forms, closed book | 90 min | Theory, framework/SDK architecture, performance & scale, observability & governance, applied engineering judgement |
| **Practical challenge** | Build and deploy an agent in your lab environment, open book | 90 min | Hands-on implementation |

!!! info "Your instructor sends the knowledge-test link"
    The questions are not published on this site. Use the blueprint and practice questions below to prepare.

## What is covered

| Part | Skill domain | Topics | Labs to revise |
|---|---|---|---|
| **A** | AI theory & concepts | Tokens & context windows · sampling/temperature · embeddings, vectors & similarity · chunking, hybrid search & semantic ranking · hallucination & grounding · RAG vs fine-tuning · fine-tuning, distillation & overfitting | M1, M4, M14 |
| **B** | Agent frameworks & hosted-agent architecture | Function calling · LangGraph nodes/edges/state, reducers, checkpointers vs stores, `interrupt()`, supervisor routing · Microsoft Agent Framework executors & workflows, supersteps, middleware, request/response human-in-the-loop, orchestration patterns (sequential, concurrent, handoff, group chat, Magentic) · hosted agents (any framework), Responses vs Invocations · Toolbox & MCP | M2, M3, M5, M6, M7, M8 + [Agent Framework docs](https://learn.microsoft.com/agent-framework/) |
| **C** | Performance, caching & scale | Prompt caching (prefix rules, `cached_tokens`) · semantic caching (thresholds, TTL, partitioning) · latency drivers, streaming & parallel tool calls · cold starts · RAG over millions of documents (HNSW vs exhaustive KNN, quantization, dimension truncation, filters) · NL2SQL over very large schemas · model routing, reasoning effort, provisioned throughput · context-window management | M1, M4, M6, M7, M8, M14 + [prompt caching](https://learn.microsoft.com/azure/foundry/openai/how-to/prompt-caching) |
| **D** | Observability, safety & governance | End-to-end GenAI tracing (spans, tool arguments, decisions) · trace propagation across agents · content recording & sensitive data · continuous evaluation in production · LLM-as-judge · guardrail intervention points (input, tool call, tool response, output) · PII protection · data residency (Global / DataZone / Regional) · egress controls & least privilege · tool approval · Defender for Cloud AI alerts · red teaming | M9, M10, M11, M12, M15 + [Foundry guardrails](https://learn.microsoft.com/azure/foundry/guardrails/guardrails-overview) |
| **E** | Applied agent engineering | Reading tool and client code · debugging deploys and config · conversation state · RAG quality · identity & RBAC · fine-tuning workflow · evaluation & evaluators · memory design · human-approval flows · versioning | M2–M15 |

Each part has 15 questions worth 1 point each. Questions marked **(Select ALL that apply)** score only when
you choose every correct option and no incorrect ones. All agent questions assume **hosted agents**, whether
built with LangGraph or Microsoft Agent Framework.

## Scoring and results

| Band | Score | Meaning |
|---|---|---|
| **Expert** | ≥ 85% | Can lead agent projects and coach others |
| **Proficient** | 70–84% | Can build and ship agents independently |
| **Developing** | 50–69% | Understands the basics; needs guided practice |
| **Needs support** | < 50% | Revisit the labs before building on your own |

**Pass** = at least **70% overall** and **50% in each of Parts A to E**, plus **12/18** on the practical challenge
(if your cohort runs it). Your result lists the labs to revisit for the topics you missed.

### How you get your results

After you submit, Forms confirms your answers were received but doesn't show a score. Your instructor grades
the cohort and emails you a **personal results report** (PDF) with:

- your score out of 75, your band, and whether you passed (and if not, exactly which requirement was missed)
- your score in each part against the 50% minimum, plus the practical challenge score if your cohort ran it
- the topics where you scored below 60%, each linked to the lab or documentation to revisit
- your strengths: topics where every answer was correct

Individual questions and correct answers are not shared, so the test stays fair for future participants.
Ask your instructor if you'd like to talk through a topic.

## Practical challenge

Build **"Trail Gear Assistant"**, a hosted LangGraph agent for Contoso Outdoor, in your own lab project.
You may use the workshop site, your lab notebooks and the `agents/` folder (especially `m15-capstone`) as
references. Name the agent **`lgws-assess-<your-alias>`**.

### Requirements

| # | Requirement | Evidence to show |
|---|---|---|
| R1 | A local tool `check_stock(product: str)` backed by in-code data (at least 3 products) | Tool call in a local test |
| R2 | Grounded policy answers using the M4 index (`lgws-m04-contoso`), citing doc ids such as `[policy-returns]` | A cited answer |
| R3 | A `place_order(product, quantity)` tool that **pauses for human approval** with `interrupt()` and a checkpointer, and only runs after approval | Pending approval, then the completed order |
| R4 | An **evaluation gate**: at least 5 test cases, run locally, ≥ 80% passing before you deploy | Gate table + pass rate |
| R5 | **Deployed** as a hosted agent and invoked with the Python SDK across at least two turns of one conversation | Agent name/version + both turns |
| R6 | **Operations**: tracing enabled, and the `lgws-strict` RAI policy attached to the agent | Trace screenshot or span list, and the agent definition showing the policy |

### Rubric (0–3 per requirement, 18 points total)

| Score | Meaning |
|---|---|
| **0** | Missing or doesn't run |
| **1** | Partly working: runs with errors or misses part of the requirement |
| **2** | Works as specified |
| **3** | Works, is robust (handles bad input/edge cases) and you can explain the design choices |

Submit a short notebook or Markdown file with the evidence column filled in, plus your agent name.
Your instructor will invoke your deployed agent to verify.

## Practice questions

These are **not** from the test. They check you are ready.

??? question "1. In retrieval, what is the difference between precision and recall?"
    **Precision**: of the chunks you retrieved, how many were relevant. **Recall**: of all the relevant
    chunks in the index, how many you retrieved. Small `top` values tend to favour precision; larger ones favour
    recall at the cost of a longer prompt. *(M4)*

??? question "2. Which LangGraph prebuilt node executes the tool calls the model requested?"
    **`ToolNode`**, usually paired with `tools_condition` to route between the model node and the tool node. *(M3)*

??? question "3. Which LangGraph primitive lets one node fan work out to several parallel branches?"
    **`Send`**: a conditional edge returns a list of `Send("node", payload)` objects, LangGraph runs them in
    parallel, and a reducer on the state collects the results (fan-in). *(M7)*

??? question "4. What does `--no-client` do in `azd ai agent run --no-client`?"
    It starts the local agent host without opening the **Agent Inspector** UI. The notebooks use it because
    they call the local `/responses` endpoint directly. *(M2)*

??? question "5. Which command streams the live container logs of a deployed hosted agent?"
    **`azd ai agent monitor`** (the notebooks call it through `agent.monitor()`). Use it when a version fails to
    start or a tool errors only in Foundry. *(M2, M10)*
