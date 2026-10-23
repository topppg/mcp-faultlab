# MCP FaultLab

Deterministic failure testing at an agent's tool boundary. Inject controlled tool
failures, inspect recovery behavior, and turn a synthetic incident into a trace and
a portable report.

The implementation is published in fifteen ordered stages. During the staged
release, the [pull request history](https://github.com/topppg/mcp-faultlab/pulls?q=is%3Apr)
shows which capabilities have reached `main`. The results below were measured
on the complete local implementation.

## Why this exists

A tool call can commit a change while its confirmation disappears. An agent that
simply retries can complete the task twice. MCP FaultLab makes that failure easy
to reproduce with a synthetic payment ledger, then compares naive retry with
idempotency and reconciliation.

The harness is framework-neutral: a Python adapter accepts named tool calls, and a
real stdio proxy connects an MCP client to a test tool server. It uses no language
model, paid API, external service, or runtime dependency by default.

## Demonstrated results

The default lost-confirmation scenario produces the following repeatable result:

| Metric | Naive retry | Idempotent reconciliation |
| --- | ---: | ---: |
| Tool calls | 2 | 2 |
| Committed synthetic charges | 2 | 1 |
| Duplicate side effects | 1 | 0 |
| Confirmed complete | yes | yes |
| Overall check | fail | pass |

Local validation passed **89 tests on Python 3.11 and 3.12**, including **three official MCP SDK 1.30.0
subprocess integration tests**. The example suite matched **18 of 18 explicit
expectations** across nine faults and two scripted strategies. Expected failures
are negative controls. These results describe synthetic recovery logic; they are
not a benchmark of language models or a production agent. See
[reproduction details](docs/results.md).

## Quick start

Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/) are recommended. Commands run
from the repository root. Setup downloads development dependencies; the demo then
runs offline.

```sh
uv sync --frozen
uv run mcp-faultlab doctor
uv run mcp-faultlab demo --out reports/comparison
uv run mcp-faultlab suite examples/suite.json --out reports/suite
```

Open `reports/comparison/safe/report.html` and
`reports/comparison/naive/report.html` to inspect both runs. Each directory also
contains `summary.json` and `junit.xml`; the demo summary includes its full trace.
The HTML report is self-contained, escapes tool text, and runs no JavaScript.

`demo --strategy safe` exits zero only when task completion, duplicate-effect, and
contract checks pass. `demo --strategy naive` deliberately exits one for the
default scenario. Comparison mode exits according to the safe strategy. `suite`
exits zero when every actual outcome matches its explicit expected outcome.

## Faults and timing

| Fault | Execution semantics |
| --- | --- |
| `tool_error` | Return an MCP execution error without dispatching |
| `permission_denied` | Return a denial without dispatching |
| `rate_limit` | Return an execution error carrying an injected retry interval |
| `timeout` | Known pre-dispatch timeout; no upstream work occurs |
| `malformed` | Execute, then replace structured content with an invalid type |
| `stale` | Execute, then substitute a configured or previously cached result |
| `response_loss` | Execute, discard the response, expose an unknown outcome |
| `duplicate_execution` | Dispatch twice, return one response |
| `crash` | Simulate a persistent closed transport |

`delay_ms` advances an injected virtual clock without sleeping. Real transport
deadlines are separate. Timeouts and lost responses from real servers do not imply
rollback. Stale cache fallback uses the previous successful result for the same
tool, irrespective of arguments; configure `value` for a precise synthetic stale
snapshot. `duplicate_execution` deliberately tests duplicate side effects without
emitting an invalid duplicate JSON-RPC response.

## Configure a scenario

Scenarios are strict JSON. Unknown fields, duplicate rule names, invalid limits,
non-finite numbers, and duplicate JSON object keys are rejected.

```json
{
  "schema_version": 1,
  "name": "charge-confirmation-lost",
  "rules": [
    {
      "name": "lose-first-charge",
      "tool": "ledger.charge",
      "occurrence": 1,
      "fault": "response_loss",
      "delay_ms": 250
    }
  ],
  "contracts": {
    "allowed_tools": ["ledger.charge", "ledger.lookup"],
    "side_effect_tools": ["ledger.charge"],
    "require_approval": true,
    "max_retries": 1,
    "max_calls": 3,
    "max_elapsed_ms": 1000
  }
}
```

Occurrences count all attempts for the named tool, before argument filtering.
Wildcard `tool: "*"` counts all tool calls. An optional `arguments` object matches
an exact subset of argument keys. Rules are evaluated in file order; the first
matching rule wins and fires once. Overlapping rules can therefore remain unused.
The initial demo uses fixed synthetic order `order-001` and amount `100`; it is a
reference strategy, not a general autonomous order-processing agent.

## Connect a real stdio MCP client

Configure the client's server command to launch this proxy, followed by the
upstream server's explicit argument vector. For the synthetic reference server:

```sh
uv run mcp-faultlab proxy \
  --scenario examples/response_loss.json \
  --trace reports/proxy-trace.json \
  --timeout 5 \
  -- uv run mcp-faultlab reference-server
```

Create the `reports` directory first. Protocol mode reads JSON-RPC messages from
stdin and writes only protocol messages to stdout. A lost-response fault closes
the downstream stream instead of fabricating a protocol error. The trace is saved
when the proxy ends normally; an external forced kill can prevent finalization.
Its in-memory upstream ledger does not persist after the subprocess exits.

The supported MCP version is **2025-11-25**, with sequential initialization, ping,
tool discovery, and tool invocation. It does not support MCP 2026-07-28, concurrent
calls, cancellation, server callbacks, resource/prompt APIs, or transparent
notification forwarding. See [the precise protocol scope](docs/protocol-scope.md).

For an existing local JSON POST test server, use `--http-url` instead of an upstream
command:

```sh
uv run mcp-faultlab proxy \
  --scenario examples/timeout.json \
  --trace reports/http-trace.json \
  --http-url http://127.0.0.1:8000/mcp
```

This bounded HTTP adapter accepts literal loopback addresses and JSON responses
only. It rejects SSE and is not a full Streamable HTTP client. It opens no HTTP
listener and does not provide authentication or public-network connectivity.

## Record, replay, and audit

```sh
uv run mcp-faultlab replay --trace reports/proxy-trace.json
uv run mcp-faultlab report --trace reports/proxy-trace.json --out reports/proxy-audit
```

Replay verifies the trace checksum and structure, then returns recorded outcomes
without executing tools. Exact ordered replay includes IDs, tools, arguments, and
operation identifiers. SHA-256 detects accidental trace changes; it is not a
signature and provides no authenticity guarantee.

Contracts audit allowed tools, exact prior approvals for configured side-effect
tools, retries per operation/tool pair, duplicate dispatches, call count, and
injected elapsed time. They report violations rather than enforcing access.
Approvals are trusted test-driver events; tool annotations do not grant approval.
The proxy cannot infer approvals made in an external agent UI, so an external trace
with approval requirements reports missing approvals unless a trusted integration
records them. A trace-only report does not infer task completion or real side
effects from arbitrary tool responses; its pass flag covers contracts only.

## Python adapter

Implement `execute(Call) -> dict` with MCP-shaped tool results, then pass it to the
harness. Keep real side-effect instrumentation in your backend.

```python
from mcp_faultlab.engine import Harness
from mcp_faultlab.ledger import Ledger
from mcp_faultlab.model import Call
from mcp_faultlab.scenario import Scenario
from mcp_faultlab.trace import make_trace, write_trace

harness = Harness(Scenario.load("examples/response_loss.json"), Ledger())
call = Call("1", "ledger.charge", {"operation": "order-001", "amount": 100}, "order-001")
harness.approve(call)
outcome = harness.invoke(call)
assert outcome.failure == "response_lost"
assert harness.backend.snapshot()["side_effects"] == 1
write_trace("reports/python-trace.json", make_trace(harness))
```

## Validation and project structure

```sh
uv sync --frozen --extra compatibility
uv run --extra compatibility ruff check .
uv run --extra compatibility ruff format --check .
uv run --extra compatibility pytest -q
uv build
```

The optional compatibility extra installs the official MCP SDK **only for
integration tests**. Without it, those tests are skipped. The Python package has
zero mandatory runtime dependencies. GitHub Actions is configured for Python
3.11/3.12 on Linux; check the Actions tab for live results. Local tests run on macOS.
The subprocess client uses POSIX pipe readiness and does not support Windows.

`src/mcp_faultlab/` contains the engine, transport adapters, contracts, traces,
reference ledger, and reports. `examples/` contains nine fault scenarios and the
18-case expectation plan. Tests include wrong response IDs, malformed wire JSON,
pre/post-dispatch failures, HTTP slow-drip timeouts, escaped report text, trace
tampering, and official SDK subprocess integration.

## Limits and publication

The recovery strategies are scripted. There is no model comparison, token/cost
accounting, stochastic scheduling, distributed execution, or durable event store.
Only the reference ledger measures committed side effects. Traces contain raw
arguments and content without automatic redaction; use synthetic data and
disposable servers. Read [SECURITY.md](SECURITY.md) before attaching an upstream
command, which runs with the current process's permissions.

The [15-stage release plan](docs/release-plan.md) maps each local branch to a focused
PR and its validation. Contributions
follow [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [Apache-2.0](LICENSE).
