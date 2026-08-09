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

Order matters between legs 2 and 3: the e2e harness pins React and five other bare specifiers into `frontend/node_modules`, so install `frontend` first.

```bash
# 1. Backend - virtual environment plus the pinned test stack
python3.9 -m venv .venv-backend && . .venv-backend/bin/activate && pip install --upgrade pip && pip install -r backend/requirements-dev.txt

# 2. Frontend - a prerequisite of leg 3, not just of the Jest suite
npm --prefix frontend install

# 3. End-to-end - install `frontend` FIRST (the harness resolves ten packages out of
#    frontend/node_modules); this installs the runner only and does NOT download a browser
npm --prefix e2e install
```

- The parentheses are load-bearing: each `cd` happens in a subshell, so the next command still starts at the repository root. `npm install --prefix frontend` is **not** an alternative — `npm install` reads the manifest of the *current* directory, and this repository has no root `package.json`, so it fails with `ENOENT ... open .../package.json`. (`npm --prefix <dir> run <script>` does work, and is used below.)
- Use `npm install`, **not** `npm ci`. No lockfile is committed in this repository, and `npm ci` refuses to run without one.
- **Pinning differs by stack, so do not assume either behaviour from the other.** `backend/requirements-dev.txt` is exact-pinned throughout: all 25 active lines are `==`, and `backend/tests/test_dependency_closure.py` fails if any one of them is not. `frontend/package.json` is a partition: the **11** devDependencies this testing work introduced are exact-pinned, and the **17** pre-existing declarations — 7 runtime dependencies and 10 development ones — are deliberately left at the caret ranges the baseline shipped, because the change boundary for that file is devDependencies and test scripts only. `frontend/src/test-utils/dependency-closure.test.ts` enforces both halves: exact pins on the first set, byte-identical specifiers on the second. `e2e/package.json` is exact-pinned throughout. Several versions are deliberately held below their latest release. See [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) for why those versions and the lockfile posture were chosen.

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

Then confirm what the runner would use, without fetching anything:

```bash
cd e2e && npm run browsers:verify
```

That runs `playwright install --dry-run chromium`, which prints the build and directory it would use and exits
non-zero if nothing is available. If you are running several clones of this repository in parallel, set
`CLONE_INDEX` so each harness gets its own port (`4173 + CLONE_INDEX`).

#### The browser is a prerequisite, not something the install fetches

`npm run browsers:verify` **reports** what the runner will load and downloads nothing — it is
`playwright install --dry-run chromium`. The pinned `@playwright/test` 1.44.1 has a browser downloader
that does not verify the TLS chain of the host it fetches from (CVE-2025-59288), so this repository
provisions browsers out of band instead and no script, and no CI step, invokes that downloader. Satisfy
the prerequisite either way:

| Route | What to do |
| --- | --- |
| A Chromium already in Playwright's cache | `cd e2e && npm run browsers:verify` prints the build and the exact directory it will be loaded from. Nothing further is needed |
| A system browser you name explicitly | Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to the full path of a Chrome or Chromium binary; `e2e/playwright.config.ts` passes it through as `launchOptions.executablePath` |

Without one of the two, every end-to-end test fails identically at launch with
`browserType.launch: Executable doesn't exist at <path>` — a clear message rather than a silent,
unverified fetch. The `e2e` job in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) takes the
second route, checks it before running anything, and logs the resolved browser path and version.
[`e2e/README.md`](e2e/README.md) covers both routes in full, and
[`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) rows `D111` and `D257` record why.

### Run

Run every backend command from `backend/`, so that `backend/pytest.ini` is the configuration file pytest loads. A **bare** `pytest` from the repository root fails in a way that is easy to misread, and worth stating precisely because the failure does not look like a configuration problem:

- Collection **succeeds** — all 774 tests are collected, and imports resolve, because pytest inserts each test file's rootdir on `sys.path` regardless.
- But `rootdir` becomes the repository root and **no `configfile` is loaded**, so `asyncio_mode = auto` is off. pytest reports `asyncio: mode=strict`, and every `async def` test errors for want of a decorator: **21 failed, 630 passed, 3 skipped**.

So a root run produces a plausible-looking collection followed by 21 failures that say nothing about the code under test. Passing an explicit path — `pytest backend/tests` — *does* find the ini, because pytest walks up from the argument; the reliable habit is simply to `cd backend` first, which is what every command below assumes and what CI does through `working-directory: backend`.

| Goal | Command |
| --- | --- |
| Backend, all layers | `cd backend && pytest` |
| Backend coverage with the gate | `cd backend && pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-fail-under=90` |
| Backend unit layer only | `cd backend && pytest tests/unit -m unit` |
| Backend integration layer only | `cd backend && pytest tests/integration -m integration` |
| Frontend, all suites | `cd frontend && npm test` |
| Frontend, watch mode | `cd frontend && npm run test:watch` |
| Frontend, coverage | `cd frontend && npm run test:coverage` |
| Frontend, CI mode | `cd frontend && npm run test:ci` |
| End-to-end | `cd e2e && npm test` |
| End-to-end, list without running | `cd e2e && npm run test:list` |
| End-to-end report | `cd e2e && npm run report` |
| End-to-end browser check, fetches nothing | `cd e2e && npm run browsers:verify` |

Every end-to-end command runs from `e2e/` through that package's own scripts, so the runner is the pinned
`e2e/node_modules/.bin/playwright` and the configuration is the one beside it. Do not invoke `npx playwright`
from the repository root: there is no root manifest and no root `node_modules`, so `npx` would fetch an
unpinned runner from the registry.

The three suites report **771 passed / 3 reasoned skips** on the backend, **346 passed / 24 reasoned skips across 24 suites** on the frontend, and **19 passed / no skip** end to end. The collection-integrity gate expects **zero errors**. It is the meaningful readiness check here, because this suite's historical failure mode was import errors rather than failed assertions: a clean collection proves every test module is importable before any assertion is evaluated.

Use `npm test` for the end-to-end suite rather than `npx playwright test`. Both resolve the pinned local
runner from inside `e2e/`, but `npx` is online-capable by design, and a script that names the binary fails
closed instead. The same command is what CI runs.

### Readiness checks

Three commands prove the suites can be *collected* before any assertion is evaluated. This matters here
more than it usually would: the failure mode this repository inherited was import errors — three legacy
test modules that never reached an assertion — so a clean collection is the check that would have caught
the original state, in a way a passing-test count would not.

| Layer | Command | Expects |
| --- | --- | --- |
| Backend | `cd backend && pytest --collect-only -q` | **zero errors** |
| Frontend | `cd frontend && npm run test:list` | every collectable test file listed, exit 0 |
| End-to-end | `cd e2e && npm run test:list` | every test listed, exit 0; launches no browser |

**All three are automated CI steps, not just local commands.** `.github/workflows/ci.yml` runs each as its
own step ahead of the corresponding suite and captures its summary to `backend/reports/collect-only.txt`,
`frontend/reports/list-tests.txt` and `e2e/reports/list-tests.txt`, all three retained as CI artifacts.
The dashboard's extractor reads those files, so a readiness result is auditable after the run rather than
scrolled past in a log. Rationale in
[`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) row `D255`.

Two of the three overwrite the run report they sit beside, which is why the step order matters:
`pytest --collect-only` and `playwright test --list` both write their configured reporters, so either can
leave a zero-case stub exactly where a result stream belongs. CI runs readiness *before* each suite, two
verification steps reject a zero-case stream outright, and the extractor refuses one rather than rendering
it as zeros (`D254`, `D258`). `jest --listTests` does not have the defect. Locally, if you run a readiness
command last, re-run the suite before trusting the artifacts.

### Coverage gates

| Scope | Gate | Enforced by |
| --- | --- | --- |
| `backend/app/core`, `backend/app/services`, `backend/app/tasks`, `backend/app/db` — **one** gate over their aggregate | ≥90% line coverage | `pytest --cov-fail-under=90`, compared at two-decimal precision via `backend/.coveragerc` |
| `frontend/src/store`, `frontend/src/schema`, `frontend/src/services` — **three** independent gates, one per path | ≥80% statements, branches, functions and lines | Jest `coverageThreshold` in `frontend/jest.config.js` |

The gates live in the runners, not only in Codecov, so a shortfall fails the command that produced it. The ≥90% figure traces to `documentation/Software Project Proposal.md`, acceptance group 10 ("Testing Artifacts", lines 505–508). The backend gate is scoped to those four packages rather than the whole `app` tree because some branches are provably unreachable; see [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) for that reasoning, and [`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md) for measured figures.

**`--cov-fail-under` needed configuration to mean what it says.** coverage.py compares
`round(total, precision)` against the threshold, and `precision` defaults to **0** — so a threshold of 90
accepted anything from 89.5% upward while pytest-cov's message, which uses the unrounded value, printed
`FAIL`. Measured before the fix: `pytest --cov=app --cov-fail-under=90` printed
`FAIL … Total coverage: 89.93%` and **exited 0**. `backend/.coveragerc` sets `precision = 2`, and the same
command now exits **1**. Boundary-checked on the gated scope too: at a measured 91.79%,
`--cov-fail-under=91.79` exits 0 and `91.80` exits 1. Those two totals - 89.93% whole-tree and 91.79%
gated - are what the tree measured when the defect was reproduced; the same two commands read **90.97%**
and **93.33%** today, and the demonstration holds with either pair substituted. Every backend percentage
is therefore reported to
two decimals — a figure quoted as a whole number predates this and is stale. Recorded as
[`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) row `D252`; the mechanism is written up in
[`backend/tests/README.md`](backend/tests/README.md) §9.

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
| Commit | Measured against `8a255fb`, the commit that introduced `backend/.coveragerc`. Check it out and re-run to reproduce both figures |
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
| `backend/tests/` | Suite-level guards that belong to no layer: `test_dependency_closure.py` and `test_coverage_gate.py` |
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

The two Codecov upload steps in `.github/workflows/ci.yml` were **reused**, and their `backend` and `frontend` flags are unchanged - but both `file:` paths were **repointed** at the artifacts that are actually produced: `./coverage.xml` became `./backend/coverage.xml`, and `./coverage/coverage-final.json` became `./frontend/coverage/coverage-final.json`. That second path is why `'json'` is a required entry in `coverageReporters` rather than an optional extra. The JUnit reporters on all three suites, the additional coverage reporters, and the collection-integrity gate were **added**. Every path listed above is ignored by the root `.gitignore`, so no artifact is committed. A dashboard layout over these feeds is in [`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md).
| Artifact | Written by | Retained by CI |
| --- | --- | --- |
| `backend/reports/junit.xml` | the backend test command | yes — artifact `build-test-evidence`, 30 days |
| `backend/reports/collect-only.txt` | the backend readiness step | yes — `build-test-evidence` |
| `backend/coverage.xml` | `--cov-report=xml` | yes — `build-test-evidence`, and the `backend`-flagged Codecov upload |
| `backend/coverage.json` | `--cov-report=json` | yes — `build-test-evidence` |
| `backend/coverage.lcov` | `--cov-report=lcov` | **no** — local only; the CI command does not request this reporter |
| `frontend/reports/jest-junit.xml` | the `jest-junit` reporter | yes — `build-test-evidence` |
| `frontend/reports/list-tests.txt` | the frontend readiness step | yes — `build-test-evidence` |
| `frontend/coverage/` — `lcov.info`, `lcov-report/`, `coverage-final.json`, `coverage-summary.json`, `cobertura-coverage.xml` | the five configured coverage reporters | yes — `build-test-evidence`, and `coverage-final.json` is the `frontend`-flagged Codecov upload |
| `e2e/reports/e2e-junit.xml` | Playwright's `junit` reporter | yes — artifact `e2e-test-evidence` |
| `e2e/reports/list-tests.txt` | the E2E readiness step | yes — `e2e-test-evidence` |
| `e2e/playwright-report/` | Playwright's `html` reporter | yes — artifact `playwright-report` |
| `e2e/test-results/` | trace, screenshot and video, **on failure only** | yes — artifact `e2e-failure-artifacts`, `if-no-files-found: warn` because a passing run legitimately writes nothing there |

Two workflow steps read the JUnit streams before those uploads and fail with an explicit annotation when a
report is missing, empty, or declares zero test cases — so a collection-time stub can never be published
as a run.

The two Codecov upload steps, and their `backend` and `frontend` flags, were **reused** unchanged; they
gained a repointed path, `fail_ci_if_error: true`, and a condition tying them to a producer step that
succeeded. The JUnit reporters on all three suites, the additional coverage reporters, the readiness steps
and the artifact retention were **added**.

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

Improvements discovered while building the test suite. **None of them was attempted here** — each falls outside the scope of adding tests, and each is left exactly as it was found.

- **Not attempted** — correct the stale product identity in this README, which describes an unrelated static-analysis tool rather than the Twitter-monitoring service this repository implements.
- **Not attempted** — reconcile the port mismatch between this README, `infrastructure/docker/docker-compose.yml` and `infrastructure/docker/nginx.conf`.
- **Done, within the authorized surface** — the five packages the source imports and no manifest declared (`react-router-dom`, `@reduxjs/toolkit`, `react-redux`, `zod`, `dayjs`) are now declared in `frontend/package.json`, at exact versions, because the suites cannot run without them. They sit in `devDependencies` alongside the other test dependencies, since AAP §0.5.3 scopes changes to that file to devDependencies and test scripts. **Still not attempted:** moving the four of them that are genuine *runtime* imports into `dependencies`, which is a packaging decision this work has no mandate to make.
- **Not attempted** — raise `python-jose[cryptography]` above `3.3.0` in `backend/requirements-dev.txt`. That version is the one the agreed dependency inventory fixes, and it is affected by CVE-2024-33663 and CVE-2024-33664, both fixed in 3.4.0. No test here reaches either — the suite round-trips one HS256 token with an explicit key and never decrypts a JWE or loads an OpenSSH ECDSA key — so the exposure is to future production use of this dependency, and changing an agreed pin is a decision for the repository's owners.
- **Not attempted** — commit lockfiles for `frontend/` and `e2e/` so that installs are reproducible and `npm ci` becomes usable.
- **Not attempted** — raise the Node floor and move `@playwright/test` past 1.44.1, which is the last release supporting the declared Node 16.x and carries the browser-downloader CVE that forces the out-of-band browser provisioning described above. A newer runner would let a script obtain the browser again.
- **Not attempted** — run `.github/workflows/ci.yml` on GitHub Actions from a branch and confirm it there. Every statement about CI in this repository's documentation describes the workflow file; the pipeline itself has never executed.
- **Not attempted** — add the missing `frontend/tsconfig.node.json`, or drop the dangling project reference to it, so that `.tsx` transforms and `npm run build` work.
- **Not attempted** — supply an HTML entry point and a `frontend/vite.config.ts` so that the application can actually be served.
- **Not attempted** — repair the invalid reducer imports in `frontend/src/store/index.ts`, and export the `useAppDispatch` and `useAppSelector` hooks that three page modules import.
- **Not attempted** — implement the missing `TweetCard` component, the `getTweets` and `setupInterceptors` exports, and the `Chart.register` call that chart construction requires. Note that chart construction is wrapped by nothing, so supplying the registration makes a failure there propagate out of the effect and unmount the component.
- **Not attempted** — give the analytics chart canvas an accessible name and description, or a table or textual summary of the series. It is a bare `<canvas>` today, so the whole of the analytics content is absent from the accessibility tree.
- **Not attempted** — announce loading and live updates: the tweet-list loading indicator is a plain `div` in a container that is not a live region, and the 30-second polled feed declares no live region either, so neither is audible to a screen reader.
- **Not attempted** — give the Twitter credential save a pending state. The control is never disabled and never carries `aria-busy`, so a second activation while the first write is open issues a second credential write and opens a second dialog.
- **Not attempted** — mask every credential field and state an intentional autofill policy. `API Key` and `Access Token` render as `type="text"` today, so both are on screen in clear text while only the `Secret`-suffixed fields are masked.
- **Not attempted** — resolve the SQLAlchemy-against-Firestore mismatch in the routes module.
- **Not attempted** — add the missing `add_response` helper to `backend/app/db/firestore.py`, which `backend/app/tasks/response_generator.py` imports.
- **Not attempted** — repair the `flake8 .`, `mypy .` and `npm run lint` steps in `.github/workflows/ci.yml`; no linter is declared and the sources do not typecheck. Until they pass, the `build` job's overall conclusion stays red even though both test steps succeed.
- **Not attempted** — raise the declared Node ceiling so `@playwright/test` >= 1.55.1 becomes available. That release carries the fix for CVE-2025-59288, which is the only reason the `e2e` job must be handed a browser provisioned out of band instead of installing one.
- **Not attempted** — align the `/health` health checks in `infrastructure/docker/docker-compose.yml` and `.github/workflows/cd.yml` with a route that actually exists.
- **Not attempted** — remove the `postgres:13` service and the `DATABASE_URL` variable, neither of which the Firestore and BigQuery application uses.

The complete register, together with the reasoning behind every item, is in [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md).
