# sim

Run an allowed simulator deck in a later phase. Phase 0 does not start ngspice.

May talk to: no other drawer in Phase 0.

Must not talk to: harness, intake, learn, mcp.

SIGNATURE: run_allowed(deck: str) -> SimResult
