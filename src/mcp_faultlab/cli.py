"""CLI stdout is JSON; protocol mode stdout contains JSON-RPC messages only."""

from __future__ import annotations

import argparse
import json
import sys

from .proxy import ToolEndpoint, serve
from .http_transport import JsonHttpClient
from .report import summarize_trace, write_reports
from .scenario import Scenario
from .trace import make_trace, read_trace, write_trace
from .transport import PROTOCOL_VERSION, StdioClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcp-faultlab")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("doctor", help="Print offline capability and runtime information")
    commands.add_parser("reference-server", help="Serve the synthetic in-memory ledger over stdio")
    report = commands.add_parser("report", help="Audit a captured trace and write portable reports")
    report.add_argument("--trace", required=True)
    report.add_argument("--out", required=True)
    proxy = commands.add_parser("proxy", help="Proxy the supported MCP stdio tool subset")
    proxy.add_argument("--scenario", required=True)
    proxy.add_argument("--trace", required=True)
    proxy.add_argument("--timeout", type=float, default=5.0)
    proxy.add_argument("--http-url", help="Loopback JSON POST upstream; SSE is unsupported")
    proxy.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by upstream argv")
    args = parser.parse_args(argv)
    try:
        if args.action == "doctor":
            print(json.dumps({"python": sys.version.split()[0], "protocol_version": PROTOCOL_VERSION,
                              "network_required": False, "runtime_dependencies": 0,
                              "transport_scope": "sequential stdio tools subset"}))
        elif args.action == "reference-server":
            serve(ToolEndpoint(Scenario("reference-ledger")), sys.stdin.buffer, sys.stdout.buffer)
        elif args.action == "report":
            report = summarize_trace(read_trace(args.trace))
            write_reports(report, args.out)
            print(json.dumps(report))
            return 0 if report["passed"] else 1
        elif args.action == "proxy":
            scenario = Scenario.load(args.scenario)
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            if bool(command) == bool(args.http_url):
                raise ValueError("select exactly one upstream: argv after -- or --http-url")
            transport = (JsonHttpClient(args.http_url, timeout=args.timeout) if args.http_url
                         else StdioClient(command, timeout=args.timeout))
            with transport as upstream:
                endpoint = ToolEndpoint(scenario, upstream)
                try:
                    serve(endpoint, sys.stdin.buffer, sys.stdout.buffer)
                finally:
                    write_trace(args.trace, make_trace(endpoint.harness))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"mcp-faultlab: {exc}", file=sys.stderr)
        return 2
    return 0
