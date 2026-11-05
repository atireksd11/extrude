"""Which checks can run for a card, and which this seat does not run."""

from pydantic import BaseModel


class CoverageMap(BaseModel):
    by_check: dict[str, str] = {}
