# 0013. Footprint pin count versus used pins

**Spec** Footprint pin count vs used pins, v2 (Linear EXTRUDE-25), supplied in the cycle 1 task attachment. This supersedes the v1 spec and draft PR #31.

Use exact fitted on-board reference matches on the paired PCB. Warn for a two-pin passive in a footprint with at least twice as many numbered pads and at least two numbered pads with no assigned net. Compare distinct connected symbol pin numbers across all units of a reference to that footprint's numbered pads. Exclude no-connect and shield pins and skip zero-numbered-pad footprints.

The paired Astra board has two such passives, R27 and R39. Its R36–R38 schematic parts have no paired footprint. Astra Jd1, J9 and MK1 have connected pins with no corresponding pad. Lily58 Pro V2 omits unwired SuperSpeed contacts on J1 and J6.
