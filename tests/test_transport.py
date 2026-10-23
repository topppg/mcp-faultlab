import json
import sys
import time

import pytest

from mcp_faultlab.engine import ProtocolError, TransportError
from mcp_faultlab.transport import StdioClient, decode_response


def test_real_subprocess_roundtrip_and_cleanup():
    script = "import sys,json\nfor line in sys.stdin:\n d=json.loads(line)\n if 'id' in d: print(json.dumps({'jsonrpc':'2.0','id':d['id'],'result':{'echo':d['method']}}),flush=True)"
    with StdioClient([sys.executable, "-u", "-c", script]) as client:
        assert client.request("tools/list") == {"echo": "tools/list"}
        process = client.process
    assert process.poll() is not None


def test_wrong_response_id_is_never_accepted():
    with pytest.raises(TransportError, match="id"):
        decode_response(b'{"jsonrpc":"2.0","id":99,"result":{}}', 1)


def test_protocol_error_is_distinct_from_tool_execution_error():
    with pytest.raises(ProtocolError) as raised:
        decode_response(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "unknown"}}
            ).encode(),
            1,
        )
    assert raised.value.error["code"] == -32601
    assert decode_response(b'{"jsonrpc":"2.0","id":1,"result":{"isError":true}}', 1)["isError"]


def test_read_deadline_kills_child_and_reports_unknown_outcome():
    start = time.monotonic()
    with StdioClient([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1) as client:
        with pytest.raises(TransportError, match="timeout"):
            client.request("tools/list")
        assert client.process.poll() is not None
    assert time.monotonic() - start < 3


def test_write_deadline_when_child_never_reads():
    start = time.monotonic()
    with StdioClient([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1) as client:
        with pytest.raises(TransportError, match="write_timeout"):
            client.request("tools/call", {"payload": "x" * 500_000})
    assert time.monotonic() - start < 3
