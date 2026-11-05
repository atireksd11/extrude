"""Re-export shared cause attribution. Product code lives in extrude.harness.causes."""

from extrude.harness.causes import classify_miss, effective_cause, store_miss

__all__ = ["classify_miss", "effective_cause", "store_miss"]
