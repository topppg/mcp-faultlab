import json
import xml.etree.ElementTree as ET

from mcp_faultlab.demo import run_demo
from mcp_faultlab.report import render_html, render_junit, summarize_trace, write_reports


def test_html_and_junit_escape_untrusted_text():
    report = {"scenario": '<script>alert("x")</script>', "strategy": '"<&', "passed": False,
              "violations": [{"message": "</pre><img src=x onerror=alert(1)>"}]}
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
