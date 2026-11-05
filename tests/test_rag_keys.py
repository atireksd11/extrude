"""RAG retrieves by spec hash and task class, not token overlap."""

from extrude.intake.models import FrozenSpec, SlotOrigin
from extrude.memory import reset
from extrude.memory.db import insert_constraint
from extrude.memory.models import ElectricalIdentity
from extrude.memory.rag import retrieve


def setup_function() -> None:
    reset()


def test_unrelated_prompt_does_not_retrieve_constraint():
    spec = FrozenSpec(
        task_class="buck",
        values_si={"vin": 5.0, "vout": 3.3, "i_load": 2.0},
        origins={"vin": SlotOrigin.user_span, "vout": SlotOrigin.user_span, "i_load": SlotOrigin.user_span},
        defaults_version="v1",
        spec_hash="abc123",
    )
    identity = ElectricalIdentity(
        manufacturer="Murata",
        capacitance=10e-6,
        dielectric="X7R",
        case="0805",
        voltage_rating=16.0,
    )
    insert_constraint(
        task_class="holdup_mlcc",
        spec_hash="other_hash",
        prompt="hold-up capacitor failed in a completely different sentence",
        check_id="minimum_capacitance",
        detail="failed",
        voltage=4.7,
        identity=identity,
        checker_version="test",
        v_fail=4.7,
        i_fail=None,
        measured=100e-6,
        limit=545e-6,
    )
    blocks = retrieve(spec, "5 V to 3.3 V buck at 2 A")
    assert blocks == []
