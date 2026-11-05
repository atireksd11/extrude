"""Quarantined answer-key prompt. Do not use for product lift metrics."""

from eval.arm_benchmark.score import PROMPT

_HARNESS = """You are inside a checker. It scores only the OpenSCAD you return.
Rules:
- Reply with OpenSCAD only. No markdown fences and no explanation.
- Name a module base for the base plate.
- Name modules link1, link2, and link3 for the three arm links.
- Name modules joint1, joint2, and joint3 for the three rotary joints.
- Name a module gripper with two fingers.
- Use cube() and cylinder() with millimeter numbers. At least one size must be 20 or larger.
- Place the parts with translate().
- Keep every { closed by a }.

USER REQUEST:
"""


def harness_prompt() -> str:
    return _HARNESS + PROMPT
