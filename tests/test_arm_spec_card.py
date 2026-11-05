"""Arm benchmark card delegates to extrude.spec.SpecCard."""

from eval.arm_benchmark.spec_card import load_spec
from extrude.spec import SpecCard


def test_arm_spec_builds_spec_card():
    spec = load_spec()
    card = spec.to_spec_card()
    assert isinstance(card, SpecCard)
    assert card.domain == "mechanical_3d"
    assert "link1" not in spec.prompt().lower()


def test_shape_only_drops_manufacturing_requirements():
    spec = load_spec().shape_only()
    assert "insert_diameter" not in spec.requirement_ids()
