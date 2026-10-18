# Fifteen staged pull requests

The implementation was prepared locally as a bootstrap commit followed by the
fifteen feature stages below. Each stage adds one commit on its predecessor.
The public `main` advances through regular PR merges. Commit dates reflect actual
development; the PR history records publication progress.

## Publication rules

1. Decide the remote name and public scope before creating it. Publish bootstrap
   `main` first; activate branch protection and require reviewed PRs/checks suitable
   for the actual stage. Early stages do not yet include the final CI workflow.
2. Push **only the next stage branch**. Compare it against the current remote main:
   there must be exactly one unpublished feature commit. Review the effective diff,
   run that stage's tests/build, and open one focused PR.
3. Merge using a **regular merge commit**, never squash or rebase. Delete only the
   merged remote feature branch. Fetch main before advancing the next stage.
4. Keep at most one open staged PR. Do not push later branches or the whole branch
   collection. Publication over time must reflect real incremental work; do not
   backdate commits or describe unfinished features as available on early stages.
5. If a stage fails validation, stop and repair that stage before publishing it.
   Do not bypass protection or hide a failing check. The root workspace audit tool
   can verify archived branch snapshots without switching this checkout.

## Ordered branches and effective changes

`uv run pytest -q` works independently in each stage from 01 onward. `uv build`
builds that stage's package. The test counts below are the recorded local counts
when each stage was implemented. The final stage adds optional SDK tests and
formatting; earlier stages are not expected to satisfy final-stage Ruff rules.

| Stage / local branch | Focused PR title and effective diff | Stage validation |
| --- | --- | --- |
| `stage/01-scenario-schema` | Add strict versioned scenario model and package skeleton. Packaging, locked test tools, parser, invalid-input controls. | pytest: 12; build |
| `stage/02-deterministic-matching` | Add virtual clock and occurrence-based matching. Tool/global counters, argument subset filtering, first-rule semantics. | pytest: 15; build |
| `stage/03-pre-execution-faults` | Add tool errors, permission denials, rate limits, and pre-execution timeouts. Separate result/error outcomes and event recording. | pytest: 19; build |
| `stage/04-result-corruption` | Add malformed structured content and stale result substitution after dispatch. Snapshot isolation controls. | pytest: 22; build |
| `stage/05-uncertain-outcomes` | Add response loss, duplicate execution, and persistent simulated transport failure. Preserve dispatch side effects. | pytest: 25; build |
| `stage/06-trace-replay` | Add canonical traces, SHA-256 integrity, size limits, and exact offline replay. Divergence and tamper controls. | pytest: 29; build |
| `stage/07-ledger-reference-server` | Add synthetic stateful ledger backend with reconciliation, idempotency keys, conflict rejection, and duplicate-effect accounting. The stdio server arrives in stage 11. | pytest: 36; build |
| `stage/08-trace-contracts` | Audit exact prior approvals, allowlists, retry ceilings, duplicate dispatches, and budgets. Validate contract configuration at load. | pytest: 43; build |
| `stage/09-recovery-comparison` | Compare naive retry and keyed reconciliation under lost confirmation. Explicit completion and duplicate metrics. | pytest: 52; build |
| `stage/10-stdio-transport` | Add bounded subprocess JSON-RPC transport. Read/write deadlines, ID correlation, protocol errors, and child cleanup. | pytest: 57; build |
| `stage/11-stdio-proxy-cli` | Add stdio proxy, reference endpoint, and doctor CLI. Lifecycle, tool calls, and lost-response subprocess tests. | pytest: 60; doctor; build |
| `stage/12-bounded-http-transport` | Add loopback JSON POST upstream. Session/version headers, bounded frames, SSE refusal, real local HTTP tests. | pytest: 68; build |
| `stage/13-portable-reports` | Add escaped self-contained HTML, JSON, JUnit, and trace audit CLI. Explicit contract-only report scope. | pytest: 70; build |
| `stage/14-scenario-suites` | Add demo/suite CLI, nine scenarios and 18 expectations; reject invalid JSON and fix HTTP slow-drip deadlines. | pytest: 78; suite: 18/18; build |
| `stage/15-docs-ci-release` | Polish release docs, CI, SDK compatibility, and trace validation. Professional README and measured results, protocol/security/contribution/release guides, Python 3.11/3.12 CI, pinned SDK integration, offline replay CLI, robust input checks, and consistent formatting. | full checks below |

## Final release gate

```sh
uv sync --frozen --extra compatibility
uv run --extra compatibility ruff check .
uv run --extra compatibility ruff format --check .
uv run --extra compatibility pytest -q
uv run --extra compatibility mcp-faultlab demo --out reports/comparison
uv run --extra compatibility mcp-faultlab suite examples/suite.json --out reports/suite
uv build
git status --short
```

The final tests passed 89 checks locally on both Python 3.11.14 and 3.12.12, including three real subprocess
interoperability tests with official MCP SDK 1.30.0. The demonstration produced one
safe charge and zero duplicates versus two naive charges and one duplicate. The
18-case suite matched all expectations. The Actions tab records live CI results
once the final-stage workflow is published.

Keep the public noreply identity already configured in this repository. Before
opening a public PR, inspect author metadata, synthetic fixtures, raw traces,
README statements, and protocol version limits. No push or scheduling is implied
by this document.
