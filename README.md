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

Three independent legs, each non-interactive and each runnable on a clean machine.

```bash
# 1. Backend - virtual environment plus the pinned test stack
python3.9 -m venv .venv-backend && . .venv-backend/bin/activate && pip install --upgrade pip && pip install -r backend/requirements-dev.txt

# 2. Frontend
cd frontend && npm install

# 3. End-to-end - needs network access and system packages
cd e2e && npm install && npx playwright install --with-deps chromium
```

- Use `npm install`, **not** `npm ci`. No lockfile is committed in this repository, and `npm ci` refuses to run without one.
- Both stacks are exact-pinned, and several versions are deliberately held below their latest release. See [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) for why those versions and the lockfile posture were chosen.

### Run

Run every backend command from `backend/`. `backend/pytest.ini` sets `pythonpath = .`, and that is what gives every test the single `app.*` import root — invoking `pytest` from the repository root will not resolve imports.

| Goal | Command |
| --- | --- |
| Backend, all layers | `cd backend && pytest` |
| Backend collection-integrity gate | `cd backend && pytest --collect-only -q` |
| Backend coverage with the gate | `cd backend && pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-fail-under=90` |
| Backend unit layer only | `cd backend && pytest tests/unit -m unit` |
| Backend integration layer only | `cd backend && pytest tests/integration -m integration` |
| Frontend, all suites | `cd frontend && npm test` |
| Frontend, watch mode | `cd frontend && npm run test:watch` |
| Frontend, coverage | `cd frontend && npm run test:coverage` |
| Frontend, CI mode | `cd frontend && npm run test:ci` |
| End-to-end | `cd e2e && npx playwright test` |
| End-to-end report | `cd e2e && npx playwright show-report` |

The collection-integrity gate expects **zero errors**. It is the meaningful readiness check here, because this suite's historical failure mode was import errors rather than failed assertions: a clean collection proves every test module is importable before any assertion is evaluated.

### Coverage gates

| Scope | Gate | Enforced by |
| --- | --- | --- |
| `backend/app/core`, `backend/app/services`, `backend/app/tasks`, `backend/app/db` | ≥90% line coverage | `pytest --cov-fail-under=90` |
| `frontend/src/store`, `frontend/src/schema`, `frontend/src/services` | ≥80% line coverage | Jest `coverageThreshold` in `frontend/jest.config.js` |

The gates live in the runners, not only in Codecov, so a shortfall fails the command that produced it. The ≥90% figure traces to `documentation/Software Project Proposal.md`, acceptance group 10 ("Testing Artifacts", lines 505–508). The backend gate is scoped to those four packages rather than the whole `app` tree because some branches are provably unreachable; see [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md) for that reasoning, and [`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md) for measured figures.

### Where the tests live

| Path | Contents |
| --- | --- |
| `backend/tests/unit/` | One unit module per backend production module |
| `backend/tests/integration/` | The FastAPI HTTP surface, driven through Starlette's `TestClient` |
| `backend/tests/conftest.py` | Shared fixtures, environment seeding, credential neutralizer, socket guard |
| `backend/tests/factories.py` | Deterministic payload and duck-object builders |
| `frontend/src/**/*.test.ts(x)` | Colocated beside the module under test |
| `frontend/src/test-utils/` | Render helper, factories, msw server and handlers, module stubs |
| `e2e/tests/*.spec.ts` | Route flows driven against the harness in `e2e/harness/` |

### Common pitfalls

1. **Seed environment variables at `conftest.py` module scope, never in a fixture.** `backend/app/core/config.py` runs `settings = Settings()` at import time with nine required fields, so an `autouse` fixture executes too late to help.
2. **Always patch `app.db.firestore.get_db`.** `google.auth.default()` can resolve in this environment, so an unpatched call performs a real Google Cloud round trip. The suite installs an autouse credential neutralizer and a socket guard so that an unmocked call fails loudly instead of escaping.
3. **Never call `start_tweet_stream()` or `start_twitter_stream()` without patching `tweepy`.** Both terminate in a live Twitter connection and will hang the interpreter.
4. **Let msw intercept all frontend HTTP.** The server runs with `onUnhandledRequest: 'error'`; an unmocked `axios` call opens a real socket whose rejection can settle inside a *later* test and fail it. The axios base URL evaluates to the literal string `"undefined"`, so handlers match on wildcard hosts.

### How to extend

- **Placement** — mirror the `app/` layout under `backend/tests/unit/`; colocate `<Name>.test.ts(x)` beside its frontend subject; add a new browser flow as a spec under `e2e/tests/`.
- **Naming** — `test_<layer>.py` for modules, `test_<operation>` and `test_<operation>_<scenario>` for functions, `mock_<entity>` for fixtures.
- **Shared setup** — put it in `backend/tests/conftest.py` or `frontend/src/test-utils/` and import it from there. Never copy-paste setup into a test.
- **Patch targets** — patch the **importing** module's boundary, for example `app.services.llm_service.Completion.create`, never the third-party library itself.

### Reporting artifacts

| Suite | Artifacts |
| --- | --- |
| Backend | `backend/reports/junit.xml`, `backend/coverage.xml`, `backend/coverage.json`, `backend/coverage.lcov` |
| Frontend | `frontend/reports/jest-junit.xml`, `frontend/coverage/lcov.info`, `frontend/coverage/coverage-final.json`, `frontend/coverage/coverage-summary.json` |
| End-to-end | `e2e/playwright-report/`, `e2e/reports/e2e-junit.xml`, `e2e/test-results/` |

The two Codecov upload steps in `.github/workflows/ci.yml`, and their `backend` and `frontend` flags, were **reused** unchanged. The JUnit reporters on all three suites, the additional coverage reporters, and the collection-integrity gate were **added**. Every path listed above is ignored by the root `.gitignore`, so no artifact is committed. A dashboard layout over these feeds is in [`docs/testing/DASHBOARD-TEMPLATE.md`](docs/testing/DASHBOARD-TEMPLATE.md).

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
- **Not attempted** — declare the five frontend runtime packages that the source imports but no manifest declares: `react-router-dom`, `@reduxjs/toolkit`, `react-redux`, `zod` and `dayjs`.
- **Not attempted** — commit lockfiles for `frontend/` and `e2e/` so that installs are reproducible and `npm ci` becomes usable.
- **Not attempted** — add the missing `frontend/tsconfig.node.json`, or drop the dangling project reference to it, so that `.tsx` transforms and `npm run build` work.
- **Not attempted** — supply an HTML entry point and a `frontend/vite.config.ts` so that the application can actually be served.
- **Not attempted** — repair the invalid reducer imports in `frontend/src/store/index.ts`, and export the `useAppDispatch` and `useAppSelector` hooks that three page modules import.
- **Not attempted** — implement the missing `TweetCard` component, the `getTweets` and `setupInterceptors` exports, and the `Chart.register` call that chart construction requires.
- **Not attempted** — resolve the SQLAlchemy-against-Firestore mismatch in the routes module.
- **Not attempted** — add the missing `add_response` helper to `backend/app/db/firestore.py`, which `backend/app/tasks/response_generator.py` imports.
- **Not attempted** — repair the `flake8 .`, `mypy .` and `npm run lint` steps in `.github/workflows/ci.yml`; no linter is declared and the sources do not typecheck.
- **Not attempted** — align the `/health` health checks in `infrastructure/docker/docker-compose.yml` and `.github/workflows/cd.yml` with a route that actually exists.
- **Not attempted** — remove the `postgres:13` service and the `DATABASE_URL` variable, neither of which the Firestore and BigQuery application uses.

The complete register, together with the reasoning behind every item, is in [`docs/testing/DECISION-LOG.md`](docs/testing/DECISION-LOG.md).
