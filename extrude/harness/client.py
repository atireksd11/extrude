"""One model seat. Dollars come only from the bill the provider returns."""

import json
import os
import urllib.error
import urllib.request

from extrude.harness.proposal import ProposalError


def complete(prompt: str, seat: str) -> tuple[str, dict]:
    key_name = "EXTRUDE_ESCALATION_KEY" if seat == "escalation" else "EXTRUDE_MODEL_KEY"
    key = os.environ.get(key_name, "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if seat == "escalation" and not os.environ.get("EXTRUDE_ESCALATION_KEY", "").strip():
        raise ProposalError("tool", "no second model key")
    if not key:
        raise ProposalError("tool", "no model key")
    if key.startswith("<") or key.endswith(">"):
        raise ProposalError("tool", "the model key still has angle brackets around it")
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
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProposalError("tool", f"the model returned {exc.code}: {_http_message(exc)}") from exc
    text = _message_text(body["choices"][0]["message"])
    usage = body.get("usage") or {}
    bill = {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cost_usd": usage.get("cost_usd", usage.get("cost")),
    }
    return text, bill


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        bits = []
        for item in content:
            if isinstance(item, str):
                bits.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                bits.append(item["text"])
        return "\n".join(bits)
    return "" if content is None else str(content)


def _http_message(exc: urllib.error.HTTPError) -> str:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:180]
        if payload.get("message"):
            return str(payload["message"])[:180]
    text = " ".join(raw.split())
    return text[:180] or exc.reason
