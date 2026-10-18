# Protocol and transport scope

MCP FaultLab targets the **2025-11-25** tool subset. The
[2025-11-25 transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
defines newline-framed stdio and HTTP responses that may use JSON or SSE. The
[tool specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
distinguishes execution failures (`result.isError`) from JSON-RPC protocol errors.
The harness preserves that distinction.

The proxy exposes `initialize`, `notifications/initialized`, `ping`, `tools/list`,
and `tools/call`. Its capabilities advertise tools only. Requests execute
sequentially, with unique IDs per stream. Upstream notifications can be skipped
within a bounded read loop, but are not forwarded. Server-to-client requests,
sampling, elicitation, resources, prompts, subscriptions, progress forwarding,
cancellation, task extensions, and multiplexed calls are unsupported. Terminating
the proxy closes its upstream; cancellation does not imply rollback.

The upstream HTTP adapter supports loopback JSON POST, initialization, version and
session headers, and notification acknowledgment. It rejects SSE, redirects, remote
addresses, and unsupported versions. GET, session DELETE, SSE resumption, OAuth, and
the legacy HTTP+SSE transport are not implemented. It opens no HTTP listener.

The [2026-07-28 HTTP specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
is a different protocol version and is **not supported**. This is a small fault
testing implementation, not a transparent general MCP gateway.

## Independent compatibility evidence

The optional `compatibility` extra pins the official
[MCP Python SDK 1.30.0](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0).
Three subprocess tests verify an SDK client using the reference server, an SDK
client using the proxy in front of an SDK server, and FaultLab's client using an SDK
server. They cover initialization, tool discovery, successful invocation, and
execution-error decoding. They do not establish compatibility with SDK v2 or
every MCP feature. HTTP tests use a real local HTTP server, including explicit SSE
refusal, session headers, and slow-drip deadlines under HTTP/1.0 and HTTP/1.1.

## Fault timing

Injected `delay_ms` advances a virtual clock without sleeping. Real transport
timeouts use wall-clock deadlines and close the transport; those durations are not
included in deterministic trace latency metrics. JSON-RPC frames are capped at
1 MiB; trace files are capped at 10 MB when loaded. Non-finite numbers, duplicate
object keys, excessive JSON nesting, malformed envelopes, and mismatched response
IDs are rejected.

The `timeout` scenario is a known pre-dispatch timeout. `response_loss` dispatches
the tool, discards the response, and leaves the outcome unknown to the caller.
`duplicate_execution` dispatches twice and emits one response. `crash` simulates a
persistent closed transport; it does not pretend to crash a remote operating
system. In proxy mode a transport fault ends the downstream stream without a fake
protocol response. The synthetic ledger is in memory and does not survive process
termination; durable reconciliation across a restart needs a separate test server.
