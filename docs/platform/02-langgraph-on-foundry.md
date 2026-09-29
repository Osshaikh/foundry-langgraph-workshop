# LangGraph on Foundry

The bridge between your graph and Foundry is the **`langchain-azure-ai[hosting]`** package
(`langchain_azure_ai.agents.hosting`).

## The minimum hosted LangGraph agent

=== "main.py"

    ```python
    import os
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI

    def _build_chat_model() -> ChatOpenAI:
        credential = DefaultAzureCredential()
        project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential)
        return ChatOpenAI(
            model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini"),
            base_url=str(project.get_openai_client().base_url),          # .../api/projects/<p>/openai/v1/
            api_key=get_bearer_token_provider(credential, "https://ai.azure.com/.default"),
            use_responses_api=True,
            output_version="responses/v1",
        )

    graph = create_agent(_build_chat_model(), tools=[], system_prompt="You are helpful.")
    ```

=== "langgraph.json"

    ```json
    { "graphs": { "agent": "./main.py:graph" } }
    ```

=== "requirements.txt"

    ```text
    langchain-azure-ai[hosting]==1.2.9
    azure-ai-projects==2.4.0
    azure-identity==1.25.3
    langchain==1.3.15
    langchain-openai==1.5.1
    langgraph==1.2.11
    python-dotenv==1.2.2
    ```

=== "azure.yaml"

    ```yaml
    name: lgws-m02-first-agent
    services:
      lgws-m02-first-agent:
        host: azure.ai.agent
        kind: hosted
        project: src/first-agent
        language: python
        codeConfiguration:
          runtime: python_3_13
          entryPoint: '-m langchain_azure_ai.agents.hosting.run --protocol responses'
        startupCommand: python -m langchain_azure_ai.agents.hosting.run --protocol responses
        protocols:
          - protocol: responses
            version: 2.0.0
        env:
          AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
        container:
          resources: { cpu: '0.5', memory: 1Gi }
    ```

## How it runs

`python -m langchain_azure_ai.agents.hosting.run --protocol responses`:

1. reads `langgraph.json` and imports the graph (a compiled graph **or** a sync/async factory such as
   `create_graph()`, which is handy when tools must be loaded at startup, e.g. from a toolbox),
2. wraps it in `ResponsesHostServer` (or `InvocationsHostServer`),
3. serves on port `8088` (or `$PORT`) with `/responses`, `/readiness` and OpenTelemetry built in.

Need custom request handling (headers, a custom JSON body, extra state)? Subclass the host class and
start it from your own `main.py`. The same command also works for existing LangGraph/LangSmith
projects: no code changes needed.

## Conversation state: two models

| Graph compiled… | Where history lives | What the graph receives each turn |
|---|---|---|
| **without** a checkpointer | Foundry Responses history (`previous_response_id` / `conversation`) | Prior history + new input |
| **with** a checkpointer (`FoundryCheckpointSaver`, `MemorySaver`) | LangGraph checkpoint keyed by conversation/session | New input only |

Use a checkpointer when you need `interrupt()` (human-in-the-loop), node-local state across turns, or the
Invocations protocol. Use **`FoundryCheckpointSaver`** in hosted agents so state survives restarts
(M6, M13).

## Human-in-the-loop on the wire

A LangGraph `interrupt()` surfaces as standard Responses output items: an `mcp_approval_request`
(`server_label="langgraph"`) plus a `function_call` named `__hosted_agent_adapter_interrupt__`. Clients resume with
an `mcp_approval_response` (approve/reject) or a `function_call_output` carrying a `Command`-style
payload (M13).

## Tracing

`langchain_azure_ai.callbacks.tracers.enable_auto_tracing()` emits **OpenTelemetry GenAI** spans for
every node, model call and tool call. Hosted agents send them to the project's Application Insights
automatically (M10).

➡️ Next: [azd lifecycle, identity & RBAC](03-azd-lifecycle-identity-rbac.md)
