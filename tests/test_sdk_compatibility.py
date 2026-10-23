import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="install the pinned compatibility extra to run SDK integration")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from mcp_faultlab.trace import read_trace  # noqa: E402
from mcp_faultlab.transport import PROTOCOL_VERSION, StdioClient  # noqa: E402

ROOT = Path(__file__).parents[1]


def test_official_sdk_client_can_use_reference_server():
    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_faultlab", "reference-server"],
            env={"PYTHONPATH": str(ROOT / "src")},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=5)
            ) as client:
                initialized = await client.initialize()
                assert initialized.protocolVersion == PROTOCOL_VERSION
                assert len((await client.list_tools()).tools) == 3
                result = await client.call_tool("ledger.charge", {"operation": "sdk", "amount": 5})
                assert result.structuredContent["entry"]["amount"] == 5
                invalid = await client.call_tool(
                    "ledger.charge", {"operation": "sdk", "amount": -1}
                )
                assert invalid.isError

    asyncio.run(exercise())


def test_proxy_between_official_sdk_client_and_server(tmp_path):
    scenario = tmp_path / "scenario.json"
    trace = tmp_path / "trace.json"
    scenario.write_text(json.dumps({"schema_version": 1, "name": "sdk-proxy", "rules": []}))

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "mcp_faultlab",
                "proxy",
                "--scenario",
                str(scenario),
                "--trace",
                str(trace),
                "--",
                sys.executable,
                str(ROOT / "tests/fixtures/sdk_server.py"),
            ],
            env={"PYTHONPATH": str(ROOT / "src")},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=5)
            ) as client:
                await client.initialize()
                assert (await client.list_tools()).tools[0].name == "echo"
                result = await client.call_tool("echo", {"message": "synthetic"})
                assert result.structuredContent == {"echo": "synthetic"}

    asyncio.run(exercise())
    assert len([e for e in read_trace(trace)["events"] if e["kind"] == "call"]) == 1


def test_own_client_uses_official_sdk_server():
    with StdioClient([sys.executable, str(ROOT / "tests/fixtures/sdk_server.py")]) as client:
        assert client.initialize()["protocolVersion"] == PROTOCOL_VERSION
        result = client.request("tools/call", {"name": "echo", "arguments": {"message": "hello"}})
        assert result["structuredContent"] == {"echo": "hello"}
