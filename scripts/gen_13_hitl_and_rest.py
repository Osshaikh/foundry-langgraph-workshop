"""Generate docs/modules/13-hitl-and-rest.ipynb."""

from nbbuild import Notebook

nb = Notebook(
    "M13 · Human-in-the-loop & REST",
    "Pause a LangGraph hosted agent for manager approval, then invoke the deployed agent with raw HTTP and streaming SSE.",
    minutes=55,
)

nb.md("""
## Objectives

- Build a LangGraph approval flow: `draft → interrupt() → approve / revise / reject`.
- Persist paused state with `FoundryCheckpointSaver(user_isolation=True)` and a conversation id.
- Exercise the exact Responses wire protocol: `mcp_approval_request`, `mcp_approval_response`, and rich `function_call_output` resume payloads.
- Call the deployed hosted agent with raw `requests` + an Azure bearer token, including `stream: true` SSE events.
- List and stop hosted-agent sessions with `azd`.

## Concept map

| Moment | Wire item | What the client sends next |
|---|---|---|
| Graph pauses | `mcp_approval_request` (`server_label="langgraph"`) plus a paired `function_call` named `__hosted_agent_adapter_interrupt__` | Choose approve, revise, or reject |
| Approve | `mcp_approval_response` with `approve: true` | Graph appends the approved draft and completes |
| Revise | `function_call_output` with `{"resume":{"feedback":"..."}}` | Graph loops to draft a new proposal |
| Reject | `mcp_approval_response` with `approve: false` | Host returns a failed response with `interrupt_rejected` |

Scenario: **Contoso Outdoor** needs a manager to approve refund and loyalty-discount proposals.
""")

nb.bootstrap()

nb.md("## 1. Read the hosted LangGraph agent")

nb.code("""
from workshop.azd import show_file
from workshop.config import AGENTS_DIR

src = AGENTS_DIR / "m13-hitl" / "src" / "hitl-agent"
show_file(src / "main.py")
show_file(src / "langgraph.json")
show_file(AGENTS_DIR / "m13-hitl" / "azure.yaml")
""")

nb.md("""
The important pattern is the `await_approval` node. It calls `interrupt({"draft": ...})` and then routes with a `Command`:

- feedback present → append to `revision_history` and go back to `draft`
- no feedback → treat it as approval and append the draft to `messages`
- reject → handled by the Responses host before the node re-enters
""")

nb.md("## 2. Initialize and run locally")

nb.code("""
from workshop.azd import init_agent, summarize_output

agent = init_agent("m13-hitl", port=8113)
print("Agent name:", agent.agent_name)
""")

nb.code("""
agent.run_local()
""")

nb.md("## 3. Local wire protocol: revise → approve")

nb.code(r"""
import json, uuid


def output_items(response):
    return response["output"] if isinstance(response, dict) else [item.model_dump() for item in response.output]


def find_interrupt(response):
    approval = None
    function = None
    for item in output_items(response):
        if item.get("type") == "mcp_approval_request" and item.get("server_label") == "langgraph":
            approval = item
        if item.get("type") == "function_call" and item.get("name") == "__hosted_agent_adapter_interrupt__":
            function = item
    assert approval, f"No mcp_approval_request found: {output_items(response)}"
    assert function, f"No paired function_call found: {output_items(response)}"
    args = json.loads(approval.get("arguments") or "{}")
    draft = args.get("value", {}).get("draft", "")
    print("approval id:", approval["id"])
    print("function call id:", function["call_id"])
    print("draft preview:", draft[:500].replace("\n", " "))
    return approval, function, draft

case = (
    "A Contoso Outdoor customer bought a TrailMaster tent for $240. "
    "The rainfly seam leaked on the first trip, and a replacement will miss their next outing. "
    "Draft a proposal for a partial refund plus a loyalty discount that needs manager approval."
)
local_conversation = {"id": "m13-local-" + uuid.uuid4().hex[:10]}
pending = agent.local_responses(case, conversation=local_conversation)
summarize_output(pending)
approval, function, draft = find_interrupt(pending)
assert "refund" in draft.lower() or "discount" in draft.lower()
""")

nb.code(r"""
revise = agent.local_responses(
    [
        {
            "type": "function_call_output",
            "call_id": function["call_id"],
            "output": json.dumps({"resume": {"feedback": "Make it shorter, cap the refund at $60, and use a 15% loyalty code."}}),
        }
    ],
    conversation=local_conversation,
)
summarize_output(revise)
approval2, function2, revised_draft = find_interrupt(revise)
assert "15" in revised_draft or "$60" in revised_draft

approved = agent.local_responses(
    [{"type": "mcp_approval_response", "approval_request_id": approval2["id"], "approve": True}],
    conversation=local_conversation,
)
summarize_output(approved)
assert any(item.get("type") == "message" for item in output_items(approved))
""")

nb.md("## 4. Local wire protocol: reject")

nb.code(r"""
reject_conversation = {"id": "m13-local-reject-" + uuid.uuid4().hex[:10]}
reject_pending = agent.local_responses(
    "Customer asks for a full refund and a 50% discount after normal wear and tear. Draft a manager proposal.",
    conversation=reject_conversation,
)
reject_approval, _, _ = find_interrupt(reject_pending)
rejected = agent.local_responses(
    [
        {
            "type": "mcp_approval_response",
            "approval_request_id": reject_approval["id"],
            "approve": False,
            "reason": "Policy does not allow both remedies for normal wear and tear.",
        }
    ],
    conversation=reject_conversation,
)
print("status:", rejected.get("status"))
print("error:", rejected.get("error"))
assert rejected.get("status") == "failed" or "interrupt_rejected" in json.dumps(rejected)
""")

nb.code("""
agent.stop_local()
""")

nb.md("## 5. Deploy and repeat against Foundry")

nb.code("""
agent.deploy()
""")

nb.code(r"""
from workshop.config import openai_client

client = openai_client(agent_name=agent.agent_name)
conversation = client.conversations.create()
print("conversation:", conversation.id)

remote_pending = client.responses.create(input=case, conversation=conversation.id)
summarize_output(remote_pending)
remote_approval, remote_function, _ = find_interrupt(remote_pending)

remote_revise = client.responses.create(
    input=[
        {
            "type": "function_call_output",
            "call_id": remote_function["call_id"],
            "output": json.dumps({"resume": {"feedback": "Use a crisp executive tone and keep the refund at $60."}}),
        }
    ],
    conversation=conversation.id,
)
summarize_output(remote_revise)
remote_approval2, _, _ = find_interrupt(remote_revise)

remote_approved = client.responses.create(
    input=[{"type": "mcp_approval_response", "approval_request_id": remote_approval2["id"], "approve": True}],
    conversation=conversation.id,
)
summarize_output(remote_approved)
assert remote_approved.status == "completed"
""")

nb.code(r"""
reject_conversation = client.conversations.create()
remote_reject_pending = client.responses.create(
    input="Draft a manager proposal for a rejected warranty claim on boots damaged by misuse.",
    conversation=reject_conversation.id,
)
remote_reject_approval, _, _ = find_interrupt(remote_reject_pending)
remote_rejected = client.responses.create(
    input=[
        {
            "type": "mcp_approval_response",
            "approval_request_id": remote_reject_approval["id"],
            "approve": False,
            "reason": "Manager declines the goodwill exception.",
        }
    ],
    conversation=reject_conversation.id,
)
print("status:", remote_rejected.status)
print("error:", remote_rejected.error)
assert remote_rejected.status == "failed" or "interrupt_rejected" in str(remote_rejected.error)
""")

nb.md("## 6. REST invocation with bearer token and streaming SSE")

nb.code(r"""
import requests
from workshop.config import AZURE_AI_SCOPE, credential

rest_client = openai_client(agent_name=agent.agent_name)
rest_url = str(rest_client.base_url).rstrip("/") + "/responses"
params = dict(getattr(rest_client, "default_query", {}) or {})
print("base_url:", rest_client.base_url)
print("default_query:", params)
print("REST URL:", rest_url + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""))

token = credential().get_token(AZURE_AI_SCOPE).token
rest_conversation = client.conversations.create()
body = {
    "input": "Draft a brief manager-review proposal for a $35 shipping refund on a delayed Contoso Outdoor order.",
    "conversation": {"id": rest_conversation.id},
    "stream": True,
}
with requests.post(
    rest_url,
    params=params,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json=body,
    stream=True,
    timeout=300,
) as r:
    print("HTTP", r.status_code)
    r.raise_for_status()
    event_types = []
    for raw_line in r.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        if raw_line.startswith("event:"):
            event = raw_line.split(":", 1)[1].strip()
            event_types.append(event)
            print("event:", event)
        if len(event_types) >= 8:
            break
assert event_types, "Expected streaming SSE events"
""")

nb.md(r"""
### PowerShell / curl equivalent

```powershell
$token = (az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
$body = @{
  input = "Draft a manager-review proposal for a delayed Contoso Outdoor order."
  conversation = @{ id = "demo-rest-conversation" }
  stream = $true
} | ConvertTo-Json -Depth 5
Invoke-WebRequest `
  -Method POST `
  -Uri "{project_endpoint}/agents/lgws-m13-hitl/endpoint/protocols/openai/responses?api-version=v1" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body $body
```

```bash
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
curl -N -X POST "{project_endpoint}/agents/lgws-m13-hitl/endpoint/protocols/openai/responses?api-version=v1" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"input":"Draft a manager-review proposal for a delayed order.","conversation":{"id":"demo-rest-conversation"},"stream":true}'
```
""".replace("{project_endpoint}", "`{settings.project_endpoint}`"))

nb.md("## 7. List and stop hosted-agent sessions")

nb.code(r"""
import json
from workshop.azd import azd

listing = azd("ai", "agent", "sessions", "list", "--output", "json", cwd=agent.project_dir, check=False)
print(listing[:2000])
try:
    sessions = json.loads(listing)
except Exception:
    sessions = []
if isinstance(sessions, dict):
    sessions = sessions.get("value") or sessions.get("sessions") or []
if sessions:
    session_id = sessions[0].get("id") or sessions[0].get("sessionId") or sessions[0].get("name")
    if session_id:
        print("Stopping session:", session_id)
        print(azd("ai", "agent", "sessions", "stop", session_id, cwd=agent.project_dir, check=False)[-1000:])
else:
    print("No sessions were returned by azd; the SDK calls above still validated conversation-scoped state.")
""")

nb.your_turn(
    """
    Add one more approval rule to the prompt: discounts over 20% must cite a director exception. Re-run locally and reject a draft that violates it.
    """,
)

nb.md("""
## Cleanup

The deployed `lgws-m13-hitl` agent is kept for M15 review. The local server is already stopped; if you restarted it, run:
""")

nb.code("""
agent.stop_local()
""", tags=["cleanup"])

nb.md("""
## Recap

| Capability | What you proved |
|---|---|
| HITL pause | `interrupt()` appeared as `mcp_approval_request` + paired function call |
| Revise path | `function_call_output` with `resume.feedback` looped to a new draft |
| Approve path | `mcp_approval_response approve=true` completed with a final message |
| Reject path | `approve=false` returned `interrupt_rejected` |
| REST path | Raw HTTP used bearer auth, the hosted-agent URL, `api-version=v1`, and streaming SSE |

➡️ Next: **M14 · Fine-tuning / distillation** — distill a teacher into a cheaper support-reply student.
""")

nb.save("docs/modules/13-hitl-and-rest.ipynb")
