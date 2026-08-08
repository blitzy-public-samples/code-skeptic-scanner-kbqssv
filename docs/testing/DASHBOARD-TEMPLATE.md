# Test Observability Dashboard — Template

**This is a template, not a report.** It defines the panels, metrics, source artifacts and
thresholds for the five-layer test suite, so that any run can be written up the same way and two
runs can be compared line by line. Cells marked `_____` are fill slots. Nothing in this document is
a live reading of the current tree; the only numbers stated as fact are the **baseline** in §1.2 and
the **verified artifact generation** in §7.1, and both are labelled as such.

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

## How to use this template

1. Run the suite for the layer you are reporting on. Each panel names the command that produces its
   artifact, and each artifact is listed in §2 with its exact path.
2. Copy this file, or the panels you need from it, into the run write-up.
3. Fill every `_____` from the **stated source artifact only**. A number typed from memory or from a
   terminal scrollback is not traceable to a run and defeats the purpose of the panel.
4. Where a panel has a *ceiling or gap?* column, resolve it against §3.3 before recording work.
   A ceiling is not a gap, and treating one as a gap drives exactly the scope expansion the
   programme forbids.
5. Carry the previous run's figures into the trend panel (§6.6) so a regression is visible rather
   than merely recorded.

Every artifact path in §2 is matched by a rule in the repository `.gitignore`, so filling this
template never adds a generated file to version control.

---

## 1. KPI header panel

### 1.1 Current run

The headline panel: seven rows covering coverage, test health, collection integrity and duration,
each with the artifact that is its only admissible source. These are the values the executive deck
lifts verbatim — keep them exact and do not round.

| # | KPI | Source artifact | Target | Value |
|---|---|---|---|---|
| K1 | Backend line coverage, gated packages (`app/core`, `app/services`, `app/tasks`, `app/db`) | `backend/coverage.xml`, or the `term-missing` summary of the gated run | **≥ 90%** | `_____` |
| K2 | Frontend coverage, gated packages (`src/store`, `src/schema`, `src/services`) — statements / branches / functions / lines | `frontend/coverage/coverage-summary.json` | **≥ 80%** on all four | `_____` |
| K3 | Backend tests: total / passed / failed / skipped | `backend/reports/junit.xml` | 0 failed | `_____` |
| K4 | Frontend tests: total / passed / failed / skipped | `frontend/reports/jest-junit.xml` | 0 failed | `_____` |
| K5 | Collection errors | `pytest --collect-only -q` exit summary | **0** | `_____` |
| K6 | E2E specs: total / passed / failed | `e2e/reports/e2e-junit.xml` | 0 failed | `_____` |
| K7 | Wall-clock duration, per layer (backend / frontend / e2e) | the `time` attribute of the root element of each JUnit artifact | no fixed target; record for trend | `_____` |

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
configuration exactly. These same paths are what the `.gitignore` rules exclude and what the CI
`e2e` job uploads, so a path that drifts in one place breaks all three.

### 2.1 Backend — produced by `backend/pytest.ini` and `pytest-cov`

Invoked from `backend/`, which is what makes `pythonpath = .` yield the single `app.*` import root.

| Artifact | Format | Produced by | Consumed by |
|---|---|---|---|
| `backend/coverage.xml` | Cobertura XML | `--cov-report=xml` | K1; the `backend`-flagged Codecov upload |
| `backend/coverage.json` | Coverage JSON | `--cov-report=json` | §6.1, §6.2 |
| `backend/coverage.lcov` | lcov tracefile | `--cov-report=lcov` | external lcov viewers |
| `backend/reports/junit.xml` | JUnit XML, `xunit2` | `--junitxml=reports/junit.xml` in `addopts`, with `junit_family = xunit2` | K3, K7, §6.3 |
| terminal summary | text | `--cov-report=term-missing` | §6.2 — this is what yields per-module **uncovered line numbers** |

Two `pytest.ini` settings shape the JUnit artifact beyond its path. `junit_logging = log` attaches
captured log records to a `<testcase>`, and `junit_log_passing_tests = false` restricts that to
failing cases, so the artifact carries the diagnostics of a failure without carrying a log section
for every passing test. Rationale in [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D82**.

### 2.2 Frontend — produced by `frontend/jest.config.js`

`<rootDir>` is `frontend/`. No `coverageDirectory` is declared, so coverage lands in Jest's default
`<rootDir>/coverage`.

| Artifact | Format | Produced by | Consumed by |
|---|---|---|---|
| `frontend/coverage/lcov.info` | lcov tracefile | the `lcov` coverage reporter | §6.2 |
| `frontend/coverage/lcov-report/` | HTML tree | the `lcov` coverage reporter | human review of §6.2 |
| `frontend/coverage/coverage-final.json` | Istanbul JSON | the **`json`** coverage reporter | the `frontend`-flagged Codecov upload |
| `frontend/coverage/coverage-summary.json` | Istanbul summary JSON | the `json-summary` reporter | K2, §6.1 — the natural KPI source |
| `frontend/coverage/cobertura-coverage.xml` | Cobertura XML | the `cobertura` reporter | Cobertura-native consumers |
| `frontend/reports/jest-junit.xml` | JUnit XML | the `jest-junit` reporter registered in `reporters`, with `outputDirectory: '<rootDir>/reports'` and `outputName: 'jest-junit.xml'` | K4, K7, §6.3 |

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

| Artifact | Format | Produced by | Consumed by |
|---|---|---|---|
| `e2e/playwright-report/` | HTML report | the `html` reporter, `outputFolder` set to this directory with `open: 'never'` | human review; uploaded as the CI `playwright-report` artifact |
| `e2e/reports/e2e-junit.xml` | JUnit XML | the `junit` reporter, `outputFile` set to this path | K6, K7, §6.3 |
| `e2e/test-results/` | traces, screenshots, video | `outputDir`, populated per the `use` block: `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'` | §6.5 |

The configured `trace` value is **`retain-on-failure`**, which captures a trace for every failing
test on its first attempt, locally as well as under CI — tracing therefore does not depend on a
retry having occurred. Determinism settings that make two runs comparable are set in the same block:
a fixed `viewport` of 1280×720, `timezoneId: 'UTC'`, `locale: 'en-US'`, and
`serviceWorkers: 'block'`.

---

## 3. Gate contract

### 3.1 The gates

| Gate | Scope | Threshold | Enforcing mechanism | Configured in |
|---|---|---|---|---|
| G1 | `backend/app/core`, `backend/app/services`, `backend/app/tasks`, `backend/app/db` | **≥ 90%** line coverage | `pytest --cov-fail-under=90`, with `--cov` scoped to those four packages | the backend test invocation; see `.github/workflows/ci.yml` |
| G2 | `frontend/src/store`, `frontend/src/schema`, `frontend/src/services` | **≥ 80%** statements, branches, functions **and** lines | Jest `coverageThreshold`, one entry per package, no global group | `frontend/jest.config.js` |
| G3 | `frontend/src/components`, `frontend/src/pages` | as high as the implemented code permits, bounded by §3.3 | measured and reported, **not** gated | `frontend/jest.config.js` (`collectCoverageFrom`) |
| G4 | Collection integrity, whole backend suite | **zero** collection errors | `pytest --collect-only -q` | `backend/pytest.ini` (`testpaths`, `pythonpath`) |

**Gates live in the runners, not in Codecov reporting.** A Codecov-only threshold annotates a pull
request but does not fail a build, so a coverage regression would merge. `--cov-fail-under` and
`coverageThreshold` both exit non-zero, which is what makes each gate binding. Codecov continues to
receive the same artifacts and remains the trend and diff view.

### 3.2 Provenance of the ≥90% figure

The 90% threshold is not an invention of this programme. It is an acceptance criterion of the
project's own proposal: `documentation/Software Project Proposal.md`, acceptance group
**`10. Testing Artifacts`** at **line 505**, whose first criterion at **line 506** requires test
coverage of at least 90% for all code. Lines **507-508** carry the group's other two criteria
(resolution of all critical and high-priority bugs, and performance tests meeting the specified
requirements), neither of which is a coverage gate.

**G1 is deliberately scoped to four packages rather than to the whole `app` tree.** Several branches
in `app/main.py` and `app/api/` cannot be executed without production changes the requirements
forbid, so a tree-wide 90% gate would fail for reasons no test can fix. Coverage of those modules is
still measured and reported — it is simply not gated. The reasoning, the alternatives and the risk
this carries are in [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D70**, and are not restated here.

### 3.3 Documented ceilings — these are not gaps

A **ceiling** is a region no test can reach without a production change the programme is not
authorized to make. A **gap** is uncovered code that a test could reach. Confusing the two turns a
correctly-bounded suite into an open work item, so resolve every uncovered region against this table
before recording it as work. Each ceiling has an assertion that stands in for it, mapped in
[`./TRACEABILITY-MATRIX.md`](./TRACEABILITY-MATRIX.md) §G.

| Ceiling | Why it is unreachable | How the suite treats it |
|---|---|---|
| `frontend/src/app.tsx` | Cannot be mounted at all: it imports a store whose reducer is invalid, imports a `setupInterceptors` symbol that is never exported, and default-imports a named-only export | Permanently 0%; excluded from `collectCoverageFrom`. See [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D71** |
| Three of the four `src/pages/*.tsx` modules | `useAppDispatch` and `useAppSelector` are imported by them but exported by nothing | Tests written, then explicitly skipped with a reason naming the missing hook |
| The tweet-rendering branch of both list components | `TweetCard` is imported by two components — one of them from itself — and defined nowhere | The current failure is asserted instead; a non-empty list yields an invalid-element-type error |
| The chart-construction branch of `src/components/Analytics` | The module imports the tree-shakeable `Chart` and never calls `Chart.register`, so construction always fails | The caught-failure path is asserted and the component stays mounted |
| The 404 branch of `GET /tweets/{tweet_id}` | An `AttributeError` fires first, because the pydantic `Tweet` declares no `id` to filter on; the response is HTTP 500 | The 500 is asserted; the unreachable 404 is documented |
| A "422 on an invalid request body" check | No implemented endpoint accepts a request body, so the check has no subject | Recorded as a gap in the register, **not** satisfied by inventing an endpoint |
| The `DOUBT_RATING_THRESHOLD` gate | The constant is declared but referenced by no production code anywhere, so the gate does not exist | The constant's value is asserted; the missing gate is recorded |
| `start_twitter_stream` beyond its failure point | Dead code: the module never imports `tweepy`, so the function always raises `NameError` | The `NameError` is asserted; the lines after it can never execute |

---

## 4. Rule 2's five mandated elements

Rule 2 (Observability) requires five things of every deliverable. All five are satisfied against the
test system, per conflict **C1** in [`./DECISION-LOG.md`](./DECISION-LOG.md) §21.

| Element | How it is satisfied | Where it is configured | Artifact evidence |
|---|---|---|---|
| **Structured logging** | `log_cli = true` at `log_cli_level = INFO`, with `log_cli_format` and `log_format` both emitting a fixed field order that includes the correlation identifier. Suites assert against production logging through `caplog` wherever production already emits it | `backend/pytest.ini` | live console output; the captured-log section of a failing `<testcase>` in `backend/reports/junit.xml` |
| **Correlation identifiers** | Backend: a `logging.setLogRecordFactory` hook puts `test_id` (the full pytest nodeid) and `correlation_id` (a stable 8-hex digest of that nodeid) on **every** log record, including records from production code and third-party libraries; the same nodeid is the `classname` and `name` pair of the matching `<testcase>`. Because the identifier is a digest rather than a counter, the same test yields the same id on every run and on every machine, which is what makes two runs comparable line by line. Frontend: `jest-junit` templates derive `classname` from the test file path, normalized to forward slashes, and `name` from the enclosing describe titles plus the leaf title — the same identity that is stamped on every intercepted request. E2E: the spec and test title name the per-test artifact directory. Decisions in [`./DECISION-LOG.md`](./DECISION-LOG.md) §8, rows **D80**, **D81** and **D83** | `backend/pytest.ini` plus `backend/tests/conftest.py`; the `reporters` block of `frontend/jest.config.js`; `e2e/playwright.config.ts` | `backend/reports/junit.xml`; `frontend/reports/jest-junit.xml`; the per-test subdirectories of `e2e/test-results/` |
| **Distributed tracing across service boundaries** | Playwright tracing at `retain-on-failure`, with `screenshot: 'only-on-failure'` and `video: 'retain-on-failure'`, giving a request-level trace of the browser-to-API boundary with timing per intercepted request. Stated honestly: the E2E layer is the **only** place in this repository where a request genuinely crosses a process boundary, so it is the only place a trace has anything to span | `e2e/playwright.config.ts` (`use`) | `e2e/test-results/` |
| **Metrics endpoint** | The coverage and JUnit artifacts in §2 **are** the metrics surface, consumed by the two Codecov upload steps that already existed in the workflow. **No production metrics endpoint is added** — doing so would be an unauthorized production change and the implementation of a missing product feature. See [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D193** | `backend/pytest.ini`, `frontend/jest.config.js`, `e2e/playwright.config.ts` | every artifact listed in §2 |
| **Health / readiness checks** | `pytest --collect-only -q` reporting zero errors. This is the meaningful readiness check for this suite specifically: its inherited failure mode was **collection errors** — three modules that never reached an assertion — so a gate proving every module imports is the check that would have caught the original state, in a way a passing-test count would not. Recommended as a first-class CI panel, not an afterthought; see §6.4 and [`./DECISION-LOG.md`](./DECISION-LOG.md) row **D72** | `backend/pytest.ini` (`pythonpath`, `testpaths`) | the command's own exit status and summary line |
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
  runs in its own working directory. **Both flag names stay exactly as they were**, `backend` and
  `frontend`. Preserving the flags is the whole point: a renamed flag starts a new series in Codecov
  and silently discards the project's historical continuity, so the repoint is a path correction
  only.
- **The single `build` job.** Unit and integration work stays in the job that already exists rather
  than being split across new jobs.
- **The runtime matrix, lines 15-16** — `python-version: [3.9]` and `node-version: [16.x]`. This is
  the authoritative source of the documented runtime ceilings, and every version pin in the test
  stack was selected to satisfy it.

### 5.2 ADDED — gaps filled with framework-appropriate tooling

- **JUnit XML on all three layers**, which none of them emitted before: `--junitxml` with
  `junit_family = xunit2` on the backend, the `jest-junit` reporter on the frontend, and Playwright's
  `junit` reporter for E2E. This is what makes test health machine-readable at all.
- **Correlation identifiers on log records and result records**, described in §4.
- **The additional coverage reporters.** The workflow previously expected a single Cobertura file;
  the suites now also emit `json`, `json-summary`, `lcov` and `text-summary`, which is what allows
  the KPI panel to be filled from a summary file rather than scraped from console output.
- **The `--collect-only` collectability gate** (§6.4), which had no equivalent.
- **Runner-enforced thresholds** — `--cov-fail-under` and Jest `coverageThreshold` — so a coverage
  regression fails a build rather than merely annotating it.
- **The new `e2e` job**, and its upload of `e2e/playwright-report/` as a CI artifact.

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
nothing else.

### 6.1 Coverage by gated package

> **How to fill:** backend rows from `backend/coverage.xml` (or the `term-missing` summary of the
> gated run); frontend rows from `frontend/coverage/coverage-summary.json`. Record `PASS` only if the
> runner exited zero — the gate's own verdict, not your reading of the percentage.

| Package | Gate | Threshold | Measured | Pass / Fail | Source artifact |
|---|---|---|---|---|---|
| `backend/app/core` | G1 | ≥ 90% lines | `_____` | `_____` | `backend/coverage.xml` |
| `backend/app/services` | G1 | ≥ 90% lines | `_____` | `_____` | `backend/coverage.xml` |
| `backend/app/tasks` | G1 | ≥ 90% lines | `_____` | `_____` | `backend/coverage.xml` |
| `backend/app/db` | G1 | ≥ 90% lines | `_____` | `_____` | `backend/coverage.xml` |
| `frontend/src/store` | G2 | ≥ 80% all four | `_____` | `_____` | `frontend/coverage/coverage-summary.json` |
| `frontend/src/schema` | G2 | ≥ 80% all four | `_____` | `_____` | `frontend/coverage/coverage-summary.json` |
| `frontend/src/services` | G2 | ≥ 80% all four | `_____` | `_____` | `frontend/coverage/coverage-summary.json` |
| `frontend/src/components` | G3 | reported, not gated | `_____` | n/a | `frontend/coverage/coverage-summary.json` |
| `frontend/src/pages` | G3 | reported, not gated | `_____` | n/a | `frontend/coverage/coverage-summary.json` |

### 6.2 Coverage by module

> **How to fill:** backend rows from the `--cov-report=term-missing` output, whose `Missing` column
> **is** the uncovered-line list; frontend rows from `frontend/coverage/coverage-summary.json` for
> the percentages and `frontend/coverage/lcov.info` (or the `lcov-report/` HTML) for the uncovered
> lines. Resolve the last column against §3.3 **before** recording anything as work.

| Module | Statements | Branches | Functions | Lines | Uncovered lines | Ceiling or gap? |
|---|---|---|---|---|---|---|
| `_____` | `_____` | `_____` | `_____` | `_____` | `_____` | `_____` |

Add one row per module. A module whose uncovered region is entirely accounted for in §3.3 is
recorded as **ceiling** and carries no follow-up; anything else is a **gap** and belongs in the next
increment.

### 6.3 Test health by layer

> **How to fill:** one row per layer, read from the root element of that layer's JUnit artifact —
> `tests`, `failures`, `errors`, `skipped` and `time` attributes. Do not total the layers by hand
> when the artifact already reports it.

| Layer | Total | Passed | Failed | Skipped | Duration | JUnit artifact |
|---|---|---|---|---|---|---|
| Backend unit | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Backend integration | `_____` | `_____` | `_____` | `_____` | `_____` | `backend/reports/junit.xml` |
| Frontend unit | `_____` | `_____` | `_____` | `_____` | `_____` | `frontend/reports/jest-junit.xml` |
| Frontend component | `_____` | `_____` | `_____` | `_____` | `_____` | `frontend/reports/jest-junit.xml` |
| End-to-end | `_____` | `_____` | `_____` | `_____` | `_____` | `e2e/reports/e2e-junit.xml` |

**Skip register.** Every skip in this suite names an unimplemented production feature, so a skip is a
record rather than a silence and must be reproduced with its reason. A skip whose reason does not
name such a feature is a defect in the test, not a documented limitation.

| Skipped test | Reason as stated in the code | Unimplemented feature it names |
|---|---|---|
| `_____` | `_____` | `_____` |

### 6.4 Collection integrity

> **How to fill:** run the command and record the summary line and the exit status. This is the
> readiness gate of §4; treat a non-zero error count as a build failure, because a module that does
> not import cannot be asserted against at all.

| Check | Command | Expected | Actual | Pass / Fail |
|---|---|---|---|---|
| Backend collection errors | `pytest --collect-only -q`, from `backend/` | **0 errors** | `_____` | `_____` |
| Tests collected | same command | matches the total in §6.3 | `_____` | `_____` |

### 6.5 E2E flow status

> **How to fill:** results from `e2e/reports/e2e-junit.xml`; artifact paths from the per-test
> subdirectories of `e2e/test-results/`, which are named after the spec and test title. A passing
> test legitimately has no trace, screenshot or video — all three are retained on failure only.

| Spec | Route under test | Result | Trace / screenshot / video |
|---|---|---|---|
| `dashboard.spec.ts` | `/` | `_____` | `_____` |
| `tweets.spec.ts` | `/tweets` | `_____` | `_____` |
| `analytics.spec.ts` | `/analytics` | `_____` | `_____` |
| `configuration.spec.ts` | `/configuration` | `_____` | `_____` |

The four rows are the route inventory the programme covers. Add a row for any spec added later, so
the panel stays a census of the E2E layer rather than a sample of it.

### 6.6 Trend row

> **How to fill:** carry the previous run's write-up into the *Previous* column before filling
> *Current* from this run's artifacts, then set *Delta* from the two. A regression that is recorded
> but not compared is a regression nobody notices.

| Metric | Previous | Current | Delta | Verdict |
|---|---|---|---|---|
| Backend gated coverage (K1) | `_____` | `_____` | `_____` | `_____` |
| Frontend gated coverage (K2) | `_____` | `_____` | `_____` | `_____` |
| Total tests, all layers | `_____` | `_____` | `_____` | `_____` |
| Failures, all layers | `_____` | `_____` | `_____` | `_____` |
| Skips, all layers | `_____` | `_____` | `_____` | `_____` |
| Collection errors (K5) | `_____` | `_____` | `_____` | `_____` |
| Total wall-clock duration (K7) | `_____` | `_____` | `_____` | `_____` |

A rising skip count with a steady failure count is the pattern most easily missed, and it is why
skips are tracked here alongside failures rather than folded into a pass rate.

---

## 7. Local verification status

Rule 2 holds that observability which cannot be exercised locally is not delivered. This section is
the honest accounting that clause requires: what was actually produced and observed, separated from
what remains to be demonstrated.

### 7.1 Verified generated

Each item below was produced and inspected during analysis on the documented runtimes.

| Evidence | What was observed |
|---|---|
| Backend artifacts | `backend/reports/junit.xml` plus the Cobertura, JSON and lcov coverage files, all generated by a 16-test demonstration suite passing at **68%** coverage on CPython 3.9.25 |
| Frontend artifacts | `frontend/reports/jest-junit.xml` and all five configured coverage reporters, generated by a demonstration suite passing on Node 16.20.2 and measuring **80.24%** statements on the ≥80% target scope |
| E2E harness | All four routes served, with an error-free dev-server log, under Vite 4.5.14 |

### 7.2 Implementation-time acceptance steps — not yet performed

These are outstanding. They are listed here rather than quietly omitted, because an unexercised
check is not a delivered one.

| # | Outstanding step | Why it could not be completed |
|---|---|---|
| A1 | Execute the Playwright suite in a real browser and confirm that `e2e/test-results/` is populated with a trace, a screenshot and a video on an induced failure | The browser automation subagent was unavailable, and provisioning a browser requires network access and system packages |
| A2 | Render `blitzy-deck/executive-summary.html` in a browser and confirm its diagrams, icons and section count | Same unavailability |
| A3 | Demonstrate the negative validations — perturb a threshold or a return value locally, confirm the corresponding test fails, then restore it — and record the exercise | Deferred to implementation time; the perturbation must never be committed |

### 7.3 Honesty statement

**No claim in this document rests on browser evidence.** The E2E tracing described in §2.3 and §4 is
a statement about what `e2e/playwright.config.ts` is configured to produce, not a report of a trace
that was observed in a browser. Until A1 is performed, treat the E2E column of every panel as
unfilled rather than as passing, and do not present the E2E layer as verified in any summary derived
from this file — including the executive deck.
