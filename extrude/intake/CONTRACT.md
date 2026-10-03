# intake

Turn a person's sentence into a requirement card, or stop and name the missing facts.

May talk to: no other drawer in Phase 0.

Must not talk to: sim, physics, learn, mcp.

SIGNATURE: resolve(raw_text: str) -> FrozenSpec | NeedsInfo
SIGNATURE: confirm(raw_text: str, spec: FrozenSpec) -> FrozenSpec
