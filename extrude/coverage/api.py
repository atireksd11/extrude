"""Coverage entry. The body stays refused until a later phase."""

from extrude.coverage.models import CoverageMap
from extrude.intake.models import FrozenSpec


def cover(spec: FrozenSpec) -> CoverageMap:
    raise NotImplementedError("not built")
