# emit

Write a simulator deck or a board file in a later phase.

May talk to: ir and physics, to read the design and the shared numbers.

Must not talk to: learn, mcp.

SIGNATURE: emit_cir(ir: CircuitIR, physics: PhysicsValues) -> str
