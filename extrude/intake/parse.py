"""Pull numbers out of a sentence. The snippet must be the text the person typed."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Quantity:
    start: int
    end: int
    si: float
    kind: str
    snippet: str


_PATTERNS = (
    ("V", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mV|millivolts)\b", re.IGNORECASE), 1e-3),
    ("V", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(V|volts)\b", re.IGNORECASE), 1.0),
    ("A", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mA|milliamps|milliamperes)\b", re.IGNORECASE), 1e-3),
    ("A", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(A|amps|amperes)\b", re.IGNORECASE), 1.0),
    ("s", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(ms|milliseconds)\b", re.IGNORECASE), 1e-3),
    ("s", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(us|µs|microseconds)\b", re.IGNORECASE), 1e-6),
    ("F", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(uF|µF|microfarads)\b", re.IGNORECASE), 1e-6),
    ("F", re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(nF)\b", re.IGNORECASE), 1e-9),
)


def find_quantities(text: str) -> list[Quantity]:
    found: list[Quantity] = []
    occupied: list[tuple[int, int]] = []
    for kind, pattern, scale in _PATTERNS:
        for match in pattern.finditer(text):
            span = (match.start(), match.end())
            if any(span[0] < end and span[1] > start for start, end in occupied):
                continue
            occupied.append(span)
            found.append(
                Quantity(
                    start=span[0],
                    end=span[1],
                    si=float(match.group(1)) * scale,
                    kind=kind,
                    snippet=match.group(0),
                )
            )
    found.sort(key=lambda hit: hit.start)
    return found
