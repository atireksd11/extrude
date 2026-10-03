"""One model seat. Dollars come only from the bill the provider returns."""

import json
import os
import urllib.request

from extrude.harness.proposal import ProposalError


def complete(prompt: str, seat: str) -> tuple[str, dict]:
    key_name = "EXTRUDE_ESCALATION_KEY" if seat == "escalation" else "EXTRUDE_MODEL_KEY"
    key = os.environ.get(key_name, "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if seat == "escalation" and not os.environ.get("EXTRUDE_ESCALATION_KEY", "").strip():
        raise ProposalError("tool", "no second model key")
    if not key:
        raise ProposalError("tool", "no model key")
    model = os.environ.get(
        "EXTRUDE_ESCALATION_MODEL" if seat == "escalation" else "EXTRUDE_MODEL",
        "",
    ).strip() or "gpt-4.1-mini"
    url = os.environ.get("EXTRUDE_MODEL_URL", "https://api.openai.com/v1/chat/completions")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    text = body["choices"][0]["message"]["content"]
    usage = body.get("usage") or {}
    bill = {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cost_usd": usage.get("cost_usd", usage.get("cost")),
    }
    return text, bill
