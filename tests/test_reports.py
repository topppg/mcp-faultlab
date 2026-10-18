import json
import xml.etree.ElementTree as ET

import pytest

from mcp_faultlab.demo import run_demo
from mcp_faultlab.report import render_html, render_junit, summarize_trace, write_reports
from mcp_faultlab.trace import digest


def test_html_and_junit_escape_untrusted_text():
    report = {
        "scenario": '<script>alert("x")</script>',
        "strategy": '"<&',
        "passed": False,
        "violations": [{"message": "</pre><img src=x onerror=alert(1)>"}],
    }
    page = render_html(report)
    assert "<script>" not in page
    assert "<img" not in page
    assert "&lt;script&gt;" in page
    assert "default-src 'none'" in page
    xml = ET.fromstring(render_junit(report))
    assert xml.find("testcase").attrib["name"] == report["scenario"]
    assert xml.attrib["failures"] == "1"


def test_reports_round_trip_and_contract_scope(tmp_path):
    demo = run_demo()
    summary = summarize_trace(demo["trace"])
    assert summary["passed"]
    assert summary["task_success"] is None
    assert summary["metrics"]["transport_failures"] == 1
    paths = write_reports(summary, tmp_path)
    assert len(paths) == 3
    assert json.loads((tmp_path / "summary.json").read_text()) == summary
    assert ET.parse(tmp_path / "junit.xml").getroot().attrib["failures"] == "0"


def test_report_rejects_rehashed_outcomes_with_missing_fields():
    for field in ("failure", "uncertain", "protocol_error", "result"):
        trace = run_demo()["trace"]
        successful = next(
            event
            for event in trace["events"]
            if event["kind"] == "outcome" and event["outcome"]["result"] is not None
        )
        del successful["outcome"][field]
        trace["sha256"] = digest({key: value for key, value in trace.items() if key != "sha256"})
        with pytest.raises(ValueError, match="invalid outcome fields"):
            summarize_trace(trace)
