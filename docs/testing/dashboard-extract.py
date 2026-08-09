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
    backend/reports/coverage-gate.txt           exact-gate verdict
    frontend/coverage/coverage-summary.json     Istanbul per-file summary
    frontend/coverage/lcov.info                 uncovered line numbers
    frontend/reports/jest-junit.xml             result stream
    frontend/reports/list-tests.txt             discovery census
    frontend/reports/load-tests.txt             readiness output - the load probe
    e2e/reports/e2e-junit.xml                   result stream
    e2e/reports/list-tests.txt                  readiness output
    e2e/reports/browser.txt                     resolved browser and runner versions
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
import datetime
import json
import os
import platform
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
BACKEND_COVERAGE_GATE = "backend/reports/coverage-gate.txt"

FRONTEND_COVERAGE_SUMMARY = "frontend/coverage/coverage-summary.json"
FRONTEND_LCOV = "frontend/coverage/lcov.info"
FRONTEND_JUNIT = "frontend/reports/jest-junit.xml"
#: The discovery census - which files a run would pick up. Imports none of them.
FRONTEND_LIST_TESTS = "frontend/reports/list-tests.txt"

#: The load probe - every discovered module transformed, imported and registered, no test
#: body run. Named for the question it answers rather than for the script that writes it.
FRONTEND_READINESS = "frontend/reports/load-tests.txt"

E2E_JUNIT = "e2e/reports/e2e-junit.xml"
E2E_LIST_TESTS = "e2e/reports/list-tests.txt"
E2E_BROWSER = "e2e/reports/browser.txt"
E2E_TEST_RESULTS = "e2e/test-results"

MISSING = "not produced"

#: Printed where a value exists but the artifact that would explain it does not, so an
#: unavailable detail is never rendered as an absence of detail.
UNAVAILABLE = "detail unavailable"

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
#: Ordered longest-prefix-first is not required, because no prefix here is a prefix of
#: another. Every backend suite must match one of these: the fallback below is a named
#: bucket rather than a silent catch-all, and an unmatched suite is reported as such.
BACKEND_LAYERS: Sequence[Tuple[str, str]] = (
    ("Backend unit", "tests.unit."),
    ("Backend integration", "tests.integration."),
    ("Backend infrastructure - dependency closure", "tests.test_dependency_closure"),
    ("Backend infrastructure - coverage gate", "tests.test_coverage_gate"),
    ("Backend infrastructure - guard contract", "tests.test_guard_contract"),
    ("Backend infrastructure - dashboard producer", "tests.test_dashboard_extract"),
    ("Backend infrastructure - document contract", "tests.test_docs_contract"),
)

#: Layer label for a backend suite matching no prefix above. Named "unclassified" rather
#: than "other" so a row appearing under it reads as a taxonomy gap to close, not as a
#: category of test.
BACKEND_UNCLASSIFIED_LAYER = "Backend unclassified - add a prefix to BACKEND_LAYERS"

#: Frontend layer partition, keyed on the ``rootDir``-relative test path jest-junit
#: writes as ``classname``. Suites under these two prefixes are the component layer;
#: every other suite is a unit suite.
FRONTEND_COMPONENT_PREFIXES = ("src/components/", "src/pages/")

METRICS = ("statements", "branches", "functions", "lines")


# --------------------------------------------------------------------------- #
# Percentage rendering - one function per producer                            #
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


class ArtifactRefused(Exception):
    """An artifact was present but this script declined to read it.

    Distinct from absence on purpose. Every reader here returns ``None`` for a missing
    artifact, and the panels render that as "not produced" - which is the honest answer
    for a run that did not emit one. A file that is present but oversized or carries a
    DTD is a different fact, and mapping it onto ``None`` would print "not produced"
    about a file sitting on disk. That is the shape of defect this project has already
    fixed once elsewhere: a check that cannot fail reads as a check that passed.
    """


#: Largest artifact this script will read, per file.
#:
#: The real ones are small and their sizes are known: the backend Cobertura report is
#: about 30 KB, the JUnit streams tens of KB, ``coverage-final.json`` a few hundred KB.
#: 64 MiB is far above any of them and far below anything that would trouble the machine,
#: so it bounds the pathological case without ever being reached by a genuine input.
#:
#: The bound is on the reader rather than on the parser because the parser is not where
#: the cost lands: ``ET.parse`` on a hostile document allocates during expansion, and
#: refusing to hand it the bytes at all is the only bound that holds for both XML and the
#: JSON and lcov readers beside it.
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

#: Markup that may only appear inside a document type declaration.
#:
#: Refusing ``<!DOCTYPE`` is a structural rule rather than a pattern match, and that is
#: why it is sufficient: an XML document can declare an entity *only* within a DTD, so a
#: document with no DTD has no entity to expand and the whole billion-laughs and
#: quadratic-blowup class is unreachable. ``<!ENTITY`` is listed too so a malformed
#: document that omits the ``DOCTYPE`` keyword is refused by name as well.
#:
#: Measured on this interpreter (CPython 3.9.13) rather than assumed:
#: ``xml.etree.ElementTree`` **does** expand internal entities - a 350-byte document with
#: five nested ten-fold entities produced 100,000 characters of text - while an *external*
#: entity is already refused by the runtime with ``ParseError: undefined entity``, since
#: external general entities have not been processed since 3.7.1. So this guard closes the
#: expansion class, which is live, and the runtime closes retrieval, which is not.
DOCTYPE_MARKERS = ("<!doctype", "<!entity")


def decode_by_bom(raw: bytes) -> str:
    """Decode ``raw`` by its byte-order mark, falling back to UTF-8.

    The readiness artifacts are produced by a shell redirection, and PowerShell 5.1's
    ``Tee-Object`` and ``Out-File`` write UTF-16LE by default - a file that decodes as
    UTF-8 into NUL-separated characters, which every regex in this script then silently
    fails to match. Detecting the mark means an artifact captured on either platform is
    read the same way instead of being reported as a missing measurement.
    """
    for mark, encoding in (
        (b"\xff\xfe\x00\x00", "utf-32"),
        (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
        (b"\xef\xbb\xbf", "utf-8-sig"),
    ):
        if raw.startswith(mark):
            return raw.decode(encoding, errors="replace")

    return raw.decode("utf-8", errors="replace")


def read_bounded(path: str) -> str:
    """Read ``path`` as text, refusing anything above :data:`MAX_ARTIFACT_BYTES`.

    Size is taken from the directory entry and then the read is capped one byte beyond the
    limit, so a file that grows between the two - or a pipe or device that reports zero -
    is still refused rather than read without bound.

    Read as bytes and then decoded by byte-order mark, so the bound and the encoding
    detection hold together: capping a *text* read would cap decoded characters rather
    than bytes, and assuming UTF-8 would misread the UTF-16LE a PowerShell 5.1 capture
    writes. Both properties are required, and neither substitutes for the other.

    :raises ArtifactRefused: when the file exceeds the limit.
    """
    declared = os.path.getsize(path)
    if declared > MAX_ARTIFACT_BYTES:
        raise ArtifactRefused(
            "{0} is {1} bytes, above the {2}-byte limit this script reads".format(
                norm(path), declared, MAX_ARTIFACT_BYTES
            )
        )

    with open(path, "rb") as handle:
        raw = handle.read(MAX_ARTIFACT_BYTES + 1)

    text = decode_by_bom(raw)

    if len(text) > MAX_ARTIFACT_BYTES:
        raise ArtifactRefused(
            "{0} yielded more than the {1}-byte limit this script reads".format(
                norm(path), MAX_ARTIFACT_BYTES
            )
        )

    return text


def read_text(path: str) -> Optional[str]:
    """Return the text of ``path``, or ``None`` when it does not exist.

    Decodes by byte-order mark rather than assuming UTF-8. The readiness artifacts are
    produced by a shell redirection, and PowerShell 5.1's ``Tee-Object`` and ``Out-File``
    write UTF-16LE by default - a file that decodes as UTF-8 into NUL-separated
    characters, which every regex below then silently fails to match. Detecting the mark
    means an artifact captured on either platform is read the same way instead of being
    reported as a missing measurement.
    """
    if not os.path.isfile(path):
        return None
    return read_bounded(path)


def parse_xml(path: str) -> Optional[ET.Element]:
    """Parse a report artifact, refusing an oversized one or one carrying a DTD.

    Parsed from the already-bounded string rather than from the path, so the size limit
    applies to XML on the same terms as every other reader here and the document is never
    handed to the parser before it has been judged.

    :raises ArtifactRefused: when the file is oversized or declares a document type.
    """
    if not os.path.isfile(path):
        return None

    text = read_bounded(path)

    lowered = text.lower()
    for marker in DOCTYPE_MARKERS:
        position = lowered.find(marker)
        if position >= 0:
            raise ArtifactRefused(
                "{0} contains {1!r} at offset {2}. Report artifacts from pytest, jest-junit "
                "and Playwright declare no document type, and an entity declaration is the "
                "one thing in XML that can expand without bound.".format(
                    norm(path), marker, position
                )
            )

    return ET.fromstring(text)


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


def lcov_is_usable() -> bool:
    """Whether the frontend lcov artifact carries at least one per-line record.

    ``FRONTEND_LCOV`` is the sole source of the uncovered-line numbers every per-file
    panel prints, so a file that exists but carries no ``SF:``/``DA:`` pair renders
    those columns empty while the command exits 0. Absence and emptiness are the same
    defect to a reader, so both are reported.
    """
    text = read_text(FRONTEND_LCOV)
    if text is None:
        return False
    lines = [line.strip() for line in text.splitlines()]
    return any(line.startswith("SF:") for line in lines) and any(
        line.startswith("DA:") for line in lines
    )


def _lcov_uncovered() -> Optional[Dict[str, List[int]]]:
    """Uncovered line numbers per file, from ``DA:<line>,<hits>`` records in lcov.

    Returns ``None`` when the tracefile is absent, which is not the same answer as an
    empty mapping: ``lcov.info`` is the **only** frontend source of uncovered line
    numbers, so without it "no uncovered lines" and "we cannot tell" are
    indistinguishable, and a per-module row must say the second rather than imply the
    first.
    """
    text = read_text(FRONTEND_LCOV)
    if text is None:
        return None
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


def gated_frontend_percentages(
    frontend: Dict[str, object],
) -> List[Tuple[str, str, Optional[float]]]:
    """Every percentage gate G2 applies, as ``(package, metric, percent)``.

    Jest declares one ``coverageThreshold`` group per path in
    :data:`GATED_FRONTEND_PACKAGES`, and each group is checked on each of the four
    metrics, so G2 is ``len(GATED_FRONTEND_PACKAGES) * len(METRICS)`` independent
    comparisons rather than one comparison over their sum.
    """
    if not frontend.get("available"):
        return []
    rows: List[Tuple[str, str, Optional[float]]] = []
    for prefix in GATED_FRONTEND_PACKAGES:
        group = frontend["packages"][prefix]        # type: ignore[index]
        for metric in METRICS:
            rows.append((prefix, metric, group[metric]["pct"]))
    return rows


def gated_frontend_worst(frontend: Dict[str, object]) -> Optional[float]:
    """The lowest of the percentages :func:`gated_frontend_percentages` reports.

    This is the figure a Jest run fails on, so it is the one the trend follows.
    Taking the minimum over the individual groups rather than over their combined
    totals is what keeps a package below the threshold from being carried by a
    stronger one.
    """
    measured = [pct for _, _, pct in gated_frontend_percentages(frontend)
                if pct is not None]
    return min(measured) if measured else None


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
    lcov_available = uncovered is not None

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
        if lcov_available:
            matched = [v for k, v in uncovered.items() if norm(k).endswith(key)]
            row["uncovered_lines"] = matched[0] if matched else []
        else:
            row["uncovered_lines"] = None
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
        "lcov_available": lcov_available,
        "lcov_source": FRONTEND_LCOV,
        "gate_cells": gated_gate_cells(packages),
    }


def gated_gate_cells(
    packages: Dict[str, object]
) -> List[Dict[str, object]]:
    """Return one row per independently gated frontend cell.

    Jest declares one ``coverageThreshold`` group per path and each group carries all
    four metrics, so gate G2 is **twelve** independent comparisons - three packages by
    four metrics - not one. Each is reported on its own here so the KPI can be the worst
    of them rather than a figure summed across groups that are never summed by the
    runner.
    """
    cells: List[Dict[str, object]] = []
    for prefix in GATED_FRONTEND_PACKAGES:
        group: Dict[str, object] = packages[prefix]   # type: ignore[assignment]
        for metric in METRICS:
            measured: Dict[str, object] = group[metric]   # type: ignore[assignment]
            pct = measured["pct"]
            cells.append({
                "package": prefix,
                "metric": metric,
                "covered": measured["covered"],
                "total": measured["total"],
                "pct": pct,
                "meets": None if pct is None else bool(float(pct) >= G2_THRESHOLD),
            })
    return cells


def worst_gate_cell(
    cells: Sequence[Dict[str, object]]
) -> Optional[Dict[str, object]]:
    """Return the gated cell with the lowest measured percentage, or ``None``.

    A cell whose denominator is empty carries no percentage and cannot be the worst of
    anything: Istanbul reports ``Unknown`` for it and Jest's own threshold check treats
    it as satisfied. Such cells are excluded rather than read as zero.
    """
    measured = [cell for cell in cells if cell["pct"] is not None]
    if not measured:
        return None
    return min(measured, key=lambda cell: float(cell["pct"]))   # type: ignore[arg-type]


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
    """Return the layer label for one backend case, from its ``classname`` prefix."""
    for label, prefix in BACKEND_LAYERS:
        if case["classname"].startswith(prefix):
            return label
    return BACKEND_UNCLASSIFIED_LAYER


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

#: ``coverage gate: 182 of 195 statements covered = 93.3333% exact, threshold 90%``
GATE_COUNTS_RE = re.compile(
    r"(\d+)\s+of\s+(\d+)\s+statements covered\s+=\s+([\d.]+)% exact,\s+threshold\s+([\d.]+)%"
)

#: ``Test Suites: 24 skipped, 0 of 24 total`` - the load probe's suite line. The phrases
#: before the total are captured together, because "1 failed" is what a module that would
#: not load reports and it has to be read from the same line as the total.
JEST_SUITE_SUMMARY_RE = re.compile(r"Test Suites:(?P<phrases>[^\n]*?)(?P<total>\d+)\s+total")

#: ``Tests:       370 skipped, 370 total`` - every identity the probe registered.
JEST_TEST_SUMMARY_RE = re.compile(r"Tests:(?P<phrases>[^\n]*?)(?P<total>\d+)\s+total")


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


def exact_coverage_gate() -> Dict[str, object]:
    """Verdict and counts from the retained exact-coverage-gate output.

    ``--cov-fail-under`` rounds before it compares, so the pytest step's own message is
    not the gate's verdict. ``backend/tests/coverage_gate.py`` is, and this reads what it
    printed rather than restating the rounded figure.
    """
    text = read_text(BACKEND_COVERAGE_GATE)
    if text is None:
        return {"available": False, "source": BACKEND_COVERAGE_GATE}
    counts = GATE_COUNTS_RE.search(text)
    if "coverage gate PASSED" in text:
        verdict_text = "PASSED"
    elif "coverage gate FAILED" in text:
        verdict_text = "FAILED"
    else:
        verdict_text = "no verdict line - the gate did not run to completion"
    return {
        "available": True,
        "source": BACKEND_COVERAGE_GATE,
        "verdict": verdict_text,
        "covered": int(counts.group(1)) if counts else None,
        "statements": int(counts.group(2)) if counts else None,
        "exact_percent": counts.group(3) if counts else None,
        "threshold": counts.group(4) if counts else None,
    }


def _jest_phrase(phrases: str, word: str) -> int:
    """Count the ``N <word>`` phrase carries, or 0 when it names none."""
    found = re.search(r"(\d+) " + word, phrases)
    return int(found.group(1)) if found else 0


def jest_readiness(path: str) -> Dict[str, object]:
    """Load-and-transform readiness of every frontend test module.

    Parses the summary of a name-filtered Jest run: every matching module is imported and
    transformed, and no test body executes, so a module that throws on import is reported
    as a failed suite while a healthy one is reported as skipped. ``jest --listTests``
    cannot report that property, because it resolves no import. A file that carries no
    ``Test Suites:`` summary, or that reports a failed suite, is unusable as a readiness
    result and is refused rather than counted.
    """
    text = read_text(path)
    if text is None:
        return {"available": False, "source": path}

    summary = JEST_SUITE_SUMMARY_RE.search(text)
    if summary is None:
        return {
            "available": False,
            "source": path,
            "reason": ("carries no Jest 'Test Suites:' summary, so no module was "
                       "loaded or transformed. Re-run `npm run test:load`"),
        }

    failed = _jest_phrase(summary.group("phrases"), "failed")
    total = int(summary.group("total"))
    tests = JEST_TEST_SUMMARY_RE.search(text)

    if failed:
        return {
            "available": False,
            "source": path,
            "reason": ("{0} of {1} test modules failed to load or transform"
                       .format(failed, total)),
        }

    return {
        "available": True,
        "source": path,
        "count": total,
        "errors": failed,
        "declared_tests": int(tests.group("total")) if tests else None,
        "executed_tests": (
            None if tests is None
            else int(tests.group("total")) - _jest_phrase(tests.group("phrases"), "skipped")
        ),
    }


def browser_provenance() -> Dict[str, object]:
    """Resolved browser and runner readings from the retained e2e provisioning output."""
    text = read_text(E2E_BROWSER)
    if text is None:
        return {"available": False, "source": E2E_BROWSER}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "available": True,
        "source": E2E_BROWSER,
        "lines": lines,
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
# Provenance - recorded by this script, never transcribed by hand              #
# --------------------------------------------------------------------------- #


def _git_head() -> Dict[str, Optional[str]]:
    """Return the current branch and commit, read straight out of ``.git``.

    Read from the repository's own files rather than through a subprocess, so the answer
    is available with no git binary and no shell. A detached HEAD carries the commit and
    no branch.
    """
    head_path = os.path.join(".git", "HEAD")
    text = read_text(head_path)
    if text is None:
        return {"branch": None, "commit": None}

    head = text.strip()
    if head.startswith("ref: "):
        ref = head[5:].strip()
        branch = ref.split("/")[-1]
        commit = read_text(os.path.join(".git", *ref.split("/")))
        if commit is None:
            packed = read_text(os.path.join(".git", "packed-refs")) or ""
            commit = next(
                (line.split(" ", 1)[0] for line in packed.splitlines()
                 if line.strip().endswith(" " + ref)),
                None,
            )
        return {"branch": branch, "commit": None if commit is None else commit.strip()}
    return {"branch": None, "commit": head}


def provenance() -> Dict[str, object]:
    """Return the identity of the tree and the runtimes this reading was taken on.

    This is the mechanism that replaces a commit hash written into prose. A hash typed
    into a document names either a tree that predates the measurement or one that does
    not exist yet, and it rots on the next commit; a hash recorded here is read from the
    working tree at the moment the artifacts are turned into a dashboard, so it is always
    the tree that was measured.
    """
    head = _git_head()
    return {
        "branch": head["branch"],
        "commit": head["commit"],
        "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "extractor": os.path.relpath(__file__).replace("\\", "/"),
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
    exact_gate: Dict[str, object] = data["backend_coverage_gate"]  # type: ignore[assignment]
    fe_discovered: Dict[str, object] = data["frontend_discovery"]  # type: ignore[assignment]
    fe_ready: Dict[str, object] = data["frontend_readiness"]  # type: ignore[assignment]
    e2e_ready: Dict[str, object] = data["e2e_readiness"]      # type: ignore[assignment]
    browser: Dict[str, object] = data["e2e_browser"]          # type: ignore[assignment]
    origin: Dict[str, object] = data["provenance"]            # type: ignore[assignment]
    previous: Dict[str, object] = data.get("previous") or {}  # type: ignore[assignment]

    out: List[str] = [
        "# Test Observability Dashboard - filled from artifacts",
        "",
        "Produced by `docs/testing/dashboard-extract.py`. Every value below was read from "
        "the artifact named beside it; nothing here was transcribed by hand.",
        "",
        "## 1.0 Provenance of this reading",
        "",
        "The commit below is read out of `.git` at the moment this reading is produced, so "
        "it is the tree the artifacts were measured on rather than a hash typed into a "
        "document. Reproduce by checking it out and re-running the commands in the Testing "
        "section of the root `README.md`.",
        "",
        table(
            ["Field", "Value"],
            [
                ["Branch", origin.get("branch") or UNAVAILABLE],
                ["Commit", origin.get("commit") or UNAVAILABLE],
                ["Recorded at (UTC)", origin.get("recorded_at_utc") or UNAVAILABLE],
                ["Python", origin.get("python") or UNAVAILABLE],
                ["Platform", origin.get("platform") or UNAVAILABLE],
                ["Producer", origin.get("extractor") or UNAVAILABLE],
                ["Browser and runner",
                 " · ".join(browser.get("lines", []))   # type: ignore[arg-type]
                 if browser.get("available") else MISSING],
            ],
        ),
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
    # K2 is the WORST of the twelve independently gated cells - three `coverageThreshold`
    # groups by four metrics - not a figure summed across them. Jest fails the run on any
    # single cell below the threshold, so summing would let a failing group be carried by
    # a passing one and report a green KPI over a red gate.
    if fe_cov.get("available"):
        cells: Sequence[Dict[str, object]] = fe_cov["gate_cells"]   # type: ignore[assignment]
        worst = worst_gate_cell(cells)
        unmeasured = len([cell for cell in cells if cell["pct"] is None])
        if worst is None:
            k2 = "{0} - no gated cell carries a denominator".format(UNAVAILABLE)
        else:
            k2 = "worst of {0} cells: {1} {2} {3}{4}".format(
                len(cells),
                worst["package"],
                worst["metric"],
                fmt_pct(worst["pct"], worst["covered"], worst["total"]),
                "" if unmeasured == 0 else
                " ({0} cell(s) have an empty denominator and are excluded)".format(unmeasured),
            )
    else:
        k2 = MISSING
    out.append(table(
        ["#", "KPI", "Source artifact", "Target", "Value"],
        [
            ["K1", "Backend line coverage, aggregate of the four gated packages",
             BACKEND_COVERAGE_XML, ">= 90%",
             fmt_pct(agg["pct"], agg["covered"], agg["statements"]) if agg else MISSING],
            ["K2", "Frontend coverage, the worst of the twelve independently gated cells",
             FRONTEND_COVERAGE_SUMMARY, ">= 80% on every cell", k2],
            ["K3", "Backend test cases: total / passed / failed / skipped",
             BACKEND_JUNIT, "0 failed", counts(be)],
            ["K4", "Frontend test cases: total / passed / failed / skipped",
             FRONTEND_JUNIT, "0 failed", counts(fe)],
            ["K5", "Backend collection errors", BACKEND_COLLECT_ONLY, "0",
             str(ready.get("errors")) if ready.get("available") else MISSING],
            ["K5b", "Backend exact coverage gate", BACKEND_COVERAGE_GATE,
             "PASSED", exact_gate.get("verdict", MISSING)
             if exact_gate.get("available") else MISSING],
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
    # G3 is measured and not gated, so it has no row here; G5 is a gate and does. An
    # unusable probe is reported as a failed gate rather than omitted, because a gate that
    # disappears when its evidence does cannot fail.
    gate_rows.append(["G5", "every frontend suite loads", "0 suites fail to load",
                      "{0} loaded, 0 failed to load".format(fe_ready.get("count"))
                      if fe_ready.get("available")
                      else str(fe_ready.get("reason", MISSING)),
                      "PASS" if (fe_ready.get("available")
                                 and int(fe_ready.get("count") or 0) > 0) else "FAIL"])
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
        if not fe_cov.get("lcov_available"):
            out.append("**Frontend uncovered-line detail is unavailable**: `{0}` was not "
                       "produced, and it is the only frontend source of uncovered line "
                       "numbers. The percentages below are read from `{1}`; the last column "
                       "reads `{2}` rather than `-`, because an empty cell here would claim "
                       "there is nothing uncovered."
                       .format(fe_cov.get("lcov_source"), FRONTEND_COVERAGE_SUMMARY,
                               UNAVAILABLE))
            out.append("")
        for row in fe_cov["modules"]:    # type: ignore[index]
            lines = row["uncovered_lines"]
            mod_rows.append([row["module"]]
                            + [fmt_pct(row[m]["pct"], row[m]["covered"], row[m]["total"])
                               for m in METRICS]
                            + [UNAVAILABLE if lines is None
                               else (", ".join(str(n) for n in lines) or "-")])
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
    fe_loaded_all = (fe_ready.get("available") and fe_discovered.get("available")
                     and fe_ready.get("count") == fe_discovered.get("count"))
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
            ["Backend exact coverage gate", BACKEND_COVERAGE_GATE, "PASSED",
             "{0} ({1} of {2} statements = {3}% exact vs {4}%)".format(
                 exact_gate.get("verdict"), exact_gate.get("covered"),
                 exact_gate.get("statements"), exact_gate.get("exact_percent"),
                 exact_gate.get("threshold"))
             if exact_gate.get("available") else MISSING,
             ("PASS" if exact_gate.get("verdict") == "PASSED" else "FAIL")
             if exact_gate.get("available") else MISSING],
            ["Frontend test files discovered", FRONTEND_LIST_TESTS, "> 0",
             str(fe_discovered.get("count")) if fe_discovered.get("available") else MISSING,
             ("PASS" if int(fe_discovered.get("count") or 0) > 0 else "FAIL")
             if fe_discovered.get("available") else MISSING],
            ["Frontend test modules loaded and transformed", FRONTEND_READINESS,
             "every discovered module, 0 failed to load",
             ("{0} loaded, 0 failed".format(fe_ready.get("count"))
              if fe_ready.get("available")
              else str(fe_ready.get("reason", MISSING))),
             ("PASS" if fe_loaded_all else "FAIL")
             if fe_ready.get("available") else "FAIL"],
            ["Frontend readiness executed no test body", FRONTEND_READINESS,
             "0 of the discovered tests run",
             (str(fe_ready.get("executed_tests"))
              if fe_ready.get("available") else MISSING),
             ("PASS" if fe_ready.get("executed_tests") == 0 else "FAIL")
             if fe_ready.get("available") else MISSING],
            ["Frontend test identities registered equal the frontend total in 6.3",
             FRONTEND_READINESS, "equal",
             str(fe_ready.get("declared_tests")) if fe_ready.get("available") else MISSING,
             ("PASS" if fe_ready.get("declared_tests") == fe.get("tests") else "FAIL")
             if fe_ready.get("available") and fe.get("available") else MISSING],
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
            # `errors` is a distinct outcome from `failures` in JUnit - Playwright writes
            # one for a hook or fixture that threw before the test body ran - so a pass
            # count that ignores it reports an errored spec as having passed.
            flow_rows.append([spec, suite["tests"],
                              suite["tests"] - suite["failures"] - suite["errors"]
                              - suite["skipped"],
                              suite["failures"], suite["errors"], suite["skipped"],
                              ", ".join(artifacts) or "none retained"])
    out.append(table(["Spec", "Total", "Passed", "Failed", "Errored", "Skipped",
                      "Retained failure artifacts"],
                     flow_rows or [[MISSING] * 7]))
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

#: The artifact contract `--require-all` enforces. `frontend/coverage/lcov.info` is part
#: of it because it is the only frontend source of uncovered line numbers: without it §6.2
#: can report a percentage but not which lines it is missing, and a dashboard that omits
#: that silently looks complete.
REQUIRED = (BACKEND_COVERAGE_XML, BACKEND_COVERAGE_JSON, BACKEND_JUNIT, BACKEND_COLLECT_ONLY,
            BACKEND_COVERAGE_GATE,
            FRONTEND_COVERAGE_SUMMARY, FRONTEND_LCOV, FRONTEND_JUNIT,
            FRONTEND_LIST_TESTS, FRONTEND_READINESS,
            E2E_JUNIT, E2E_LIST_TESTS)


def collect() -> Dict[str, object]:
    be = junit(BACKEND_JUNIT)
    fe = junit(FRONTEND_JUNIT)
    e2e = junit(E2E_JUNIT)
    ready = backend_readiness()
    streams = [s for s in (be, fe, e2e) if s.get("available")]
    coverage = backend_coverage()
    frontend = frontend_coverage()

    # K2 is twelve independent comparisons; the trend follows the worst of them, because
    # that is the one a per-path Jest threshold group fails on. Summing them would let a
    # failing group be carried by a passing one.
    k2_worst: Optional[float] = None
    if frontend.get("available"):
        worst = worst_gate_cell(frontend["gate_cells"])   # type: ignore[arg-type]
        k2_worst = None if worst is None else float(worst["pct"])   # type: ignore[arg-type]

    data: Dict[str, object] = {
        "provenance": provenance(),
        "backend_coverage": coverage,
        "frontend_coverage": frontend,
        "backend_junit": be,
        "frontend_junit": fe,
        "e2e_junit": e2e,
        "backend_readiness": ready,
        "backend_coverage_gate": exact_coverage_gate(),
        "frontend_discovery": listed_count(FRONTEND_LIST_TESTS, r"\.test\.tsx?$"),
        "frontend_readiness": jest_readiness(FRONTEND_READINESS),
        "e2e_readiness": listed_count(E2E_LIST_TESTS, r"\.spec\.ts:"),
        "e2e_browser": browser_provenance(),
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
                       ("end-to-end result stream", "e2e_junit"),
                       ("frontend readiness output", "frontend_readiness")):
        stream = data.get(key) or {}
        if not stream.get("available"):
            unusable.append((label, stream.get("source", "?"), stream.get("reason", "not parseable")))

    if not lcov_is_usable():
        unusable.append((
            "frontend uncovered-line source",
            FRONTEND_LCOV,
            "carries no SF:/DA: record pair, so every uncovered-line column would "
            "render empty; add 'lcov' to coverageReporters and re-run",
        ))

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
