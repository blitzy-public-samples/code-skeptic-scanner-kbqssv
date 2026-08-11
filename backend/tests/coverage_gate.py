"""Exact coverage gate for the backend suite.

Subject
-------
``backend/coverage.json``, the JSON report ``pytest --cov-report=json`` writes.
This module answers two questions about it that ``--cov-fail-under`` cannot:

1. **Is the measured total at or above the threshold, exactly?**
   ``--cov-fail-under`` compares ``round(total, precision) < fail_under``
   (:func:`coverage.results.should_fail_under`), so at *any* finite precision
   there is a band of sub-threshold totals that round up and pass. At the library
   default of 0 decimals the band is ``[89.5, 90)``; at the two decimals
   ``backend/.coveragerc`` configures it narrows to ``[89.995, 90)``. It never
   closes. The gate here compares integer counts instead - ``covered * 100`` against
   ``threshold * statements`` as exact rational arithmetic - so ``89.995%`` fails
   and only a genuine ``>= 90%`` passes.

2. **Was the total measured over the packages the threshold is calibrated for?**
   A percentage is meaningless without its denominator. ``--cov`` scoping lives on
   the command line, so a run that measured the whole ``app`` tree writes a
   ``coverage.json`` indistinguishable, to any later reader, from one that measured
   the four gated packages. ``--require-scope`` makes the denominator part of the
   gate: every measured file must fall inside the named packages, and every named
   package must contribute at least one measured file.

Together those two make "backend coverage is at least 90% of
``app/core`` + ``app/services`` + ``app/tasks`` + ``app/db``" a checkable
statement rather than a reported one.

Use
---
Run it from ``backend/`` immediately after the gated pytest invocation, which is
what produces the report it reads::

    python tests/coverage_gate.py --coverage-json coverage.json --fail-under 90 \\
        --require-scope app/core --require-scope app/services \\
        --require-scope app/tasks --require-scope app/db

Exit status is the contract: ``0`` when every check passes, ``1`` when the total is
below the threshold or the measured scope does not match, ``2`` when the report is
missing or unreadable. A missing report is deliberately its own status: it means
no measurement happened, which is a different failure from a measurement that came
in low.

The threshold is accepted as a decimal string and compared as a
:class:`~fractions.Fraction`, so ``--fail-under 93.33`` is the exact value written
rather than the nearest binary float to it.

Scope
-----
Standard library only, Python 3.9 compatible, and importable without side effects:
``backend/tests/test_coverage_gate.py`` drives every function below directly.
Nothing here imports an ``app`` module, opens a socket, or reads the environment.

.. seealso:: ``docs/testing/DECISION-LOG.md`` for why the gate is two parts rather
   than a precision setting, ``backend/.coveragerc`` for the reporting precision
   this gate backstops, and ``docs/testing/DASHBOARD-TEMPLATE.md`` §3.1 for the G1
   contract it enforces.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from fractions import Fraction
from typing import Dict, List, Optional, Sequence, Tuple

#: Exit status when every check passes.
EXIT_OK = 0

#: Exit status when a check fails: the total is short, or the scope is wrong.
EXIT_GATE_FAILED = 1

#: Exit status when the report cannot be read at all, so nothing was measured.
EXIT_NO_REPORT = 2

#: Default report path, relative to ``backend/``.
DEFAULT_COVERAGE_JSON = "coverage.json"

#: Default threshold, as a decimal string so it is compared exactly.
DEFAULT_FAIL_UNDER = "90"

#: The four packages the backend threshold is calibrated against, as ``--cov``
#: names them. Also the default for ``--require-scope``.
GATED_PACKAGES: Tuple[str, ...] = ("app/core", "app/services", "app/tasks", "app/db")


class ReportUnavailable(Exception):
    """Raised when the coverage report is absent, unreadable or malformed."""


def normalize_path(path: str) -> str:
    """Return ``path`` with forward slashes and no leading ``./``.

    ``coverage.json`` keys files with the separator of the platform that wrote
    them, so a scope comparison has to normalize before it compares. Windows
    writes ``app\\core\\config.py`` for the same file POSIX writes as
    ``app/core/config.py``.
    """
    forward = path.replace("\\", "/")
    while forward.startswith("./"):
        forward = forward[2:]
    return forward


def load_report(path: str) -> Dict[str, object]:
    """Return the parsed coverage report at ``path``.

    :raises ReportUnavailable: when the file does not exist, is not readable, is
        not JSON, or carries no ``totals`` mapping - each of which means there is
        no measurement to gate.
    """
    if not os.path.isfile(path):
        raise ReportUnavailable(
            "no coverage report at {0} - run the gated pytest command with "
            "--cov-report=json first".format(path)
        )
    try:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, ValueError) as error:
        raise ReportUnavailable("cannot read {0}: {1}".format(path, error))

    if not isinstance(report, dict) or not isinstance(report.get("totals"), dict):
        raise ReportUnavailable(
            "{0} carries no 'totals' object, so it is not a coverage JSON "
            "report".format(path)
        )
    return report


def report_counts(report: Dict[str, object]) -> Tuple[int, int]:
    """Return ``(covered_lines, num_statements)`` from a parsed report.

    These are the two integers the percentage is derived from, and comparing them
    is what makes the gate exact - the ``percent_covered`` float in the same object
    has already lost the distinction between ``89.995`` and ``90``.

    :raises ReportUnavailable: when either count is missing or not an integer.
    """
    totals = report["totals"]
    try:
        covered = int(totals["covered_lines"])
        statements = int(totals["num_statements"])
    except (KeyError, TypeError, ValueError) as error:
        raise ReportUnavailable(
            "coverage totals are incomplete: {0}".format(error)
        )
    if statements < 0 or covered < 0 or covered > statements:
        raise ReportUnavailable(
            "coverage totals are inconsistent: {0} covered of {1} "
            "statements".format(covered, statements)
        )
    return covered, statements


def measured_files(report: Dict[str, object]) -> Tuple[str, ...]:
    """Return every measured file path in the report, normalized and sorted."""
    files = report.get("files")
    if not isinstance(files, dict):
        return ()
    return tuple(sorted(normalize_path(name) for name in files))


def parse_threshold(text: str) -> Fraction:
    """Return ``text`` as an exact :class:`~fractions.Fraction` percentage.

    :raises ValueError: when ``text`` is not a decimal number in ``[0, 100]``.
    """
    threshold = Fraction(text)
    if threshold < 0 or threshold > 100:
        raise ValueError("threshold must be between 0 and 100, got {0}".format(text))
    return threshold


def meets_threshold(covered: int, statements: int, threshold: Fraction) -> bool:
    """Whether ``covered / statements`` is at least ``threshold`` percent, exactly.

    Compared as ``covered * 100 >= threshold * statements`` over integers and
    rationals, so no rounding step exists for a sub-threshold total to survive.
    A zero denominator is treated as *not* meeting any positive threshold: nothing
    was measured, and a run that measured nothing must not satisfy a coverage bar.
    """
    if statements == 0:
        return threshold == 0
    return Fraction(covered * 100) >= threshold * statements


def exact_percentage(covered: int, statements: int) -> Optional[Fraction]:
    """Return the exact coverage percentage, or ``None`` when nothing was measured."""
    if statements == 0:
        return None
    return Fraction(covered * 100, statements)


def format_percentage(value: Optional[Fraction], places: int = 4) -> str:
    """Render ``value`` to ``places`` decimals without rounding it up to the bar.

    Truncates toward zero rather than rounding, so a total of ``89.99999`` prints
    as ``89.9999`` and never as ``90.0000``. That matters here specifically: the
    defect this gate exists to remove was a message that read like a pass.
    """
    if value is None:
        return "n/a"
    scale = 10 ** places
    truncated = (value * scale).numerator // (value * scale).denominator
    whole, fraction = divmod(truncated, scale)
    return "{0}.{1:0{2}d}".format(whole, fraction, places)


def scope_violations(
    files: Sequence[str], required_packages: Sequence[str]
) -> Tuple[List[str], List[str]]:
    """Return ``(files_outside_scope, packages_with_no_measured_file)``.

    Both halves are needed. A file outside the scope means the denominator is
    wider than the threshold was calibrated for, which inflates or deflates the
    total against a different population. A package with no measured file means it
    is missing from the denominator entirely - the total then describes three
    packages while claiming four.
    """
    prefixes = [normalize_path(package).rstrip("/") + "/" for package in required_packages]
    normalized = [normalize_path(name) for name in files]

    outside = [
        name
        for name in normalized
        if not any(name.startswith(prefix) for prefix in prefixes)
    ]
    empty = [
        package
        for package, prefix in zip(required_packages, prefixes)
        if not any(name.startswith(prefix) for name in normalized)
    ]
    return outside, empty


def _build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser for :func:`main`."""
    parser = argparse.ArgumentParser(
        prog="coverage_gate",
        description=(
            "Gate a coverage JSON report on an exact count ratio and on the "
            "packages it measured."
        ),
    )
    parser.add_argument(
        "--coverage-json",
        default=DEFAULT_COVERAGE_JSON,
        metavar="FILE",
        help="coverage JSON report to read (default: %(default)s)",
    )
    parser.add_argument(
        "--fail-under",
        default=DEFAULT_FAIL_UNDER,
        metavar="PERCENT",
        help="minimum coverage percentage, compared exactly (default: %(default)s)",
    )
    parser.add_argument(
        "--require-scope",
        action="append",
        default=None,
        metavar="PACKAGE",
        help=(
            "package the report must be confined to; repeatable. Defaults to the "
            "four gated backend packages. Pass --no-require-scope to skip the check."
        ),
    )
    parser.add_argument(
        "--no-require-scope",
        action="store_true",
        help="check the total only, without checking which packages were measured",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Read the report, apply both checks, print the reading, and return the status."""
    args = _build_parser().parse_args(argv)

    try:
        threshold = parse_threshold(args.fail_under)
    except (ValueError, ZeroDivisionError) as error:
        sys.stderr.write("invalid --fail-under: {0}\n".format(error))
        return EXIT_GATE_FAILED

    try:
        report = load_report(args.coverage_json)
        covered, statements = report_counts(report)
    except ReportUnavailable as error:
        sys.stderr.write("coverage gate: {0}\n".format(error))
        return EXIT_NO_REPORT

    files = measured_files(report)
    measured = exact_percentage(covered, statements)

    sys.stdout.write(
        "coverage gate: {0} of {1} statements covered = {2}% exact, "
        "threshold {3}%\n".format(
            covered, statements, format_percentage(measured), args.fail_under
        )
    )

    failures: List[str] = []

    if not meets_threshold(covered, statements, threshold):
        failures.append(
            "total coverage {0}% is below the required {1}% - compared as "
            "{2} * 100 >= {1} * {3}, which is false".format(
                format_percentage(measured), args.fail_under, covered, statements
            )
        )

    if not args.no_require_scope:
        required = args.require_scope if args.require_scope else list(GATED_PACKAGES)
        outside, empty = scope_violations(files, required)
        sys.stdout.write(
            "coverage gate: {0} file(s) measured, scope {1}\n".format(
                len(files), ", ".join(required)
            )
        )
        if outside:
            failures.append(
                "measured outside the gated scope: {0} - the total was computed "
                "over a different denominator from the one the threshold is "
                "calibrated against".format(", ".join(outside))
            )
        if empty:
            failures.append(
                "no measured file in: {0} - the total describes fewer packages "
                "than it claims".format(", ".join(empty))
            )

    if failures:
        for failure in failures:
            sys.stderr.write("coverage gate FAILED: {0}\n".format(failure))
        return EXIT_GATE_FAILED

    sys.stdout.write("coverage gate PASSED\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
