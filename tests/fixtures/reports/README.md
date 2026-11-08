These synthetic report schema fixtures exercise the offline lift-report validator;
they are not measured benchmark results or claims of improvement.

- `solid-repair.json` covers an explicitly labeled solid-verifier improvement.
- `legacy.json` covers the historical report shape without a quote flag.

The live benchmark runners (`eval.arm_benchmark.run` and `_repair_off`) call a
paid model and write ignored `eval/**/results*.json` files. Offline unit tests
must not depend on those local outputs. The baseline snapshot test instead runs
`eval.snapshot_baseline` with offline credentials and a temporary output/database.
