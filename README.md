# axme-sdk-python

**Python SDK for AXME** - send intents, listen for deliveries, resume workflows. Durable execution without polling or webhooks.

[![Alpha](https://img.shields.io/badge/status-alpha-orange)](https://cloud.axme.ai/alpha/cli) [![PyPI](https://img.shields.io/pypi/v/axme)](https://pypi.org/project/axme/) [![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

**[Quick Start](https://cloud.axme.ai/alpha/cli)** · **[Docs](https://github.com/AxmeAI/axme-docs)** · **[Examples](https://github.com/AxmeAI/axme-examples)**

---

## Install

```bash
pip install axme
```

Requires Python 3.11+.

---

## Quick Start

```python
from axme import AxmeClient, AxmeClientConfig

client = AxmeClient(AxmeClientConfig(api_key="axme_sa_..."))

# Send an intent - survives crashes, retries, timeouts
intent = client.create_intent({
    "intent_type": "order.fulfillment.v1",
    "to_agent": "agent://myorg/production/fulfillment-service",
    "payload": {"order_id": "ord_123"},
}, idempotency_key="fulfill-ord-123-001")

# Wait for resolution - blocks until done, even across process restarts
result = client.wait_for(intent["intent_id"])
print(result["status"])
```

---

## Connect an Agent

```python
for delivery in client.listen("agent://myorg/production/my-agent"):
    intent = client.get_intent(delivery["intent_id"])
    result = process(intent["payload"])
    client.resume_intent(delivery["intent_id"], result)
```

---

## Human Approvals

```python
intent = client.create_intent({
    "intent_type": "intent.budget.approval.v1",
    "to_agent": "agent://myorg/prod/agent_core",
    "payload": {"amount": 32000},
    "human_task": {
        "task_type": "approval",
        "notify_email": "approver@example.com",
        "allowed_outcomes": ["approved", "rejected"],
    },
})
result = client.wait_for(intent["intent_id"])  # waits until human acts
```

8 task types: `approval`, `confirmation`, `review`, `assignment`, `form`, `clarification`, `manual_action`, `override`. Full reference: [axme-docs](https://github.com/AxmeAI/axme-docs).

---

## Observe Lifecycle Events

```python
for event in client.observe(intent["intent_id"]):
    print(event["event_type"], event["status"])
    if event["status"] in {"RESOLVED", "CANCELLED", "EXPIRED"}:
        break
```

---

## Agent Mesh - Monitor and Govern

```python
# Start heartbeat - agent appears in dashboard with live health
client.mesh.start_heartbeat()  # background thread, every 30s

# Report metrics after each task
client.mesh.report_metric(success=True, latency_ms=230, cost_usd=0.02)

# List all agents with health status
agents = client.mesh.list_agents()

# Kill a misbehaving agent - blocks all intents instantly
client.mesh.kill(address_id="addr_...")

# Resume it
client.mesh.resume(address_id="addr_...")
```

Set action policies (allowlist/denylist intent types) and cost policies (intents/day, $/day limits) per agent via dashboard or API. [Agent Mesh overview](https://github.com/AxmeAI/axme#agent-mesh---see-and-control-your-agents).

---

## Examples

```bash
export AXME_API_KEY="axme_sa_..."
python examples/basic_submit.py
```

More: [axme-examples](https://github.com/AxmeAI/axme-examples)

---

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

---

## Related

| | |
|---|---|
| [axme-docs](https://github.com/AxmeAI/axme-docs) | API reference and integration guides |
| [axme-examples](https://github.com/AxmeAI/axme-examples) | Runnable examples |
| [axp-spec](https://github.com/AxmeAI/axp-spec) | Protocol specification |
| [axme-cli](https://github.com/AxmeAI/axme-cli) | CLI tool |
| [axme-conformance](https://github.com/AxmeAI/axme-conformance) | Conformance suite |

---

[hello@axme.ai](mailto:hello@axme.ai) · [Security](SECURITY.md) · [License](LICENSE)
