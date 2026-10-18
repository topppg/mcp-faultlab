# Security and data handling

MCP FaultLab deliberately causes tool failures. Run the supplied synthetic ledger
or disposable test servers. An upstream command is executed with the current
process's permissions and inherited environment. The proxy is not a sandbox.

Traces contain raw tool names, arguments, returned content, and trusted approval
events. They are not automatically redacted. Keep real credentials and private
conversations out of tests; treat trace files as sensitive. Raw upstream stderr is
discarded. HTML output escapes text, runs no scripts, and loads no external assets.
SHA-256 detects accidental changes, not a malicious rewrite with a new hash.

The HTTP adapter is an outbound loopback client. It does not expose a server and
does not implement authentication, TLS, or public endpoints. It accepts literal
loopback HTTP addresses, rejects credentials and query strings, does not follow
redirects, caps frames at 1 MiB, and uses bounded socket operations. Avoid binding
test servers to public interfaces. A transport timeout means the outcome may be
unknown: upstream work is not rolled back.

Contracts audit an event stream. Approval events come from a trusted test driver;
tool annotations and tool output never grant approval. These checks do not provide
authorization enforcement against an untrusted agent process or host.

Report sensitive vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/topppg/mcp-faultlab/security/advisories/new).
Use synthetic reproductions and omit credentials. Do not include secrets in public issues.
