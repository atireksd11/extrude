"""Parts cost uses quantity-100 prices, and only a working circuit receives it."""

from extrude.eval.api import score
from extrude.eval.bom import design_bom_usd
from extrude.eval.tasks import load_tasks
from extrude.harness.models import RunResult
from extrude.ir.models import CircuitIR, Part


def test_a_bench_source_is_free_and_a_matching_buck_meets_the_reference():
    task = next(item for item in load_tasks() if item.id == "buck")
    design = CircuitIR(
        parts=[
            Part(refdes="V1", kind="ideal_voltage_source"),
            Part(refdes="U1", kind="ic"),
            Part(refdes="L1", kind="inductor", inductance=4.7e-6),
            Part(refdes="C1", kind="capacitor", capacitance=10e-6),
            Part(refdes="C2", kind="capacitor", capacitance=10e-6),
        ]
    )
    assert design_bom_usd(design, "buck") == task.reference_bom_usd


def test_an_extra_part_costs_more_than_the_reference_and_a_named_mpn_uses_its_price():
    task = next(item for item in load_tasks() if item.id == "holdup")
    bare = CircuitIR(
        parts=[
            Part(refdes="C1", kind="capacitor", capacitance=680e-6, mpn="EKZE100ELL681MJC5S"),
            Part(refdes="R1", kind="resistor", mpn="CRCW08052R00FKEA"),
        ]
    )
    assert design_bom_usd(bare, "holdup_mlcc") == task.reference_bom_usd
    extra = CircuitIR(parts=[*bare.parts, Part(refdes="U1", kind="ic")])
    assert design_bom_usd(extra, "holdup_mlcc") > task.reference_bom_usd


def test_cost_credit_stays_zero_until_the_circuit_works():
    failed = score(RunResult(status="stopped", bom_usd=0.2, reference_bom_usd=1.0))
    assert failed.technical == 0.0
    assert failed.cost_efficiency == 0.0
    assert failed.score == 0.0
    worked = score(RunResult(status="checked", bom_usd=0.5, reference_bom_usd=1.0))
    assert worked.technical == 1.0
    assert worked.cost_efficiency == 1.0
    assert worked.score == 1.0
