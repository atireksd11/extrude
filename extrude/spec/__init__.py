"""Frozen requirement cards. Numbers only in prompts — never checker names."""

from extrude.spec.card import Requirement, RequirementKind, SpecCard, forbidden_prompt_tokens

__all__ = ["Requirement", "RequirementKind", "SpecCard", "forbidden_prompt_tokens"]
