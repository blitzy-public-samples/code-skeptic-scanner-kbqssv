"""Gate on the exactness of the backend coverage threshold.

Subject
-------
The two-part coverage gate:

* ``backend/tests/coverage_gate.py`` - the **binding** comparison. It reads the
  integer counts out of ``backend/coverage.json`` and compares
  ``covered * 100 >= threshold * statements`` as exact rational arithmetic, and it
  refuses a report whose measured files fall outside the four gated packages.
* ``backend/.coveragerc`` - the **reporting** precision, ``[report] precision = 2``,
  which is the resolution pytest-cov formats and compares the total at while the
  run is still in progress.

Why both, stated as behaviour rather than as intent: ``--cov-fail-under`` compares
``round(total, precision) < fail_under``
(:func:`coverage.results.should_fail_under`), and *no* finite precision closes that
comparison. At the library default of 0 decimals a threshold of 90 admits every
total from ``89.5`` upward; at two decimals it still admits the band
``[89.995, 90)``. So the rounded comparison cannot be made literal by configuring
it, and the exact comparison is a separate step. What the precision setting *does*
achieve is that the number pytest-cov prints agrees with the status it exits on.

What is asserted
----------------
* ``backend/.coveragerc`` exists, sets ``[report] precision`` to 2, and that is the
  value :class:`coverage.Coverage` derives from it - the attribute pytest-cov reads
  when ``--cov-precision`` is absent.
* At precision 2 the rounded comparison refuses 89.5, 89.93 and 89.99, and at
  precision 0 it **admits** every one of them. That is the behaviour the
  configuration removes, asserted directly.
* The residual band the rounded comparison still admits - a total in
  ``[89.995, 90)`` - is admitted by ``should_fail_under`` and **rejected by the
  delivered gate**. Both halves are asserted on the same values, because the pair
  is the whole reason the exact gate exists.
* The exact gate's arithmetic, formatting, report loading, scope checking and exit
  statuses, each driven directly.
* ``backend/.coveragerc`` declares no ``fail_under`` and no ``[run] source``, so the
  threshold and the measured scope remain command-line arguments.
* ``backend/pytest.ini`` carries neither ``--cov-fail-under`` nor ``--cov`` in
  ``addopts``, so an ungated measurement run stays ungated.
* ``.github/workflows/ci.yml`` invokes the exact gate after the gated pytest step,
  so the binding half cannot be dropped from the pipeline without failing a test.

Scope
-----
This module reads three text files, calls one pure function from
:mod:`coverage.results`, and drives ``tests/coverage_gate.py`` against temporary
JSON payloads. It imports no ``app`` module, opens no socket and needs no fixture
beyond :func:`tmp_path`.

.. seealso:: ``docs/testing/DECISION-LOG.md`` for why the gate is two parts, and
   ``docs/testing/DASHBOARD-TEMPLATE.md`` §3.1 for the G1 contract it enforces.
"""

import configparser
import json
import os

import pytest
from coverage import Coverage
from coverage.results import should_fail_under

from tests import coverage_gate

pytestmark = pytest.mark.unit

#: ``backend/`` - the directory pytest is invoked from, resolved from this file
#: rather than from the working directory.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The repository root, one level above ``backend/``.
REPOSITORY_ROOT = os.path.dirname(BACKEND_ROOT)

COVERAGERC_PATH = os.path.join(BACKEND_ROOT, ".coveragerc")

PYTEST_INI_PATH = os.path.join(BACKEND_ROOT, "pytest.ini")

WORKFLOW_PATH = os.path.join(REPOSITORY_ROOT, ".github", "workflows", "ci.yml")

#: Digits after the decimal point the *report* is rendered and compared at.
REQUIRED_PRECISION = 2

#: The threshold the CI workflow and the documented gated command pass.
GATED_THRESHOLD = 90.0

#: Totals below :data:`GATED_THRESHOLD` that round up to it at precision 0 and
#: down at precision 2.
ADMITTED_AT_PRECISION_ZERO = (89.5, 89.93, 89.99)

#: Totals at or above the threshold, which must pass at either precision.
PASSING_TOTALS = (90.0, 90.01, 93.33, 100.0)

#: ``(covered, statements, float total)`` triples whose exact percentage lies in the
#: residual band ``[89.995, 90)`` - below the threshold, yet rounding to ``90.00``.
#: The exact gate must reject every one; ``should_fail_under`` admits every one.
RESIDUAL_BAND_COUNTS = (
    pytest.param(17999, 20000, 89.995, id="89.995"),
    pytest.param(899999, 1000000, 89.9999, id="89.9999"),
    pytest.param(8999999, 10000000, 89.99999, id="89.99999"),
)


def _coveragerc():
    """Return ``backend/.coveragerc`` parsed as an ini document."""
    parser = configparser.ConfigParser()
    with open(COVERAGERC_PATH, encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser


def _write_report(directory, covered, statements, files=("app/core/config.py",)):
    """Write a minimal coverage JSON report and return its path.

    Carries only the keys the gate reads, so a case states exactly the condition it
    is about.
    """
    payload = {
        "meta": {"branch_coverage": False},
        "files": {name: {"summary": {}} for name in files},
        "totals": {"covered_lines": covered, "num_statements": statements},
    }
    path = os.path.join(str(directory), "coverage.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


#: One measured file per gated package, so a scope check passes by default.
FULL_SCOPE_FILES = (
    "app/core/config.py",
    "app/services/llm_service.py",
    "app/tasks/tweet_processor.py",
    "app/db/firestore.py",
)


# --------------------------------------------------------------------------- #
# The reporting precision - backend/.coveragerc
# --------------------------------------------------------------------------- #


def test_coveragerc_exists():
    """The configuration file the reported precision depends on is present."""
    assert os.path.isfile(COVERAGERC_PATH)


def test_coveragerc_sets_report_precision():
    """``[report] precision`` is declared and equal to :data:`REQUIRED_PRECISION`."""
    parser = _coveragerc()

    assert parser.has_section("report")
    assert parser.getint("report", "precision") == REQUIRED_PRECISION


def test_coverage_reads_the_precision_from_the_file():
    """The precision pytest-cov reads is the one the file declares.

    ``pytest_cov.plugin`` falls back to ``getattr(cov_config, "precision", 0)``
    when ``--cov-precision`` is absent, so this is the value the in-run comparison
    uses.
    """
    coverage = Coverage(config_file=COVERAGERC_PATH)

    assert coverage.config.precision == REQUIRED_PRECISION


@pytest.mark.parametrize("total", ADMITTED_AT_PRECISION_ZERO)
def test_a_sub_threshold_total_fails_at_the_configured_precision(total):
    """A total below 90 fails the in-run comparison once the precision is 2."""
    assert should_fail_under(total, GATED_THRESHOLD, REQUIRED_PRECISION) is True


@pytest.mark.parametrize("total", ADMITTED_AT_PRECISION_ZERO)
def test_the_same_total_is_admitted_at_the_default_precision(total):
    """The same total passes at precision 0, which is what the file removes."""
    assert should_fail_under(total, GATED_THRESHOLD, 0) is False


@pytest.mark.parametrize("total", PASSING_TOTALS)
def test_a_total_at_or_above_the_threshold_passes(total):
    """The configuration does not reject a total that meets the threshold."""
    assert should_fail_under(total, GATED_THRESHOLD, REQUIRED_PRECISION) is False


def test_coveragerc_declares_no_threshold():
    """No ``fail_under`` here, so an ungated ``--cov`` run stays ungated.

    pytest-cov adopts ``cov_config.fail_under`` when ``--cov-fail-under`` is
    absent, so a value in this file would gate the documented
    coverage-measurement command as well as the gated one.
    """
    parser = _coveragerc()

    assert not parser.has_option("report", "fail_under")


def test_coveragerc_declares_no_measured_scope():
    """No ``[run] source``, so the ``--cov=`` scoping on the command line stands."""
    parser = _coveragerc()

    assert not (parser.has_section("run") and parser.has_option("run", "source"))


def test_pytest_ini_does_not_carry_the_gate():
    """``addopts`` names neither ``--cov`` nor ``--cov-fail-under``.

    The gate is an argument of the CI step and of the documented gated command;
    putting it in ``addopts`` would make every invocation, including
    ``--collect-only``, measure and gate.
    """
    parser = configparser.ConfigParser()
    with open(PYTEST_INI_PATH, encoding="utf-8") as handle:
        parser.read_file(handle)
    addopts = parser.get("pytest", "addopts")

    assert "--cov" not in addopts


# --------------------------------------------------------------------------- #
# The residual band: admitted by rounding, rejected by the delivered gate
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("covered", "statements", "total"), RESIDUAL_BAND_COUNTS)
def test_a_residual_band_total_is_admitted_by_the_rounded_comparison(
    covered, statements, total
):
    """``should_fail_under`` lets a total in ``[89.995, 90)`` through.

    Asserted rather than assumed, because it is the premise of the case below: if
    rounding ever stopped admitting these totals the exact gate would be redundant,
    and this suite should say so by failing.
    """
    assert exact_ratio_is_below_threshold(covered, statements)
    assert should_fail_under(total, GATED_THRESHOLD, REQUIRED_PRECISION) is False


@pytest.mark.parametrize(("covered", "statements", "total"), RESIDUAL_BAND_COUNTS)
def test_a_residual_band_total_is_rejected_by_the_exact_gate(
    covered, statements, total
):
    """The delivered gate refuses every total the rounded comparison admits.

    This is the contract change the two-part gate makes: ``>= 90%`` now means what
    it says, for every total, at every distance below the bar.
    """
    threshold = coverage_gate.parse_threshold("90")

    assert coverage_gate.meets_threshold(covered, statements, threshold) is False


@pytest.mark.parametrize(("covered", "statements", "total"), RESIDUAL_BAND_COUNTS)
def test_a_residual_band_report_exits_non_zero(covered, statements, total, tmp_path):
    """End to end: a report in the residual band fails the gate command."""
    report = _write_report(tmp_path, covered, statements, FULL_SCOPE_FILES)

    status = coverage_gate.main(
        ["--coverage-json", report, "--fail-under", "90"]
    )

    assert status == coverage_gate.EXIT_GATE_FAILED


def exact_ratio_is_below_threshold(covered, statements):
    """Whether ``covered / statements`` is strictly below 90 percent, exactly."""
    return covered * 100 < 90 * statements


# --------------------------------------------------------------------------- #
# The exact gate's arithmetic
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("covered", "statements", "expected"),
    [
        (90, 100, True),
        (9000, 10000, True),
        (9001, 10000, True),
        (8999, 10000, False),
        (182, 195, True),
        (0, 0, False),
        (1, 1, True),
    ],
)
def test_meets_threshold_compares_counts_exactly(covered, statements, expected):
    """Exactly-90% passes, one statement short fails, and an empty run fails."""
    threshold = coverage_gate.parse_threshold("90")

    assert coverage_gate.meets_threshold(covered, statements, threshold) is expected


def test_a_zero_threshold_admits_an_empty_measurement():
    """With no statements measured, only a threshold of zero is satisfiable."""
    zero = coverage_gate.parse_threshold("0")

    assert coverage_gate.meets_threshold(0, 0, zero) is True


def test_a_fractional_threshold_is_compared_without_binary_rounding():
    """``93.33`` is the decimal written, not the nearest float to it.

    ``182/195`` is ``93.333...``, which clears ``93.33`` and not ``93.34``. Both
    directions are asserted, because a float-based comparison of the same values
    can land either way depending on the literal.
    """
    assert coverage_gate.meets_threshold(182, 195, coverage_gate.parse_threshold("93.33"))
    assert not coverage_gate.meets_threshold(
        182, 195, coverage_gate.parse_threshold("93.34")
    )


@pytest.mark.parametrize("text", ["-1", "101", "abc", ""])
def test_an_out_of_range_or_unparseable_threshold_is_refused(text):
    """A threshold outside ``[0, 100]`` or not a number raises rather than defaulting."""
    with pytest.raises((ValueError, ZeroDivisionError)):
        coverage_gate.parse_threshold(text)


def test_exact_percentage_is_a_rational_not_a_float():
    """The percentage keeps full precision, so no comparison rounds it first."""
    value = coverage_gate.exact_percentage(1, 3)

    assert value is not None
    assert value.numerator == 100
    assert value.denominator == 3
    assert coverage_gate.exact_percentage(0, 0) is None


@pytest.mark.parametrize(
    ("covered", "statements", "expected"),
    [
        (899999, 1000000, "89.9999"),
        (17999, 20000, "89.9950"),
        (182, 195, "93.3333"),
        (1, 1, "100.0000"),
        (0, 1, "0.0000"),
    ],
)
def test_a_percentage_is_truncated_rather_than_rounded(covered, statements, expected):
    """Rendering never rounds a sub-threshold total up to the bar."""
    value = coverage_gate.exact_percentage(covered, statements)

    assert coverage_gate.format_percentage(value) == expected


def test_a_percentage_with_nothing_measured_renders_as_not_applicable():
    """An empty measurement prints ``n/a`` rather than ``0.0000``."""
    assert coverage_gate.format_percentage(None) == "n/a"


# --------------------------------------------------------------------------- #
# The exact gate's scope check
# --------------------------------------------------------------------------- #


def test_the_gated_packages_are_the_four_the_threshold_is_calibrated_for():
    """The default scope is the four packages the CI command names."""
    assert coverage_gate.GATED_PACKAGES == (
        "app/core",
        "app/services",
        "app/tasks",
        "app/db",
    )


def test_a_report_confined_to_the_gated_packages_has_no_scope_violation():
    """One measured file per gated package satisfies both halves of the check."""
    outside, empty = coverage_gate.scope_violations(
        FULL_SCOPE_FILES, coverage_gate.GATED_PACKAGES
    )

    assert outside == []
    assert empty == []


def test_a_whole_tree_report_is_reported_as_out_of_scope():
    """A file outside the four packages widens the denominator and is named.

    This is the condition a whole-``app`` measurement produces, and it is exactly
    the substitution that would let a 90.97% whole-tree total be read as the G1
    figure.
    """
    outside, empty = coverage_gate.scope_violations(
        FULL_SCOPE_FILES + ("app/main.py", "app/api/routes/tweets.py"),
        coverage_gate.GATED_PACKAGES,
    )

    assert outside == ["app/main.py", "app/api/routes/tweets.py"]
    assert empty == []


def test_a_package_with_no_measured_file_is_reported():
    """A gated package absent from the report is named, not silently dropped."""
    outside, empty = coverage_gate.scope_violations(
        ("app/core/config.py",), coverage_gate.GATED_PACKAGES
    )

    assert outside == []
    assert empty == ["app/services", "app/tasks", "app/db"]


def test_a_windows_separator_is_normalized_before_the_scope_comparison():
    """``coverage.json`` keys files with the writing platform's separator."""
    outside, empty = coverage_gate.scope_violations(
        ("app\\core\\config.py",), ("app/core",)
    )

    assert outside == []
    assert empty == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("app\\core\\config.py", "app/core/config.py"),
        ("./app/core/config.py", "app/core/config.py"),
        ("app/core/config.py", "app/core/config.py"),
    ],
)
def test_path_normalization_is_platform_independent(raw, expected):
    """Separator and leading-``./`` differences do not change a path's identity."""
    assert coverage_gate.normalize_path(raw) == expected


def test_scope_checking_can_be_switched_off_for_a_wider_measurement(tmp_path):
    """``--no-require-scope`` gates the total alone, for a deliberately wider run."""
    report = _write_report(tmp_path, 95, 100, ("app/main.py",))

    assert (
        coverage_gate.main(
            ["--coverage-json", report, "--fail-under", "90", "--no-require-scope"]
        )
        == coverage_gate.EXIT_OK
    )
    assert (
        coverage_gate.main(["--coverage-json", report, "--fail-under", "90"])
        == coverage_gate.EXIT_GATE_FAILED
    )


# --------------------------------------------------------------------------- #
# The exact gate's report handling and exit statuses
# --------------------------------------------------------------------------- #


def test_a_passing_report_exits_zero(tmp_path):
    """A report at the threshold and in scope exits 0."""
    report = _write_report(tmp_path, 90, 100, FULL_SCOPE_FILES)

    assert (
        coverage_gate.main(["--coverage-json", report, "--fail-under", "90"])
        == coverage_gate.EXIT_OK
    )


def test_a_missing_report_is_its_own_exit_status(tmp_path):
    """No report means nothing was measured, which is not the same as measuring low."""
    missing = os.path.join(str(tmp_path), "absent.json")

    assert (
        coverage_gate.main(["--coverage-json", missing])
        == coverage_gate.EXIT_NO_REPORT
    )


def test_a_malformed_report_is_refused_rather_than_read_as_zero(tmp_path):
    """Unparseable JSON exits with the no-report status."""
    path = os.path.join(str(tmp_path), "coverage.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not json")

    assert (
        coverage_gate.main(["--coverage-json", path]) == coverage_gate.EXIT_NO_REPORT
    )


def test_a_report_without_totals_is_refused(tmp_path):
    """A JSON document that is not a coverage report is refused by shape."""
    path = os.path.join(str(tmp_path), "coverage.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"files": {}}, handle)

    with pytest.raises(coverage_gate.ReportUnavailable):
        coverage_gate.load_report(path)


def test_inconsistent_totals_are_refused(tmp_path):
    """More covered lines than statements is a broken report, not 100% coverage."""
    report = _write_report(tmp_path, 200, 100, FULL_SCOPE_FILES)

    with pytest.raises(coverage_gate.ReportUnavailable):
        coverage_gate.report_counts(coverage_gate.load_report(report))


def test_counts_and_files_are_read_from_the_real_report():
    """The two readers work on the report the gated command actually writes.

    Skipped rather than failed when no report is present, because a bare ``pytest``
    run deliberately requests no coverage and this module must stay runnable on its
    own.
    """
    path = os.path.join(BACKEND_ROOT, "coverage.json")
    if not os.path.isfile(path):
        pytest.skip("backend/coverage.json is written by the gated coverage command")

    report = coverage_gate.load_report(path)
    covered, statements = coverage_gate.report_counts(report)

    assert statements > 0
    assert 0 <= covered <= statements
    assert coverage_gate.measured_files(report) != ()


def test_an_invalid_threshold_on_the_command_line_fails_the_gate(tmp_path):
    """A malformed ``--fail-under`` fails rather than falling back to a default."""
    report = _write_report(tmp_path, 100, 100, FULL_SCOPE_FILES)

    assert (
        coverage_gate.main(["--coverage-json", report, "--fail-under", "ninety"])
        == coverage_gate.EXIT_GATE_FAILED
    )


# --------------------------------------------------------------------------- #
# The gate is wired into the pipeline
# --------------------------------------------------------------------------- #


def test_the_workflow_runs_the_exact_gate_after_the_gated_pytest_step():
    """``ci.yml`` invokes ``tests/coverage_gate.py``, so the binding half ships.

    Asserted against the workflow text because the exact comparison is a separate
    command: without this case it could be deleted from the pipeline while every
    other assertion in this module still passed.
    """
    with open(WORKFLOW_PATH, encoding="utf-8") as handle:
        workflow = handle.read()

    assert "tests/coverage_gate.py" in workflow
    assert "--cov-report=json" in workflow

    gate_index = workflow.index("tests/coverage_gate.py")
    pytest_index = workflow.index("--cov-fail-under=90")

    assert pytest_index < gate_index
