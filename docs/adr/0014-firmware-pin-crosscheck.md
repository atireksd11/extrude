# ADR 0014 — Cross-check literal firmware pin bindings against the paired PCB

The electrical collector resolves fitted schematic pin names to pads in the paired PCB. A literal port binding in the firmware source and its preceding comment provide the intended MCU pin and peer function. For Webcam this makes the `conf_board.h` binds authoritative. The conflicting ESP GPIO numbers in `wifi.h` lack a SAM pin binding. The comment-only COMM role is reported as coverage.

The UART check requires an explicit ESP32 USART setup in the firmware. The only curated mapping is ATSAM4S USART0, RX on PA21 and TX on PA22, from the SAM4S datasheet pin multiplexing table. Other USARTs and MCU families lack a verified mapping. Matching a pin name requires a unique fitted endpoint.

This is a literal topological check. Firmware buildability (Deep Test 3 item 11), SPI routing through the ESP32 GPIO matrix, and unbound numeric GPIO definitions are outside its scope.
