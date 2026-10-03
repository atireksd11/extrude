"""Simulator entry. Switching decks never start a process."""

from extrude.sim.models import SimResult
from extrude.sim.runner import run_deck


def run_allowed(deck: str) -> SimResult:
    return run_deck(deck)
