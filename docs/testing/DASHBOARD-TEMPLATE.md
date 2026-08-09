# Test Observability Dashboard — Template

**This is a template, not a report.** It defines the panels, metrics, source artifacts and
thresholds for the five-layer test suite, so that any run can be written up the same way and two
runs can be compared line by line. Cells marked `_____` are fill slots, and
[`./dashboard-extract.py`](./dashboard-extract.py) is what fills them from the artifacts.

Nothing in a `_____` slot is a live reading of the current tree. Numbers **are** stated as fact in
exactly four places, each labelled: the **baseline** in §1.2, the **gate-exactness measurement** in
§3.2, the **verified artifact generation** in §7.1, and the **acceptance record** in §7.2. Each of
those carries the command, runtime and artifact it came from, per the provenance form at the head of
§7.

This document is also the **definitional source for the metric contract**: the artifact paths, the
gate scopes and the threshold values below are the canonical statements of those facts. Wherever the
same figures appear elsewhere — the Testing section of the root `README.md` under Rule 3 (Onboarding
& Continued Development), or the KPI slides of `blitzy-deck/executive-summary.html` under Rule 4
(Executive Presentation) — those are projections of this file and are expected to point back here
rather than restate it. If one of them ever disagrees with this document, this document is the one to
trust and the other is the one to correct. Figures in §1 are therefore stated to their full recorded
precision, so a slide can lift one without recalculating or rounding it.

**Scope.** Rule 2 (Observability) is satisfied here against the **test system** rather than the
production application, because instrumenting production would require both an unauthorized
production change and the implementation of missing product features — resolved as conflict **C1**
and recorded in [`./DECISION-LOG.md`](./DECISION-LOG.md) §21. That decision is not re-argued in this
document.

## Related documents

| Document | What it carries |
|---|---|
| [`./DECISION-LOG.md`](./DECISION-LOG.md) | The single source of truth for **why**, per Rule 1 (Explainability). Every rationale behind a number in this file lives there — §7 for the coverage gates, §8 for test-system observability, §21 for the conflict resolutions, §23 for the noted-but-not-fixed register. |
| [`./TRACEABILITY-MATRIX.md`](./TRACEABILITY-MATRIX.md) | The bidirectional matrix Rule 1 requires for a migration. §E holds the 25-function legacy disposition, §F maps every test artifact to the construct it covers, and §G maps each coverage ceiling to the assertion that stands in for it. |
| [`./dashboard-extract.py`](./dashboard-extract.py) | The **producer** for this template. Reads every artifact in §2 and emits §1.1, §3.1 and §6.1-§6.6 already filled, so no panel is ever transcribed by hand. Standard library only, Python 3.9, no manifest entry. |

## How to use this template

### 1. Produce the artifacts, in this order

The order is load-bearing, not stylistic. `pytest --collect-only` and `playwright test --list` both
write their **configured reporters**, so either will overwrite a real result stream with a zero-case
discovery stub. Readiness therefore runs *before* the suite it reports on, in exactly the order
`.github/workflows/ci.yml` uses.

Order is no longer the *only* protection, and it should not be. Each readiness command below carries its
own neutraliser — the backend probe repeats `--junitxml` to a separate file, `test:load` pins
`--reporters=default`, `test:list` pins `--reporter=line` — so running one out of order costs nothing.
Independently of that, the backend result stream's case count is required to equal the collected count
this step records; a partial run is named and refused rather than published (`D355`).

Every command below is one a CI step also runs, and every one **creates the artifact §2 names** —
including the three readiness text files, which nothing else produces. Both shells are given because
the redirection differs and a POSIX-only instruction is not a cross-platform instruction.

**POSIX shells**

```bash
# 1. Readiness - creates the three .txt artifacts §2 requires
mkdir -p backend/reports frontend/reports e2e/reports
(cd backend  && pytest --collect-only -q --junitxml=reports/collect-only-junit.xml \
                  | tee reports/collect-only.txt)
(cd frontend && npm run --silent test:load 2>&1   | tee reports/load-tests.txt)
(cd e2e      && npm run --silent test:list        | tee reports/list-tests.txt)

# 2. The suites. The backend pair below is the CANONICAL producer command - see §2.1
(cd backend  && pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db \
                  --cov-report=term-missing --cov-report=xml --cov-report=json \
                  --cov-precision=2 --cov-fail-under=90 --junitxml=reports/junit.xml)
(cd backend  && python tests/coverage_gate.py --coverage-json coverage.json --fail-under 90 \
                  --require-scope app/core --require-scope app/services \
                  --require-scope app/tasks --require-scope app/db | tee reports/coverage-gate.txt)
(cd frontend && npm run test:ci)
(cd e2e      && npm run --silent browsers:require | tee reports/browser.txt)
(cd e2e      && npm test)
```

**PowerShell**

```powershell
# 1. Readiness
New-Item -ItemType Directory -Force backend\reports, frontend\reports, e2e\reports | Out-Null
cd backend;  cmd /c "pytest --collect-only -q --junitxml=reports/collect-only-junit.xml 2>&1" | Tee-Object reports\collect-only.txt; cd ..
cd frontend; cmd /c "npm run --silent test:load 2>&1"      | Tee-Object reports\load-tests.txt;   cd ..
cd e2e;      cmd /c "npm run --silent test:list 2>&1"      | Tee-Object reports\list-tests.txt;   cd ..

# 2. The suites
cd backend
pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-report=term-missing --cov-report=xml --cov-report=json --cov-precision=2 --cov-fail-under=90 --junitxml=reports/junit.xml
cmd /c "python tests\coverage_gate.py --coverage-json coverage.json --fail-under 90 --require-scope app/core --require-scope app/services --require-scope app/tasks --require-scope app/db 2>&1" | Tee-Object reports\coverage-gate.txt
cd ..\frontend; npm run test:ci; cd ..
cd e2e; cmd /c "npm run --silent browsers:require 2>&1" | Tee-Object reports\browser.txt; npm test; cd ..
```

Two PowerShell details, both measured rather than assumed:

- **`cmd /c "… 2>&1"` rather than a bare `2>&1`.** PowerShell turns a native command's stderr into
  `ErrorRecord` objects, which `Tee-Object` then reformats — and Jest writes its whole summary to
  stderr, so a bare redirection loses the counts. Letting `cmd` merge the streams first keeps the
  retained text identical to what the terminal showed, and `$LASTEXITCODE` still carries the status.
  Do not append `| Select-Object -First n` to one of these pipelines if you care about the exit code:
  stopping the pipeline early leaves `$LASTEXITCODE` at `-1`.
- **`Tee-Object` writes UTF-16LE on PowerShell 5.1**, which has no `-Encoding` parameter. The extractor
  decodes by byte-order mark — UTF-16, UTF-32 and UTF-8-with-BOM as well as plain UTF-8 — so an
  artifact captured on either platform is read identically. Without that, a UTF-16 file decodes into
  NUL-separated characters, every regex silently fails to match, and a perfectly good run is reported
  as three missing measurements.

### 2. Fill the panels with the extractor, never by hand

`docs/testing/dashboard-extract.py` reads every artifact in §2 and emits §1.0, §1.1, §3.1, §6.1,
§6.2, §6.3, §6.4, §6.5 and §6.6 already filled. Run it from the repository root, writing into
`docs/testing/reports/`, which the repository `.gitignore` covers — a reading is a generated artifact
like any other, and neither file below is a committed record:

```bash
mkdir -p docs/testing/reports
python docs/testing/dashboard-extract.py --require-all > docs/testing/reports/run-write-up.md
python docs/testing/dashboard-extract.py --json        > docs/testing/reports/run.json
python docs/testing/dashboard-extract.py --previous docs/testing/reports/previous-run.json
```

`--require-all` exits 1 and names any artifact that is **absent or unusable**, so a partial run
cannot quietly become a partial dashboard. Unusable matters as much as absent: a result stream can
be present, well-formed, and still declare `tests="0"` for the reporter-overwriting reason above.
Rendered naively that reads as a clean run of nothing, so the extractor refuses it and names the
command that overwrote it. `--json` is the form to keep for the next run's `--previous`.

### 3. Read the result honestly

- Copy the extractor's output, or the panels you need from it, into the run write-up. Fill anything
  the extractor does not produce — §3.3 dispositions, §7 acceptance state — from the **stated
  source only**. A number typed from memory or from a terminal scrollback is not traceable to a run
  and defeats the purpose of the panel.
- Where a panel has a *ceiling or gap?* column, resolve it against §3.3 before recording work.
  A ceiling is not a gap, and treating one as a gap drives exactly the scope expansion the
  programme forbids.
- Pass the previous run's `--json` output to `--previous` so the trend panel (§6.6) carries a delta
  rather than a bare current value: a regression that is recorded but not compared is a regression
  nobody notices.

Every artifact path in §2, and both extractor outputs above, are matched by a rule in the repository
`.gitignore`, so filling this template never adds a generated file to version control. Every artifact
in §2 is also uploaded by `.github/workflows/ci.yml` — §2.4 is the retention contract.

---

## 1. KPI header panel

### 1.1 Current run

The headline panel: eight rows covering coverage, test health, collection integrity and duration,
each with the artifact that is its only admissible source. These are the values the executive deck
lifts verbatim — keep them exact and do not round.

Every row is produced by `dashboard-extract.py`; the `_____` slots are for a hand-filled copy of the
panel and should agree with the extractor's output exactly.

| # | KPI | Source artifact | Target | Value |
|---|---|---|---|---|
| K1 | Backend line coverage, the **aggregate** of the four gated packages (`app/core`, `app/services`, `app/tasks`, `app/db`) | `backend/coverage.xml` root `lines-covered` / `lines-valid` | **≥ 90%** | `_____` |
| K2 | Frontend coverage, the three gated packages (`src/store`, `src/schema`, `src/services`) combined — statements / branches / functions / lines | `frontend/coverage/coverage-summary.json` | **≥ 80%** on all four | `_____` |
| K3 | Backend test **cases**: total / passed / failed / skipped | `backend/reports/junit.xml` root attributes | 0 failed | `_____` |
| K4 | Frontend test **cases**: total / passed / failed / skipped | `frontend/reports/jest-junit.xml` (root `tests`/`failures`; `skipped` summed from the suites, which is the only place jest-junit records it) | 0 failed | `_____` |
| K5 | Backend collection errors | `backend/reports/collect-only.txt`, the retained output of the CI readiness step | **0** | `_____` |
| K6 | E2E test **cases**: total / passed / failed / skipped — these are `<testcase>` elements, **not** spec files | `e2e/reports/e2e-junit.xml` root attributes | 0 failed | `_____` |
| K6b | E2E **spec files** — the `<testsuite>` count, which is the route census, reported separately from K6 so the two are never conflated | `e2e/reports/e2e-junit.xml` | census, no target | `_____` |
| K7 | Wall-clock seconds, per layer (backend / frontend / e2e) | the `time` attribute of the root element of each JUnit artifact | no fixed target; record for trend | `_____` |

### 1.2 Baseline — the starting position, not a current reading

Every KPI above is measured against this baseline. It describes the repository **before** this
programme, and it is a measurement rather than an estimate: all three legacy backend test modules
failed at *collection*, so no backend production line was ever executed by a test, and the frontend
had no test file of any kind.

| Baseline metric | Value | Note |
|---|---|---|
| Executed coverage, whole system | **0%** | Across **33 production modules** — **14 backend** and **19 frontend** test targets, as enumerated by the plan. |
| Backend test modules that collected | **0 of 3** | Failure mode was import resolution plus a `SyntaxError`, not assertion failure. |
| Frontend test files | **0** | The Jest toolchain was declared in `package.json` and entirely unbound. |
| Legacy test code | **216 lines**, **25 test functions** | 19 with bodies, 6 empty. |
| Legacy disposition | **7 rewritten, 3 skipped with a reason, 15 removed with a reason** | Every one accounted for in [`./TRACEABILITY-MATRIX.md`](./TRACEABILITY-MATRIX.md) §E. |

**Demonstration measurements — treat as floors, not forecasts.** Taken during planning against the
real sources by partial suites that the delivered suite is a strict superset of.

| Demonstration | Measured | Denominator |
|---|---|---|
| Frontend, on exactly the ≥80% target scope | **80.24% statements / 100% branches / 82.35% functions / 78.66% lines** | `src/store`, `src/schema`, `src/services` |
| Frontend, full `src` denominator | **64.42% statements / 21.87% branches / 61.76% functions** | all of `src` |
| Backend, overall | **68%** | the `app` package |

Module counts (14 / 19 / 33) are the plan's enumeration of test targets and are the figures to
quote. **Do not** quote an aggregate production line total as measured: the plan states 476 backend
and 690 frontend lines, a line-counting utility reports 486 and 783, and the two do not agree.
Attribute any line total to the plan explicitly or omit it.

---

## 2. The metrics surface, per runner

Rule 2 requires a metrics surface. Here the **coverage and result artifacts are that surface** —
they are what the two Codecov steps already in the workflow consume, so the programme extends
instrumentation the project has rather than inventing a parallel one. See
[`./DECISION-LOG.md`](./DECISION-LOG.md) row **D193**.

Every path below is stated relative to the repository root and must match its producing
configuration exactly. All of them are written locally by the command that produces them, and all of
them are excluded by the `.gitignore` rules, so a path that drifts in one place breaks both.

**Two different consumers, and the difference matters when a panel comes up empty.** *Codecov* consumes
exactly two files — the `build` job's two upload steps send `./backend/coverage.xml` and
`./frontend/coverage/coverage-final.json`, nothing else. *Artifact retention* is much wider: seven
`upload-artifact` steps between the two jobs retain almost everything this section lists, so a panel can
be filled after the workspace is gone. The four contract artifacts are tabulated in §2.4; on top of them
the workflow uploads `backend-junit`, `frontend-junit` and `e2e-junit`, each carrying one JUnit file
directly under `if: always()`, so a result stream survives even a run whose later steps did not execute.

Exactly one artifact in this section is **local-only**: `backend/coverage.lcov`, because the CI coverage
command does not request the `lcov` reporter. The "Retained by CI" column of each table below names the
artifact that carries each file, so a missing panel can be traced to a missing upload rather than guessed
at.

### 2.1 Backend — produced by `backend/pytest.ini` and `pytest-cov`

Invoked from `backend/`, which is what makes `pythonpath = .` yield the single `app.*` import root.

**The canonical producer command.** One command produces every backend artifact below, and it is the
same one `.github/workflows/ci.yml` runs — which matters because the `--cov` scoping is what defines
G1's denominator, and a wider run writes a `coverage.xml` and `coverage.json` that are
indistinguishable, to any later reader, from a gated one:

```
cd backend
pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db \
       --cov-report=term-missing --cov-report=xml --cov-report=json \
       --cov-precision=2 --cov-fail-under=90 --junitxml=reports/junit.xml
python tests/coverage_gate.py --coverage-json coverage.json --fail-under 90 \
       --require-scope app/core --require-scope app/services \
       --require-scope app/tasks --require-scope app/db | tee reports/coverage-gate.txt
```

Do not substitute `--cov=app`. A whole-tree measurement is a legitimate thing to want, and there is a
command for it in §8 of [`../../backend/tests/README.md`](../../backend/tests/README.md), but it must
not be the run that fills these panels: the second command above **refuses** a report whose measured
files fall outside the four gated packages, which is what stops a whole-tree total being labelled G1.

| Artifact | Format | Produced by | Consumed by | Retained by CI |
|---|---|---|---|---|
| `backend/coverage.xml` | Cobertura XML | `--cov-report=xml` | K1 and the G1 verdict; the `backend`-flagged Codecov upload | yes — `build-test-evidence` |
| `backend/coverage.json` | Coverage JSON | `--cov-report=json` | §6.1 and §6.2, **per-module and per-package**; the exact gate | yes — `build-test-evidence` |
| `backend/coverage.lcov` | lcov tracefile | `--cov-report=lcov` | external lcov viewers | **no** — local only; the canonical command does not request this reporter |
| `backend/reports/junit.xml` | JUnit XML, `xunit2` | `--junitxml=reports/junit.xml` in `addopts`, with `junit_family = xunit2` | K3, K7, §6.3 | yes — `build-test-evidence` and `backend-junit` |
| `backend/reports/collect-only.txt` | text | the readiness step, `pytest --collect-only -q --junitxml=reports/collect-only-junit.xml \| tee reports/collect-only.txt` | K5, §6.4, and the case-count comparison that guards the row above | yes — `build-test-evidence` |
| `backend/reports/collect-only-junit.xml` | JUnit XML, `xunit2` | the same readiness step, which repeats `--junitxml` so the `addopts` value cannot send a zero-case discovery stub to `reports/junit.xml` | nothing — it exists so that the canonical stream is not overwritten | yes — `build-test-evidence`, as a by-product of the directory upload |
| `backend/reports/coverage-gate.txt` | text | `tests/coverage_gate.py`, the second command above | **K5b** and the §6.4 exact-gate row | yes — `build-test-evidence` |
| terminal summary | text | `--cov-report=term-missing` | human reading of a local run | no — the log only |

**Why the exact gate is a separate artifact from the pytest step's own message.**
`--cov-fail-under` compares `round(total, precision)` against the threshold, so it admits a band of
sub-threshold totals at any finite precision — `[89.5, 90)` at the library default, `[89.995, 90)` at
the two decimals `backend/.coveragerc` configures. `backend/tests/coverage_gate.py` compares the
integer counts instead (`covered * 100 >= 90 * statements`, as exact rational arithmetic) and checks
the measured scope, so **its** verdict is the one K5b reports. `backend/tests/test_coverage_gate.py`
holds both behaviours, including three totals the rounded comparison admits and the exact gate refuses.

**Why per-module backend rows come from the JSON and not the Cobertura.** With `--cov` given four
package paths, coverage.py writes four `<source>` roots, a single `<package name=".">`, and bare
basenames as each `filename`. A per-module or per-package row read from that file would be a guess
about which root each file came from. `coverage.json` keys files by their full relative path, carries
`missing_lines` outright, and records `meta.branch_coverage`, which is what lets §6.2's branch column
be reported as unmeasured rather than as zero. The extractor reads the aggregate from the Cobertura,
the detail from the JSON, and reports it loudly if the two disagree.

Two `pytest.ini` settings shape the JUnit artifact beyond its path. `junit_logging = log` attaches
captured log records to a `<testcase>`, and `junit_log_passing_tests = false` restricts that to
failing cases, so the artifact carries the diagnostics of a failure without carrying a log section
for every passing test. Rationale in [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D82**.

### 2.2 Frontend — produced by `frontend/jest.config.js`

`<rootDir>` is `frontend/`. No `coverageDirectory` is declared, so coverage lands in Jest's default
`<rootDir>/coverage`.

| Artifact | Format | Produced by | Consumed by | Retained by CI |
|---|---|---|---|---|
| `frontend/coverage/lcov.info` | lcov tracefile | the `lcov` coverage reporter | §6.2 — this is the source of the frontend **uncovered line numbers** | yes — `build-test-evidence` |
| `frontend/coverage/lcov-report/` | HTML tree | the `lcov` coverage reporter | human review of §6.2 | yes — `build-test-evidence` |
| `frontend/coverage/coverage-final.json` | Istanbul JSON | the **`json`** coverage reporter | the `frontend`-flagged Codecov upload | yes — `build-test-evidence` |
| `frontend/coverage/coverage-summary.json` | Istanbul summary JSON | the `json-summary` reporter | K2, §6.1, §6.2 — the natural KPI source | yes — `build-test-evidence` |
| `frontend/coverage/cobertura-coverage.xml` | Cobertura XML | the `cobertura` reporter | Cobertura-native consumers | yes — `build-test-evidence` |
| `frontend/reports/jest-junit.xml` | JUnit XML | the `jest-junit` reporter registered in `reporters`, with `outputDirectory: '<rootDir>/reports'` and `outputName: 'jest-junit.xml'` | K4, K7, §6.3 | yes — `build-test-evidence` |
| `frontend/reports/list-tests.txt` | text | the CI discovery step, `npm run --silent test:list \| tee reports/list-tests.txt` | §6.4, the discovery census | yes — `build-test-evidence` |
| `frontend/reports/load-tests.txt` | text | the readiness step, `npm run --silent test:load 2>&1 \| tee reports/load-tests.txt` | §6.4 — the suite-load gate | yes — `build-test-evidence` |

**The frontend readiness artifact is a load probe, not a file listing.** `jest --listTests` walks the
filesystem against `testMatch` and imports nothing, so a suite with a broken import or a failing
transformer is listed exactly like a healthy one and exits 0 — measured: with one unresolvable import
added, `test:list` still listed all 24 files and exited 0. `test:load` is
`jest --ci --watchAll=false --runInBand -t "__readiness_probe_that_matches_no_test__"`; Jest can only
know a test's name after transforming the file, evaluating it at module scope and running its
`describe` callbacks, so it loads every suite and every module in their import graphs, registers every
test identity, runs zero test bodies, and exits **1** naming the suite on the same perturbation. Both
artifacts are retained, because the census answers "which files" and the probe answers "do they load".
The `2>&1` is required on the probe: Jest writes its summary to stderr.

**Percentages here are truncated, not rounded.** Istanbul reports functions 47/67 as `70.14` where
rounding gives `70.15`, and Jest's threshold messages use the same value. The backend is the opposite:
coverage.py rounds to `precision` and clamps so a non-zero total never displays as 0 and an incomplete
one never displays as 100. The extractor implements both, one function each, so a frontend cell agrees
with `coverage-summary.json` and a backend cell agrees with `term-missing` — to the hundredth.

The configured set is:

```js
coverageReporters: ['text-summary', 'lcov', 'json', 'json-summary', 'cobertura']
```

**`coverageReporters` must include `'json'`.** That reporter, and only that reporter, writes
`coverage/coverage-final.json` — which is the exact file the `frontend`-flagged Codecov step
uploads. Dropping `'json'` leaves the upload pointing at a file nothing produces, and the step
fails without any coverage number having changed.

**`jest-junit` must be declared in the config file's `reporters`, not on the command line.** The CLI
form mis-parses a positional test path as a third reporter and fails with
`Could not resolve a module for a custom reporter`. It is registered in `jest.config.js` for exactly
this reason.

### 2.3 End-to-end — produced by `e2e/playwright.config.ts`

Paths are derived from the config file's own directory rather than from the working directory, so
they resolve identically however the runner is invoked.

| Artifact | Format | Produced by | Consumed by | Retained by CI |
|---|---|---|---|---|
| `e2e/playwright-report/` | HTML report | the `html` reporter, `outputFolder` set to this directory with `open: 'never'` | human review | yes — `playwright-report` |
| `e2e/reports/e2e-junit.xml` | JUnit XML | the `junit` reporter, `outputFile` set to this path | K6, K6b, K7, §6.3, §6.5 | yes — `e2e-test-evidence` |
| `e2e/reports/list-tests.txt` | text | the readiness step, `npm run --silent test:list \| tee reports/list-tests.txt` | §6.4 | yes — `e2e-test-evidence` |
| `e2e/reports/browser.txt` | text | the provisioning step, `npm run --silent browsers:require -- --min-major <n> \| tee reports/browser.txt`, then the runner version appended | §1.0 provenance — **which browser produced the result** | yes — `e2e-test-evidence` |
| `e2e/test-results/` | traces, screenshots, video | `outputDir`, populated per the `use` block: `trace: { mode: 'retain-on-failure', sources: false }`, `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'` | §6.5 | yes — `e2e-failure-artifacts`, `if-no-files-found: warn` |

The configured `trace` mode is **`retain-on-failure`** with `sources: false`, which captures a trace for every failing
test on its first attempt, locally as well as under CI — tracing therefore does not depend on a
retry having occurred. `sources: false` is the one reduction available that costs no diagnosis: a trace
otherwise embeds a verbatim copy of every spec file it executed, and `configuration.spec.ts` declares four
credential-shaped literals at module scope, so the default packed those values into the artifact as source
text in addition to the DOM and network records that are the point of it. The source is in git at the same
commit, so nothing a reader needs is lost. Verified two-sidedly rather than asserted: with the option on,
a real failure trace carries an extra `src@<sha>.txt` entry holding the spec text; with it off, that entry
is absent. What still remains is stated in §2.4 and bounded at the source by a fixture-honesty gate.

Determinism settings that make two runs comparable are set in the same block:
a fixed `viewport` of 1280×720, `timezoneId: 'UTC'`, `locale: 'en-US'`, and
`serviceWorkers: 'block'`.

`test:list` overrides the reporter (`playwright test --list --reporter=line`) so that listing the
suite cannot overwrite a previous run's JUnit and HTML reports with an all-skipped stub. Verified:
plain `--list` rewrites `e2e-junit.xml` with an all-skipped stub of the same test count; with `--reporter=line` the
file is untouched.

### 2.4 Retention contract

Local runs leave every artifact above in the working tree, where `.gitignore` keeps it out of version
control. A CI run additionally uploads them, so a result can be audited after the workspace is gone.

| Artifact name | Contents | `if-no-files-found` | Retention |
|---|---|---|---|
| `build-test-evidence` | `backend/reports/`, `backend/coverage.xml`, `backend/coverage.json`, `frontend/reports/`, `frontend/coverage/` | `error` | 30 days |
| `playwright-report` | `e2e/playwright-report/` | `error` | **7 days** |
| `e2e-test-evidence` | `e2e/reports/` | `error` | 30 days |
| `e2e-failure-artifacts` | `e2e/test-results/` | `warn` | **7 days** |
| `backend-junit` | `backend/reports/junit.xml` | default (`warn`) | repository default |
| `frontend-junit` | `frontend/reports/jest-junit.xml` | default (`warn`) | repository default |
| `e2e-junit` | `e2e/reports/e2e-junit.xml` | default (`warn`) | 30 days |

`error` on the unconditional artifacts: if the suite ran, they exist, and their absence is a defect
worth failing on. `warn` on `e2e-failure-artifacts` alone, because trace, screenshot and video are all
configured `on-failure` only — a fully passing run legitimately writes nothing there, and `error` would
turn a green run red.

**Retention is 7 days for the two artifacts that carry failure evidence and 30 for the result streams.**
That split is deliberate rather than incidental. `playwright-report` and `e2e-failure-artifacts` are the
two that can contain a DOM snapshot, filmstrip, screenshot and video of `configuration.spec.ts`, which is
the one spec that drives credential-shaped values through a real browser — and two of its four fields
render as `type="text"`, which Playwright 1.44 cannot mask on automatic failure evidence. Debugging a
failed run is a matter of days, so the window is days. The result streams carry no attachment body and
keep 30. `e2e-junit` is listed with the value it now declares: it previously named none and so inherited
the repository default of 90 days, a longer window than anything else this job uploads, decided somewhere
the workflow file cannot see. See `DECISION-LOG.md` D318.

The last three are single-file uploads of the result streams, guarded by `if: always()` rather than by
`if: ${{ !cancelled() }}`, so a stream survives a cancellation as well as a failure. They duplicate a
file the directory artifacts already carry; the duplication is the point, because a result stream is the
one artifact a reader wants without downloading a directory tree. Seven uploads in all,
and the panel is a census of them: an upload the workflow performs and this table omits is a retained
artifact nobody knows to look for. Two workflow steps additionally read the JUnit streams
before the uploads and fail with a `::error file=…::` annotation when a report is missing, empty, or
declares zero test cases, so a collection-time stub can never be published as a run.

The last three rows deliberately overlap the first three: each retains one JUnit file that is already
inside a bundle above, under `if: always()` and its own artifact name. The duplication is cheap and buys
one thing — a single-file download for whoever only wants the result stream, and one that is still
published when a job ends in a state the bundle steps skip.

---

## 3. Gate contract

### 3.1 The gates

| Gate | Scope | Threshold | Enforcing mechanism | Configured in |
|---|---|---|---|---|
| G1 | `backend/app/core`, `backend/app/services`, `backend/app/tasks`, `backend/app/db` — **summed into one denominator, gated once** | **≥ 90%** line coverage of that total, compared **exactly** | Two commands. `pytest --cov-fail-under=90 --cov-precision=2` with `--cov` scoped to those four packages in one invocation, then `python tests/coverage_gate.py …`, which is the binding comparison. One threshold, one denominator: a single package below 90% does not fail the build if the total clears it | the two backend commands in §2.1; see `.github/workflows/ci.yml` |
| G2 | `frontend/src/store`, `frontend/src/schema`, `frontend/src/services` | **≥ 80%** statements, branches, functions **and** lines — **twelve independent comparisons** | Jest `coverageThreshold`, one entry per package, no global group. Any single cell below 80% fails the run, so K2 reports the **worst** cell rather than a figure summed across groups | `frontend/jest.config.js` |
| G3 | `frontend/src/components`, `frontend/src/pages` | as high as the implemented code permits, bounded by §3.3 | measured and reported, **not** gated | `frontend/jest.config.js` (`collectCoverageFrom`) |
| G4 | Collection integrity, whole backend suite | **zero** collection errors | `pytest --collect-only -q`, run as its own CI step ahead of the suite, with its summary retained as `backend/reports/collect-only.txt` | `backend/pytest.ini` (`testpaths`, `pythonpath`) and the `Check backend collection integrity` step of `.github/workflows/ci.yml` |
| G5 | Every frontend suite loads | **zero** suites that fail to load | `npm run test:load` — a non-watch run whose name filter matches nothing, so every suite is transformed, imported and evaluated to its `describe` bodies before Jest can decide nothing matched. Run as its own CI step ahead of `test:ci`, retained as `frontend/reports/load-tests.txt` | `frontend/package.json` (`test:load`) and the `Check that every frontend suite loads` step of `.github/workflows/ci.yml` |

**G1 is one gate, not four.** The threshold is compared against a single total computed across
everything `--cov` measured, so there is no per-package verdict to report and §6.1 does not invent
one: the per-package backend rows there are **measurements**. A package could sit below 90% while G1
passes, and the panel is built so that is visible rather than hidden. G2 is the opposite — Jest
declares one threshold group per path and each group carries four metrics, so G2 is **twelve**
independent comparisons, each with its own verdict.

**G1 is compared exactly, and that needed a second command rather than a setting.** `--cov-fail-under`
is `round(total, precision) < fail_under` — see `coverage.results.should_fail_under` — so it admits a
band of sub-threshold totals at *every* finite precision. At coverage.py's default of 0 decimals a
threshold accepted anything from half a point below it upward, while pytest-cov's message — which uses
the unrounded value — printed `FAIL`. Reproducible on the delivered tree, where the whole `app` tree
measures 90.97%: `pytest --cov=app --cov-precision=0 --cov-fail-under=91` prints
`FAIL Required test coverage of 91% not reached. Total coverage: 90.97%` and **exits 0**, because 90.97
rounds to 91. `backend/.coveragerc` sets `precision = 2`, which makes the printed number agree with the
exit status, and the same command without `--cov-precision=0` exits **1** with
`ERROR: Coverage failure: total of 90.97 is less than fail-under=91.00`. But two decimals still admit
`[89.995, 90)`, and no precision closes that band.

So the binding comparison is `backend/tests/coverage_gate.py`, run immediately after the suite. It
reads `totals.covered_lines` and `totals.num_statements` out of `coverage.json` and compares
`covered * 100 >= threshold * statements` as exact rational arithmetic, and it **refuses a report
measured over a different scope**. Measured on the delivered tree: `182 of 195 statements covered =
93.3333% exact, threshold 90% → coverage gate PASSED`; at `--fail-under 93.34` it exits **1** printing
the comparison it performed; on a genuine whole-`app` report (262/288 = 90.9722%) it exits **1**
naming all eight files outside the gated scope; with no report at all it exits **2**, which is a
distinct status because "nothing was measured" is not the same failure as "measured low".
`backend/tests/test_coverage_gate.py` asserts all of it, including three totals — 89.995%, 89.9999%
and 89.99999% — that the rounded comparison admits and the exact gate refuses.

**Gates live in the runners, not in Codecov reporting.** A Codecov-only threshold annotates a pull
request but does not fail a build, so a coverage regression would merge. `--cov-fail-under` and
`coverageThreshold` both exit non-zero, which is what makes each gate binding. Codecov continues to
receive the same artifacts and remains the trend and diff view.

**Every gate is reachable on every push.** The test and reporting steps carry
`if: ${{ !cancelled() }}`, so the acknowledged-broken `flake8 .`, `mypy .` and `npm run lint` steps no
longer prevent them from running. Those three steps are unchanged and the job still goes red when
they fail: the condition makes the gates independent of their conclusion, it does not hide it.

### 3.2 Provenance of the ≥90% figure

The 90% threshold is not an invention of this programme. It is an acceptance criterion of the
project's own proposal: `documentation/Software Project Proposal.md`, acceptance group
**`10. Testing Artifacts`** at **line 505**, whose first criterion at **line 506** requires test
coverage of at least 90% for all code. Lines **507-508** carry the group's other two criteria
(resolution of all critical and high-priority bugs, and performance tests meeting the specified
requirements), neither of which is a coverage gate.

**G1 is deliberately scoped to four packages rather than to the whole `app` tree.** Several branches
in `app/main.py` and `app/api/` cannot be executed without production changes the requirements
forbid, so a tree-wide gate would be held hostage to branches no test can fix — measured, the whole tree
lands at **90.97%** (262/288) against the gated scope's 93.33%, clearing a 90 bar by less than a point,
so a single new unreachable line in a route module would drop it under. The reasoning, the alternatives
and the risk this carries are in
[`./DECISION-LOG.md`](./DECISION-LOG.md) row **D70**, and are not restated here.

**Those modules are therefore not measured by the gated run at all, and this dashboard does not
report them.** `--cov` names four packages, so `app/main.py`, `app/api/dependencies.py` and
`app/api/routes/*` appear in neither `coverage.xml` nor `coverage.json` and have no row in §6.1 or
§6.2. They are *exercised* — `tests/integration/` covers the application object, the assembled route
table and the three implemented endpoints, and [`./TRACEABILITY-MATRIX.md`](./TRACEABILITY-MATRIX.md)
§I names the covering artifact for each — but exercised is not the same as measured, and a dashboard
cell claiming a percentage for them would have no producer behind it. To measure them, add
`--cov=app/main.py --cov=app/api` to a **local** run; do not add them to the CI command, because that
changes the denominator G1 is calibrated against.

### 3.3 Documented ceilings — these are not gaps

A **ceiling** is a region no test can reach without a production change the programme is not
authorized to make. A **gap** is uncovered code that a test could reach. Confusing the two turns a
correctly-bounded suite into an open work item, so resolve every uncovered region against this table
before recording it as work. Each ceiling has an assertion that stands in for it, mapped in
[`./TRACEABILITY-MATRIX.md`](./TRACEABILITY-MATRIX.md) §G.

The first eight rows are unexecutable **branches**, which is what the gate scoping in §3.1 answers to.
The last four are a different kind of ceiling: the code executes and is covered, but what it produces
falls short of an accessibility or credential-handling expectation. Closing any of those four means
editing a `frontend/src` production module, which is outside the two authorized touches, so each is
characterised by assertions and carried into the suggested-next-tasks lists instead.

| Ceiling | Why it is unreachable | How the suite treats it |
|---|---|---|
| `frontend/src/app.tsx` | Cannot be mounted at all: it imports a store whose reducer is invalid, imports a `setupInterceptors` symbol that is never exported, and default-imports a named-only export | Permanently 0%; excluded from `collectCoverageFrom`. See [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D71** |
| Three of the four `src/pages/*.tsx` modules | `useAppDispatch` and `useAppSelector` are imported by them but exported by nothing | Tests written, collected, and skipped **per test** — an ordinary `describe` so the module graph still resolves, and the blocker on each individual test's own title so it reaches that test's `<testcase>`. See `./DECISION-LOG.md` D215 |
| The tweet-rendering branch of both list components | `TweetCard` is imported by two components — one of them from itself — and defined nowhere | The current failure is asserted instead; a non-empty list yields an invalid-element-type error |
| The chart-construction branch of `src/components/Analytics` | The module imports the tree-shakeable `Chart` and never calls `Chart.register`, so a working chart is unreachable wherever a canvas exists — and **nothing wraps it**: the module's only `try`/`catch` covers the `getTrendData` call | All four paths asserted, kept apart, and split across the two layers that can each reach one. Under jsdom (`src/components/Analytics.test.tsx`): a controlled `Chart` constructor (nothing fails; the configuration is asserted), the real library (`chart.js` cannot acquire a 2D context and returns early itself — nothing thrown, nothing caught, component still mounted), and a rejected trend request (`renderCharts` never entered). In a real browser (`e2e/tests/analytics.spec.ts` test 4, which opts into the harness stub's forwarding header): the raise from the empty registry, its arrival as an uncaught page error, and the **unmount** that follows. What remains unreachable is that outcome *under jsdom*, where there is no 2D context to acquire, so no part is left unevidenced. See `./TRACEABILITY-MATRIX.md` G4 and F83, and `./DECISION-LOG.md` D216 with its superseding row D327 |

| The 404 branch of `GET /tweets/{tweet_id}` | An `AttributeError` fires first, because the pydantic `Tweet` declares no `id` to filter on; the response is HTTP 500 | The 500 is asserted; the unreachable 404 is documented |
| A "422 on an invalid request body" check | No implemented endpoint accepts a request body, so the check has no subject | Recorded as a gap in the register, **not** satisfied by inventing an endpoint |
| The `DOUBT_RATING_THRESHOLD` gate | The constant is declared but referenced by no production code anywhere, so the gate does not exist | The constant's value is asserted; the missing gate is recorded |
| `start_twitter_stream` beyond its failure point | Dead code: the module never imports `tweepy`, so the function always raises `NameError` | The `NameError` is asserted; the lines after it can never execute |
| The analytics chart canvas in the accessibility tree | `src/components/Analytics` renders a bare `<canvas>` with no role, name, description or fallback content, and a canvas has no implicit ARIA role | The absence of every naming mechanism is asserted at both layers, including against Chromium's own accessibility snapshot. `./TRACEABILITY-MATRIX.md` G9 |
| Announcement of loading and of polled feed updates | Neither `src/components/TweetManagement`'s loading `div` nor `src/components/Dashboard`'s polled wrapper declares `role`, `aria-live` or `aria-busy` | The absence is asserted across a mount and a completed transition. `./TRACEABILITY-MATRIX.md` G10 |
| A pending state on the credential save | `src/components/Configuration` awaits the write but holds no state for it, so the control stays live | The absent attributes and roles, plus the duplicate write and duplicate dialog a second activation produces. `./TRACEABILITY-MATRIX.md` G11 |
| Masking of the API key and access token | Both are `type="text"`; only the `Secret`-suffixed fields are `type="password"`, and no field declares `autocomplete` | The exact per-field treatment is asserted, including the rendered values in a real browser. `./TRACEABILITY-MATRIX.md` G12 |

---

## 4. Rule 2's five mandated elements

Rule 2 (Observability) requires five things of every deliverable. All five are satisfied against the
test system, per conflict **C1** in [`./DECISION-LOG.md`](./DECISION-LOG.md) §21.

| Element | How it is satisfied | Where it is configured | Artifact evidence |
|---|---|---|---|
| **Structured logging** | `log_cli = true` at `log_cli_level = INFO`, with `log_cli_format` and `log_format` both emitting a fixed field order that includes the correlation identifier. Suites assert against production logging through `caplog` wherever production already emits it | `backend/pytest.ini` | live console output; the captured-log section of a failing `<testcase>` in `backend/reports/junit.xml` |
| **Correlation identifiers** | Backend: a `logging.setLogRecordFactory` hook puts `test_id` (the full pytest nodeid) and `correlation_id` (a stable 8-hex digest of that nodeid) on **every** log record, including records from production code and third-party libraries; the same nodeid is the `classname` and `name` pair of the matching `<testcase>`. Because the identifier is a digest rather than a counter, the same test yields the same id on every run and on every machine, which is what makes two runs comparable line by line. Frontend: `jest-junit` templates derive `classname` from the test file path, normalized to forward slashes, and `name` from the enclosing describe titles plus the leaf title — the same identity that is stamped on every intercepted request. E2E: the spec and test title name the per-test artifact directory. Decisions in [`./DECISION-LOG.md`](./DECISION-LOG.md) §8, rows **D80**, **D81** and **D83** | `backend/pytest.ini` plus `backend/tests/conftest.py`; the `reporters` block of `frontend/jest.config.js`; `e2e/playwright.config.ts` | `backend/reports/junit.xml`; `frontend/reports/jest-junit.xml`; the per-test subdirectories of `e2e/test-results/` |
| **Distributed tracing across service boundaries** | Playwright tracing at `retain-on-failure` with `sources: false`, plus `screenshot: 'only-on-failure'` and `video: 'retain-on-failure'`, giving a request-level trace of the browser-to-API boundary with timing per intercepted request. Stated honestly: the E2E layer is the **only** place in this repository where a request genuinely crosses a process boundary, so it is the only place a trace has anything to span — and all three settings are failure-conditional, so a green run leaves them unexercised. They were exercised deliberately: an induced failure produced a trace, a video and a screenshot, recorded with their byte counts in §7.2 A1-b | `e2e/playwright.config.ts` (`use`) | `e2e/test-results/`, populated only on a failing test — observed populated in §7.2 A1-b |
| **Metrics endpoint** | The coverage and JUnit artifacts in §2 **are** the metrics surface, consumed by the two Codecov upload steps that already existed in the workflow. **No production metrics endpoint is added** — doing so would be an unauthorized production change and the implementation of a missing product feature. See [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D193** | `backend/pytest.ini`, `frontend/jest.config.js`, `e2e/playwright.config.ts` | every artifact listed in §2 |
| **Health / readiness checks** | Three, one per layer, each its **own CI step** ahead of the suite it reports on: `pytest --collect-only -q` reporting zero errors for the backend, `npm run test:load` for the frontend, and `npm run test:list` for the E2E layer. This is the meaningful readiness check for this suite specifically: its inherited failure mode was **collection errors** — three modules that never reached an assertion — so a gate proving every module imports is the check that would have caught the original state, in a way a passing-test count would not. The frontend check is the load probe rather than `test:list` precisely because `jest --listTests` resolves no import and so proves nothing loads (§3.1 G5). Each step pipes its summary into a retained file, and `set -o pipefail` keeps `tee` from masking a non-zero exit. See §6.4 and [`./DECISION-LOG.md`](./DECISION-LOG.md) rows **D72** and **D255** | `backend/pytest.ini` (`pythonpath`, `testpaths`); the three readiness steps of `.github/workflows/ci.yml`; the `test:load` script of `frontend/package.json` and the `test:list` script of `e2e/package.json` | `backend/reports/collect-only.txt`, `backend/reports/coverage-gate.txt`, `frontend/reports/load-tests.txt`, `e2e/reports/list-tests.txt` and `e2e/reports/browser.txt` — all inside retained CI artifacts |
| **Dashboard template** | This document | — | — |

---

## 5. Reused, added, and checked-but-absent

Rule 2's check-reuse-document clause requires that existing observability be found and used before
anything new is introduced, and that the split be documented. The three lists below are that split.
Every line-number reference is against the workflow and infrastructure files as they stood before
this change.

### 5.1 REUSED — instrumentation that already existed

- **The backend Codecov upload step, `.github/workflows/ci.yml` lines 57-61** — named
  `Upload backend coverage to Codecov`, running `codecov/codecov-action@v1` with
  `file: ./coverage.xml` and `flags: backend`. The step, the action and the flag are kept.
- **The frontend Codecov upload step, lines 63-67** — the same action, with
  `file: ./coverage/coverage-final.json` and `flags: frontend`. Likewise kept.
- **What changed in those two steps, and what did not.** Both `file:` values are **repointed** — to
  `./backend/coverage.xml` and `./frontend/coverage/coverage-final.json` — because each suite now
  runs in its own working directory. Both gained `fail_ci_if_error: true`, an `if:` condition making
  them independent of the lint conclusion, and a requirement that their producer step succeeded, so a
  report is never consumed from a failed run and a failed upload is never silent. **Both flag names
  stay exactly as they were**, `backend` and `frontend`. Preserving the flags is the whole point: a
  renamed flag starts a new series in Codecov and silently discards the project's historical
  continuity, so the repoint is a path correction only.
- **The single `build` job.** Unit and integration work stays in the job that already exists rather
  than being split across new jobs.
- **The runtime matrix, lines 15-16** — `python-version: [3.9]` and `node-version: [16.x]`. This is
  the authoritative source of the documented runtime ceilings, and every version pin in the test
  stack was selected to satisfy it.

### 5.2 ADDED — gaps filled with framework-appropriate tooling

- **JUnit XML on all three layers**, which none of them emitted before: `--junitxml` with
  `junit_family = xunit2` on the backend, the `jest-junit` reporter on the frontend, and Playwright's
  `junit` reporter for E2E. This is what makes test health machine-readable at all.
- **Persistence for all three of those streams.** Emitting a file inside a job that then ends leaves a
  KPI unsourceable, so `.github/workflows/ci.yml` uploads each one with `if: always()` — as the
  `backend-junit`, `frontend-junit` and `e2e-junit` artifacts — and a failing run therefore still
  publishes the results that explain it (`D243`).
- **Correlation identifiers on log records and result records**, described in §4.
- **The additional coverage reporters.** The workflow previously expected a single Cobertura file;
  the suites now also emit `json`, `json-summary`, `lcov` and `text-summary`, which is what allows
  the KPI panel to be filled from a summary file rather than scraped from console output.
- **The `--collect-only` collectability gate** (§6.4), which had no equivalent — now an automated CI
  step rather than a documented command, alongside a `test:list` discovery step for the frontend and
  E2E layers.
- **Runner-enforced thresholds** — `--cov-fail-under` and Jest `coverageThreshold` — so a coverage
  regression fails a build rather than merely annotating it, with `backend/.coveragerc` supplying the
  two-decimal precision that makes the backend comparison exact.
- **Reachability of all of the above.** `if: ${{ !cancelled() }}` on every test and reporting step, so
  the acknowledged-broken lint and type-check steps no longer skip the producers that follow them.
- **Retention and consumption.** Four uploaded artifacts covering all three JUnit streams, both
  coverage trees, the E2E HTML report and the E2E failure evidence, each with an explicit
  `if-no-files-found` policy and a 30-day retention (§2.4); two workflow steps that read the JUnit
  streams and fail visibly when a report is missing, empty or declares zero test cases; and
  `dashboard-extract.py`, which is what turns those files into the panels in §6.
- **A case-count comparison between the backend result stream and the collected count**, in
  `dashboard-extract.py` and in the workflow's verify step, plus a separate `--junitxml` path on the
  readiness probe. A zero-case stub was already refused; a *partial* run — one file, one `-k` filter —
  leaves a non-zero count that no presence or non-zero check can distinguish from a full run, and
  `--junitxml` living in `addopts` makes every invocation a writer of the canonical stream. The
  readiness artifact's collected count is the independent witness, so a stream that disagrees with it
  is withdrawn, named on stderr and fatal under `--require-all` (`D355`).
- **The new `e2e` job**, running the package-local pinned runner against a pre-provisioned browser.

### 5.3 CHECKED, and found absent

The other half of the clause, stated plainly. Each item below was looked for and does not exist.
All of them are **documented and left unfixed**: closing any one is production work outside the two
authorized touches. The decision is [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D194**, the
register is §23 of that document, and each item is carried into the Rule 3 suggested-next-tasks
lists in the onboarding documents.

- **No metrics endpoint** anywhere in the application, and none added — row **D193**.
- **No tracing of any kind**, and no correlation identifier on any production code path. The
  correlation identifiers described in §4 belong to the test system.
- **No structured logging in production.** Failures are reported with `print`, and nothing under
  `backend/app/` imports `logging` or calls `getLogger` at all.
- **No `codecov.yml`.** Codecov behaviour is entirely whatever the two upload steps imply.
- **No usable health check of the application.** Two probes aim at a `/health` route the application
  never declares, and neither can therefore succeed.
  `infrastructure/docker/docker-compose.yml` **line 36** sets the backend service's healthcheck test
  to `["CMD", "curl", "-f", "http://localhost:5000/health"]`, so that container can never become
  healthy. `.github/workflows/cd.yml` **lines 46-51** is a `Run post-deployment health checks` step
  whose `run:` block contains only comments — including a commented-out
  `curl -f https://your-app-url.com/health || exit 1` — so it passes vacuously and gates nothing.
  The other two healthchecks in that compose file probe a port and a database rather than the
  application's own readiness, so nothing in the repository verifies that the API is serving.

### 5.4 A measurement-scope defect corrected in passing

`ci.yml` **line 51** previously ran `pytest --cov=./ --cov-report=xml` from the repository root, so
the coverage denominator was the entire tree rather than `backend/app`. Any percentage it produced
would have been diluted by every non-application file it swept in. Correcting the working directory
and the `--cov` scope is part of the backend test step, and it is what makes G1 mean what it says.

---

## 6. Panels to fill

Six panels. Each one names the single artifact it is filled from; fill from that artifact and from
nothing else. **All six are produced by `dashboard-extract.py`** — the `_____` slots below document
the shape and the source, and a hand-filled copy must agree with the extractor's output exactly.

### 6.1 Coverage by package

> **How to fill:** run the extractor. Backend rows come from `backend/coverage.json`, frontend rows
> from `frontend/coverage/coverage-summary.json`. Record a verdict **only** where a gate actually
> exists: G2 has one per package, G1 does not.

**Read the shape of the two gates before filling this in, because they are not alike.** G1 is **one
aggregate gate**: the backend step runs a single `pytest` with four `--cov=` scopes and one
`--cov-fail-under=90`, so coverage.py sums those four packages into one denominator and compares that
total once. A package sitting below 90% therefore does **not** fail the build if the other three carry
the total above it. G2 is the opposite: Jest's `coverageThreshold` declares a separate entry per path,
so each of the three frontend scopes is gated independently and any one of them failing fails the run.

The four backend packages appear below as *measurements without a verdict of their own* — recording a
per-package `PASS` would assert a gate that does not exist. The verdict belongs to the aggregate row.

| Scope | Gate | Threshold | Measured | Pass / Fail | Source artifact |
|---|---|---|---|---|---|
| **`core` + `services` + `tasks` + `db`, summed** | **G1 — the only backend gate** | **≥ 90.00% lines**, compared at two decimals (`--cov-precision=2`) | `_____` | `_____` | the gated run's `TOTAL` line and its exit status |
| ↳ `backend/app/core` | — measured, not separately gated | — | `_____` | n/a | `backend/coverage.json` |
| ↳ `backend/app/services` | — measured, not separately gated | — | `_____` | n/a | `backend/coverage.json` |
| ↳ `backend/app/tasks` | — measured, not separately gated | — | `_____` | n/a | `backend/coverage.json` |
| ↳ `backend/app/db` | — measured, not separately gated | — | `_____` | n/a | `backend/coverage.json` |
| `frontend/src/store` | G2 — gated independently | ≥ 80% all four | `_____` | `_____` | `frontend/coverage/coverage-summary.json` |
| `frontend/src/schema` | G2 — gated independently | ≥ 80% all four | `_____` | `_____` | `frontend/coverage/coverage-summary.json` |
| `frontend/src/services` | G2 — gated independently | ≥ 80% all four | `_____` | `_____` | `frontend/coverage/coverage-summary.json` |
| `frontend/src/components` | G3 | reported, not gated | `_____` | n/a | `frontend/coverage/coverage-summary.json` |
| `frontend/src/pages` | G3 | reported, not gated | `_____` | n/a | `frontend/coverage/coverage-summary.json` |

A per-package backend gate is possible — four `coverage report --include=… --fail-under=90` invocations
after the run, or four separate runs — and is listed in §7 as work this template does not assume.

### 6.2 Coverage by module

> **How to fill:** run the extractor. Backend rows come from `backend/coverage.json` — its
> `missing_lines` array **is** the uncovered-line list, the same information the `term-missing`
> `Missing` column shows. Frontend percentages come from `coverage-summary.json` and frontend
> uncovered lines from `coverage/lcov.info`. Resolve the last column against §3.3 **before** recording
> anything as work.

| Module | Statements | Branches | Functions | Lines | Uncovered lines | Ceiling or gap? |
|---|---|---|---|---|---|---|
| `_____` | `_____` | `_____` | `_____` | `_____` | `_____` | `_____` |

**Backend rows are line-only, and the two middle columns say so rather than showing a zero.** The
backend coverage run measures no branches — `coverage.json` records `meta.branch_coverage: false`,
which the extractor reads rather than assumes — and coverage.py emits no function metric at all. For
the backend, *statements* and *lines* are the same measurement and are printed identically. Frontend
rows carry all four, because Istanbul measures all four.

Add one row per module. A module whose uncovered region is entirely accounted for in §3.3 is
recorded as **ceiling** and carries no follow-up; anything else is a **gap** and belongs in the next
increment. The extractor fills every column except this last one, which is a judgement rather than a
measurement.

### 6.3 Test health by runner, then by layer

> **How to fill:** run the extractor. Each layer is a **partition of one aggregate JUnit stream**, not
> a separate artifact — see the partition rule below. Do not total the layers by hand.

Each runner writes one result stream per suite, not one per layer, so a layer row has to be derived.
The rule is stated in code, at the top of `dashboard-extract.py`, so it is reproducible rather than
editorial:

| Layer | Derived by |
|---|---|
| Backend unit | `<testcase classname>` starting `tests.unit.` |
| Backend integration | `<testcase classname>` starting `tests.integration.` |
| Backend infrastructure - dependency closure | `<testcase classname>` starting `tests.test_dependency_closure` |
| Backend infrastructure - coverage gate | `<testcase classname>` starting `tests.test_coverage_gate` |
| Backend infrastructure - guard contract | `<testcase classname>` starting `tests.test_guard_contract` |
| Backend infrastructure - dashboard producer | `<testcase classname>` starting `tests.test_dashboard_extract` |
| Backend infrastructure - document contract | `<testcase classname>` starting `tests.test_docs_contract` |
| Backend unclassified - add a prefix to BACKEND_LAYERS | every remaining backend `<testcase>`. The extractor's `classify_backend` returns this label rather than `None`, so the partition is exhaustive and the layer rows sum to the runner row — and a row appearing under it is a taxonomy gap to close, not a category of test. Each of the five repository-contract suites at the `tests/` root has its own row above, so this one is expected to be empty |
| Frontend component | `<testcase classname>` starting `src/components/` or `src/pages/` |
| Frontend unit | every other frontend `<testcase>` |
| End-to-end | the whole `e2e` stream; its root totals are used directly |

The backend classnames are the same strings the layers are selected by on the command line
(`pytest tests/unit`, `pytest tests/integration`), which is what makes the partition match the suite
rather than approximate it.

**Per runner** — read straight off the root element's `tests`, `failures`, `errors`, `skipped` and
`time` attributes. Passed is `tests - failures - errors - skipped`. Do not total these by hand.

| Runner | Total | Passed | Failed | Skipped | Duration | JUnit artifact |
|---|---|---|---|---|---|---|
| Backend unit | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend integration | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend infrastructure - dependency closure | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend infrastructure - coverage gate | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend infrastructure - guard contract | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend infrastructure - dashboard producer | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend infrastructure - document contract | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend unclassified - add a prefix to BACKEND_LAYERS | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Frontend unit | `_____` | `_____` | `_____` | `_____` | `_____` | `frontend/reports/jest-junit.xml` |
| Frontend component | `_____` | `_____` | `_____` | `_____` | `_____` | `frontend/reports/jest-junit.xml` |
| End-to-end | `_____` | `_____` | `_____` | `_____` | `_____` | `e2e/reports/e2e-junit.xml` |
| pytest | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Jest | `_____` | `_____` | `_____` | `_____` | `_____` | `frontend/reports/jest-junit.xml` |
| Playwright | `_____` | `_____` | `_____` | `_____` | `_____` | `e2e/reports/e2e-junit.xml` |

**Per layer** — group the `<testcase>` elements of the named artifact by the selector given, then
count. A case is skipped when it carries a `<skipped>` child, failed when it carries `<failure>` or
`<error>`, and passed otherwise; duration is the sum of the group's `time` attributes.

| Layer | Total | Passed | Failed | Skipped | Duration | Group `<testcase>` by |
|---|---|---|---|---|---|---|
| Backend unit | `_____` | `_____` | `_____` | `_____` | `_____` | `classname` beginning `tests.unit.` in `backend/reports/junit.xml` |
| Backend integration | `_____` | `_____` | `_____` | `_____` | `_____` | `classname` beginning `tests.integration.` in the same artifact |
| Frontend unit | `_____` | `_____` | `_____` | `_____` | `_____` | `classname` **not** under `src/components/` or `src/pages/` in `frontend/reports/jest-junit.xml` |
| Frontend component | `_____` | `_____` | `_____` | `_____` | `_____` | `classname` under `src/components/` or `src/pages/` in the same artifact |
| End-to-end | `_____` | `_____` | `_____` | `_____` | `_____` | every `<testcase>` in `e2e/reports/e2e-junit.xml`; its root element fills this row too, being one layer per runner |

Both `classname` selectors are stable by configuration rather than by convention: `backend/pytest.ini`
makes `classname` the dotted module path of the test, and `frontend/jest.config.js` gives `jest-junit`
a `classNameTemplate` that emits the `/`-separated source path. The one layer whose runner and layer
rows are necessarily identical is end-to-end, and it is the only row that may be copied between the
two tables.

**Skip register.** Every skip in this suite names an unimplemented production feature, so a skip is a
record rather than a silence and must be reproduced with its reason. A skip whose reason does not
name such a feature is a defect in the test, not a documented limitation.

Where the reason lives differs by runner, and the panel has to read the right place. pytest writes it
as the `message` attribute of `<skipped>`. jest-junit and Playwright write no message at all, so those
two layers carry the reason in the **suite or test title** instead — which is why a frontend skipped
test reads `… — SKIPPED: useAppSelector is not a function …`. A dash in the reason column of an
extractor-produced register is therefore not a missing reason; read the first column.

| Skipped test | Reason, from `<skipped message>` or from the title | Unimplemented feature it names |
|---|---|---|
| `_____` | `_____` | `_____` |

### 6.4 Readiness

> **How to fill:** run the extractor, which reads the retained output of the three CI readiness steps.
> Treat a non-zero error count as a build failure, because a module that does not import cannot be
> asserted against at all.

| Check | Source artifact | Expected | Actual | Pass / Fail |
|---|---|---|---|---|
| Backend collection errors | `backend/reports/collect-only.txt` | **0 errors** | `_____` | `_____` |
| Backend tests collected | `backend/reports/collect-only.txt` | equals the backend total in §6.3 | `_____` | `_____` |
| Backend exact coverage gate | `backend/reports/coverage-gate.txt` | `PASSED` | `_____` | `_____` |
| Frontend test files discovered | `frontend/reports/list-tests.txt` | greater than 0 | `_____` | `_____` |
| Frontend suites loaded | `frontend/reports/load-tests.txt` | every suite loads, **zero** failed to load | `_____` | `_____` |
| Frontend readiness executed no test body | `frontend/reports/load-tests.txt` | 0 of the discovered tests run | `_____` | `_____` |
| Frontend test identities registered | `frontend/reports/load-tests.txt` | equals the frontend total in §6.3 | `_____` | `_____` |
| E2E tests discovered | `e2e/reports/list-tests.txt` | equals the E2E total in §6.3 | `_____` | `_____` |

Each row has a **CI producer**, not just a documented command: `Check backend collection integrity`,
`Enforce the exact backend coverage gate`, `Check frontend test discovery`,
`Check that every frontend suite loads` and `Check end-to-end test discovery`. Discovery and readiness
are two different checks and the panel keeps them apart: `jest --listTests` enumerates the files a run
would pick up without importing any of them, so a module that no longer parses is still listed. The
readiness step is what loads and transforms every one of them, and it exits non-zero when one fails —
measured against a module carrying an unresolvable import, where discovery exited 0 and readiness
exited 1. The E2E discovery step is deliberately ordered ahead of the browser-provisioning gate,
because `playwright test --list` launches no browser — so a host with no browser still leaves a
retained readiness result rather than nothing. Every command is also runnable locally, verbatim, from
the block at the top of this document, and each of them **creates** the artifact its row reads.

The load-probe rows read a run rather than a file listing, and the distinction is the whole point of
keeping both: a listing proves files exist, a load proves they can run. See §2.2 for the measured
demonstration.

### 6.5 E2E flow status

> **How to fill:** run the extractor. Results come from `e2e/reports/e2e-junit.xml`, one row per
> `<testsuite>`, which is one row per spec file. Artifact names come from the per-test subdirectories
> of `e2e/test-results/`, which are named after the spec and test title. A passing test legitimately
> has no trace, screenshot or video — all three are retained on failure only, so `none retained` in a
> green run is the expected reading and not a gap.

| Spec | Tests | Route or property under test | Result | Trace / screenshot / video |
|---|---:|---|---|---|
| `dashboard.spec.ts` | 3 | `/` | `_____` | `_____` |
| `tweets.spec.ts` | 3 | `/tweets` | `_____` | `_____` |
| `analytics.spec.ts` | 4 | `/analytics` (three on the transport path, one on the chart-construction path, asserting that ceiling as current behaviour rather than skipping it) | `_____` | `_____` |
| `configuration.spec.ts` | 6 | `/configuration`, plus the fixture-honesty gate that keeps its retained failure evidence harmless | `_____` | `_____` |
| `isolation.spec.ts` | 15 | Not a route: that an anchored spec route claims the harness origin and no other, and that the harness's **own** origin is not exempt either - the dev-server control paths and every out-of-graph read are refused | `_____` | `_____` |
| **Total** | **31** | | `_____` | |

Five rows: the four route specs plus the isolation spec, which asserts the interception and
containment properties the other four rest on rather than a route. Thirty-one tests, **none
skipped**, so a green run reads **31 passed, 0 skipped** and the JUnit root reads
`tests="31" failures="0" skipped="0" errors="0"`. A non-zero `skipped` here is therefore a finding,
not a baseline. There is no skipped chart case: the unreachable chart branch is a *coverage* ceiling
asserted at the jsdom layer (G4) and measured at this one, so this layer never had a test to skip.
Add a row for any spec added later, so the panel stays a census of the E2E layer rather than a
sample of it.

The extractor's **Passed** column is `tests - failures - errors - skipped`. `errors` is a distinct
JUnit outcome from `failures` — Playwright writes one when a fixture or hook throws before the test
body runs — so a pass count that ignored it would report an errored spec as having passed.

### 6.6 Trend row

> **How to fill:** keep each run's `--json` output and pass it to the next run as `--previous`. The
> extractor computes the delta; nothing here is carried by hand.

| Metric | Previous | Current | Delta |
|---|---|---|---|
| Backend gated coverage (K1) | `_____` | `_____` | `_____` |
| Frontend gated coverage, worst metric (K2) | `_____` | `_____` | `_____` |
| Test cases, all layers | `_____` | `_____` | `_____` |
| Failures, all layers | `_____` | `_____` | `_____` |
| Skips, all layers | `_____` | `_____` | `_____` |
| Collection errors (K5) | `_____` | `_____` | `_____` |
| Wall-clock seconds, all layers (K7) | `_____` | `_____` | `_____` |

K2 is twelve independent comparisons — three `coverageThreshold` groups by four metrics — so both the
KPI and the trend follow the **worst** of them, the one a per-path Jest threshold group would actually
fail on. Summing them would let a failing group be carried by a passing one and publish a green KPI
over a red gate. A cell whose denominator is empty carries no percentage, and Jest's own threshold
check treats it as satisfied, so such cells are excluded from the minimum rather than read as zero and
their count is stated in the cell.

Without a `--previous` file the *Previous* column reads `no previous run supplied` — which is honest,
and is not the same as a zero. A rising skip count with a steady failure count is the pattern most
easily missed, and it is why skips are tracked here alongside failures rather than folded into a pass
rate.

---

## 7. Verification status

Rule 2 holds that observability which cannot be exercised locally is not delivered. This section is
the honest accounting that clause requires: what was produced and observed, and what a reader should
still treat as unproven.

**Provenance form.** Any figure quoted anywhere in this repository carries, or points at, four things:
the **command** that produced it, the **runtime** it ran on, the **artifact** it was read from, and the
**commit** whose tree was measured. A figure missing any of the four is a figure nobody can re-derive,
and should be re-measured rather than quoted.

**The commit is recorded by the tooling, not transcribed into prose.** This is a correction of the
earlier form, and the reason is arithmetic rather than stylistic: a hash typed into a document names
either a tree that predates the measurement or one that does not exist yet, because the sentence
recording it necessarily lands in a *later* commit than the run it describes. That is not a hazard in
the abstract — a previous revision of this document, and four others, cited a measured commit `8a255fb`
that is not a git object in this repository at all, so every figure resting on it was unreproducible in
exactly the way this section exists to prevent.

So the commit element is supplied by `docs/testing/dashboard-extract.py`, which reads `.git/HEAD` and
the ref it points at, at the moment a reading is produced, and emits **§1.0 Provenance of this reading**
carrying the branch, the commit, a UTC timestamp, the Python version, the platform, and the browser and
runner versions read from `e2e/reports/browser.txt`. Run the extractor and the commit in the output is
by construction the tree the artifacts were measured on. `--json` carries the same block under
`provenance`.

Prose elsewhere in this repository therefore states the **command**, the **runtime** and the
**artifact** — the three a document can keep true — and points here for the fourth. To re-derive any
figure: run the local sequence at the top of this document, then read §1.0 of your own output. A figure
quoted without a reading beside it is a claim about some tree, and the honest response to one is to
re-measure rather than to trust it.

### 7.1 Verified executed

Each item below was produced and inspected. The delivered-suite rows supersede the planning-time
demonstration figures that this section previously carried; the demonstration numbers survive only in
§1.2, labelled as the floors they were.

Read the two kinds of number in these rows differently. The **counts** — 1068 backend cases with 3 skips,
371 frontend cases with 24 skips, 31 E2E tests with no skip, and zero failures anywhere — are properties of the
suite, and a re-run reproduces them exactly; the reproduction below is the evidence for that. Every
**`time` attribute** is a property of the one invocation that wrote the file, so a later run overwrites it
with its own figure. Quote the counts as facts about the suite; quote a duration only as what that run took
on that host.

One consequence of that split is worth stating, because it is the one way these rows can go stale in a
working tree rather than in CI. `backend/pytest.ini` carries `--junitxml` in `addopts`, so *every* pytest
invocation writes `backend/reports/junit.xml` — including a single-file run, a `-k` filtered run, and the
readiness probe. A partial run therefore leaves a non-zero case count where the suite's count belongs. That
is now compared rather than trusted: the readiness probe writes its own `--junitxml` path, and both
`dashboard-extract.py` and the workflow's verify step require the stream's case count to equal the collected
count, naming both figures when they differ (`D355`). If you see that message, re-run the canonical gated
command in §2.1; the counts below are what it reproduces.

| Evidence | What was observed |
|---|---|
| Backend artifacts | `backend/reports/junit.xml` (`<testsuite name="pytest" errors="0" failures="0" skipped="3" tests="1068">`, that run's `time="12.988"`) plus the Cobertura and JSON coverage files — the two the canonical gated command requests; `backend/coverage.lcov` is the local measurement command's, as §2.1 records — from the gated run on CPython 3.9.13: **1065 passed, 3 skipped, exit 0, 93.33% (182/195)** over `app/core` 100.00% (47/47), `app/db` 100.00% (45/45), `app/services` 94.12% (48/51) and `app/tasks` 80.77% (42/52). The exact gate's own reading is retained beside them as `backend/reports/coverage-gate.txt`: `182 of 195 statements covered = 93.3333% exact, threshold 90%` / `9 file(s) measured` / `coverage gate PASSED` |
| Frontend artifacts | `frontend/reports/jest-junit.xml` (`<testsuites tests="371" failures="0" errors="0">`, that run's `time="54.122"`, 24 `<testsuite>` children, `skipped` summing to 24 across them) and all five configured coverage reporters, from `jest --ci --coverage`: **21 suites passed / 3 skipped, 347 passed / 24 skipped, exit 0** |
| E2E artifacts | `e2e/reports/e2e-junit.xml` (`tests="31" failures="0" skipped="0" errors="0"`, that run's `time="19.096366"`; per spec `analytics` 4, `configuration` 6, `dashboard` 3, `isolation` 15, `tweets` 3), `e2e/playwright-report/index.html` (about 456 KB; its exact size moves with the run) and `e2e/test-results/.last-run.json` = `{"status":"passed","failedTests":[]}` |
| Reproduction | All three suites were re-run end to end after the last change in this checkpoint, on the same host. Backend **1068 collected / 0 collection errors, 1065 passed, 3 skipped, exit 0, 93.33%**; frontend **21 suites passed / 3 skipped, 347 passed / 24 skipped, exit 0**, gated scopes `src/store` 100 / `src/schema` 100 / `src/services` 100 against an 80 bar, and the worst of the twelve gates 100.00%; e2e **31 passed, 0 skipped, 0 failed, 0 flaky, exit 0**. Identical counts, different durations — which is exactly the split described above. Two consecutive gated backend runs read `12.24 s` and `12.09 s`, and the same suite under `pytest -n auto` read `106.81 s` for the identical `1065 passed, 3 skipped`, which is the same point about durations |
| Test identity | Across both artifacts every `<testcase>` is uniquely identified: 1068 of 1068 distinct `classname`+`name` pairs on the backend, 371 of 371 on the frontend, and not one `classname` or suite name containing a backslash |
| E2E harness | All four routes served, with an error-free dev-server log, under Vite 4.5.14 on `127.0.0.1:<4173 + CLONE_INDEX>` |

### 7.2 Implementation-time acceptance steps — performed

All three are complete. Each row states the runtime it ran on and the artifact that survives it, so the
claim is checkable rather than asserted.

| # | Step | Performed | Evidence |
|---|---|---|---|
| A1 | Execute the Playwright suite in a real browser | **Yes** — `npm test` from `e2e/`, `@playwright/test` 1.44.1 driving system **Google Chrome 151.0.7922.76**, resolved by `browsers:require` rather than by a hardcoded path, harness on `127.0.0.1:<4173 + CLONE_INDEX>`, Node v22.23.1. Resolved **by path**: `browsers:require` recorded the executable's SHA-256 into the artifact, and the run was **not digest-bound**, because binding the launch to that digest requires `PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256` to be set and it was unset — which is what the artifact's own closing line says, together with two warnings that the executable and its directory are writable by this user | Exit 0. **31 tests over 5 spec files: 31 passed, 0 skipped, 0 failed, 0 flaky, 19.10 s** — per spec `analytics` 4, `configuration` 6, `dashboard` 3, `isolation` 15, `tweets` 3. `e2e/reports/e2e-junit.xml` (`tests="31" failures="0" skipped="0" errors="0"`), `e2e/playwright-report/index.html`, `.last-run.json`, and `e2e/reports/browser.txt` carrying the resolved executable, `Browser version: 151.0.7922.76 (from the install layout)` and `Version 1.44.1`. Nothing is skipped: the chart-construction case runs and asserts the ceiling §3.3 records rather than being skipped for it. Retention on failure is observed rather than only configured — see the A1b row |
| A1b | Induce a failure and confirm `e2e/test-results/` carries a trace, a screenshot and a video for it | **Yes — performed as a by-product of A3.** The negative validation of the route anchoring failed four `isolation.spec.ts` tests deliberately, and each produced `test-failed-1.png`, `video.webm` and `trace.zip` under its own `e2e/test-results/` subdirectory named after the spec and test title. Those artifacts were deleted with the perturbation | Retention is therefore observed, not merely configured |
| A2 | Render `blitzy-deck/executive-summary.html` in a browser | **Yes, repeatedly — and re-performed against the compressed deck** — headless Chrome 151 at a 1920×1080 viewport, all 16 slides visited individually via `Reveal.slide(N)`: two independent passes over the compressed bytes and one confirmation pass after the headline KPI was restamped | `Reveal.VERSION "5.1.0"`, `isReady() true`, **16** sections, config read back as `{width:1920, height:1080, hash:true, transition:"slide", controlsTutorial:false}`; **6 of 6** Mermaid diagrams `data-processed="true"` with exactly one non-zero-sized `<svg>` each and real node geometry, including the subgraph-anchored edge on slide 2; **19 of 19** Lucide icons rendered with **zero** surviving `i[data-lucide]` placeholders and none of zero size on its own slide; **9 of 9** network requests HTTP 200, the four integrity-pinned CDN assets among them with decoded byte sizes matching their sha384 declarations exactly; **zero** console messages of any type and **zero** CSP violations, both proven by instruments validated against deliberate violations rather than merely installed; and no clipping or overflow on any slide. Screenshots and recordings survive in the working tree under the git-ignored `blitzy/screenshots/` and `blitzy/screen_recordings/`, one capture per slide and one per diagram; what is committed is the measured table in §7.4, re-measured whenever the deck changes |
| A3 | Demonstrate the negative validations | **Yes** — **28 critical-path production modules, one primary probe each** (14 backend, 14 frontend; `src/app.tsx` and `src/index.tsx` are excluded as the unmountable ceilings §3.3 records), plus **14 additional probes** on 13 of the same modules and on one harness module — each perturbing exactly one threshold, string or return value, running only the covering target, then restoring the file and re-verifying its sha256 | **42 of 42 probes turned the covering target red** and **42 of 42 restorations were byte-exact**. Nothing was committed: `git status` over `backend/app` and every frontend production path is clean and all nine `# TESTING:` markers are unchanged. The complete ledger, primary and additional, is §7.3. Separately, each fix in this checkpoint carries its own performed-and-reverted negative validation — the coverage precision gate, the dependency-pin grammar, the socket-ownership registry (twice), the spec-bound Firestore client, and the integer-coercion domain. The **security checkpoint's** eleven fail-closed demonstrations are §7.3.4 and are counted separately from the 42, because they perturb a control rather than a production module (D328) |

### 7.3 Negative validation — one case per critical-path module

A suite that passes proves nothing on its own: it has to be shown to fail when the code it guards
changes. This is that demonstration, one entry per critical-path module.

**Method, identical for every entry.** Hash the production file. Apply one textual perturbation,
refusing to proceed unless the target string occurs exactly once. Run **only** the named test. Restore
the original bytes from the copy taken before the edit, in a `finally` block so restoration happens
even if the run itself errors. Re-hash and require the digest to equal the original. Run the named
test again and require it to pass. Nothing is left perturbed between entries, and no perturbation is
committed — `git status --porcelain` reported no production file modified after the run.

**Environment.** Windows Server 2022 container, 9 August 2026. Backend: CPython 3.9.13 in
`.venv-backend`, pytest 8.4.2, one node id per run (`pytest <nodeid> -q --no-header`). Frontend: Node
v22.23.1 / npm 10.9.8, jest 29.7.0, one suite file per run
(`jest <path> --ci --watchAll=false --coverage=false`).

**Result: 28 of 28 modules detected their perturbation.** Every restored run returned to green and
every restoration was byte-identical.

#### 7.3.1 Backend — 14 modules

| # | Module | Perturbation | Test that had to fail | Observed when perturbed |
|---|---|---|---|---|
| N1 | `app/core/config.py` | `POPULARITY_THRESHOLD: int = 100` → `101` | `tests/unit/test_core_config.py::test_popularity_threshold_declared_default` | `AssertionError: assert 101 == 100` |
| N2 | `app/core/security.py` | `timedelta(minutes=15)` → `minutes=16` | `tests/unit/test_core_security.py::test_create_access_token_defaults_to_fifteen_minutes` | `assert 1704068160 == 1704068100` |
| N3 | `app/db/firestore.py` | `return doc_ref[1].id` → `doc_ref[0].id` | `tests/unit/test_db_firestore.py::test_add_tweet_returns_the_id_of_the_second_element` | `assert 'write-time-not-a-document-id' == 'doc123'` |
| N4 | `app/db/bigquery.py` | the error branch's `return False` → `return True` | `tests/unit/test_db_bigquery.py::test_insert_tweet_analytics_returns_false_with_errors[structured]` | `assert True is False` |
| N5 | `app/schema/tweet.py` | `retweets_count: int` → `retweet_count: int` | `tests/unit/test_schema.py::test_tweet_declares_the_ten_documented_fields` | field-set inequality, extra item in the left set |
| N6 | `app/schema/user.py` | `followers_count: int` → `followers_count: int = 0` | `tests/unit/test_schema.py::test_user_rejects_payload_missing_field[followers_count]` | `Failed: DID NOT RAISE <class 'pydantic.error_wrappers.ValidationError'>` |
| N7 | `app/services/twitter_service.py` | `stream = tweepy.Stream(auth=api.auth, listener=listener)` → `stream = API(auth)` | `tests/unit/test_services_twitter.py::test_start_twitter_stream_raises_name_error` | the `NameError` no longer occurs; execution reaches the next line and raises `AttributeError: 'types.SimpleNamespace' object has no attribute 'TWITTER_TRACK_KEYWORDS'` |
| N8 | `app/services/llm_service.py` | `response.choices[0].text.strip()` → `.text` | `tests/unit/test_services_llm.py::test_generate_response_returns_the_stripped_completion_text` | `assert '  hello  ' == 'hello'` |
| N9 | `app/services/analytics_service.py` | `avg_daily_tweets` computed with `.mean()` → `.sum()` | `tests/unit/test_services_analytics.py::test_get_tweet_analytics_averages_the_daily_tweet_counts` | `assert 8.0 == 4.0` |
| N10 | `app/tasks/tweet_processor.py` | the popularity gate `<` → `<=` | `tests/unit/test_tasks_tweet_processor.py::test_on_status_rejects_at_or_above_popularity_threshold[100-0]` | `Failed: DID NOT RAISE <class 'pydantic.error_wrappers.ValidationError'>` — the exact-boundary case falls to the early return |
| N11 | `app/tasks/response_generator.py` | `raise ValueError(...)` → `raise RuntimeError(...)` | `tests/unit/test_tasks_response_generator.py::test_generate_response_raises_value_error_when_the_tweet_is_absent[none]` | `RuntimeError: Tweet with id 1 not found` escaped `pytest.raises(ValueError)` |
| N12 | `app/api/dependencies.py` | `status_code=401` → `403` on the exception path | `tests/unit/test_api_dependencies.py::test_get_current_user_raises_401_when_verify_token_raises[exception]` | `assert 403 == 401` |
| N13 | `app/api/routes/tweets.py` | `@router.get('/tweets')` → `@router.get('/tweet-list')` | `tests/integration/test_http_tweets.py::test_get_tweets_returns_serialized_tweet` | `assert 404 == 200` |
| N14 | `app/main.py` | `allow_origins=settings.ALLOWED_ORIGINS` → `allow_origins=["*"]` | `tests/integration/test_app_lifecycle.py::test_cors_middleware_registered_with_expected_options` | `AssertionError: assert ['*'] == []` |

**Two perturbations the suite did not detect, and why.** Both are recorded because a silent
non-detection is exactly what this exercise exists to surface.

- `POPULARITY_THRESHOLD: int = 100` → `101` does **not** fail
  `test_core_config.py::test_popularity_threshold_default`. That test reads the shared singleton,
  whose value comes from the environment variable the parent `conftest.py` pins to `"100"` before
  `app.core.config` is imported, so the class default is not what it observes. The test that does
  observe the declared default is `test_popularity_threshold_declared_default`, which builds a
  `Settings` with the name absent and the `.env` source disabled — N1 uses that one.
- Deleting `app.include_router(config.router)` from `main.py` fails **nothing**, and cannot. The
  `config` router carries no routes, so including it changes neither the application's operation set
  nor any attribute the lifecycle suite asserts. This is a property of the production code, not a gap
  in the suite: an empty router's inclusion is unobservable through the app object. N14 therefore
  perturbs the CORS origin list, which the same suite does observe.

#### 7.3.2 Frontend — 14 modules

Each entry names the suite file that was run; the failing case is the one quoted in the last column.

| # | Module | Perturbation | Suite that had to fail | Observed when perturbed |
|---|---|---|---|---|
| N15 | `src/store/tweetSlice.ts` | `rejectWithValue('Failed to fetch tweets')` → `'Could not fetch tweets'` | `src/store/tweetSlice.test.ts` | 3 failed / 17 passed; `Expected: "Failed to fetch tweets"` / `Received: "Could not fetch tweets"` in *settles as rejected, carrying the message* |
| N16 | `src/store/configSlice.ts` | `state.status = 'updated'` → `'changed'` | `src/store/configSlice.test.ts` | 2 failed / 13 passed; `Expected: "updated"` / `Received: "changed"` |
| N17 | `src/store/index.ts` | added one extra `export const perturbationProbe = 1` | `src/store/index.test.ts` | 1 failed / 5 passed; the module's export list no longer deep-equals `['setupStore','store']` |
| N18 | `src/schema/tweetSchema.ts` | `timestamp: z.date()` → `z.string()` | `src/schema/tweetSchema.test.ts` | 5 failed / 1 passed; the string-timestamp rejection inverts, `Expected: true` / `Received: false` |
| N19 | `src/schema/userSchema.ts` | `followers_count: z.number()` → `.optional()` | `src/schema/userSchema.test.ts` | 1 failed / 8 passed; *rejects a user with no followers_count* now parses, `Expected: false` / `Received: true` |
| N20 | `src/services/api.ts` | query string `?page=…&limit=…` → `?limit=…&page=…` | `src/services/api.test.ts` | 2 failed / 23 passed; `Expected: "undefined/tweets?page=2&limit=10"` / `Received: "undefined/tweets?limit=10&page=2"` |
| N21 | `src/services/twitterService.ts` | `fetchTweets(count)` → `fetchTweets(count, 10)` | `src/services/twitterService.test.ts` | 3 failed / 14 passed; the one-argument defect the suite pins disappears, and *limit set to the string "undefined"* no longer holds |
| N22 | `src/services/llmService.ts` | `'Failed to generate tweet response'` → `'Could not generate tweet response'` | `src/services/llmService.test.ts` | 2 failed / 4 passed; `Expected: "Failed to generate tweet response"` / `Received: "Could not generate tweet response"` |
| N23 | `src/utils/formatUtils.ts` | grouping separator `","` → `"_"` | `src/utils/formatUtils.test.ts` | 4 failed / 6 passed; `Expected: "1,234,567"` / `Received: "1_234_567"` |
| N24 | `src/utils/dateUtils.ts` | `` `${diffInSeconds} seconds ago` `` → `` `${diffInSeconds} sec ago` `` | `src/utils/dateUtils.test.ts` | 2 failed / 17 passed; `Expected: "30 seconds ago"` / `Received: "30 sec ago"` |
| N25 | `src/components/Dashboard` | `setInterval(fetchTweets, 30000)` → `25000` | `src/components/Dashboard.test.tsx` | 2 failed / 10 passed; *does not refetch at 29999 ms* now sees a second call — `Expected number of calls: 1` / `Received number of calls: 2` |
| N26 | `src/components/TweetManagement` | `className="tweet-list"` → `"tweet-listing"` | `src/components/TweetManagement.test.tsx` | 4 failed / 4 passed; the container query returns nothing and the loading-indicator assertion receives `undefined` |
| N27 | `src/components/Analytics` | `<h2>Trend Charts</h2>` → `<h2>Trend Graphs</h2>` | `src/components/Analytics.test.tsx` | 4 failed / 4 passed, starting with *renders the "Trend Charts" heading and the trendChart canvas* |
| N28 | `src/components/Configuration` | `alert('Twitter API settings updated successfully')` → `alert('Twitter API settings saved')` | `src/components/Configuration.test.tsx` | 2 failed / 9 passed; `Expected: "Twitter API settings updated successfully"` / `Received: "Twitter API settings saved"` |

**What this ledger does not claim.** It shows that each module's suite is sensitive to a change in
that module. It does not measure mutation-testing thoroughness: a single perturbation per module is
one probe, not a survivor analysis, and there is no automated mutation run behind these numbers.

#### 7.3.3 Additional probes on the same modules

The sweep above is not the only one this delivery ran. Earlier sweeps perturbed many of the
same modules differently, and those probes are recorded here rather than discarded: a module
probed twice, in two unrelated places, is better evidenced than one probed once. Method,
restoration and digest re-check are identical to §7.3.1. **Every probe below bit.** The pass and
fail counts are what each earlier run printed at the time, against the case counts those files
carried then — several have since grown, so they are readings rather than current totals, and
§1.1 is where today's figures live.

| # | Module | Perturbation | Covering target | Observed when perturbed |
|---|---|---|---|---|
| A1 | `app/db/firestore.py` | `update_tweet`'s swallowed-failure `return False` → `return True` | `tests/unit/test_db_firestore.py` | 3 failed, 7 passed — `assert True is False` on both `test_update_tweet_returns_false_when_the_update_fails` cases |
| A2 | `app/services/analytics_service.py` | `total_tweets` aggregate `+ 1` | `tests/unit/test_services_analytics.py` | 4 failed, 61 passed — the totals and the daily breakdown disagreed |
| A3 | `app/services/twitter_service.py` | `on_status` payload key `'id'` → `'tweet_id'` | `tests/unit/test_services_twitter.py` | failed — the `ValidationError` reported eight missing schema fields where the oracle requires nine |
| A4 | `app/services/llm_service.py` | the swallowed-OpenAI fallback string reworded | `tests/unit/test_services_llm.py` | 2 failed, 5 passed |
| A5 | `app/tasks/response_generator.py` | the `ValueError` message reworded | `tests/unit/test_tasks_response_generator.py` | failed — `assert 'Tweet 1 was not found' == 'Tweet with id 1 not found'` |
| A6 | `app/api/routes/tweets.py` | `return tweets` → `return []` | `tests/integration/test_http_tweets.py` | 2 failed, 41 passed — the 200 response body no longer carried the injected tweet |
| A7 | `src/schema/userSchema.ts` | `created_at` made optional | `src/schema/userSchema.test.ts` | failed — the missing-field rejection case parsed instead of throwing |
| A8 | `src/store/index.ts` | the invalid named reducer import repaired to a default import | `src/store/index.test.ts` | failed — the invalid-reducer console error the suite pins was no longer emitted |
| A9 | `src/store/tweetSlice.ts` | the thunk rejection message reworded | `src/store/tweetSlice.test.ts` | 1 suite failed, 3 of 20 tests failed at the `state.error` assertion |
| A10 | `src/services/api.ts` | the `page` query parameter renamed | `src/services/api.test.ts` | failed — the literal-URL oracle no longer matched |
| A11 | `src/services/api.ts` | one extra query parameter appended to the tweets URL | `src/services/api.test.ts` | 1 suite failed, 4 of 25 tests failed — and the msw guard answered the now un-allow-listed URL with **HTTP 599** rather than letting it reach the network, so this probe doubles as proof the no-network guard is fail-closed |
| A12 | `src/utils/formatUtils.ts` | `truncateText`'s `maxLength - 3` → `- 2` | `src/utils/formatUtils.test.ts` | 1 suite failed, 2 of 10 tests failed |
| A13 | `src/components/Dashboard` | poll interval `30000` → `29000` ms | `src/components/Dashboard.test.tsx` | 1 suite failed, 2 tests failed — the 29,999 ms and 30,000 ms boundary pair (2 of the 12 the suite carried when this probe ran; it now carries 13) |
| A14 | `e2e/harness/main.tsx` (harness, not production) | `endDate` `2024-01-31` → `2024-02-29` | `e2e/tests/analytics.spec.ts` | 1 failed, 1 passed — and the failing test's output directory received a trace, a video and a screenshot, independently corroborating A1b |

**Counting these probes.** 28 production modules carry a primary probe (§7.3.1 and §7.3.2);
13 of them carry a second probe as well, and one harness module carries one, for **42 probes**
in total. `app/services/api.ts` carries two additional probes rather than one, because the two
exercise different properties — the URL oracle and the fail-closed guard.

**Two cases had to be redesigned, and the reason is worth recording**, because a perturbation that
does not bite is easy to mistake for a well-covered module:

- `app/services/twitter_service.py`: perturbing `on_status`'s `return True` changed nothing, because
  `Tweet(**tweet_data)` raises two lines earlier — that return is **unreachable**. The assertable value
  this function produces is the payload it builds, so the perturbation moved to a payload key.
- `src/services/api.ts`: renaming the *path* made msw's handler miss, and the unhandled-request object
  Jest then tried to diff aborted the worker with exit 134 — a failure, but a crash rather than a clean
  assertion. Perturbing the query parameter instead keeps the handler matched and fails one assertion.

Beyond the per-module set, the two layers whose guarantees are structural rather than numeric were
validated the same way: the backend guards (a sentinel credential in a failure message, a recycled
loopback port, a child process during collection and during teardown) and the e2e diagnostics verdict
(an injected console error, an injected page error, the same error against a spec that expects one of
its own, a removed `allow(...)`, and the chart ceiling's dependence on its opt-in header). All bit.

#### 7.3.4 Fail-closed demonstrations for the controls added at the security checkpoint

A different exercise from §7.3.1–§7.3.3, recorded separately and **not** added to their arithmetic.
Those probe a *production module* to show its suite is sensitive to it. These probe a *control this
delivery added* to show it refuses rather than waves through — the failure mode a control has that a
test does not, because a guard that never denies anything passes every test written against it.

**Method, as in §7.3.1**: hash the file, apply one textual perturbation only if its anchor occurs
exactly once, run only the named target, restore the original bytes in a `finally` block, and re-check
the hash. Every restoration below was confirmed byte-identical by SHA-256. **All eleven bit.**

| # | Control, and the row that decided it | Perturbation | What had to fail | Observed when perturbed |
|---|---|---|---|---|
| S1 | `_guard_bind` refuses a bind to a routable or unspecified address (D312) | `if not _is_bindable_address(...)` → `if False and not …` | `tests/unit/test_egress_guard.py` bind refusals | **4 failed / 31 deselected.** `Failed: DID NOT RAISE <class 'tests.conftest.UnmockedNetworkAccessError'>` on both wildcard hosts and on `::`; the routable case failed differently — `OSError: [WinError 10049] The requested address is not valid in its context` — which is the point of refusing in the guard: without it the outcome is whatever the OS happens to do |
| S2 | The msw runtime override is registered at the **exact** allowed origin, never a wildcard (D322) | the override's URL → `'*/tweets'` | `setup-jest.test.ts::does not let an override claim the same path on a foreign origin` | **1 failed / 13 skipped.** `expect(received).rejects.toBeDefined()` — *Received promise resolved instead of rejected*: the wildcard override answered `https://api.example.test/tweets`, so the foreign origin was served instead of refused and nothing reached the isolation ledger |
| S3 | Only a **registered** virtual module id bypasses the harness path checks (D317) | the registry membership test → `? true` | `isolation.spec.ts::the dev server answers 403 to …` | **2 failed, 7 passed** — the unregistered virtual module id and the traversal dressed as one: `Expected: 403 / Received: 404`, i.e. both fell through the gate into Vite's own resolution. The two plain traversal shapes still 403, because root containment catches those independently |
| S4 | The guard prologue primes the **second** `platform` cache so an xdist worker never shells out (D315) | the fix reverted (changes stashed) | `pytest -n 2` starting at all | Worker aborted in `pytest_sessionstart` → `platform.platform()` → `win32_ver` → `_syscmd_ver()` → `subprocess.Popen('ver')`, refused by the guard → **INTERNALERROR, "no tests ran"**. Restored: `-n 2` → 802 passed, 3 skipped in 9.17 s |
| S5 | `trace: { sources: false }` keeps spec text out of a retained trace (D318) | `sources: false` → `true` | the trace containing no spec source | Two-sided, on a temporary probe spec carrying a unique phrase and a forced failure. With `false`: entries are `0-trace.network`, `0-trace.stacks`, `0-trace.trace`, `test.trace`, four sha-named resources and four jpegs — **the phrase absent**. With `true`: an extra entry `src@e28c685c…txt`, 606 B, **holding the whole spec**. Config restored byte-identically and the probe deleted |
| S6 | The credential fixture types only synthetic values, so no failure artifact can retain a real one (D318) | `apiKey: 'test-api-key'` → `'AKIAREALLOOKINGKEY123'` | `configuration.spec.ts::types only synthetic credentials …` | **exit 1** with the gate's own message naming the offending field. Restored → exit 0. The gate also asserts its own field list is complete, so dropping a key cannot satisfy it vacuously |
| S7 | `browsers:require` fails closed when it cannot resolve a browser (D319) | `PLAYWRIGHT_CHROMIUM_EXECUTABLE` → a path that does not exist | the script exiting non-zero | **exit 1**, naming the path it could not use — rather than deferring a certain launch failure to the runner |
| S8 | `browsers:verify` confirms the digest the resolver published (D319) | published digest → `deadbeef` | the confirming gate | **exit 1** on mismatch. Two controls either side of it also measured: unbound → exit 0 with the explicit *not digest-bound* note, and a correct digest in upper case → exit 0, so the check is case-insensitive by intent rather than by accident |
| S9 | `playwright.config.ts` re-hashes the executable at config load (D319) | published digest → `000…0` | the run refusing to start | **exit 1**, `Error: The browser named by PLAYWRIGHT_CHROMIUM_EXECUTABLE is not the one that was validated` with expected and actual, thrown from `verifiedExecutable` **before any browser launched**. Matching digest → 15 passed |
| S10 | `dashboard-extract.py` refuses an artifact that declares a document type (D323) | none needed — the hostile input **is** the probe | the parser refusing | Before the guard, a ~350-byte document with five nested ten-fold entities expanded to **100,000 characters** through `xml.etree.ElementTree` on CPython 3.9.13 and was accepted. After: refused, naming the marker and its byte offset. An XXE document is refused the same way, and a benign document still parses with its attributes readable |
| S11 | `dashboard-extract.py` refuses an oversized artifact (D323) | `MAX_ARTIFACT_BYTES` temporarily lowered to 512 | the reader refusing | Refused, naming the size. The bound is checked on `getsize` **and** on the read itself capped at limit + 1, so a file that grows between the two is still refused. Then all **seven** real artifacts read clean: exit 0, zero stderr |

**Counting these separately is deliberate (D328).** They are eleven demonstrations of eleven controls,
and they are **not** part of the 42-probe figure in §7.3.3 or of §7.2's A3 row: those count one probe per
critical-path production module, and the executive deck quotes that number. Nothing above perturbs a
production module — S1 through S3 and S5 through S9 perturb test-side controls, S4 perturbs the guard
prologue, and S10 and S11 perturb nothing at all, because for those two the hostile input is itself the
probe. Both figures are therefore unchanged, and this table is additive evidence rather than a revision.

### 7.4 Executive deck rendering — as observed in a browser

Rule 4 asks for browser verification that every diagram and icon renders. The deck was served over HTTP
from its own directory and driven in headless Chrome 151 at a 1920×1080 viewport. Two independent
passes were made against the same bytes — one walking and capturing all 16 slides and auditing
structure, navigation and the per-slide visual census, one auditing diagram and icon rendering,
re-render idempotence, console, network and Content-Security-Policy. Each figure below was read out of
the live DOM, not inferred from the source, and each was taken after the slide compression D337 records,
so unlike the previous revision of this section it describes the deck as it ships.

**One number changed after those passes, and a further pass confirmed it.** The headline KPI moved
from `1,390` to the `1,443` this checkpoint measures — the sum of the three result streams, 1065
backend, 347 frontend and 31 browser — so the deck was reloaded cache-ignoring, twice, and re-read over
a full sixteen-slide traversal each time: the four `.kpi-value` elements of the KPI slide read `0%`,
**`1,443`**, `93%`, `42`, with `1,443` still paired to its `Tests passing now` label in card two of
four, and `1,390` appears in no markup, no attribute, no injected SVG or style content, no slide’s
painted text on any of the sixteen, and no on-disk byte — nor in un-comma’d form as `1390`. Every
structural figure in the table below re-measured identically: 16 sections, 6 of 6 diagrams each holding
exactly one rendered `<svg>` marked `data-processed`, 19 distinct icons with 0 placeholders left
unreplaced, an empty console on both loads — one of them a cold load addressed straight at the closing
slide — and 18 of 18 requests answered `200` with 0 Content-Security-Policy violations, which is also
what proves every sha384 integrity hash matched.

Two measurement traps were found while re-reading, recorded so a later automated check does not report a
false failure. There are **two** `.kpi-grid` elements, not one: the second is on the isolation slide and
holds `Live cloud` and `300s`, so an unscoped `.kpi-value` query returns six values rather than four.
And Lucide **copies** `data-lucide` onto the `<svg>` it generates, so `[data-lucide]` legitimately still
matches 19 after a successful replacement — B7’s `i[data-lucide]` element-qualified form is the reading
that means what it says.

**Re-verified at the security checkpoint**, after four slides were reworded and one diagram repaired, in
three further passes: a full 16-slide walk with viewport captures of the four edited slides, an
idempotency measurement over two away-and-back cycles, and a targeted re-read of the repaired diagram.
Every row below carries the reading from those passes. That verification is also what **found** the
diagram defect: the boundary flowchart's five edges pointed at ids the same diagram never declared, so
Mermaid invented five empty boxes and the five named layers sat disconnected — a graph contradicting the
headline above it, rendering without a single console message. Static structure passes either way, which
is the argument for rendering (D326).

| # | What was checked | Observed |
|---|---|---|
| B1 | Slide count | `Reveal.getTotalSlides()` **16**; `.reveal .slides > section` **16**; `Reveal.getSlides()` **16**, and a nested `:scope > section` query returned **0** on all sixteen, so the deck is flat and the slide index maps 1:1 to the section index |
| B2 | Every slide reachable and distinct | hash `#/0`–`#/15` each resolved to the matching index **and** the matching physical section, with `Reveal.getCurrentSlide() === sections[i]` true for all sixteen; **16 distinct, non-empty headings**, no duplicate. A cold load addressed straight at `#/8` — a diagram slide, the path the deck's own comments flag as hazardous — landed correctly with its diagram rendered and no console error |
| B3 | Runtime configuration, read back live | `hash` **true**, `controlsTutorial` **false**, `width` **1920**, `height` **1080**, `transition` `"slide"`; `Reveal.VERSION` **5.1.0**. The stage measured 1920×1080 with `Reveal.getScale()` **0.96** and `scrollWidth`/`scrollHeight` equal to the viewport, so nothing sits outside the frame |
| B4 | Mermaid diagrams rendered | **6 of 6** — on slides 2, 4, 8, 10, 12 and 14. Each `data-processed="true"` with **exactly one** `<svg>`, each carrying real graph structure and a non-zero painted box measured while its own slide was current: 1498×136, 633×451, 1498×259, 633×451, 1498×259 and 1498×153, over 99, 55, 69, 89, 113 and 69 SVG descendants respectively. The widest is slide 2's, a 1583-unit viewBox painted 1498×136 |
| B4b | The subgraph-anchored edge draws | slide 2's diagram links a **subgraph** to a node — `subgraph L["Layers"] … end` followed by `L --> G["Isolation boundary"]`. Rendered: **1** `.cluster`, **2** edge paths and **7** `.node` elements, so both edges drew, all five inner nodes exist and no phantom node was invented; **0** error-classed elements inside the svg. Visually the arrow leaves the cluster border rather than a node border. This replaced a diagram whose edges named five ids it never defined |
| B5 | No un-rendered diagram source on screen | no visible literal `flowchart` anywhere across **2,383 characters of painted text on all 16 slides**; no `error`-classed element; no `Syntax error in text`; no `mermaid version`. The only lower-case `error` in painted text is the authored node label `Lookup errors` |
| B6 | Diagram rendering is idempotent | the deck re-runs `mermaid.run()` on every `slidechanged`. Two away-and-back cycles on the slide-2 diagram gave **exactly one** `<svg>` at all five measurement points, and an identical **1498×136** box at all three of them where that slide was current; the generated `svg` id rotated on each return, so the re-render is real rather than a cached no-op, and the document-wide `pre.mermaid svg` count settled at **6**. A pixel diff of the captures taken before and after the two cycles differs in **2 of 2,073,600 pixels**, one anti-aliased step on a single arrow |
| B7 | Lucide icons rendered | `i[data-lucide]` **0** — no placeholder left unreplaced — and `svg.lucide` **19**, being all 19 expected names, no duplicate, none missing, **56** vector children between them and **none** of zero size when measured on its own slide. The sizes fall into the four classes the stylesheet defines: 142 px hero, 50 px icon row, 46 px brand lockup, 38 px KPI |
| B8 | Non-text visual on every slide | **16 of 16.** A per-slide census of diagrams, icons, KPI grids, tables and accent bars, taken while each slide was current, returned an empty list of slides with no visual; the sparsest carry one apiece — slides 2 and 12, each a full-slide diagram. The totals reconcile with the file: 6 diagrams, 19 icons, 8 accent bars, 3 tables, 2 KPI grids |
| B8b | Slide-type census | **1** `slide-title`, **6** `slide-divider`, **1** `slide-closing` and **8** unclassed content sections, summing to 16. Established twice — from the authored source, and from the live DOM with reveal's own `present`/`future`/`past` state classes stripped |
| B9 | Console | **empty at every level** across a cold load and 79 slide changes, read through two independent instruments: the DevTools console, and a 17-method in-page mirror installed before any document script ran. This is a meaningful silence — the deck runs `mermaid.run({ suppressErrors: false })` and carries explicit `console.error` handlers on its Mermaid, Lucide and layout paths, none of which fired — and it is a verified one: a deliberately CSP-violating image injected after every measurement drove the same instruments from 0 to 2 messages |
| B10 | Network | **9 of 9 requests HTTP 200**, including all three pinned CDN bundles — reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0 — the pinned `reveal.css`, and the three font faces. Each pinned bundle's `decodedBodySize` equals the byte count its sha384 declaration was taken over (52,279 / 107,670 / 2,571,838 / 355,975), each carried an `x-jsd-version` header equal to its pin, and a sha384 recomputed over the served bytes matched all four declarations. The request set was identical on a second cold load, so the deck issues no runtime fetch |
| B11 | Content-Security-Policy | **one** policy element, and **zero** `securitypolicyviolation` events across the cold load and all 79 slide changes, with the listener registered on both `document` and `window` before the policy was parsed. Both are proven live rather than assumed: the negative control drove the counter 0 → 2 with `disposition: "enforce"`. The policy is strict — `default-src 'none'` — and the deck still runs clean under it, including Mermaid's and reveal's runtime `<style>` injection and Lucide's runtime SVG generation |

**Four measurement lessons worth keeping**, because each one turns a healthy deck into a false failure:

- A single-shot `getBoundingClientRect` sweep taken from one slide reports most diagrams and icons as
  **0×0**. That is reveal.js setting `display:none` on non-adjacent slides, not a rendering
  fault — measured that way, 13 of the 19 icons read 0×0. Measure each element while its own slide
  is present, or use display-independent geometry.
- `document.querySelectorAll('[data-lucide]').length === 0` is **not** a valid success assertion for
  Lucide 0.460.0: the library copies `data-lucide` onto the `<svg>` it generates, so the selector
  matches finished icons and returns 19 on a perfectly rendered deck. The probe that means "nothing was
  left unreplaced" is `i[data-lucide]`.
- Scan **`innerText`, not `textContent`**, for leftover diagram source. `textContent` over the same
  sixteen slides returns 27,048 characters against `innerText`'s 2,383 and contains `flowchart` twelve
  times — two per diagram, inside the `<style>` blocks Mermaid injects, as the selectors
  `.flowchart-link` and `.flowchartTitleText`. None of the twelve is un-consumed source.
- The same `display:none` hazard has a text form: `document.body.innerText` read at the end of a walk
  returns only the current slide and its two neighbours — 632 of the 2,383 characters — so a
  single-shot body scan can "prove" a string absent merely because thirteen slides are invisible.
  Collect each slide's text while that slide is current.

**One capture-mode caveat.** A `fullPage` screenshot of this deck is clipped, not fuller: reveal.js
renders a fixed 1920×1080 stage and fits it with an already-computed CSS transform, and changing the
capture viewport metrics invalidates that transform — the observed result pushed slide 2's content
right and cut the fourth KPI card mid-word. Because the document's `scrollWidth`×`scrollHeight` is
exactly 1920×1080, a default viewport capture at a 1920×1080 viewport **is** the full page, and is
the faithful mode. Nothing about the deck is at fault.

**The label overflow this section previously recorded is gone.** It followed from long multi-line
Mermaid node labels under the deck's own diagram typography; after the compression D337 records, every
node label is one or two words, and both browser passes reported no clipped, overflowing or overlapping
text on any slide.

**Artifacts from the three passes.** 30 screenshots under `blitzy/screenshots/` and 3 recordings under
`blitzy/screen_recordings/` — `deck-slide-00.png` through `deck-slide-15.png` (one per slide, each
1920×1080), `deck-diagram-slide02/04/08/10/12/14.png` (one per diagram), `deck-kpi-final.png` and
`deck-architecture-final.png` from the confirmation pass, three recordings of the full sixteen-slide
walk, and six diagnostic captures including the cold-load deep link and the post-idempotence
comparison. Both directories are git-ignored, so the files exist in the working tree and are
deliberately not committed; the substance of what was seen is the table above.

### 7.5 Honesty statement

Every figure in §7.1 was observed, including the E2E line: that layer has been executed in a real
browser, so the E2E column of the panels in §6 may be filled from `e2e/reports/e2e-junit.xml` rather
than left blank. Both implementation-time browser steps in §7.2 have now been performed, so no claim in
this file is waiting on evidence that was never gathered.

Three limits remain, and none should be papered over in a summary derived from this file:

- **Only `chromium` is exercised** at the E2E layer, and the browser is a prerequisite the repository
  cannot itself provision. A green E2E run is therefore a statement about one browser family on a host
  that already had one. The same single-family caveat applies to §7.4.
- **The deck's committed evidence is a record, not an artifact set.** The 30 screenshots and 3 recordings
  the §7.4 passes produced do exist in the working tree, but `blitzy/screenshots/` and
  `blitzy/screen_recordings/` are git-ignored, so they are deliberately not committed — they are neither an AAP
  deliverable nor small. What a reader of this repository gets is the measured table above, which is the
  substance of what was seen.
- **§7.4 attests to rendering, not to editorial quality.** That every diagram draws and every icon
  resolves is a mechanical property. Whether the deck reads well to its intended audience is the
  leadership acceptance the deck itself names as the remaining step.

Four further limits, carried forward from the governance checkpoint:

- **Failure-path artifact retention was exercised only under a deliberate perturbation.** `trace:
  'retain-on-failure'`, `screenshot: 'only-on-failure'` and `video: 'retain-on-failure'` in
  `e2e/playwright.config.ts` produced a trace, a screenshot and a video for each of the four
  `isolation.spec.ts` tests that the A1b route-anchoring perturbation failed on purpose; those artifacts
  were deleted with the perturbation. The passing A1 run had no failure, so `e2e/test-results/` holds only
  `.last-run.json` after it. Read §6.5's artifact column as observed under A1b and configured under A1.
- **The CI pipeline has never run on a hosted runner.** Every figure here comes from a local invocation.
  `.github/workflows/ci.yml` is authored so that each step names a manifest and working directory that
  exist, and its `e2e` job resolves a pre-provisioned browser instead of downloading one, but no
  workflow run has exercised it. Do not present a green local run as a green pipeline — the executive
  deck states the same distinction on its enforcement slide.
- **The gate admits a narrow band below the bar.** `--cov-fail-under=90` compares a total rounded to the
  `precision` in `backend/.coveragerc`, which is 2, so any total from 89.995 upward passes and prints as
  `90.00`. §3.1 carries the same statement; it is a property of the gate, not of this run, whose measured
  total is 93.33%.
- **One dependency is pinned below its patched release.** `python-jose[cryptography]==3.3.0` is the
  version the frozen plan fixes. The exposure and the escalation are recorded in
  [`./DECISION-LOG.md`](./DECISION-LOG.md); this document does not treat it as closed.

- **Only `chromium` is exercised.** That is a limit rather than an omission: the Playwright releases that
  broaden browser support require a Node version above the ceiling this programme is pinned to, so the E2E
  evidence speaks for one engine only.

The deck verification in A2 earned its keep rather than rubber-stamping the artifact: its first pass
**failed**. One slide's diagram — the limits flowchart, newly converted from a table — parsed and rendered,
but its label lines exceeded Mermaid's 200 px wrapping width while the label wrapper computes
`white-space: nowrap`, so unwrappable text was painted across node and subgraph borders and clipped
mid-phrase at the SVG edge. The diagram was reflowed and every label line brought under that width;
re-verification measured zero overflow and zero clipping, and the untouched diagram slides re-rendered
identically, which is what bounds the change. Recorded as D221 in [`./DECISION-LOG.md`](./DECISION-LOG.md).
