# ir

Hold the design file: parts, nets, and pins.

May talk to: no other drawer. The file is the source of truth.

Must not talk to: learn, mcp, sim.

SIGNATURE: save(ir: CircuitIR, path: Path) -> None
SIGNATURE: load(path: Path) -> CircuitIR
