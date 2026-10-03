"""Canonical hash. 30 mV and 0.03 V are the same quantity."""

import hashlib
import json

from extrude.intake.models import FrozenSpec, SlotOrigin


def card_hash(spec: FrozenSpec) -> str:
    payload = {
        "defaults_version": spec.defaults_version,
        "labels": {key: spec.labels[key] for key in sorted(spec.labels)},
        "origins": {key: spec.origins[key].value for key in sorted(spec.origins)},
        "task_class": spec.task_class,
        "values_si": {key: _canon(spec.values_si[key]) for key in sorted(spec.values_si)},
        "waivers": sorted(
            key for key, origin in spec.origins.items() if origin is SlotOrigin.waived
        ),
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _canon(value: float) -> str:
    return format(float(value), ".12g")
