Electrical facts reduced from Shashvat1333/Bluetooth-Audio-Transmiter at
f5c2b29347f9eaced1b67b3011b986baca8b7777. `board.kicad_pcb` is a synthetic,
minimal reconstruction of the relevant U3/U4 pad assignments, not the original
board or a manufacturable design. The firmware snapshot is from that commit.
The full original files are independently replayed by eval.design_rules_benchmark.

U4 PCM1808PWR: VREF pad 1 and SCKI pad 6 unconnected; LRCK pad 7 to U3 IO27
pad 12, BCK pad 8 to U3 IO14 pad 13, DOUT pad 9 to U3 IO34 pad 6. MD0/MD1
pads 10/11 share the ground net. Firmware WS=28, BCK=14, DATA_IN=34, slave RX.
The original firmware has WS on line 31 at this revision, rather than the
298–307 range in the supplied narrative. Tests cite parsed file evidence.
