# Room map

The code drawers sit side by side under `extrude/`. They call each other directly. They are not separate servers.

## What you asked

A sentence from the user lands in **intake**. That drawer turns it into a requirement card, or stops and asks for a missing fact.

**coverage** reads the finished card and says which checks can be run and which cannot (airflow, radios, fast memory).

## The design file

**ir** holds the design itself: parts, nets, and pins. That file is the source of truth.

**emit** will later write that design out as a simulator deck or a board file. It does not judge the design.

## The checkers

**checks** looks for obvious wiring mistakes.

**physics** computes the shared numbers, such as the capacitance a ceramic part still has under voltage.

**sim** is the only drawer that may start the ngspice program. It refuses a full switching transient.

## The run and the memory

**harness** is the front door. It walks the other drawers in order. In Phase 0 it still refuses to do that walk.

**memory** will keep three notebooks: bad design choices, vague requests, and tool crashes. A banned part would be stored here, and only from the design notebook.

**eval** will score practice tasks. It does not design anything.

## Parked

**learn** sits off to the side. Nothing on the user path may call it. It does not rewrite rules during a design.

**mcp** is the later slot for KiCad, part sites, and mechanical tools. The user path does not call it in Phase 0.

## Where a banned part, the simulator, and learning sit

| Question | Drawer |
| --- | --- |
| Where does the user's sentence land? | intake |
| Where would a banned part be stored? | memory |
| Where would the simulator run? | sim |
| Where does offline learning sit? | learn |
