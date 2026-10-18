# Reproduced synthetic results

Measured locally on 2026-10-18. These are deterministic scripted strategies and
synthetic charges, not language-model, provider, or production reliability results.

```sh
uv run --extra compatibility pytest -q
uv run --extra compatibility mcp-faultlab demo --out reports/comparison
uv run --extra compatibility mcp-faultlab suite examples/suite.json --out reports/suite
```

The test suite passed **89 tests on Python 3.11.14 and 3.12.12**, including three official-SDK subprocess
interoperability tests. The scenario suite matched **18 of 18** explicit expected
outcomes across nine faults and two scripted strategies. Expected failures are
negative controls, not successful task completions.

| Lost-confirmation default demo | Naive retry | Idempotent reconciliation |
| --- | ---: | ---: |
| Tool calls | 2 | 2 |
| Dispatches | 2 | 2 |
| Committed synthetic charges | 2 | 1 |
| Duplicate side effects | 1 | 0 |
| Contract violations | 0 | 0 |
| Task confirmed complete | yes | yes |
| Overall check | fail | pass |
| Injected elapsed time, milliseconds | 250 | 250 |

The safe strategy uses an idempotency key and reads back the ledger after losing
the response. The naive strategy repeats an unkeyed charge. Both appear to finish;
the ledger exposes the extra side effect in the naive strategy.

Both strategies stop on permission denial and simulated transport crash. Both
fail the duplicate-dispatch contract when the harness deliberately dispatches a
call twice. The safe strategy's idempotency key still prevents a second ledger
charge in that case. Therefore a contract failure is distinct from a duplicate
side effect, and a clean contract audit alone does not prove task success.

Replaying a trace returns recorded outcomes without executing tools. SHA-256 is
deterministic for the same synthetic run; it is an integrity checksum, not a signed
attestation. Virtual elapsed time is not measured network latency.
