"""Portable JSON, JUnit XML, and self-contained HTML reports; all text is escaped."""

from __future__ import annotations

import html
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .contracts import evaluate
from .trace import validate_trace


def summarize_trace(trace: dict[str, Any]) -> dict[str, Any]:
    trace = validate_trace(trace)
    events = trace["events"]
    violations = evaluate(events, trace["scenario"].get("contracts", {}))
    outcomes = [e["outcome"] for e in events if e["kind"] == "outcome"]
    return {
        "scenario": trace["scenario"]["name"],
        "strategy": "external-trace",
        "passed": not violations,
        "task_success": None,
        "scope": "Contract audit only; task completion and real side effects are not inferred",
        "metrics": {
            "calls": len(outcomes),
            "dispatches": sum(e["kind"] == "dispatch" for e in events),
            "faults": sum(e["kind"] == "fault" for e in events),
            "transport_failures": sum(o["failure"] is not None for o in outcomes),
            "tool_errors": sum(bool(o["result"] and o["result"].get("isError")) for o in outcomes),
            "virtual_elapsed_ms": events[-1]["time_ms"] if events else 0,
            "contract_violations": len(violations),
        },
        "violations": violations,
        "trace_sha256": trace["sha256"],
    }


def render_html(report: dict[str, Any]) -> str:
    name = html.escape(str(report.get("scenario", "FaultLab run")))
    outcome = "PASS" if report.get("passed") else "FAIL"
    data = html.escape(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>{name} — MCP FaultLab</title><style>
body{{font:16px/1.6 system-ui,sans-serif;max-width:1000px;margin:3rem auto;padding:0 1rem;color:#182333;background:#f5f7fb}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:1.5rem;border:1px solid #cbd5e1;border-radius:8px}}
h1{{line-height:1.2}}.result{{font-weight:700}}small{{color:#475569}}
</style></head><body><h1>{name}</h1><p class="result">{outcome}</p>
<p>Synthetic test results. Injected virtual delay is not wall-clock latency.</p>
<pre>{data}</pre><small>MCP FaultLab · local artifact · no external assets or scripts</small></body></html>"""


def render_junit(report: dict[str, Any]) -> str:
    passed = bool(report.get("passed"))
    suite = ET.Element("testsuite", name="mcp-faultlab", tests="1", failures="0" if passed else "1")
    case = ET.SubElement(
        suite,
        "testcase",
        name=str(report.get("scenario", "run")),
        classname=str(report.get("strategy", "external")),
    )
    if not passed:
        failure = ET.SubElement(case, "failure", message="FaultLab run did not meet its checks")
        failure.text = json.dumps(
            {"violations": report.get("violations", []), "metrics": report.get("metrics", {})},
            allow_nan=False,
        )
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def write_reports(report: dict[str, Any], directory: str | Path) -> list[Path]:
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "summary.json": json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        "report.html": render_html(report),
        "junit.xml": render_junit(report),
    }
    for name, contents in artifacts.items():
        (output / name).write_text(contents, encoding="utf-8")
    return [output / name for name in artifacts]
