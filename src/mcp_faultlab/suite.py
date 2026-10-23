"""Run explicit scenario expectations. Expected negative controls count as passing cases."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .demo import run_demo
from .jsonutil import loads
from .report import write_reports
from .scenario import Scenario, fields, string


def run_suite(path: str | Path, output: str | Path) -> dict[str, Any]:
    path = Path(path)
    plan = fields(loads(path.read_text()), {"schema_version", "name", "cases"}, "suite")
    if type(plan.get("schema_version")) is not int or plan["schema_version"] != 1:
        raise ValueError("suite.schema_version must be 1")
    name = string(plan.get("name"), "suite.name")
    if not isinstance(plan.get("cases"), list) or not plan["cases"]:
        raise ValueError("suite requires at least one case")
    cases = []
    names = set()
    # Validate the entire plan before generating any artifacts.
    for raw in plan["cases"]:
        case = fields(raw, {"name", "scenario", "strategy", "expect_pass"}, "case")
        case_name = string(case.get("name"), "case.name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", case_name) or case_name in names:
            raise ValueError("case names must be unique safe directory names")
        names.add(case_name)
        if (
            case.get("strategy") not in {"naive", "safe"}
            or type(case.get("expect_pass")) is not bool
        ):
            raise ValueError("case requires strategy and boolean expect_pass")
        scenario = Scenario.load(path.parent / string(case.get("scenario"), "case.scenario"))
        cases.append((case, scenario))
    results = []
    for case, scenario in cases:
        report = run_demo(case["strategy"], scenario)
        write_reports(report, Path(output) / case["name"])
        results.append(
            {
                "name": case["name"],
                "expected_pass": case["expect_pass"],
                "actual_pass": report["passed"],
                "expectation_met": report["passed"] == case["expect_pass"],
                "metrics": report["metrics"],
                "trace_sha256": report["trace"]["sha256"],
            }
        )
    return {
        "name": name,
        "cases": results,
        "passed": all(r["expectation_met"] for r in results),
        "matched": sum(r["expectation_met"] for r in results),
        "total": len(results),
    }
