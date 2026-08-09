#!/usr/bin/env python3
"""Fill every panel of DASHBOARD-TEMPLATE.md from the report artifacts, and only from them.

The template defines the metric contract; this script is its producer. Each panel is
built by reading the artifact the template names for it, so no cell is ever typed from a
terminal scrollback and every number in a write-up traces to a file on disk.

Usage, from the repository root::

    python docs/testing/dashboard-extract.py                      filled panels, markdown
    python docs/testing/dashboard-extract.py --json                the same values, JSON
    python docs/testing/dashboard-extract.py --previous prev.json  fills the trend panel
    python docs/testing/dashboard-extract.py --require-all         missing artifact is fatal

Artifacts read, all relative to the repository root and all matched by ``.gitignore``:

    backend/coverage.xml                        Cobertura, gated packages, aggregate only
    backend/coverage.json                       coverage JSON, per-module and per-package
    backend/reports/junit.xml                   xunit2 result stream
    backend/reports/collect-only.txt            readiness output
    frontend/coverage/coverage-summary.json     Istanbul per-file summary
    frontend/coverage/lcov.info                 uncovered line numbers
    frontend/reports/jest-junit.xml             result stream
    frontend/reports/list-tests.txt             readiness output
    e2e/reports/e2e-junit.xml                   result stream
    e2e/reports/list-tests.txt                  readiness output
    e2e/test-results/                           failure evidence, present only on failure

Exit status: 0 when every panel it was asked for could be produced, 1 under
``--require-all`` when a contract artifact is absent. An absent artifact is always named
on stderr rather than silently rendered as an empty cell, because an empty cell in a
published dashboard reads as a measurement of zero.

Standard library only and Python 3.9 compatible, so it runs on the interpreter the
backend suite already pins without adding a dependency to any manifest.

@see docs/testing/DASHBOARD-TEMPLATE.md - the panels this fills and the gate contract.
@see docs/testing/DECISION-LOG.md - row D253 for why this exists rather than manual
    transcription, and how the per-layer partition is defined.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Artifact locations                                                          #
# --------------------------------------------------------------------------- #

BACKEND_COVERAGE_XML = "backend/coverage.xml"
BACKEND_COVERAGE_JSON = "backend/coverage.json"
BACKEND_JUNIT = "backend/reports/junit.xml"
BACKEND_COLLECT_ONLY = "backend/reports/collect-only.txt"

FRONTEND_COVERAGE_SUMMARY = "frontend/coverage/coverage-summary.json"
FRONTEND_LCOV = "frontend/coverage/lcov.info"
FRONTEND_JUNIT = "frontend/reports/jest-junit.xml"
FRONTEND_LIST_TESTS = "frontend/reports/list-tests.txt"

E2E_JUNIT = "e2e/reports/e2e-junit.xml"
E2E_LIST_TESTS = "e2e/reports/list-tests.txt"
E2E_TEST_RESULTS = "e2e/test-results"

MISSING = "not produced"

# --------------------------------------------------------------------------- #
# Contract constants - these mirror DASHBOARD-TEMPLATE.md section 3.1         #
# --------------------------------------------------------------------------- #

#: The four packages gate G1 measures, as ``--cov`` names them. G1 is ONE gate over
#: their aggregate, not four independent gates; per-package figures below are
#: measurements, and the template says so.
GATED_BACKEND_PACKAGES = ("app/core", "app/services", "app/tasks", "app/db")

#: G1 threshold in percent, compared against that aggregate.
G1_THRESHOLD = 90.0

#: The three packages gate G2 measures, as ``coverageThreshold`` keys name them. Each
#: IS an independent gate, because Jest declares one threshold group per path.
GATED_FRONTEND_PACKAGES = ("src/store", "src/schema", "src/services")

#: G2 threshold, applied to statements, branches, functions and lines alike.
G2_THRESHOLD = 80.0

#: Decimal places every percentage is rendered at, matching ``backend/.coveragerc``
#: ``precision`` and Istanbul's own two-decimal reporting.
PRECISION = 2

#: Backend layer partition, keyed on the ``classname`` prefix pytest writes. One
#: aggregate JUnit root cannot report a layer by itself, so the layer is derived from
#: the test id - the same string the layer is selected by on the command line.
BACKEND_LAYERS: Sequence[Tuple[str, str]] = (
    ("Backend unit", "tests.unit."),
    ("Backend integration", "tests.integration."),
    ("Backend dependency closure", "tests.test_dependency_closure"),
)

#: Frontend layer partition, keyed on the ``rootDir``-relative test path jest-junit
#: writes as ``classname``. Suites under these two prefixes are the component layer;
#: every other suite is a unit suite.
FRONTEND_COMPONENT_PREFIXES = ("src/components/", "src/pages/")

METRICS = ("statements", "branches", "functions", "lines")


# --------------------------------------------------------------------------- #
# Percentage rendering - one function per producer, deliberately              #
# --------------------------------------------------------------------------- #


def pct_backend(covered: int, total: int) -> Optional[float]:
    """Percentage the way coverage.py renders it, so a cell matches its own report.

    coverage.py rounds to the configured precision and then clamps, so a non-zero total
    never displays as 0 and an incomplete one never displays as 100. Reproducing that is
    what stops this panel disagreeing with the ``term-missing`` summary of the same run
    by one hundredth.

    An empty denominator returns ``None`` rather than 0 or 100: coverage of no
    statements is undefined, and either literal would be read as a measurement.
    """
    if total == 0:
        return None
    raw = covered * 100.0 / total
    near_zero = 1.0 / 10 ** PRECISION
    if 0 < raw < near_zero:
        return near_zero
    if (100.0 - near_zero) < raw < 100:
        return 100.0 - near_zero
    return round(raw, PRECISION)


def pct_frontend(covered: int, total: int) -> Optional[float]:
    """Percentage the way Istanbul renders it, which is truncation, not rounding.

    Measured: ``coverage-summary.json`` reports functions 47/67 as 70.14, where rounding
    gives 70.15. Jest's threshold messages use the same value, so a truncating cell is
    the one that agrees with both the summary file and a gate failure message.
    """
    if total == 0:
        return None
    scale = 10 ** PRECISION
    return int(covered * 100.0 / total * scale) / float(scale)


# --------------------------------------------------------------------------- #
# Small helpers                                                               #
# --------------------------------------------------------------------------- #


def fmt_pct(value: Optional[float], covered: int = -1, total: int = -1) -> str:
    """Render a percentage with its raw counts, so a reader can re-derive it."""
    if value is None:
        return "n/a (0 measurable)"
    if covered >= 0 and total >= 0:
        return "{0:.2f}% ({1}/{2})".format(value, covered, total)
    return "{0:.2f}%".format(value)


def verdict(value: Optional[float], threshold: float) -> str:
    """A threshold comparison at the same precision the runners compare at."""
    if value is None:
        return "n/a"
    return "PASS" if value >= threshold else "FAIL"


def norm(path: str) -> str:
    """Forward-slashed path, so Windows and Linux artifacts key and read identically."""
    return path.replace("\\", "/")


def read_text(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def parse_xml(path: str) -> Optional[ET.Element]:
    if not os.path.isfile(path):
        return None
    return ET.parse(path).getroot()


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Backend coverage - Cobertura                                                #
# --------------------------------------------------------------------------- #


def backend_coverage() -> Dict[str, object]:
    """Aggregate, per-package and per-module line coverage for the backend.

    Two artifacts, each for what it can honestly supply:

    * ``coverage.xml`` (Cobertura) for the **aggregate**, from its root ``lines-valid``
      and ``lines-covered``. It cannot supply anything finer here: with ``--cov`` given
      four package paths, coverage.py writes four ``<source>`` roots, one
      ``<package name=".">`` and bare basenames as ``filename``, so a per-module or
      per-package row read from it would be a guess about which root each file came from.
    * ``coverage.json`` for **per-module and per-package** rows, because it keys files by
      their full relative path, carries ``missing_lines`` outright, and states
      ``meta.branch_coverage`` - which is what lets the branch column below be reported
      as unmeasured rather than as zero.

    Both come from the same run, so the aggregate is cross-checked against the JSON
    totals and any disagreement is reported rather than silently preferred.
    """
    root = parse_xml(BACKEND_COVERAGE_XML)
    text = read_text(BACKEND_COVERAGE_JSON)
    if root is None and text is None:
        return {"available": False, "source": BACKEND_COVERAGE_XML}

    modules: List[Dict[str, object]] = []
    packages: Dict[str, List[int]] = {}
    branch_measured = False
    json_totals: Dict[str, object] = {}

    if text is not None:
        report = json.loads(text)
        branch_measured = bool(report.get("meta", {}).get("branch_coverage"))
        json_totals = report.get("totals", {})
        for filename, entry in sorted(report.get("files", {}).items()):
            path = norm(filename)
            summary = entry["summary"]
            statements = int(summary["num_statements"])
            hit = int(summary["covered_lines"])
            package_name = path.rsplit("/", 1)[0] if "/" in path else "."
            modules.append({
                "module": path,
                "package": package_name,
                "statements": statements,
                "covered": hit,
                "pct": pct_backend(hit, statements),
                "uncovered_lines": list(entry.get("missing_lines", [])),
            })
            bucket = packages.setdefault(package_name, [0, 0])
            bucket[0] += hit
            bucket[1] += statements

    if root is not None:
        valid = int(root.get("lines-valid", "0"))
        covered = int(root.get("lines-covered", "0"))
        aggregate_source = BACKEND_COVERAGE_XML
    else:
        valid = int(json_totals.get("num_statements", 0))
        covered = int(json_totals.get("covered_lines", 0))
        aggregate_source = BACKEND_COVERAGE_JSON

    mismatch = None
    if root is not None and json_totals:
        if (int(json_totals.get("num_statements", -1)) != valid
                or int(json_totals.get("covered_lines", -1)) != covered):
            mismatch = "coverage.xml reports {0}/{1}, coverage.json reports {2}/{3}".format(
                covered, valid, json_totals.get("covered_lines"),
                json_totals.get("num_statements"))

    package_rows = {
        name: {"covered": nums[0], "statements": nums[1],
               "pct": pct_backend(nums[0], nums[1])}
        for name, nums in sorted(packages.items())
    }

    return {
        "available": True,
        "source": aggregate_source,
        "module_source": BACKEND_COVERAGE_JSON if text is not None else None,
        "branch_measured": branch_measured,
        "aggregate_mismatch": mismatch,
        "aggregate": {"covered": covered, "statements": valid,
                      "pct": pct_backend(covered, valid)},
        "packages": package_rows,
        "modules": modules,
    }


# --------------------------------------------------------------------------- #
# Frontend coverage - Istanbul summary plus lcov                              #
# --------------------------------------------------------------------------- #


def _lcov_uncovered() -> Dict[str, List[int]]:
    """Uncovered line numbers per file, from ``DA:<line>,<hits>`` records in lcov."""
    text = read_text(FRONTEND_LCOV)
    if text is None:
        return {}
    uncovered: Dict[str, List[int]] = {}
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            current = norm(line[3:])
        elif line.startswith("DA:") and current is not None:
            number, _, hits = line[3:].partition(",")
            try:
                if int(hits) == 0:
                    uncovered.setdefault(current, []).append(int(number))
            except ValueError:
                continue
        elif line == "end_of_record":
            current = None
    return uncovered


def _relative_src(path: str) -> str:
    """``src/...`` key for a coverage-summary path, which is absolute."""
    forward = norm(path)
    index = forward.find("/src/")
    return forward[index + 1:] if index >= 0 else forward


def frontend_coverage() -> Dict[str, object]:
    """Per-package and per-module coverage from ``coverage-summary.json``.

    All four Istanbul metrics exist here, unlike the backend, so frontend rows carry all
    four. Package rows are summed from the files under each prefix, which is how Jest
    computes a per-path ``coverageThreshold`` group as well.
    """
    text = read_text(FRONTEND_COVERAGE_SUMMARY)
    if text is None:
        return {"available": False, "source": FRONTEND_COVERAGE_SUMMARY}

    data = json.loads(text)
    uncovered = _lcov_uncovered()

    modules: List[Dict[str, object]] = []
    for path, entry in data.items():
        if path == "total":
            continue
        key = _relative_src(path)
        row: Dict[str, object] = {"module": key}
        for metric in METRICS:
            measured = entry[metric]
            # Prefer the percentage the artifact itself reports, so a per-file row is
            # read rather than recomputed. Istanbul writes `"Unknown"` for an empty
            # denominator, which is not a number and falls through to pct_frontend's
            # explicit `None`.
            reported = measured.get("pct")
            row[metric] = {
                "covered": measured["covered"],
                "total": measured["total"],
                "pct": (float(reported)
                        if isinstance(reported, (int, float)) and measured["total"]
                        else pct_frontend(measured["covered"], measured["total"])),
            }
        matched = [v for k, v in uncovered.items() if norm(k).endswith(key)]
        row["uncovered_lines"] = matched[0] if matched else []
        modules.append(row)
    modules.sort(key=lambda item: str(item["module"]))

    def group(prefix: str) -> Dict[str, object]:
        out: Dict[str, object] = {}
        members = [m for m in modules if str(m["module"]).startswith(prefix)]
        for metric in METRICS:
            covered = sum(int(m[metric]["covered"]) for m in members)   # type: ignore[index]
            total = sum(int(m[metric]["total"]) for m in members)       # type: ignore[index]
            out[metric] = {"covered": covered, "total": total,
                           "pct": pct_frontend(covered, total)}
        return out

    prefixes = list(GATED_FRONTEND_PACKAGES) + ["src/components", "src/pages", "src/utils"]
    packages = {prefix: group(prefix + "/") for prefix in prefixes}

    total = data["total"]
    aggregate = {
        metric: {
            "covered": total[metric]["covered"],
            "total": total[metric]["total"],
            "pct": pct_frontend(total[metric]["covered"], total[metric]["total"]),
        }
        for metric in METRICS
    }

    return {
        "available": True,
        "source": FRONTEND_COVERAGE_SUMMARY,
        "aggregate": aggregate,
        "packages": packages,
        "modules": modules,
    }


# --------------------------------------------------------------------------- #
# Result streams - JUnit                                                      #
# --------------------------------------------------------------------------- #


def _case_state(case: ET.Element) -> str:
    if case.find("failure") is not None:
        return "failed"
    if case.find("error") is not None:
        return "error"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def junit(path: str) -> Dict[str, object]:
    """Totals, per-suite rows, per-case rows and the skip register from one stream."""
    root = parse_xml(path)
    if root is None:
        return {"available": False, "source": path}

    cases: List[Dict[str, str]] = []
    for case in root.iter("testcase"):
        skipped = case.find("skipped")
        cases.append({
            "classname": norm(case.get("classname", "")),
            "name": case.get("name", ""),
            "time": case.get("time", "0"),
            "state": _case_state(case),
            "skip_reason": (skipped.get("message", "") if skipped is not None else ""),
        })

    suites = [{
        "name": norm(suite.get("name", "")),
        "tests": int(suite.get("tests", "0")),
        "failures": int(suite.get("failures", "0")),
        "errors": int(suite.get("errors", "0")),
        "skipped": int(suite.get("skipped", "0")),
        "time": suite.get("time", "0"),
    } for suite in root.iter("testsuite")]

    def total(attr: str) -> int:
        value = root.get(attr)
        if value is not None:
            return int(value)
        return sum(int(suite[attr]) for suite in suites)   # type: ignore[arg-type]

    tests = total("tests")
    failures = total("failures")
    errors = total("errors")
    # jest-junit declares no `skipped` on the root, so it is summed from the suites.
    skipped = total("skipped")

    duration = root.get("time")
    if duration is None:
        duration = "{0:.3f}".format(sum(float(suite["time"]) for suite in suites))

    # A stream declaring zero cases is a discovery stub, not a run. Both `pytest
    # --collect-only` and `playwright test --list` write the configured reporters,
    # so either can leave a zero-case file exactly where a result stream belongs.
    # Reporting that as "0 tests, 0 failures" would read as a clean run, so it is
    # refused here the same way the workflow's verify steps refuse it.
    if tests == 0:
        return {
            "available": False,
            "source": path,
            "reason": ("declares zero test cases - this is a discovery stub, not a run. "
                       "Re-run the suite; a collection or --list command overwrote it."),
        }

    return {
        "available": True,
        "source": path,
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": tests - failures - errors - skipped,
        "time": duration,
        "suites": suites,
        "cases": cases,
        "skips": [c for c in cases if c["state"] == "skipped"],
    }


def layer_rows(stream: Dict[str, object],
               classify: Callable[[Dict[str, str]], Optional[str]]) -> List[Dict[str, object]]:
    """Partition one aggregate stream into layers by a stated, reproducible rule."""
    if not stream.get("available"):
        return []
    buckets: Dict[str, Dict[str, float]] = {}
    order: List[str] = []
    for case in stream["cases"]:   # type: ignore[index]
        layer = classify(case)
        if layer is None:
            continue
        if layer not in buckets:
            order.append(layer)
        bucket = buckets.setdefault(
            layer, {"tests": 0, "passed": 0, "failed": 0, "skipped": 0, "time": 0.0})
        bucket["tests"] += 1
        bucket["time"] += float(case["time"] or 0)
        state = case["state"]
        if state == "passed":
            bucket["passed"] += 1
        elif state == "skipped":
            bucket["skipped"] += 1
        else:
            bucket["failed"] += 1
    return [{
        "layer": layer,
        "tests": int(buckets[layer]["tests"]),
        "passed": int(buckets[layer]["passed"]),
        "failed": int(buckets[layer]["failed"]),
        "skipped": int(buckets[layer]["skipped"]),
        "time": "{0:.3f}".format(buckets[layer]["time"]),
    } for layer in sorted(order)]


def classify_backend(case: Dict[str, str]) -> Optional[str]:
    for label, prefix in BACKEND_LAYERS:
        if case["classname"].startswith(prefix):
            return label
    return "Backend other"


def classify_frontend(case: Dict[str, str]) -> Optional[str]:
    if case["classname"].startswith(FRONTEND_COMPONENT_PREFIXES):
        return "Frontend component"
    return "Frontend unit"


# --------------------------------------------------------------------------- #
# Readiness                                                                   #
# --------------------------------------------------------------------------- #

COLLECTED_RE = re.compile(r"(\d+)\s+tests?\s+collected")
ERRORS_RE = re.compile(r"(\d+)\s+errors?")
E2E_TOTAL_RE = re.compile(r"Total:\s+(\d+)\s+tests?\s+in\s+(\d+)\s+files?")


def backend_readiness() -> Dict[str, object]:
    """Collected count and error count from the retained ``--collect-only`` output."""
    text = read_text(BACKEND_COLLECT_ONLY)
    if text is None:
        return {"available": False, "source": BACKEND_COLLECT_ONLY}
    collected = COLLECTED_RE.search(text)
    errors = ERRORS_RE.search(text)
    return {
        "available": True,
        "source": BACKEND_COLLECT_ONLY,
        "collected": int(collected.group(1)) if collected else None,
        "errors": int(errors.group(1)) if errors else 0,
    }


def listed_count(path: str, pattern: str) -> Dict[str, object]:
    """Discovered-item count from a retained listing, plus any total line it carries."""
    text = read_text(path)
    if text is None:
        return {"available": False, "source": path}
    matches = [line for line in text.splitlines() if re.search(pattern, line)]
    declared = E2E_TOTAL_RE.search(text)
    return {
        "available": True,
        "source": path,
        "count": len(matches),
        "declared_tests": int(declared.group(1)) if declared else None,
        "declared_files": int(declared.group(2)) if declared else None,
    }


# --------------------------------------------------------------------------- #
# E2E failure evidence                                                        #
# --------------------------------------------------------------------------- #


def e2e_evidence() -> Dict[str, List[str]]:
    """Per-test failure-artifact directories, if any were retained."""
    found: Dict[str, List[str]] = {}
    if not os.path.isdir(E2E_TEST_RESULTS):
        return found
    for entry in sorted(os.listdir(E2E_TEST_RESULTS)):
        directory = os.path.join(E2E_TEST_RESULTS, entry)
        if os.path.isdir(directory):
            found[entry] = sorted(os.listdir(directory))
    return found


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #


def render(data: Dict[str, object]) -> str:
    be_cov: Dict[str, object] = data["backend_coverage"]      # type: ignore[assignment]
    fe_cov: Dict[str, object] = data["frontend_coverage"]     # type: ignore[assignment]
    be: Dict[str, object] = data["backend_junit"]             # type: ignore[assignment]
    fe: Dict[str, object] = data["frontend_junit"]            # type: ignore[assignment]
    e2e: Dict[str, object] = data["e2e_junit"]                # type: ignore[assignment]
    ready: Dict[str, object] = data["backend_readiness"]      # type: ignore[assignment]
    fe_ready: Dict[str, object] = data["frontend_readiness"]  # type: ignore[assignment]
    e2e_ready: Dict[str, object] = data["e2e_readiness"]      # type: ignore[assignment]
    previous: Dict[str, object] = data.get("previous") or {}  # type: ignore[assignment]

    out: List[str] = [
        "# Test Observability Dashboard - filled from artifacts",
        "",
        "Produced by `docs/testing/dashboard-extract.py`. Every value below was read from "
        "the artifact named beside it; nothing here was transcribed by hand.",
        "",
    ]

    agg = be_cov.get("aggregate") if be_cov.get("available") else None

    def counts(stream: Dict[str, object]) -> str:
        if not stream.get("available"):
            return MISSING
        return "{0} / {1} / {2} / {3}".format(stream["tests"], stream["passed"],
                                              stream["failures"], stream["skipped"])

    # 1.1 KPI header ------------------------------------------------------- #
    out.append("## 1.1 Current run")
    out.append("")
    if fe_cov.get("available"):
        gated = {metric: [0, 0] for metric in METRICS}
        for prefix in GATED_FRONTEND_PACKAGES:
            group = fe_cov["packages"][prefix]    # type: ignore[index]
            for metric in METRICS:
                gated[metric][0] += group[metric]["covered"]
                gated[metric][1] += group[metric]["total"]
        k2 = " / ".join("{0} {1}".format(metric[:4],
                                         fmt_pct(pct_frontend(v[0], v[1]), v[0], v[1]))
                        for metric, v in gated.items())
    else:
        k2 = MISSING
    out.append(table(
        ["#", "KPI", "Source artifact", "Target", "Value"],
        [
            ["K1", "Backend line coverage, aggregate of the four gated packages",
             BACKEND_COVERAGE_XML, ">= 90%",
             fmt_pct(agg["pct"], agg["covered"], agg["statements"]) if agg else MISSING],
            ["K2", "Frontend coverage, the three gated packages combined",
             FRONTEND_COVERAGE_SUMMARY, ">= 80% on all four metrics", k2],
            ["K3", "Backend test cases: total / passed / failed / skipped",
             BACKEND_JUNIT, "0 failed", counts(be)],
            ["K4", "Frontend test cases: total / passed / failed / skipped",
             FRONTEND_JUNIT, "0 failed", counts(fe)],
            ["K5", "Backend collection errors", BACKEND_COLLECT_ONLY, "0",
             str(ready.get("errors")) if ready.get("available") else MISSING],
            ["K6", "E2E test cases: total / passed / failed / skipped",
             E2E_JUNIT, "0 failed", counts(e2e)],
            ["K6b", "E2E spec files", E2E_JUNIT, "census, no target",
             str(len(e2e.get("suites", []))) if e2e.get("available") else MISSING],
            ["K7", "Wall-clock seconds, backend / frontend / e2e",
             "the root `time` attribute of each result stream", "record for trend",
             "{0} / {1} / {2}".format(be.get("time", MISSING), fe.get("time", MISSING),
                                      e2e.get("time", MISSING))],
        ]))
    out.append("")

    # 3.1 gate verdicts ---------------------------------------------------- #
    out.append("## 3.1 Gate verdicts")
    out.append("")
    gate_rows: List[Sequence[object]] = []
    gate_rows.append(["G1", "one gate over the aggregate of "
                      + ", ".join(GATED_BACKEND_PACKAGES),
                      ">= {0:.0f}% lines".format(G1_THRESHOLD),
                      fmt_pct(agg["pct"], agg["covered"], agg["statements"]) if agg else MISSING,
                      verdict(agg["pct"], G1_THRESHOLD) if agg else MISSING])
    if fe_cov.get("available"):
        for prefix in GATED_FRONTEND_PACKAGES:
            group = fe_cov["packages"][prefix]    # type: ignore[index]
            measured = [group[metric]["pct"] for metric in METRICS
                        if group[metric]["pct"] is not None]
            gate_rows.append(["G2", prefix + " (its own threshold group)",
                              ">= {0:.0f}% on all four".format(G2_THRESHOLD),
                              " / ".join(fmt_pct(group[m]["pct"], group[m]["covered"],
                                                 group[m]["total"]) for m in METRICS),
                              verdict(min(measured) if measured else None, G2_THRESHOLD)])
    if ready.get("available"):
        gate_rows.append(["G4", "backend collection integrity", "0 errors",
                          "{0} collected, {1} errors".format(ready.get("collected"),
                                                             ready.get("errors")),
                          "PASS" if ready.get("errors") == 0 else "FAIL"])
    out.append(table(["Gate", "Scope", "Threshold", "Measured", "Verdict"], gate_rows))
    out.append("")

    # 6.1 coverage by package --------------------------------------------- #
    out.append("## 6.1 Coverage by package")
    out.append("")
    out.append("Backend packages are **measurements**, not gates: G1 is a single gate over "
               "their aggregate, so a package row has no independent verdict to report.")
    out.append("")
    module_source_pkg = str(be_cov.get("module_source") or BACKEND_COVERAGE_XML)
    pkg_rows: List[Sequence[object]] = []
    if be_cov.get("available"):
        for name, group in be_cov["packages"].items():    # type: ignore[index]
            pkg_rows.append([name, "measured; gated only through the G1 aggregate",
                             fmt_pct(group["pct"], group["covered"], group["statements"]),
                             "n/a", module_source_pkg])
    if fe_cov.get("available"):
        for prefix, group in fe_cov["packages"].items():  # type: ignore[index]
            gated = prefix in GATED_FRONTEND_PACKAGES
            measured = [group[metric]["pct"] for metric in METRICS
                        if group[metric]["pct"] is not None]
            pkg_rows.append([prefix, "G2 gated" if gated else "measured, not gated",
                             " / ".join(fmt_pct(group[m]["pct"], group[m]["covered"],
                                                group[m]["total"]) for m in METRICS),
                             verdict(min(measured) if measured else None, G2_THRESHOLD)
                             if gated else "n/a",
                             FRONTEND_COVERAGE_SUMMARY])
    out.append(table(["Package", "Gate status", "Measured", "Verdict", "Source"], pkg_rows))
    out.append("")

    # 6.2 coverage by module ---------------------------------------------- #
    out.append("## 6.2 Coverage by module")
    out.append("")
    module_source = str(be_cov.get("module_source") or BACKEND_COVERAGE_JSON)
    branch_cell = "measured" if be_cov.get("branch_measured") else "not measured"
    out.append("Backend rows are line-only: `{0}` records `meta.branch_coverage` as {1}, "
               "and coverage.py emits no function metric at all, so those two columns are "
               "frontend-only and say so rather than showing a zero."
               .format(module_source, bool(be_cov.get("branch_measured"))))
    out.append("")
    if be_cov.get("aggregate_mismatch"):
        out.append("**The two backend producers disagree**: "
                   + str(be_cov["aggregate_mismatch"])
                   + ". Re-run the suite before quoting either.")
        out.append("")
    mod_rows: List[Sequence[object]] = []
    if be_cov.get("available"):
        for row in be_cov["modules"]:    # type: ignore[index]
            rendered = fmt_pct(row["pct"], row["covered"], row["statements"])
            mod_rows.append([row["module"], rendered, branch_cell, "not measured",
                             rendered,
                             ", ".join(str(n) for n in row["uncovered_lines"]) or "-"])
    if fe_cov.get("available"):
        for row in fe_cov["modules"]:    # type: ignore[index]
            mod_rows.append([row["module"]]
                            + [fmt_pct(row[m]["pct"], row[m]["covered"], row[m]["total"])
                               for m in METRICS]
                            + [", ".join(str(n) for n in row["uncovered_lines"]) or "-"])
    out.append(table(["Module", "Statements", "Branches", "Functions", "Lines",
                      "Uncovered lines"], mod_rows))
    out.append("")

    # 6.3 test health by layer -------------------------------------------- #
    out.append("## 6.3 Test health by layer")
    out.append("")
    out.append("Each layer is a partition of one aggregate result stream, by the rule in "
               "`BACKEND_LAYERS` and `FRONTEND_COMPONENT_PREFIXES` at the top of the "
               "extractor: backend by `classname` prefix, frontend by test-file prefix.")
    out.append("")
    health_rows: List[Sequence[object]] = []
    for row in layer_rows(be, classify_backend):
        health_rows.append([row["layer"], row["tests"], row["passed"], row["failed"],
                            row["skipped"], row["time"], BACKEND_JUNIT])
    for row in layer_rows(fe, classify_frontend):
        health_rows.append([row["layer"], row["tests"], row["passed"], row["failed"],
                            row["skipped"], row["time"], FRONTEND_JUNIT])
    if e2e.get("available"):
        health_rows.append(["End-to-end", e2e["tests"], e2e["passed"], e2e["failures"],
                            e2e["skipped"], e2e["time"], E2E_JUNIT])
    out.append(table(["Layer", "Total", "Passed", "Failed", "Skipped", "Duration",
                      "JUnit artifact"], health_rows))
    out.append("")

    out.append("### Skip register")
    out.append("")
    out.append("A dash in the reason column is not a missing reason. pytest records a skip "
               "reason as the `message` attribute of `<skipped>`; jest-junit and Playwright "
               "do not, and those layers carry the reason in the suite or test title "
               "instead - which is where the `SKIPPED: ...` text in the first column comes "
               "from.")
    out.append("")
    skip_rows: List[Sequence[object]] = []
    for stream in (be, fe, e2e):
        if not stream.get("available"):
            continue
        for case in stream["skips"]:    # type: ignore[index]
            skip_rows.append([case["classname"] + " :: " + case["name"],
                              (case["skip_reason"] or "-").replace("|", "\\|"),
                              stream["source"]])
    out.append(table(["Skipped test", "Reason as recorded in the stream", "Source"],
                     skip_rows or [["none", "-", "-"]]))
    out.append("")

    # 6.4 readiness ------------------------------------------------------- #
    out.append("## 6.4 Readiness")
    out.append("")
    collected_matches = (ready.get("available") and be.get("available")
                         and ready.get("collected") == be.get("tests"))
    e2e_matches = (e2e_ready.get("available") and e2e.get("available")
                   and e2e_ready.get("declared_tests") == e2e.get("tests"))
    out.append(table(
        ["Check", "Source artifact", "Expected", "Actual", "Verdict"],
        [
            ["Backend collection errors", BACKEND_COLLECT_ONLY, "0 errors",
             str(ready.get("errors")) if ready.get("available") else MISSING,
             ("PASS" if ready.get("errors") == 0 else "FAIL")
             if ready.get("available") else MISSING],
            ["Backend tests collected", BACKEND_COLLECT_ONLY,
             "equals the backend total in 6.3",
             str(ready.get("collected")) if ready.get("available") else MISSING,
             ("PASS" if collected_matches else "FAIL")
             if ready.get("available") and be.get("available") else MISSING],
            ["Frontend test files discovered", FRONTEND_LIST_TESTS, "> 0",
             str(fe_ready.get("count")) if fe_ready.get("available") else MISSING,
             ("PASS" if int(fe_ready.get("count") or 0) > 0 else "FAIL")
             if fe_ready.get("available") else MISSING],
            ["E2E tests discovered", E2E_LIST_TESTS, "equals the E2E total in 6.3",
             "{0} in {1} files".format(e2e_ready.get("declared_tests"),
                                       e2e_ready.get("declared_files"))
             if e2e_ready.get("available") else MISSING,
             ("PASS" if e2e_matches else "FAIL")
             if e2e_ready.get("available") and e2e.get("available") else MISSING],
        ]))
    out.append("")

    # 6.5 E2E flows ------------------------------------------------------- #
    out.append("## 6.5 E2E flow status")
    out.append("")
    out.append("A passing test legitimately retains no trace, screenshot or video: all "
               "three are configured `on-failure` only.")
    out.append("")
    evidence: Dict[str, List[str]] = data["e2e_evidence"]   # type: ignore[assignment]
    flow_rows: List[Sequence[object]] = []
    if e2e.get("available"):
        for suite in e2e["suites"]:    # type: ignore[index]
            spec = str(suite["name"])
            stem = spec.replace(".spec.ts", "")
            artifacts = sorted({name for key, names in evidence.items()
                                if key.startswith(stem) for name in names})
            flow_rows.append([spec, suite["tests"],
                              suite["tests"] - suite["failures"] - suite["skipped"],
                              suite["failures"], suite["skipped"],
                              ", ".join(artifacts) or "none retained"])
    out.append(table(["Spec", "Total", "Passed", "Failed", "Skipped",
                      "Retained failure artifacts"],
                     flow_rows or [[MISSING] * 6]))
    out.append("")

    # 6.6 trend ----------------------------------------------------------- #
    out.append("## 6.6 Trend")
    out.append("")
    current: Dict[str, object] = data["trend"]              # type: ignore[assignment]
    prior: Dict[str, object] = previous.get("trend") or {}  # type: ignore[assignment]
    trend_rows: List[Sequence[object]] = []
    for label, key in (("Backend gated coverage (K1)", "K1"),
                       ("Frontend gated coverage, worst metric (K2)", "K2"),
                       ("Test cases, all layers", "tests"),
                       ("Failures, all layers", "failures"),
                       ("Skips, all layers", "skipped"),
                       ("Collection errors (K5)", "K5"),
                       ("Wall-clock seconds, all layers (K7)", "K7")):
        was = prior.get(key, "no previous run supplied")
        now = current.get(key)
        delta = ""
        if isinstance(was, (int, float)) and isinstance(now, (int, float)):
            delta = "{0:+.2f}".format(now - was)
        trend_rows.append([label, was, now, delta or "n/a"])
    out.append(table(["Metric", "Previous", "Current", "Delta"], trend_rows))
    out.append("")

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #

REQUIRED = (BACKEND_COVERAGE_XML, BACKEND_COVERAGE_JSON, BACKEND_JUNIT, BACKEND_COLLECT_ONLY,
            FRONTEND_COVERAGE_SUMMARY, FRONTEND_JUNIT, FRONTEND_LIST_TESTS,
            E2E_JUNIT, E2E_LIST_TESTS)


def collect() -> Dict[str, object]:
    be = junit(BACKEND_JUNIT)
    fe = junit(FRONTEND_JUNIT)
    e2e = junit(E2E_JUNIT)
    ready = backend_readiness()
    streams = [s for s in (be, fe, e2e) if s.get("available")]
    coverage = backend_coverage()
    frontend = frontend_coverage()

    # K2 is four numbers; the trend follows the worst of them, because that is the one a
    # per-path Jest threshold group fails on.
    k2_worst: Optional[float] = None
    if frontend.get("available"):
        gated: Dict[str, List[int]] = {metric: [0, 0] for metric in METRICS}
        for prefix in GATED_FRONTEND_PACKAGES:
            group = frontend["packages"][prefix]   # type: ignore[index]
            for metric in METRICS:
                gated[metric][0] += group[metric]["covered"]
                gated[metric][1] += group[metric]["total"]
        measured = [pct_frontend(v[0], v[1]) for v in gated.values()]
        present = [value for value in measured if value is not None]
        k2_worst = min(present) if present else None

    data: Dict[str, object] = {
        "backend_coverage": coverage,
        "frontend_coverage": frontend,
        "backend_junit": be,
        "frontend_junit": fe,
        "e2e_junit": e2e,
        "backend_readiness": ready,
        "frontend_readiness": listed_count(FRONTEND_LIST_TESTS, r"\.test\.tsx?$"),
        "e2e_readiness": listed_count(E2E_LIST_TESTS, r"\.spec\.ts:"),
        "e2e_evidence": e2e_evidence(),
    }
    data["trend"] = {
        "K1": (coverage.get("aggregate") or {}).get("pct"),
        "K2": k2_worst,
        "tests": sum(int(s["tests"]) for s in streams),
        "failures": sum(int(s["failures"]) for s in streams),
        "skipped": sum(int(s["skipped"]) for s in streams),
        "K5": ready.get("errors") if ready.get("available") else None,
        "K7": round(sum(float(s["time"]) for s in streams), 3),
    }
    return data


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true",
                        help="emit the collected values as JSON instead of markdown")
    parser.add_argument("--previous", metavar="FILE",
                        help="a previous --json output, used to fill the trend panel")
    parser.add_argument("--require-all", action="store_true",
                        help="exit 1 when any artifact in the contract is absent")
    args = parser.parse_args(argv)

    absent = [path for path in REQUIRED if not os.path.isfile(path)]
    for path in absent:
        sys.stderr.write("artifact not produced: {0}\n".format(path))

    data = collect()

    # Presence on disk is not the same as usability. A result stream can exist and
    # still be unreadable or a zero-case discovery stub, which would render as a
    # dashboard of dashes while the command exited 0 - the exact shape of a claim
    # that looks measured and is not. So the contract is checked against what was
    # actually parsed, not against the directory listing.
    unusable = []
    for label, key in (("backend result stream", "backend_junit"),
                       ("frontend result stream", "frontend_junit"),
                       ("end-to-end result stream", "e2e_junit")):
        stream = data.get(key) or {}
        if not stream.get("available"):
            unusable.append((label, stream.get("source", "?"), stream.get("reason", "not parseable")))

    for label, source, reason in unusable:
        sys.stderr.write("artifact unusable: {0} ({1}): {2}\n".format(label, source, reason))

    if absent or unusable:
        sys.stderr.write("run the suites first; every command is in the Testing section "
                         "of README.md\n")
        if args.require_all:
            return 1

    if args.previous:
        previous = read_text(args.previous)
        if previous is None:
            sys.stderr.write("previous run file not found: {0}\n".format(args.previous))
            return 1
        data["previous"] = json.loads(previous)

    if args.json:
        printable = {key: value for key, value in data.items() if key != "previous"}
        sys.stdout.write(json.dumps(printable, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render(data) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
