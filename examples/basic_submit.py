import os
from uuid import uuid4

from axme import AxmeClient, AxmeClientConfig


def main() -> None:
    client = AxmeClient(
        AxmeClientConfig(
            api_key=os.environ["AXME_API_KEY"],
            base_url=os.getenv("AXME_BASE_URL", "https://api.cloud.axme.ai"),
        )
    )
    correlation_id = str(uuid4())
    created = client.create_intent(
        {
            "intent_type": "intent.demo.v1",
            "from_agent": "agent://basic/python/source",
            "to_agent": "agent://basic/python/target",
            "payload": {"task": "hello-from-python"},
        },
        correlation_id=correlation_id,
    )
    intent_id = str(created["intent_id"])
    current = client.get_intent(intent_id)
    intent = current.get("intent") if isinstance(current, dict) else None
    if isinstance(intent, dict):
        print(intent.get("status") or intent.get("lifecycle_status"))
    else:
        print(current.get("status") if isinstance(current, dict) else "UNKNOWN")


if __name__ == "__main__":
    main()
