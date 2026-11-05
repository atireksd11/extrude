"""Spec cards expose numbers only — never answer keys."""

import pytest

from extrude.spec import SpecCard, forbidden_prompt_tokens


def test_prompt_rejects_answer_key_tokens():
    card = SpecCard(
        sentence="Build a robotic arm. Name module link1 for the base.",
        domain="mechanical_3d",
    )
    with pytest.raises(ValueError, match="forbidden"):
        card.prompt()


def test_clean_prompt_passes():
    card = SpecCard(
        sentence="Build a desktop robotic arm in OpenSCAD with three links.",
        domain="mechanical_3d",
        material="PETG",
        insert="M3",
        insert_count=4,
        min_wall_mm=2.0,
    )
    text = card.prompt()
    for token in forbidden_prompt_tokens():
        assert token not in text.lower()
