"""Gate on the exactness of the backend coverage threshold.

Subject
-------
``backend/.coveragerc`` and the pytest-cov machinery that reads it. The coverage
target this repository is measured against is enforced by the runner through
``--cov-fail-under=90``, and that flag's comparison is
``round(total, precision) < fail_under`` in
:func:`coverage.results.should_fail_under`. ``precision`` therefore decides which
totals the gate admits, and it is a configuration value rather than part of the
flag.

What is asserted
----------------
* ``backend/.coveragerc`` exists and sets ``[report] precision`` to 2.
* :class:`coverage.Coverage` built from that file reports ``precision == 2``,
  which is the attribute pytest-cov reads when ``--cov-precision`` is absent.
* At precision 2, ``should_fail_under`` refuses 89.5, 89.93 and 89.99 against a
  threshold of 90 and admits 90.0 and 90.01 - so the gate bites at the resolution
  pytest-cov reports the total in, which its message formats as ``.2f``.
* At precision 0, the same call **admits** every one of those sub-90 totals. This
  is the behaviour the configuration removes, asserted directly so the reason the
  file exists cannot be lost.
* The residual band a two-decimal comparison still admits - a total in
  ``[89.995, 90)``, which rounds to ``90.00`` - is asserted rather than omitted:
  such a total is admitted, and it is also indistinguishable from ``90.00`` in the
  printed message, so the exit status and the message agree. No finite precision
  removes that band; 2 is the precision at which it is invisible in the report.
* ``backend/.coveragerc`` declares no ``fail_under`` and no ``[run] source``, so
  the threshold and the measured scope remain command-line arguments.
* ``backend/pytest.ini`` carries neither ``--cov-fail-under`` nor ``--cov`` in
  ``addopts``, so an ungated measurement run stays ungated.

Scope
-----
This module reads two text files and calls one pure function from
:mod:`coverage.results`. It imports no ``app`` module, opens no socket and needs
no fixture.

.. seealso:: ``docs/testing/DECISION-LOG.md`` for why the precision is 2 rather
   than 0 or 1, and ``docs/testing/DASHBOARD-TEMPLATE.md`` for the KPI the gate
   protects.
"""

import configparser
import os

import pytest
from coverage import Coverage
from coverage.results import should_fail_under

pytestmark = pytest.mark.unit

#: ``backend/`` - the directory pytest is invoked from, resolved from this file
#: rather than from the working directory.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COVERAGERC_PATH = os.path.join(BACKEND_ROOT, ".coveragerc")

PYTEST_INI_PATH = os.path.join(BACKEND_ROOT, "pytest.ini")

#: Digits after the decimal point the gate must compare at.
REQUIRED_PRECISION = 2

#: The threshold the CI workflow and the documented gated command pass.
GATED_THRESHOLD = 90.0

#: Totals below :data:`GATED_THRESHOLD` that round up to it at precision 0 and
#: down at precision 2.
ADMITTED_AT_PRECISION_ZERO = (89.5, 89.93, 89.99)

#: Totals in the band a two-decimal comparison still admits, because they round
#: to exactly ``90.00``.
ROUNDING_TO_THE_THRESHOLD = (89.995, 89.9999)

#: Totals at or above the threshold, which must pass at either precision.
PASSING_TOTALS = (90.0, 90.01, 91.79, 100.0)


def _coveragerc():
    """Return ``backend/.coveragerc`` parsed as an ini document."""
    parser = configparser.ConfigParser()
    with open(COVERAGERC_PATH, encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser


def test_coveragerc_exists():
    """The configuration file the gate depends on is present."""
    assert os.path.isfile(COVERAGERC_PATH)


def test_coveragerc_sets_report_precision():
    """``[report] precision`` is declared and equal to :data:`REQUIRED_PRECISION`."""
    parser = _coveragerc()

    assert parser.has_section("report")
    assert parser.getint("report", "precision") == REQUIRED_PRECISION


def test_coverage_reads_the_precision_from_the_file():
    """The precision pytest-cov reads is the one the file declares.

    ``pytest_cov.plugin`` falls back to ``getattr(cov_config, "precision", 0)``
    when ``--cov-precision`` is absent, so this is the value the gate uses.
    """
    coverage = Coverage(config_file=COVERAGERC_PATH)

    assert coverage.config.precision == REQUIRED_PRECISION


@pytest.mark.parametrize("total", ADMITTED_AT_PRECISION_ZERO)
def test_a_sub_threshold_total_fails_at_the_configured_precision(total):
    """A total below 90 fails the gate once the precision is 2."""
    assert should_fail_under(total, GATED_THRESHOLD, REQUIRED_PRECISION) is True


@pytest.mark.parametrize("total", ADMITTED_AT_PRECISION_ZERO)
def test_the_same_total_is_admitted_at_the_default_precision(total):
    """The same total passes at precision 0, which is what the file removes."""
    assert should_fail_under(total, GATED_THRESHOLD, 0) is False


@pytest.mark.parametrize("total", PASSING_TOTALS)
def test_a_total_at_or_above_the_threshold_passes(total):
    """The configuration does not reject a total that meets the threshold."""
    assert should_fail_under(total, GATED_THRESHOLD, REQUIRED_PRECISION) is False


@pytest.mark.parametrize("total", ROUNDING_TO_THE_THRESHOLD)
def test_a_total_rounding_to_the_threshold_is_still_admitted(total):
    """A total in ``[89.995, 90)`` passes: the residual of a finite precision."""
    assert should_fail_under(total, GATED_THRESHOLD, REQUIRED_PRECISION) is False


@pytest.mark.parametrize("total", ROUNDING_TO_THE_THRESHOLD)
def test_an_admitted_residual_total_prints_as_the_threshold(total):
    """That residual is reported as ``90.00``, so status and message agree.

    pytest-cov formats the total with ``{actual:.2f}``, and a value the gate
    admits at precision 2 is by construction one that format renders as ``90.00``
    or higher - so no run can print a sub-threshold number and exit 0.
    """
    assert "{0:.2f}".format(total) == "90.00"


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
