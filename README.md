# Code Skeptic Scanner

Code Skeptic Scanner is an advanced static code analysis tool designed to identify potential security vulnerabilities, code smells, and best practice violations in your codebase. It provides developers with actionable insights to improve code quality and security.

## Features

- Multi-language support (Python, JavaScript, Java, and more)
- Customizable rule sets
- Integration with popular CI/CD platforms
- Detailed reports with severity levels and remediation suggestions
- API for seamless integration with other tools
- Real-time scanning capabilities

## Technology Stack

- Python 3.8+
- FastAPI
- SQLAlchemy
- PostgreSQL
- Docker
- Redis (for caching)

## Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose
- PostgreSQL 12 or higher
- Git

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/your-org/code-skeptic-scanner.git
   cd code-skeptic-scanner
   ```

2. Set up a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up the database:
   ```
   docker-compose up -d postgres
   alembic upgrade head
   ```

5. Start the application:
   ```
   uvicorn app.main:app --reload
   ```

## Configuration

1. Copy the example environment file:
   ```
   cp .env.example .env
   ```

2. Edit the `.env` file with your specific configuration settings.

## Usage

1. To scan a local project:
   ```
   python -m code_skeptic_scanner scan /path/to/your/project
   ```

2. To start the API server:
   ```
   python -m code_skeptic_scanner serve
   ```

3. Access the web interface at `http://localhost:8000`

## API Documentation

API documentation is available at `http://localhost:8000/docs` when the server is running.

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for more details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact Information

For support or queries, please contact us at:
- Email: support@codeskepticscanner.com
- Twitter: @CodeSkepticScan
- GitHub Issues: https://github.com/your-org/code-skeptic-scanner/issues

## Testing

This repository now has an executable test suite arranged in five layers: backend unit, backend integration, frontend unit, frontend component, and end-to-end. The suites assert the behaviour the code exhibits **today**, which in several places diverges from the design documents under `documentation/`. Where the two disagree the test encodes the observed behaviour, and the divergence is recorded rather than silently reconciled.

### Runtime prerequisites

| Runtime | Version | Source of truth |
| --- | --- | --- |
| Python | 3.9 | `.github/workflows/ci.yml` — `python-version: [3.9]` |
| Node.js | 16.x | `.github/workflows/ci.yml` — `node-version: [16.x]` |

The "Python 3.8 or higher" line in the Prerequisites section above is a lower bound only. 3.9 is the version the test stack is pinned and verified against, so use 3.9 to run the suites.

### Install

Three independent legs, each non-interactive and each runnable on a clean machine. Every command below is written to run **from the repository root**, so you can paste the block as-is without tracking which directory you are left in.

Order matters between legs 2 and 3: the e2e harness aliases ten bare specifiers into `frontend/node_modules` — and forces five of them, React among them, to resolve to exactly one copy — so install `frontend` first.

```bash
# POSIX shells
# 1. Backend - virtual environment plus the pinned test stack
python3.9 -m venv .venv-backend && . .venv-backend/bin/activate && pip install --upgrade pip && pip install -r backend/requirements-dev.txt

# 2. Frontend - a prerequisite of leg 3, not just of the Jest suite
(cd frontend && npm install)

# 3. End-to-end - install `frontend` FIRST (the harness resolves ten packages out of
#    frontend/node_modules); this installs the runner only and does NOT download a browser
(cd e2e && npm install)
```

```powershell
# PowerShell - only leg 1 differs; a venv on Windows has Scripts\, not bin/
py -3.9 -m venv .venv-backend
.\.venv-backend\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt
Push-Location frontend; npm install; Pop-Location
Push-Location e2e; npm install; Pop-Location
```

Every `pytest` command below assumes that environment is **active**. If you would rather not activate it,
call the interpreter directly — `..\.venv-backend\Scripts\python.exe -m pytest` from `backend\`, or
`../.venv-backend/bin/python -m pytest` on a POSIX shell — which is equivalent and is what a
non-interactive script should do.

- **The parentheses are load-bearing.** Each `cd` happens in a subshell, so the next command still starts at the repository root and the block pastes as one unit. They are also not optional: `npm install` reads the manifest of the *current* directory and **`--prefix` does not change that**, in either position. This repository has no root `package.json`, so both `npm --prefix frontend install` and `npm install --prefix frontend` fail with `ENOENT ... open .../package.json`. Entering the directory is the only form that works, in either shell - `Push-Location`/`Pop-Location` plays the subshell's part in PowerShell, which has no `( ... )` grouping of its own. (`npm --prefix <dir> run <script>` is different — it *does* read the target's manifest, and it is what the run table below uses.)
- Use `npm install`, **not** `npm ci`. No lockfile is committed in this repository, and `npm ci` refuses to run without one.
- **Pinning differs by stack, so do not assume either behaviour from the other.** `backend/requirements-dev.txt` is exact-pinned throughout: all **25** active lines are `==` — 7 test-stack distributions and 18 of the runtime stack the tests exercise — and `backend/tests/test_dependency_closure.py` fails if any one of them is not. `frontend/package.json` is a partition: the **11** devDependencies this testing work introduced are exact-pinned, and the **17** pre-existing declarations — 7 runtime dependencies and 10 development ones — are deliberately left at the caret ranges the baseline shipped, because the change boundary for that file is devDependencies and test scripts only. `frontend/src/test-utils/dependency-closure.test.ts` enforces both halves: exact pins on the first set, byte-identical specifiers on the second. `e2e/package.json` is exact-pinned throughout. Several versions are deliberately held below their latest release. See [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) for why those versions and the lockfile posture were chosen.

### Provisioning a browser for the end-to-end suite

**Nothing in this repository downloads a browser, and that is deliberate.** `playwright install` does not
verify the TLS chain of the host it fetches from (CVE-2025-59288), and the fix release requires a Node major
version this project does not declare, so the download was removed from every automated path instead: there is
no `install:browsers` script, the pinned `@playwright/test` 1.44.1 package declares no install script of its
own, and the CI workflow resolves a browser the runner image already provides rather than fetching one.

Provision Chromium or Chrome yourself from an artifact you have verified out of band, then point the suite at
it. On a machine that already has Google Chrome, that is the whole step:

```bash
# POSIX shells
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/google-chrome
```

```powershell
# PowerShell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Then let the gate decide whether a run can proceed. It fetches nothing:

```bash
cd e2e && npm run browsers:require
```

**`browsers:require` is the gate; `browsers:verify` is a narrower reporter over the same provision.**
Neither downloads anything, and both exit non-zero when no launchable browser is found — the difference is
what they look at:

| Script | Looks at | Publishes | Use it to |
| --- | --- | --- | --- |
| `browsers:require` | `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, then `CHROME_BIN`, then the platform's vendor install locations, then the exact path `chromium.executablePath()` reports for this pin — first hit wins | prints the route, the absolute path and the resolved build's own version, and writes `PLAYWRIGHT_CHROMIUM_EXECUTABLE=<path>` to `$GITHUB_ENV` when that variable is set | decide whether a run can proceed. Accepts `--min-major <n>` to refuse a build older than `n` |
| `browsers:verify` | an explicit `PLAYWRIGHT_CHROMIUM_EXECUTABLE` and, only if unset, the same cache path | nothing | see what a run *without* an explicit executable would load |

Neither runs `playwright install --dry-run chromium`, which is what `browsers:verify` used to be: that
command prints the location it *would* use and exits **0 whether or not anything is there**, so a pipeline
running it looked green while every test was about to fail at launch.

Either way the executable you name is what the run launches: `e2e/playwright.config.ts` passes
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` through as `launchOptions.executablePath`.

The gate does more than find a file: on success `npm run browsers:require` prints the **canonical** path and its SHA-256 and publishes both, and `npm run browsers:verify` fails when the executable no longer matches a published digest — so the browser a later step launches is provably the one that was validated.

Without a browser, every end-to-end test fails identically at launch with
`browserType.launch: Executable doesn't exist at <path>` — a clear message rather than a silent,
unverified fetch. The `e2e` job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) hardcodes no
path: it sets a minimum major version, runs the gate with it, and runs the reporter against whatever the
gate published. [`e2e/README.md`](e2e/README.md) covers every route in full, and
[`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) rows `D111`, `D257`, and `D264` as
superseded by `D300`, `D301` and `D319`, record why.

If you are running several clones of this repository in parallel, set `CLONE_INDEX` so each harness gets
its own port (`4173 + CLONE_INDEX`).

### Run

Run every backend command from `backend/`, so that `backend/pytest.ini` is the configuration file pytest loads. A **bare** `pytest` from the repository root fails in a way that is easy to misread, and worth stating precisely because the failure does not look like a configuration problem:

- Collection **succeeds** — all 1150 tests are collected, and imports resolve, because pytest inserts each test file's rootdir on `sys.path` regardless.
- But `rootdir` becomes the repository root and **no `configfile` is loaded**, so `asyncio_mode = auto` is off. pytest reports `asyncio: mode=strict`, and every `async def` test errors for want of a decorator: **21 failed, 1126 passed, 3 skipped** — 21 + 1126 + 3 = 1150, the collected total above, so nothing is missing from the run, only mis-configured within it. The `filterwarnings` entries are not applied either, so the same run is noisy with warnings a `cd backend` run suppresses. Both figures assume the retained artifact set is present, as every count in this README does; a clone that has not produced one yet reports the two artifact-dependent cases as skips rather than passes.

So a root run produces a plausible-looking collection followed by 21 failures that say nothing about the code under test. Passing an explicit path — `pytest backend/tests` — *does* find the ini, because pytest walks up from the argument, and it therefore also inherits `addopts`; be aware that `--junitxml=reports/junit.xml` resolves against the directory you invoked from, so this form writes `reports/junit.xml` at the **repository root**, where `.gitignore` does not match it and it dirties `git status`. Delete it afterwards, or pass an explicit `--junitxml` of your own. The reliable habit is simply to `cd backend` first, which is what every command below assumes and what CI does through `working-directory: backend`.

| Goal | Command |
| --- | --- |
| Backend, all layers | `cd backend && pytest` |
| Backend coverage, the gate, **and every report** | the two-command block below |
| Backend unit layer only | `cd backend && pytest tests/unit -m unit` |
| Backend integration layer only | `cd backend && pytest tests/integration -m integration` |
| Frontend, all suites | `cd frontend && npm test` |
| Frontend, watch mode | `cd frontend && npm run test:watch` |
| Frontend, coverage | `cd frontend && npm run test:coverage` |
| Frontend, CI mode | `cd frontend && npm run test:ci` |
| End-to-end | `cd e2e && npm test` |
| End-to-end, list without running | `cd e2e && npm run test:list` |
| End-to-end report | `cd e2e && npm run report` |
| End-to-end browser gate, fetches nothing | `cd e2e && npm run browsers:require` |
| End-to-end browser report, fetches nothing | `cd e2e && npm run browsers:verify` |

**The canonical backend command.** One block produces every backend artifact *and* applies both halves
of the gate, and it is byte-for-byte what CI runs. Use it whenever a figure will be quoted or a
dashboard filled — the `--cov` scoping *is* the denominator the 90% bar is calibrated against, so a
`coverage.xml` written by a wider run cannot be told apart from a gated one afterwards:

```bash
cd backend
pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db \
       --cov-report=term-missing --cov-report=xml --cov-report=json \
       --cov-precision=2 --cov-fail-under=90 --junitxml=reports/junit.xml
python tests/coverage_gate.py --coverage-json coverage.json --fail-under 90 \
       --require-scope app/core --require-scope app/services \
       --require-scope app/tasks --require-scope app/db | tee reports/coverage-gate.txt
```

A whole-tree measurement — `pytest --cov=app …` — is still worth running to find where the unreachable
branches are, and [`backend/tests/README.md`](backend/tests/README.md) §8 has it. It is not a producer
for the dashboard: the second command above **refuses** a report whose measured files fall outside the
four gated packages.

Every end-to-end command runs from `e2e/` through that package's own scripts, so the runner is the pinned
`e2e/node_modules/.bin/playwright` and the configuration is the one beside it. Do not invoke `npx playwright`
from the repository root: there is no root manifest and no root `node_modules`, so `npx` would fetch an
unpinned runner from the registry.

The three suites report **1147 passed / 3 reasoned skips** on the backend, **359 passed / 24 reasoned skips across 24 suites** on the frontend, and **31 passed / no skip across 5 spec files** end to end. The collection-integrity gate expects **zero errors**. It is the meaningful readiness check here, because this suite's historical failure mode was import errors rather than failed assertions: a clean collection proves every test module is importable before any assertion is evaluated.

**The backend figure above is a warm one, and the very first run in a fresh clone reports 1145 passed and 5 skipped on a first pass instead — which is correct, not a failure.** Two tests read an artifact a *previous* run wrote, and both artifacts are gitignored, so neither exists until something has produced them: `backend/tests/test_coverage_gate.py` reads `backend/coverage.json`, written by the gated command below, and `backend/tests/test_docs_contract.py` reads `e2e/reports/e2e-junit.xml`, written by the end-to-end suite. Each skips with a reason naming the artifact rather than failing on its absence. Run the gated backend command and the end-to-end suite once and every subsequent run reports 1147/3. Either way the collected total is 1150 and nothing fails; the difference is only which two of those cases can be evaluated yet.

Use `npm test` for the end-to-end suite rather than `npx playwright test`. Both resolve the pinned local
runner from inside `e2e/`, but `npx` is online-capable by design, and a script that names the binary fails
closed instead. The same command is what CI runs.

### Readiness checks

Four commands prove the suites can be *collected and loaded* before any assertion is evaluated. This matters
here more than it usually would: the failure mode this repository inherited was import errors — three
legacy test modules that never reached an assertion — so a clean collection is the check that would have
caught the original state, in a way a passing-test count would not.

**Discovery and readiness are different checks on the frontend, and both are listed.** Discovery names the
files a run would pick up; readiness proves each one loads. Measured against a module carrying an
unresolvable import: `test:list` exited 0 and `test:load` exited 1.

| Layer | Command | Expects |
| --- | --- | --- |
| Backend | `cd backend && pytest --collect-only -q --junitxml=reports/collect-only-junit.xml` | **zero errors** |
| Frontend, discovery | `cd frontend && npm run test:list` | every collectable test file listed, exit 0; imports nothing |
| Frontend, readiness | `cd frontend && npm run test:load` | every listed module loaded and transformed, 0 failed, 0 test bodies run, exit 0 |
| End-to-end | `cd e2e && npm run test:list` | every test listed, exit 0; launches no browser |

**The readiness check loads the suites; the discovery check merely lists them, and that is why both are
run.** `npm run test:list` (`jest --listTests`) walks the filesystem against `testMatch` and imports
nothing, so a suite with a broken import or a failing transformer is listed exactly like a healthy one —
measured: with one unresolvable import added it still listed all 24 files and exited **0**. `npm run
test:load` is
`jest --ci --watchAll=false --runInBand --reporters=default -t "__readiness_probe_that_matches_no_test__"`;
Jest can only know a test's name after transforming the file, evaluating it at module scope and running its
`describe` callbacks, so it loads every suite and every module in their import graphs, registers every test
identity, runs zero test bodies, and on that same perturbation exits **1** naming the suite. `--reporters=default`
is there because the probe is a real Jest run: without it the configured `jest-junit` reporter would write an
all-skipped stream over `frontend/reports/jest-junit.xml`, and a later reader could not tell that from a run in
which everything was skipped.

**All four are automated CI steps, not just local commands.** `.github/workflows/ci.yml` runs each as its
own step ahead of the corresponding suite and captures its summary to `backend/reports/collect-only.txt`,
`frontend/reports/list-tests.txt`, `frontend/reports/load-tests.txt` and `e2e/reports/list-tests.txt`, all
four retained as CI artifacts.
The dashboard's extractor reads those files, so a readiness result is auditable after the run rather than
scrolled past in a log. Rationale in
[`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) row `D255`.

**Locally, the commands above print to the terminal and leave nothing behind.** The extractor needs the
files, so redirect them — these are the same commands CI runs, with the same redirection, and they
**create** the four artifacts `dashboard-extract.py --require-all` requires:

```bash
# POSIX shells
mkdir -p backend/reports frontend/reports e2e/reports
(cd backend  && pytest --collect-only -q --junitxml=reports/collect-only-junit.xml \
                  | tee reports/collect-only.txt)
(cd frontend && npm run --silent test:list      | tee reports/list-tests.txt)
(cd frontend && npm run --silent test:load 2>&1 | tee reports/load-tests.txt)
(cd e2e      && npm run --silent test:list      | tee reports/list-tests.txt)
```

```powershell
# PowerShell
New-Item -ItemType Directory -Force backend\reports, frontend\reports, e2e\reports | Out-Null
cd backend;  cmd /c "pytest --collect-only -q --junitxml=reports/collect-only-junit.xml 2>&1" | Tee-Object reports\collect-only.txt; cd ..
cd frontend; cmd /c "npm run --silent test:list 2>&1" | Tee-Object reports\list-tests.txt;   cd ..
cd frontend; cmd /c "npm run --silent test:load 2>&1" | Tee-Object reports\load-tests.txt;   cd ..
cd e2e;      cmd /c "npm run --silent test:list 2>&1" | Tee-Object reports\list-tests.txt;   cd ..
```

`cmd /c "… 2>&1"` rather than a bare `2>&1` on PowerShell: PowerShell turns a native command's stderr
into `ErrorRecord` objects that `Tee-Object` reformats, and Jest writes its whole summary to stderr.
Letting `cmd` merge the streams keeps the retained file identical to what the terminal showed, and
`$LASTEXITCODE` still carries the status. `Tee-Object` on PowerShell 5.1 writes **UTF-16LE** and takes
no `-Encoding`; the extractor decodes by byte-order mark, so that is harmless here, but it is why a
tool that assumed UTF-8 would report these artifacts as missing. The full local sequence,
including the suites and the extractor, is at the top of
[`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md).

Two of the four would overwrite the run report they sit beside, which is why the step order matters:
`pytest --collect-only` and `playwright test --list` both write their configured reporters, so either can
leave a zero-case stub exactly where a result stream belongs. CI runs readiness *before* each suite, two
verification steps reject a zero-case stream outright, and the extractor refuses one rather than rendering
it as zeros (`D254`, `D258`); `e2e`'s `test:list` script additionally pins `--reporter=line`. The frontend
probe is a real Jest run and would have had the same defect, so `test:load` pins `--reporters=default`
instead — verified by hashing `frontend/reports/jest-junit.xml` either side of a probe.

The backend probe now carries its own neutraliser as well, which is why the command above repeats
`--junitxml`: the value given on the command line wins over the one `backend/pytest.ini` puts in `addopts`,
so the probe writes `backend/reports/collect-only-junit.xml` and leaves the run's stream alone. A zero-case
stub was never the only way that stream could be wrong, though — a **partial** run leaves a non-zero count
that no presence check can tell from a full one. So the stream's case count is required to equal the
collected count this readiness step records, in the extractor and in CI's verify step, and a difference
names both figures instead of publishing the smaller one (`D355`).

### Coverage gates

| Scope | Gate | Enforced by |
| --- | --- | --- |
| `backend/app/core`, `backend/app/services`, `backend/app/tasks`, `backend/app/db` — **one** gate over their aggregate | ≥90% line coverage, compared **exactly** | `pytest --cov-fail-under=90` for the in-run message, then `backend/tests/coverage_gate.py` for the binding comparison |
| `frontend/src/store`, `frontend/src/schema`, `frontend/src/services` — **three** independent groups, so **twelve** independent comparisons | ≥80% statements, branches, functions and lines | Jest `coverageThreshold` in `frontend/jest.config.js` |
| Every frontend suite loads | **zero** suites that fail to load | `npm run test:load`, run as its own CI step ahead of `test:ci` |

The gates live in the runners, not only in Codecov, so a shortfall fails the command that produced it. The ≥90% figure traces to `documentation/Software Project Proposal.md`, acceptance group 10 ("Testing Artifacts", lines 505–508). The backend gate is scoped to those four packages rather than the whole `app` tree because some branches are provably unreachable; see [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) for that reasoning, and [`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md) for measured figures.

**`--cov-fail-under` cannot mean >=90% on its own, at any setting.** coverage.py compares
`round(total, precision)` against the threshold, so there is always a band of sub-threshold totals that
round up and pass. At the library default of **0** decimals, pytest-cov's message — which uses the
unrounded value — printed `FAIL` while the run exited 0. Measured on this tree, where the whole `app`
tree sits at 90.97%: `pytest --cov=app --cov-precision=0 --cov-fail-under=91` prints
`FAIL Required test coverage of 91% not reached. Total coverage: 90.97%` and **exits 0**, because 90.97
rounds to 91. `backend/.coveragerc` sets `precision = 2`, and the same command without
`--cov-precision=0` exits **1** with
`ERROR: Coverage failure: total of 90.97 is less than fail-under=91.00` — which makes the printed number
agree with the exit status, and is why every backend percentage here is reported to two decimals. But two
decimals still admit `[89.995, 90)`, and no finite precision closes that band.

So the binding comparison is a second command, `backend/tests/coverage_gate.py`, run immediately after
the suite. It reads the integer counts out of `coverage.json` and compares
`covered * 100 >= 90 * statements` as exact rational arithmetic, and it refuses a report measured over
the wrong scope. Measured on this tree: `182 of 195 statements covered = 93.3333% exact, threshold 90%
-> coverage gate PASSED`; at `--fail-under 93.34` it exits **1** printing the comparison it performed;
on a genuine whole-`app` report (262/288 = 90.9722%) it exits **1** naming all eight out-of-scope
files; with no report it exits **2**, a distinct status because nothing-measured is not the same
failure as measured-low. `backend/tests/test_coverage_gate.py` asserts all of it, including three
totals — 89.995%, 89.9999% and 89.99999% — that the rounded comparison admits and the exact gate
refuses. Recorded in [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md); the mechanism is
written up in [`backend/tests/README.md`](backend/tests/README.md) §9.

The backend gate is **one** comparison over a single total, so a package inside it can sit below 90% while
the gate passes. That is visible rather than hidden: the per-package figures are reported in
[`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md) §6.1 and labelled as
measurements without verdicts of their own.

#### Where the two numbers above came from

Both are measurements, not targets, so they carry their origin. Re-derive them before quoting them on any
later commit — a figure that outlives the tree it was measured on is a claim, not evidence.

| | |
| --- | --- |
| Commands | `cd backend && pytest --cov=app --cov-fail-under=90` for the 90.97% whole-tree figure; `cd backend && pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-fail-under=90` for the 93.33% gated figure |
| Runner | `pytest` 8.4.2, `pytest-cov` 6.1.1, `coverage` 7.10.7, from `backend/requirements-dev.txt` |
| Runtime | CPython 3.9.13 in `.venv-backend`, Windows |
| Commit | Recorded by the tooling rather than typed here: `python docs/testing/dashboard-extract.py` prints the branch and commit of the tree it read in its §1.0 block, so a figure and the tree it came from travel together. A hash written into prose necessarily names an older tree than the run it describes, and an earlier revision of this file proved it by citing a commit that is not a git object in this repository |
| Artifacts | `backend/coverage.xml` (aggregate), `backend/coverage.json` (per-package and per-module), `backend/reports/junit.xml` |
| Retention | Local-only as run above. The equivalent CI step retains all three — see [Reporting artifacts](#reporting-artifacts) |

Every other measured figure in this repository lives in one of four places, each with the same provenance
block rather than a bare number: [`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md)
§6 and §7 for the cross-layer view, [`backend/tests/README.md`](backend/tests/README.md) for the backend,
[`frontend/TESTING.md`](frontend/TESTING.md) for the frontend, and
[`e2e/README.md`](e2e/README.md) §8 for the browser layer.

### Where the tests live

| Path | Contents |
| --- | --- |
| `backend/tests/unit/` | 12 modules mirroring the `app/` layout. Not one per production module: `test_schema.py` covers both schema modules, and `app/main.py` and `app/api/routes/` are covered from `integration/` instead. `docs/testing/TRACEABILITY-MATRIX.md` §I names the covering artifact for each of the 14 |
| `backend/tests/integration/` | The FastAPI HTTP surface, driven through Starlette's `TestClient` |
| `backend/tests/` | Five suite-level guards that belong to no layer, and whose subjects are this repository rather than `app/`: `test_dependency_closure.py` (the pip manifest), `test_coverage_gate.py` (the `precision` the gate compares at), `test_guard_contract.py` (the conftest credential, egress and child-process guards), `test_dashboard_extract.py` (the dashboard producer) and `test_docs_contract.py` (the arithmetic the Rule 1 and Rule 2 documents state) — plus `coverage_gate.py`, the exact gate itself, a module CI runs after the suite rather than a test |
| `backend/tests/conftest.py` | Shared fixtures, environment seeding, credential neutralizer, egress guard |
| `backend/tests/factories.py` | Deterministic payload and duck-object builders |
| `frontend/src/**/*.test.ts(x)` | Colocated beside the module under test |
| `frontend/src/test-utils/` | Render helper, factories, msw server and handlers, module stubs |
| `e2e/tests/*.spec.ts` | Route flows driven against the harness in `e2e/harness/` |

### Common pitfalls

1. **Seed environment variables at `conftest.py` module scope, never in a fixture.** `backend/app/core/config.py` runs `settings = Settings()` at import time, and eight of its fields are declared without a default (`SECRET_KEY`, the four `TWITTER_*` credentials, `OPENAI_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `BIGQUERY_DATASET`), so an `autouse` fixture executes too late to help. (The design documents say nine; the tree declares eight.)
2. **Always patch `app.db.firestore.get_db`.** `google.auth.default()` can resolve in this environment, so an unpatched call performs a real Google Cloud round trip. The suite installs an autouse credential neutralizer and a socket guard so that an unmocked call fails loudly instead of escaping.
3. **Never call `app.tasks.tweet_processor.start_tweet_stream()` without patching `tweepy`.** It does a function-local `import tweepy`, so it reaches `stream.filter(track=…)` and hangs the interpreter on a live Twitter connection. Its near-twin `app.services.twitter_service.start_twitter_stream()` behaves differently and it is worth knowing which is which: that module imports only `StreamListener`, `OAuthHandler` and `API`, never the module name, so it raises `NameError: name 'tweepy' is not defined` one statement *before* the connection — dead code that cannot hang. Both read `settings.TWITTER_CONSUMER_KEY`, which `Settings` never declares, so both raise `AttributeError` first unless a test supplies it.
4. **Let msw intercept all frontend HTTP.** An unmocked `axios` call opens a real socket whose rejection can settle inside a *later* test and fail it, so an unhandled request is recorded in an isolation ledger and then refused, and the shared `afterEach` fails the test that caused it. Handlers are registered as **exact absolute URLs** — no wildcard host and no wildcard path segment: `ALLOWED_REQUEST_ORIGINS` is a frozen two-entry loopback list (`http://localhost`, `http://127.0.0.1`) and every pattern spells out its origin, its base path prefix and its route path in full. The axios base URL evaluates to the literal string `"undefined"`, so that prefix is `/undefined` and a handler reads `http://localhost/undefined/tweets`. A request under any other origin or prefix matches nothing and fails loudly; to drive one deliberately, register a handler for that exact URL with `server.use(...)`.

### How to extend

- **Placement** — mirror the `app/` layout under `backend/tests/unit/`; colocate `<Name>.test.ts(x)` beside its frontend subject; add a new browser flow as a spec under `e2e/tests/`.
- **Naming** — `test_<layer>.py` for modules, `test_<operation>` and `test_<operation>_<scenario>` for functions, `mock_<entity>` for fixtures.
- **Shared setup** — put it in `backend/tests/conftest.py` or `frontend/src/test-utils/` and import it from there. Never copy-paste setup into a test.
- **Patch targets** — patch the **importing** module's boundary, for example `app.services.llm_service.Completion.create`, never the third-party library itself.

### Reporting artifacts

Every path below is ignored by the root `.gitignore`, so **no artifact is committed** — a local run leaves
them in your working tree and nowhere else. The last column is what a CI run additionally uploads, and it
is the difference between a figure you can re-derive after the fact and one you have to take on trust.

| Artifact | Written by | Retained by CI |
| --- | --- | --- |
| `backend/reports/junit.xml` | the backend test command | yes — artifact `build-test-evidence`, 30 days |
| `backend/reports/collect-only.txt` | the backend readiness step | yes — `build-test-evidence` |
| `backend/reports/coverage-gate.txt` | the exact coverage gate, `tests/coverage_gate.py`, piped through `tee` | yes — `build-test-evidence` |
| `backend/coverage.xml` | `--cov-report=xml` | yes — `build-test-evidence`, and the `backend`-flagged Codecov upload |
| `backend/coverage.json` | `--cov-report=json` | yes — `build-test-evidence` |
| `backend/coverage.lcov` | `--cov-report=lcov` | **no** — local only; the CI command does not request this reporter |
| `frontend/reports/jest-junit.xml` | the `jest-junit` reporter, on a real suite run only — the load probe passes `--reporters=default` so it cannot overwrite this file | yes — `build-test-evidence` |
| `frontend/reports/list-tests.txt` | the frontend discovery step, `npm run test:list` | yes — `build-test-evidence` |
| `frontend/reports/load-tests.txt` | the frontend readiness step, `npm run test:load` | yes — `build-test-evidence` |
| `frontend/coverage/` — `lcov.info`, `lcov-report/`, `coverage-final.json`, `coverage-summary.json`, `cobertura-coverage.xml` | the five configured coverage reporters | yes — `build-test-evidence`, and `coverage-final.json` is the `frontend`-flagged Codecov upload |
| `e2e/reports/e2e-junit.xml` | Playwright's `junit` reporter | yes — artifact `e2e-test-evidence` |
| `e2e/reports/list-tests.txt` | the E2E readiness step | yes — `e2e-test-evidence` |
| `e2e/reports/browser.txt` | the browser gate, `browsers:require`, plus the runner version and the reporter | yes — `e2e-test-evidence` |
| `e2e/playwright-report/` | Playwright's `html` reporter | yes — artifact `playwright-report` |
| `e2e/test-results/` | trace, screenshot and video, **on failure only** | yes — artifact `e2e-failure-artifacts`, `if-no-files-found: warn` because a passing run writes only `.last-run.json` there, and no trace, screenshot or video |

Two workflow steps read the JUnit streams before those uploads and fail with an explicit annotation when a
report is missing, empty, or declares zero test cases — so a collection-time stub can never be published
as a run.

The two Codecov upload steps in `.github/workflows/ci.yml` were **reused**, and their `backend` and
`frontend` flags are unchanged — but both `file:` paths were **repointed** at the artifacts that are
actually produced: `./coverage.xml` became `./backend/coverage.xml`, and `./coverage/coverage-final.json`
became `./frontend/coverage/coverage-final.json`. That second path is why `'json'` is a required entry in
`coverageReporters` rather than an optional extra. Both also gained `fail_ci_if_error: true` and a
condition tying them to a producer step that succeeded. The JUnit reporters on all three suites, the
additional coverage reporters, the three readiness steps, the exact coverage gate and the artifact
retention were **added**. Every path in the table is ignored by the root `.gitignore`, so no artifact is
committed. A dashboard layout over these feeds is in
[`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md).

**What CI does and does not tell you.** The `flake8 .`, `mypy .` and `npm run lint` steps are broken for
reasons that predate this test suite and were deliberately left alone, so the workflow's overall
conclusion is **red**. That no longer means the suite did not run: every test and reporting step carries
`if: ${{ !cancelled() }}`, so the suites, the gates, the Codecov uploads and the artifact retention all
execute regardless of the lint outcome. Read the individual step results, not just the check mark. And
note that this workflow has **never run on GitHub Actions from this branch** — every statement here
describes the workflow file.

A dashboard layout over these feeds is in
[`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md), and
[`docs/testing/dashboard-extract.py`](docs/testing/dashboard-extract.py) fills it from the artifacts:

```bash
python docs/testing/dashboard-extract.py --require-all
```

It exits non-zero and names any artifact that was not produced, so a partial run cannot quietly become a
partial dashboard.

### Further reading

- [`backend/tests/README.md`](backend/tests/README.md) — backend suite: import-root convention, fixture catalogue, per-dependency mocking strategy
- [`frontend/TESTING.md`](frontend/TESTING.md) — frontend suite: Jest configuration, transformers, module mapping, msw contract
- [`e2e/README.md`](e2e/README.md) — end-to-end harness rationale, browser prerequisites and current status
- [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) — every non-trivial decision with its alternatives, reasoning and risks
- [`docs/testing/TRACEABILITY-MATRIX.md`](docs/testing/TRACEABILITY-MATRIX.md) — bidirectional mapping between the previous tests and this suite
- [`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md) — coverage and test-health dashboard template
- [`blitzy-deck/executive-summary.html`](blitzy-deck/executive-summary.html) — executive summary of this work for non-technical readers

### Suggested next tasks

Improvements discovered while building the test suite. Almost none of them was attempted here — each falls outside the scope of adding tests, and each is left exactly as it was found. Three entries read differently and say so in their own opening words: two record work that *was* closed because it fell inside the authorized surface, and the first asks for a decision rather than describing work.

- **Owner decision, not a task** — ratify or reverse the seven places where a delivered detail differs from the literal text of the agreed plan. They are: the `python-jose` pin described below; two `grpcio` pins the agreed inventory does not list, which the test guards patch by name; two extra `test:` scripts in `frontend/package.json` beyond the five the plan enumerates, both of them pipeline readiness gates; twenty-one test-side files beyond the plan's transformation map, all inside the directories it declares in scope; a Playwright trace kept on every failing test rather than only on a retry; an unhandled-request ledger in place of a literal `'error'` setting, which is what makes an unmocked call fail loudly in a codebase whose callers all swallow; and an end-to-end job that resolves a pre-installed browser instead of downloading one, through a runner release whose downloader carries CVE-2025-59288. Every one is recorded with its alternatives and its risks in [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md), whose §40 closes with a register stating, item by item, what an owner is being asked to sign off and what reversing it would cost. Five of the seven are put to an owner to ratify and the remaining two are already authorised by the plan's own scope clause; none is a defect, so nothing needs changing to keep the suite green — but until they are ratified, every future review raises them again.
- **Not attempted** — correct the stale product identity in this README, which describes an unrelated static-analysis tool rather than the Twitter-monitoring service this repository implements.
- **Not attempted** — reconcile the port mismatch between this README, `infrastructure/docker/docker-compose.yml` and `infrastructure/docker/nginx.conf`.
- **Done, within the authorized surface** — the five packages the source imports and no manifest declared (`react-router-dom`, `@reduxjs/toolkit`, `react-redux`, `zod`, `dayjs`) are now declared in `frontend/package.json`, at exact versions, because the suites cannot run without them. They sit in `devDependencies` alongside the other test dependencies, since AAP §0.5.3 scopes changes to that file to devDependencies and test scripts. **Still not attempted:** moving the four of them that are genuine *runtime* imports into `dependencies`, which is a packaging decision this work has no mandate to make.
- **Done, within the authorized surface** — `python-jose[cryptography]` is pinned at `3.5.0` in `backend/requirements-dev.txt`, above CVE-2024-33663 and CVE-2024-33664, both of which affect the `3.3.0` the agreed dependency inventory names and are fixed in 3.4.0. No test here reaches either — the suite round-trips one HS256 token with an explicit key and never decrypts a JWE or loads an OpenSSH ECDSA key — so what the pin removes is a future production exposure rather than a present test one. Because the delivered manifest therefore differs from the agreed inventory by one line, it is the first of the seven items in the frozen-plan deviation register described in the bullet above, and it is that register, not this bullet, that asks the owners to ratify it.
- **Not attempted, and now measured** — commit lockfiles for `frontend/` and `e2e/` so that installs are reproducible and `npm ci` becomes usable. AAP §0.6.2 decided against committing one and §0.8.1 scopes `frontend/package.json` to devDependencies and test scripts, so neither a lockfile nor an `engines` field could be added here; what this delivery did instead was ignore the two generated lockfiles at their anchored paths so a documented install no longer dirties a clean tree (`D380`), and later stop the install *executing* anything: all three `npm install` steps in the workflow carry `--ignore-scripts`, the pip bootstrap is pinned, and the backend install is wheels-only, so no dependency runs code in CI even though the resolution still floats (`D411`, and `docs/testing/SECURITY-GAPS.md` row 32 for what that leaves open — including the absent `--require-hashes`, which needs a transitive digest set the AAP's direct-pin manifest does not provide). The cost of that decision is no longer hypothetical: with the graph left floating, **four packages in `frontend/node_modules` and one in `e2e/node_modules` now declare `engines.node` that excludes the `node-version: [16.x]` the workflow declares**, none of them a direct declaration — `@testing-library/dom@10.4.1` under the frozen `@testing-library/user-event ^14.4.3`, `@inquirer/external-editor@1.0.3` under `msw@1.3.5` → `inquirer@8.2.7`, `postcss-load-config@6.0.1` under the floating `tailwindcss ^3.3.2`, and `node-releases@2.0.53` in both trees. On Node 22.23.1, the runtime the suites are actually exercised on, nothing is excluded. Three ways out — commit both lockfiles and switch the three `npm install` steps to `npm ci`, declare `engines`, or raise the declared Node ceiling — and one of them needs choosing, because the declared ceiling and the installed closure currently disagree. `D381` carries the audit and the trade-offs.
- **Not attempted** — raise the Node floor and move `@playwright/test` past 1.44.1, which is the last release supporting the declared Node 16.x and carries the browser-downloader CVE that forces the out-of-band browser provisioning described above. A newer runner would let a script obtain the browser again.
- **Not attempted** — run `.github/workflows/ci.yml` on GitHub Actions from a branch and confirm it there. Every statement about CI in this repository's documentation describes the workflow file; the pipeline itself has never executed.
- **Not attempted** — add the missing `frontend/tsconfig.node.json`, or drop the dangling project reference to it, so that `.tsx` transforms and `npm run build` work.
- **Not attempted** — supply an HTML entry point and a `frontend/vite.config.ts` so that the application can actually be served.
- **Not attempted** — give the application a stylesheet. `tailwindcss`, `postcss` and `autoprefixer` are declared in `frontend/package.json`, but there is no `tailwind.config.js`, no `postcss.config.js`, no `frontend/src/index.css`, and no module imports a stylesheet, so `document.styleSheets.length` is **0** on every screen and each one renders as unstyled default HTML — browser-default serif type, a bare `<canvas>`, and credential inputs stepped into a staircase by their label widths. This is the most visible gap between the delivered UI and the visual language of the executive deck, and closing it needs the two entries above closed first: a stylesheet with no build to process it and no entry to load it changes nothing. Measured on the end-to-end harness, which loads the real component modules, so the reading is a property of `frontend/src` rather than of the harness.
- **Not attempted** — repair the invalid reducer imports in `frontend/src/store/index.ts`, and export the `useAppDispatch` and `useAppSelector` hooks that three page modules import.
- **Not attempted** — implement the missing `TweetCard` component, the `getTweets` and `setupInterceptors` exports, and the `Chart.register` call that chart construction requires. Note that chart construction is wrapped by nothing, so supplying the registration makes a later failure there propagate out of the effect and — measured in a real browser — take down the whole React root rather than the one component, for the reason the next entry describes.
- **Not attempted** — give the analytics chart canvas an accessible name and description, or a table or textual summary of the series. It is a bare `<canvas>` today, so the whole of the analytics content is absent from the accessibility tree.
- **Not attempted** — give each routed screen a level-one heading. Every routed component's own heading is an `<h2>` (`components/Analytics`, `components/Configuration`, `components/Dashboard`), and neither `frontend/src/app.tsx` nor the end-to-end harness supplies an `<h1>`, so a screen reader's outline of any screen has no level-one entry. Neither place can be fixed within this delivery: the application entry is production code outside the two authorized touches, and the harness deliberately adds no page chrome so that a spec observes the component unaltered.
- **Not attempted** — announce loading and live updates: the tweet-list loading indicator is a plain `div` in a container that is not a live region, and the 30-second polled feed declares no live region either, so neither is audible to a screen reader.
- **Not attempted** — give the Twitter credential save a pending state. The control is never disabled and never carries `aria-busy`, so a second activation while the first write is open issues a second credential write and opens a second dialog.
- **Not attempted** — mask every credential field and state an intentional autofill policy. `API Key` and `Access Token` render as `type="text"` today, so both are on screen in clear text while only the `Secret`-suffixed fields are masked.

The fifteen entries that follow came from a runtime pass through all four screens in a real browser, driving the production components through the end-to-end harness. Each is stated as a fact about the code so it can be scheduled without reading that report; the full list, against the files and lines that produce it, is in [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) §23, and the reason none was fixed here is its row D400.

- **Not attempted, and the one that changes the most** — contain a render fault. There is no error boundary in `frontend/src/app.tsx`, in any component, or anywhere else under `frontend/src`, so a throw out of any routed component unmounts the **whole React root**: the landmark above the router goes with it, `#root` is emptied, and a client-side history change afterwards moves the URL while rendering nothing, so the page cannot recover from inside itself. Two paths reach it today — a non-empty feed mapping into the undefined `TweetCard`, and the unregistered `Chart` on the analytics route — and on the feed React's unmount also clears the 30-second poll, which nothing reinstalls. The end-to-end suite asserts this teardown as current behaviour, so adding a boundary will fail those assertions on purpose.
- **Not attempted** — give the polled feed an error state and bound its failures. `frontend/src/components/Dashboard` awaits the collection with no `try`/`catch`, so every failing poll becomes an unhandled rejection — one per 30-second tick, indefinitely, with nothing visible to the user — while a healthy empty feed, a request in flight and a hard failure all render the same heading and nothing else. It needs a visible error state, an empty state, a loading state, a backoff and a stop condition.
- **Not attempted** — validate the feed payload before rendering it. `axios`'s `transitional.silentJSONParsing` default returns an unparsable body as a raw string with the response reported as successful, and a well-formed 200 of the wrong shape passes just as easily, so either arrives at render as `tweets.map is not a function` rather than as a caught fetch failure. `frontend/src/schema/tweetSchema.ts` already describes the shape; no caller parses with it.
- **Not attempted** — make the 30-second poll cache-proof and overlap-proof. The request carries no cache-busting parameter, no `Cache-Control: no-cache` and no revalidation, so a response carrying `max-age` leaves a feed that looks live and is frozen; and the interval is installed with no in-flight guard, so a response slower than the period stacks overlapping requests racing into one state setter.
- **Not attempted** — key the feed list on a field the payload has. `key={tweet.id}` reads `id` off a shape that declares `tweet_id`, so every key is `undefined` and React warns on every list render. The same absent `id` is what makes `frontend/src/store/tweetSlice.ts` overwrite index 0 on any update.
- **Not attempted** — make the tweet-list screen able to report anything. Its mount effect throws before its first `await`, because of the missing `getTweets` export above, so its `Loading...` branch can never commit, the container renders with no child and therefore no bounding box, and the only failure signal anywhere is one developer-facing `console.error`. Its pagination guard compares `innerHeight + scrollTop === offsetHeight` with strict equality, which one fractional pixel defeats — and with nothing rendered there is nothing to scroll, so the branch is unreachable either way.
- **Not attempted** — make the analytics screen responsive and honest about failure. The canvas stays at its intrinsic 300×150 in every viewport because Chart.js never runs on the mounted path, a failed construction leaves a live `ResizeObserver` attached to a detached canvas, and a 500, a 404, a malformed body, a request in flight and a delayed failure all render the heading and an empty canvas with no message, no retry and no loading affordance. The component logs the caught rejection and discards everything else the response carried.
- **Not attempted** — stop the credential values being readable in the DOM. React mirrors all four controlled values into the `value` attribute, both `type="password"` fields included, from first render onwards, and the form is never cleared after a successful save, so every value sits in `outerHTML` in clear text for the page's lifetime. This and the two entries below are stated as exposures in rows 26 to 28 of [`docs/testing/SECURITY-GAPS.md`](docs/testing/SECURITY-GAPS.md).
- **Not attempted** — guard the credential write. There is no in-flight guard, no idempotency key and no `AbortController`: every activation issues its own `POST` carrying the full payload, several can be open at once, and a write abandoned by a route change completes anyway and pops its success dialog over an unrelated screen.
- **Not attempted** — normalise and bound the credential fields. Whitespace-only values are accepted and reported as updated successfully with their padding preserved, and no field declares `maxlength`, so four 10,000-character values produce one 40,068-byte request.
- **Not attempted** — replace the two `alert()` calls with real outcome feedback. Success and failure leave byte-identical screens, one fixed 37-character sentence covers every failure mode with no status and no reason, `:invalid` carries no visual treatment, hover changes zero pixels, the pressed state flips only a property the native painter ignores under `appearance: auto`, and Chrome's validation bubble occludes three of the four rows while naming one error.
- **Not attempted** — make the credential form's controls hittable and legible. Five controls 21 px tall on a 21-px pitch leaves 0 px of separation, with the submit button abutting the last field so a purely horizontal pointer move switches between them, failing WCAG 2.5.8's 24×24 as well as the 44×44 guideline; the button background is 1.14:1 against the page, below WCAG 1.4.11's 3:1 non-text floor; 13.33-px inputs invite iOS focus auto-zoom; a long clear-text value truncates at the field edge with no wrap, tooltip or reveal; and inline labels of differing width produce a 76-px staircase of input left edges in a form that mixes two font families.
- **Not attempted** — name the credential form and its fields for assistive technology. There is no `aria-*` attribute anywhere on the screen, no accessible error channel, no `name` or `autocomplete`, no `fieldset`, no accessible name on the `<form>`, and no required indicator on any of the four required fields; the two password fields are indistinguishable from the text fields in the serialized accessibility tree. Chrome also emits `[DOM] Multiple forms should be contained in their own form elements` at load, before any interaction.
- **Not attempted** — add a catch-all route and a way back from it. An unrouted URL answers 200 and renders an empty landmark: the same `document.title` as a working route, no visible text, and no link, button, nav or form to return with, so `Tab` leaves the document. Because three of the four routes render no visible text in their normal state either, one blank white frame is the rendered output of a working screen, an unknown URL and a torn-down root alike. `e2e/tests/tweets.spec.ts` pins that indistinguishability, so supplying a not-found route will fail it on purpose.
- **Not attempted** — stop reading an automated accessibility score on these screens as a signal. A Lighthouse accessibility score of 100 here is vacuous rather than reassuring: most audits report `notApplicable` on a document with almost no interactive content, and no rule ever examines the unnamed canvas.
- **Not attempted** — resolve the SQLAlchemy-against-Firestore mismatch in the routes module.
- **Not attempted** — add the missing `add_response` helper to `backend/app/db/firestore.py`, which `backend/app/tasks/response_generator.py` imports.
- **Not attempted** — repair the `flake8 .`, `mypy .` and `npm run lint` steps in `.github/workflows/ci.yml`; no linter is declared and the sources do not typecheck. Until they pass, the `build` job's overall conclusion stays red even though both test steps succeed.
- **Not attempted** — pin the five remaining floating action references in `.github/workflows/ci.yml` to commit SHAs, so the whole workflow is pinned rather than most of it. Measured on the delivered file: **9 of the 14 `uses:` references are SHA-pinned and 5 are floating tags** — `actions/checkout@v2`, `actions/setup-python@v2` and `actions/setup-node@v2` in the `build` job, and the two `codecov/codecov-action@v1` steps. A floating major tag is mutable, so each of those five resolves to whatever the tag points at on the day the workflow runs. The asymmetry is not an oversight: every reference this delivery *added* is pinned, and the five that are not are all in steps outside the authorized change surface — `checkout` and the two `setup-*` steps are not test steps, and AAP §0.10.2 records the two Codecov steps as **reused unchanged**, which is why they still carry `@v1`. Pinning them is a one-line change per step for whoever holds that boundary, and it is the whole of the task. `D392` carries the audit.
- **Not attempted** — raise the declared Node ceiling so `@playwright/test` >= 1.55.1 becomes available. That release carries the fix for CVE-2025-59288, which is the only reason the `e2e` job must be handed a browser provisioned out of band instead of installing one.
- **Not attempted** — align the `/health` health checks in `infrastructure/docker/docker-compose.yml` and `.github/workflows/cd.yml` with a route that actually exists.
- **Not attempted, and the highest-value group here** — the security exposures a whole-project assessment found and this delivery could not close, because they live in production code, in pinned dependency versions, and in the infrastructure and deployment files that the plan places off-limits. There are thirty of them in those three categories — thirty-three rows in the register in total, two of them, rows 24 and 25, being about this delivery's own executive deck rather than the application, and one, row 33, about the end-to-end harness's own development server — and the three that matter most are that all three implemented HTTP operations have no authentication or authorization of any kind, that `backend/app/services/analytics_service.py` builds both BigQuery queries by f-string interpolation of caller-supplied date strings, and that `infrastructure/terraform/main.tf` provisions network and storage without the access restrictions and in-transit encryption those resources support. Each one is written up individually — stated as a fact about the code, with the clause that put it out of reach, what it is worth to an attacker, and what has to be done — in [`docs/testing/SECURITY-GAPS.md`](docs/testing/SECURITY-GAPS.md). Read that before scheduling anything else on this list.
- **Not attempted** — remove the `postgres:13` service and the `DATABASE_URL` variable, neither of which the Firestore and BigQuery application uses.

The five entries that follow came from a dedicated runtime security assessment of the delivered tree. Each is stated as a fact about the code so it can be scheduled without reading that report; all five are written up as exposures, with what they are worth to an attacker, in [`docs/testing/SECURITY-GAPS.md`](docs/testing/SECURITY-GAPS.md), and the reason none was fixed here is `D412`.

- **Not attempted** — validate `BIGQUERY_DATASET` before it reaches a query. `backend/app/services/analytics_service.py` interpolates it into a backtick-quoted table identifier, so a value containing a backtick closes the identifier and the remainder becomes statement text: set to `` p.d`; DROP SCHEMA d; -- ``, the emitted SQL reads `` `p.d`; DROP SCHEMA d; --.tweets` ``. This is a second injection point on the same statement as the date-string one, and its input is configuration rather than a request. Register row 29.
- **Not attempted** — replace the digit-grouping regex in `frontend/src/utils/formatUtils.ts` with `Intl.NumberFormat`. Its lookahead backtracks quadratically, so a plain digit string is enough to freeze the renderer: 100,000 digits took 9.9 seconds and 400,000 took **162 seconds** in one synchronous call, with no console output while it hung. Neither utility module has a single production call site today, so this is dead code — and it becomes a live availability bug the moment a component renders a count through it. The same replacement fixes the decimal-mangling defect the suite already pins. Register row 30.
- **Not attempted** — make the zod schemas reject unknown keys rather than strip them. `z.object()` silently drops what it does not declare, and neither store slice guards what it keeps, so a payload carrying `__proto__` and `constructor` as own keys reaches Redux state with those keys intact. `Object.prototype` was **not** polluted, but that is a JavaScript guarantee rather than a defence: the margin depends on nothing in the codebase ever deep-merging or `for…in`-copying that state. Register row 31.
- **Not attempted** — restrict uvicorn's proxy-header trust alongside the `TrustedHostMiddleware` the entry above asks for. Without it the trailing-slash redirect's **scheme** is attacker-chosen as well as its host: `X-Forwarded-Proto: javascript` with a hostile `Host` answered `location: javascript://attacker.example/tweets`. Behind the reverse proxy the deployment files describe, every client is the trusted peer. Register row 11.
- **Do not expose the end-to-end harness dev server beyond loopback.** A failing module transform is answered with Vite's own `500` payload, which carries the file's verbatim source. It is bounded today by a loopback bind, a host allow-list and the filesystem guard, and removing the payload would remove the diagnostic every harness change is debugged with, so it is an accepted risk rather than a task — recorded as register row 33 and `D413`.

The eleven entries that follow came from a later pass that drove the **real FastAPI application over a real socket** alongside the browser, so each is a fact about the server rather than about a component. The first ten are now pinned by assertions, so scheduling any of them means updating the tests those assertions live in; §23 of the decision log names which test holds which behaviour. The eleventh is a repository-hygiene gap rather than a behaviour, so nothing asserts it.

- **Not attempted, and the highest-value single item on this list** — refuse an empty tweet identifier. `GET /tweets/` does not reach the detail route: starlette strips the empty trailing segment, retries, and `/tweets` matches, so the request answers **307** toward the collection and following it returns **200 with every stored record**, byte-identical to a collection read, with no authentication anywhere on the path. `/tweets//` reaches the same outcome, while an explicitly encoded `%20` does not — a one-character segment matches the detail route and `500`s — which is what identifies an empty path segment as the mechanism. The declared parameter is a bare `str` with no `minLength` and no `pattern`, and `frontend/src/services/api.ts` interpolates the identifier with no validation while declaring a single-`Tweet` return type, so a caller receives an array and reads `undefined` from every field rather than raising. Constrain the parameter, disable `redirect_slashes` for the route, and validate the identifier client-side.
- **Not attempted** — stop one malformed stored row from making the whole feed unavailable. The response model is `List[Tweet]`, validated as one value, so three rows of which the middle one omits `content` answer a bare `500` and **both valid rows become unreachable**; they are retrievable only by a caller who already knows the bad row's index. Validate on write, or serialize per record and return a partial result with a per-record error envelope.
- **Not attempted** — decide what serialization should do to a non-conforming value instead of changing it silently. `"777"` becomes `777`, `12.9` becomes `12` with the fraction discarded, a boolean becomes `1`, an undeclared key is dropped, and `doubt_rating` emits `42.5` and `-1.0` unbounded — none of it logged, despite `DOUBT_RATING_THRESHOLD` being `0.7`.
- **Not attempted** — reconcile the field names across the seam. `id` and `text`, the two the frontend declares, are stripped from the emitted body **even when the stored row carries them**, so those names can never reach the browser whatever is stored.
- **Not attempted** — decide the wire format of `timestamp`. A naive stored value renders with **no timezone designator** while an aware one keeps its offset, and per ES2015 a designator-free date-time string is parsed by `new Date()` as *local* time — so the instant a browser reconstructs depends on the reader's zone. The frontend's `z.date()` rejects both forms as strings, and coercing the one field is sufficient to make the whole record parse.
- **Not attempted** — add security response headers. The application installs `CORSMiddleware` and nothing else, so a `200`, a `404`, a `405` and a `422` all carry only what the payload needs: no `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy`, cross-origin policy or `Cache-Control`. The JSON content type is consequently the only thing keeping a payload-bearing response inert when it is navigated to directly.
- **Not attempted** — make a cross-origin browser client able to call the API at all. With `ALLOWED_ORIGINS = []` a simple request from an origin answers `200` with `access-control-allow-credentials` and **no** `access-control-allow-origin`, so the server records a success while the browser discards the body; a true preflight answers `400 Disallowed CORS origin` while still advertising all seven methods and a ten-minute cache; and `OPTIONS` without an `Origin` falls through to the router as `405`. There is no working preflight by either path. The `[]` default is deliberate and least-privilege, so this is a deployment decision rather than a defect.
- **Not attempted** — bound `skip` and `limit`. Both are bare `int`s, so a negative offset, a zero page and a magnitude above a signed 32-bit maximum all reach the query unchanged.
- **Not attempted** — validate URL schemes in emitted data. `media_urls` is `List[str]`, so a `javascript:` entry is returned exactly as stored; it is inert only for as long as no component binds it to an `href` or a `src`.
- **Not attempted** — attach a rejection handler to the polled feed and bound its retries. Measured in a real browser over a 757-second session against a failing endpoint: **26 failed requests, 26 unhandled rejections, a strict 1:1, and none ever handled**; the interval never lengthens (13 periods averaging 30000.238 ms) and never stops; and the page shows the heading and nothing else throughout, with zero DOM mutations after mount. This is the same item as the polled-feed error state above, now with the measurement behind it.
- **Not attempted, and the cheapest item on this list** — ignore the artifact the documented root-misuse reproduction leaves behind. Running bare `pytest` at the repository root is published above as a reproduction, and because `--junitxml=reports/junit.xml` in `backend/pytest.ini` resolves against the invocation directory rather than the config file, that run writes a **`reports/junit.xml` at the repository root**. `.gitignore` covers `backend/reports/`, `frontend/reports/`, `docs/testing/reports/` and `e2e/reports/` but not the root path, so a reader who follows the documented reproduction is left with an untracked artifact the ignore rules do not catch. It was deliberately not added: the ignore set is enumerated exactly in the agreed plan and its pattern count, anchored/unanchored split and full membership are each pinned by `backend/tests/test_docs_contract.py` against row F39 of the traceability matrix, so a one-line addition is a four-file coordinated change to an artifact no suite produces when invoked correctly. Either add `/reports/` and restate F39, or make the `--junitxml` path absolute so the artifact can only ever land under `backend/`.

The complete register, together with the reasoning behind every item, is in [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md).
