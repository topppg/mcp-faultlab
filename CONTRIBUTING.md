# Contributing

Use Python 3.11 or 3.12 and uv 0.9.7 or newer. Runtime code uses the standard
library; the optional `compatibility` extra pins the official MCP SDK for tests.

```sh
uv sync --frozen --extra compatibility
uv run --extra compatibility ruff check .
uv run --extra compatibility ruff format --check .
uv run --extra compatibility pytest -q
uv run --extra compatibility mcp-faultlab suite examples/suite.json --out reports/check
uv build
```

Add a deterministic synthetic case and a negative control when changing fault
semantics. Document whether a fault occurs before or after dispatch. Keep protocol
errors, MCP tool errors, and unknown transport outcomes separate. Never infer that
a timeout rolled back a side effect. Do not add live API calls to the default suite.

Protocol changes need an explicit supported-version statement and compatibility
tests with a pinned official SDK. Cross-platform subprocess support is currently
tested on macOS locally and configured for Linux CI; Windows is not supported.

For staged publication, follow [the release plan](docs/release-plan.md). Each branch
is one feature commit on the previous stage. Use regular merge commits so later
branches keep valid ancestry. No branches have been pushed from this local draft.
