# eval

Score a finished run against the practice set. Phase 0 does not score anything.

May talk to: harness, and only to read the run result shape.

Must not talk to: learn, mcp.

SIGNATURE: score(result: RunResult) -> ScoreCard
