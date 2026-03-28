# axme-sdk-python

**Official Python SDK for the AXME platform.** Send and manage intents, observe lifecycle events, work with inbox and approvals, and access the full enterprise admin surface — all from idiomatic Python.

> **Alpha** · API surface is stabilizing. Not recommended for production workloads yet.  
> **Alpha** — install CLI, log in, run your first example in under 5 minutes. [Quick Start](https://cloud.axme.ai/alpha/cli) · [hello@axme.ai](mailto:hello@axme.ai)

---

## What Is AXME?

AXME is a coordination infrastructure for durable execution of long-running intents across distributed systems.

It provides a model for executing **intents** — requests that may take minutes, hours, or longer to complete — across services, agents, and human participants.

## AXP — the Intent Protocol

At the core of AXME is **AXP (Intent Protocol)** — an open protocol that defines contracts and lifecycle rules for intent processing.

AXP can be implemented independently.  
The open part of the platform includes:

- the protocol specification and schemas
- SDKs and CLI for integration
- conformance tests
- implementation and integration documentation

## AXME Cloud

**AXME Cloud** is the managed service that runs AXP in production together with **The Registry** (identity and routing).

It removes operational complexity by providing:

- reliable intent delivery and retries  
- lifecycle management for long-running operations  
- handling of timeouts, waits, reminders, and escalation  
- observability of intent status and execution history  

State and events can be accessed through:

- API and SDKs  
- event streams and webhooks  
- the cloud console

---

## What You Can Do With This SDK

The AXME Python SDK gives you a fully typed client for the AXME platform. You can:

- **Send intents** — create typed, durable actions that the platform guarantees to deliver
- **Observe lifecycle** — stream real-time state transitions, waiting events, and delivery confirmations
- **Approve or reject** — handle human-in-the-loop steps directly from Python code
- **Control workflows** — pause, resume, cancel, update retry policies and reminders mid-flight
- **Administer** — manage organizations, workspaces, service accounts, and access grants

---

## Install

```bash
pip install axme
```

Primary import path is `axme` (legacy `axme_sdk` remains as compatibility alias).

For local development from source:

```bash
python -m pip install -e ".[dev]"
```

---

## Quickstart

```python
from axme import AxmeClient, AxmeClientConfig

client = AxmeClient(
    AxmeClientConfig(
        api_key="AXME_API_KEY",  # sent as x-api-key
        actor_token="OPTIONAL_USER_OR_SESSION_TOKEN",  # sent as Authorization: Bearer
        # Optional override (defaults to https://api.cloud.axme.ai):
        # base_url="https://staging-api.cloud.axme.ai",
    )
)

# Check connectivity
print(client.health())

# Send an intent to a registered agent address
intent = client.create_intent(
    {
        "intent_type": "order.fulfillment.v1",
        "to_agent": "agent://acme-corp/production/fulfillment-service",
        "payload": {"order_id": "ord_123", "priority": "high"},
    },
    idempotency_key="fulfill-ord-123-001",
    correlation_id="corr-ord-123-001",
)
print(intent["intent_id"], intent["status"])

# List registered agent addresses in your workspace
agents = client.list_agents(org_id="acme-corp-uuid", workspace_id="prod-ws-uuid")
for agent in agents["agents"]:
    print(agent["address"], agent["status"])

# Wait for resolution
resolved = client.wait_for(intent["intent_id"])
print(resolved["status"])
```

---

## Minimal Language-Native Example

Short basic submit/get example (about 25 lines):

- [`examples/basic_submit.py`](examples/basic_submit.py)

Run:

```bash
export AXME_API_KEY="axme_sa_..."
python examples/basic_submit.py
```

Full runnable scenario set lives in:

- Cloud: <https://github.com/AxmeAI/axme-examples/tree/main/cloud>
- Protocol-only: <https://github.com/AxmeAI/axme-examples/tree/main/protocol>

---

## API Method Families

The SDK covers the full public API surface organized into families. The map below shows all method groups and how they relate to the platform's intent lifecycle.

![API Method Family Map](https://raw.githubusercontent.com/AxmeAI/axme-docs/main/docs/diagrams/api/01-api-method-family-map.svg)

*Each family corresponds to a segment of the lifecycle or an operational domain. Intents and inbox are D1 (core). Approvals, schemas, and media are D2. Enterprise admin and service accounts are D3.*

---

## Create and Control Sequence

From calling `create_intent()` to receiving a delivery confirmation — the full interaction sequence with the platform:

![Create and Control Sequence](https://raw.githubusercontent.com/AxmeAI/axme-docs/main/docs/diagrams/intents/02-create-and-control-sequence.svg)

*The SDK sets the `Idempotency-Key` and `X-Correlation-Id` headers automatically. The gateway validates, persists, and returns the intent in `PENDING` state. The scheduler picks it up and drives delivery.*

---

## Idempotency and Replay Protection

Every mutating call in the SDK accepts an optional `idempotency_key`. Use it for all operations you might retry.

![Idempotency and Replay Protection](https://raw.githubusercontent.com/AxmeAI/axme-docs/main/docs/diagrams/protocol/03-idempotency-and-replay-protection.svg)

*Duplicate requests with the same key return the original response without re-executing. Keys expire after 24 hours. The SDK will warn if you reuse a key with different parameters.*

```python
# Safe to call multiple times — only executes once
intent = client.create_intent(payload, idempotency_key="my-unique-key-001")
```

---

## Observing Intent Events

The SDK provides a streaming event observer that delivers real-time lifecycle events over SSE:

```python
for event in client.observe(intent["intent_id"]):
    print(event["event_type"], event["status"])
    if event["status"] in {"RESOLVED", "CANCELLED", "EXPIRED"}:
        break
```

---

## Human-in-the-Loop (8 Task Types)

AXME supports 8 human task types. Each pauses the workflow and notifies a human via email with a link to a web task page.

| Task type | Use case | Default outcomes |
|-----------|----------|-----------------|
| `approval` | Approve or reject a request | approved, rejected |
| `confirmation` | Confirm a real-world action completed | confirmed, denied |
| `review` | Review content with multiple outcomes | approved, changes_requested, rejected |
| `assignment` | Assign work to a person or team | assigned, declined |
| `form` | Collect structured data via form fields | submitted |
| `clarification` | Request clarification (comment required) | provided, declined |
| `manual_action` | Physical task completion (evidence required) | completed, failed |
| `override` | Override a policy gate (comment required) | override_approved, rejected |

```python
# Create an intent with a human task step
result = client.create_intent(
    intent_type="intent.budget.approval.v1",
    to_agent="agent://agent_core",
    payload={"amount": 32000, "department": "engineering"},
    human_task={
        "title": "Approve Q3 budget",
        "description": "Review and approve the Q3 infrastructure budget.",
        "task_type": "approval",
        "notify_email": "approver@example.com",
        "allowed_outcomes": ["approved", "rejected"],
    },
)
```

Task types with forms use `form_schema` to define required fields:

```python
human_task={
    "title": "Assign incident commander",
    "task_type": "assignment",
    "notify_email": "oncall@example.com",
    "form_schema": {
        "type": "object",
        "required": ["assignee"],
        "properties": {
            "assignee": {"type": "string", "title": "Commander name"},
            "priority": {"type": "string", "enum": ["P1", "P2", "P3"]},
        },
    },
}
```

### Programmatic approvals (inbox API)

```python
# Fetch pending approvals for an agent
pending = client.list_inbox(owner_agent="agent://manager")

for item in pending.get("items", []):
    thread_id = item.get("thread_id")
    if not thread_id:
        continue
    client.approve_inbox_thread(
        thread_id,
        {"note": "LGTM"},
        owner_agent="agent://manager",
    )
```

---

## Workflow Controls

Update retry policy, reminders, or TTL on a live intent without cancelling it:

```python
client.update_intent_controls(
    intent_id,
    {
        "controls": {
            "max_retries": 5,
            "retry_delay_seconds": 30,
            "reminders": [{"offset_seconds": 3600, "note": "1h reminder"}],
        }
    },
    policy_generation=intent["policy_generation"],
)
```

---

## Cross-Org Delivery Control

Organizations can control which external orgs may send intents to their agents. Three levels of control:

1. **Org receive policy** — org-wide default (`open`, `allowlist`, `closed`)
2. **Agent receive override** — per-agent exceptions to the org policy

```python
# Get org receive policy
policy = client.get("/v1/organizations/{org_id}/receive-policy")

# Set org receive policy to allowlist mode
client.put("/v1/organizations/{org_id}/receive-policy", json={
    "mode": "allowlist",
    "allowlist": ["org_id_of_trusted_partner"]
})

# Allow a specific agent to receive from any org (override)
client.put("/v1/agents/{address}/receive-override", json={
    "override_type": "allow",
    "source_org_id": "org_id_of_partner"
})
```

See [`cross-org-receive-policy.md`](https://github.com/AxmeAI/axme-docs/blob/main/docs/cross-org-receive-policy.md) for the full decision flow.

---

## SDK Diagrams

The SDK docs folder contains diagrams for the API patterns used by this client:

| Diagram | Description |
|---|---|
| [`01-api-method-family-map`](https://raw.githubusercontent.com/AxmeAI/axme-docs/main/docs/diagrams/api/01-api-method-family-map.svg) | Full API family overview |
| [`02-create-and-control-sequence`](https://raw.githubusercontent.com/AxmeAI/axme-docs/main/docs/diagrams/intents/02-create-and-control-sequence.svg) | Intent creation and control flow |
| [`03-idempotency-and-replay-protection`](https://raw.githubusercontent.com/AxmeAI/axme-docs/main/docs/diagrams/protocol/03-idempotency-and-replay-protection.svg) | Idempotency protocol |

---

## MCP (Model Context Protocol)

The Python SDK includes a built-in MCP endpoint client for gateway-hosted MCP sessions:

```python
# Initialize an MCP session
init = client.mcp_initialize()
print(init["serverInfo"])

# List available tools
tools = client.mcp_list_tools()
for tool in tools.get("tools", []):
    print(tool["name"])

# Call a tool
result = client.mcp_call_tool("create_intent", arguments={
    "intent_type": "order.fulfillment.v1",
    "payload": {"order_id": "ord_123"},
    "owner_agent": "agent://fulfillment-service",
})
print(result)
```

MCP calls go to `/mcp` by default. Override with `mcp_endpoint_path` in `AxmeClientConfig`.

---

## Tests

```bash
pytest
```

---

## Repository Structure

```
axme-sdk-python/
├── axme/
│   ├── client.py              # Canonical public import path
│   └── exceptions.py          # Canonical exception import path
├── axme_sdk/
│   ├── client.py              # AxmeClient — all API methods
│   ├── config.py              # AxmeClientConfig
│   └── exceptions.py          # AxmeAPIError and subclasses
├── tests/                     # Unit and integration tests
├── examples/
│   └── basic_submit.py        # Minimal language-native quickstart
└── docs/
```

---

## Related Repositories

| Repository | Role |
|---|---|
| [axme-docs](https://github.com/AxmeAI/axme-docs) | Full API reference and integration guides |
| [axp-spec](https://github.com/AxmeAI/axp-spec) | Schema contracts this SDK implements |
| [axme-conformance](https://github.com/AxmeAI/axme-conformance) | Conformance suite that validates this SDK |
| [axme-examples](https://github.com/AxmeAI/axme-examples) | Runnable examples using this SDK |
| [axme-sdk-typescript](https://github.com/AxmeAI/axme-sdk-typescript) | TypeScript equivalent |
| [axme-sdk-go](https://github.com/AxmeAI/axme-sdk-go) | Go equivalent |
| [axme-sdk-java](https://github.com/AxmeAI/axme-sdk-java) | Java equivalent |
| [axme-sdk-dotnet](https://github.com/AxmeAI/axme-sdk-dotnet) | .NET equivalent |

---

## Contributing & Contact

- Bug reports and feature requests: open an issue in this repository
- Quick Start: https://cloud.axme.ai/alpha/cli · Contact: [hello@axme.ai](mailto:hello@axme.ai)
- Security disclosures: see [SECURITY.md](SECURITY.md)
- Contribution guidelines: [CONTRIBUTING.md](CONTRIBUTING.md)
