"""Which checks can run for a card. The map is empty until a later phase fills it."""

from pydantic import BaseModel


class CoverageMap(BaseModel):
    by_check: dict[str, str] = {}
