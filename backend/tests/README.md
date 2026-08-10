# Backend test suite

Everything you need to run, understand, and extend the tests under `backend/tests`.

This suite is the first executable test coverage this repository has ever had. It asserts what the
production code **actually does today**, including the places where that diverges from the design
documents, because a test that asserts an intention the code does not implement fails for the wrong
reason and teaches nobody anything.

**Current state:** 1096 tests collected, 1093 passing, 3 skipped with reasons, 93.33% line coverage on
the four gated packages. `pytest --collect-only -q` reports zero errors.

**That is a warm reading.** A first run in a fresh clone
reports **1091 passed and 5 skipped on a first pass**, and both figures are correct.
Two cases read an artifact a *previous* run wrote, and both
artifacts are gitignored, so neither exists yet: `tests/test_coverage_gate.py` reads
`backend/coverage.json`, which §8's gated command writes, and `tests/test_docs_contract.py` reads
`e2e/reports/e2e-junit.xml`, which the end-to-end suite writes. Each skips with a reason naming the
artifact rather than failing on its absence, which is the honest disposition for a case whose subject
has not been produced. Run the gated command once — and the e2e suite once, if you want the second —
and every later run reads 1093/3. The collected total is 1096 either way and nothing fails.

Those are measurements from CPython 3.9.13 with `backend/requirements-dev.txt` installed, read out of
`backend/reports/junit.xml` and `backend/coverage.json`. Every figure in this document names the command
that produced it, the runtime it ran on and the artifact it was read from. The fourth element of
provenance — the commit whose tree was measured — is recorded by the tooling rather than transcribed
here, because a hash written into prose necessarily names a tree older than the run it claims to
describe, and an earlier revision of this page proved the hazard by citing a commit that is not a git
object in this repository at all. Run `python docs/testing/dashboard-extract.py` and read
**§1.0 Provenance of this reading** in its output: the branch and commit there are, by construction, the
tree your own figures were measured on. None of this is a target — re-run before quoting any of it. §8
lists the artifacts and which of them a CI run retains.

---

## What this document is, and what it is not

| | |
|---|---|
| **This document covers** | The backend-specific depth: how the single import root works, the fixture and factory catalogues, the per-dependency mocking strategy, the pitfalls, how to extend the suite, and the suggested next tasks. |
| **The root [`README.md`](../../README.md) covers** | The whole-repository view — the runtime contract, all three install legs, the top-level commands, the coverage-gate summary and the reporting-artifact paths. Its `## Testing` section links here. Start there if you want the frontend or end-to-end suites; per the **Onboarding & Continued Development** rule this file fills the gap the root cannot carry rather than restating it. Only the runtime and the one install command are repeated below, so that this page stands alone. |
| **[`docs/testing/DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) covers** | *Why* each contestable choice was made, with the alternatives weighed and the risks accepted. The **Explainability** rule puts rationale there and only there, so this page confines itself to *what* and *how* and links across rather than re-arguing a decision. The sections most relevant here are §2 (backend test infrastructure), §7 (coverage scope and gates), §8 (observability of the test system), §22 (the two authorized production touches) and §23 (the noted-but-not-fixed register). |
| **[`docs/testing/TRACEABILITY-MATRIX.md`](../../docs/testing/TRACEABILITY-MATRIX.md) covers** | The bidirectional record: every legacy test to its replacement or its recorded disposition, and every new artifact back to the construct it covers. |

Where this page describes a production defect the suite has to work around, that is **specification**,
not rationale — you cannot read the tests without it, so it lives here.

---

## 1. Runtime and install

### The runtime is Python 3.9

`.github/workflows/ci.yml` pins `python-version: [3.9]`, and that is the only place in the repository
where a Python version is declared as a **ceiling**. The root `README.md` says "Python 3.8+", which is
a lower bound only; it does not authorise 3.10 or later, and several pins below have no wheels for
newer interpreters.

> **Your ambient interpreter is almost certainly not 3.9.** Use a virtual environment. Running the
> suite on a modern interpreter does not produce a handful of failures you can triage — it produces
> a wall of collection errors, because `app/core/config.py` line 1 does `from pydantic import
> BaseSettings`, which **pydantic 2.x removed**. The failure is at import, not at assertion, so
> nothing at all is measured.

```bash
# from the repository root
python3.9 -m venv .venv-backend
. .venv-backend/bin/activate          # Windows: .\.venv-backend\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt
```

`.venv-backend/` is listed in `.gitignore`, so it never reaches a commit.

### The manifest

[`backend/requirements-dev.txt`](../requirements-dev.txt) is the **only** Python manifest in the
repository. There is no `requirements.txt`, no `pyproject.toml`, no `setup.cfg` and no `tox.ini`
anywhere in the tree, so nothing else can be installed from and nothing else can drift.

Every entry is an exact `==` pin, and the way to hold an environment to them is to rebuild it from
this file rather than to patch it in place. `pip check` is not that gate: it verifies that installed
distributions satisfy one another's declared ranges, and stays silent when an installed version
merely differs from a manifest pin. `pip install -r backend/requirements-dev.txt` — the command
`ci.yml` runs and the one the install section above gives — is what makes the two agree.

### Pins that are hard constraints, not preferences

Changing any of these breaks the suite outright rather than shifting a number.

| Pin | Why it cannot move |
|---|---|
| `pytest==8.4.2` | The 9.x line drops Python 3.9 support. 8.4.2 is the last release that runs on the documented runtime. |
| `httpx==0.27.2` | **Must stay below 0.28.** 0.28 removed the `app=` shortcut that starlette 0.27's `TestClient` passes to `httpx.Client`. On 0.28 the client cannot be constructed at all — `TypeError: __init__() got an unexpected keyword argument 'app'` — so every integration test errors during setup. The deprecation warning 0.27.2 emits is suppressed by a `filterwarnings` entry in `pytest.ini`. |
| `pydantic==1.10.13` | v1 only. `app/core/config.py` imports `BaseSettings` from `pydantic`, which does not exist in v2. Several assertions also depend on v1 semantics — notably that v1 strips declared fields from the model **class** namespace. |
| `tweepy==3.10.0` | Below 4.0 only. `StreamListener` was removed in 4.x, and both production listeners subclass it. |
| `openai==0.27.8` | 0.x only. `from openai import Completion` was removed in 1.x. |
| `bcrypt==4.0.1` | passlib 1.7.4 cannot drive the 5.x line. A silent upgrade does not change a password assertion, it breaks every one. |
| `numpy==1.24.4` | 2.x is binary-incompatible with pandas 1.5.3 (`numpy.dtype size changed`), and `analytics_service` aggregates through a pandas `DataFrame`. |
| `python-jose[cryptography]==3.5.0` | The JWT implementation the whole token surface runs on. Pinned **above** CVE-2024-33663 (algorithm and key confusion) and CVE-2024-33664 (compressed-JWE decompression bomb), which affect 3.3.0 and are fixed in 3.4.0. Verified on CPython 3.9.13: the whole suite passes at 3.5.0, and `app/core/security.py`'s `from jose import jwt` surface is unchanged from 3.3.0. |
| `grpcio==1.80.0`, `grpcio-status==1.62.3` | Declared because `tests/conftest.py` patches `grpc`, `grpc.aio` and `grpc._channel` **directly** — by module name rather than by import, which is why a static import scan does not see them. `test_dependency_closure.py` enforces that direction of the closure. `grpcio-status` stays on the 1.62 line: 1.63 and later require `protobuf >= 6.31.1`, which the pinned `google-*` distributions cap below 5. |

The rest of the manifest is the test stack (`pytest-asyncio`, `pytest-cov`, `coverage`, `freezegun`,
`pytest-xdist`) plus the runtime stack the tests exercise. `starlette==0.27.0` is a **documented
exception** covering GHSA-f96h-pmfr-66vw / CVE-2024-47874 and GHSA-86qp-5c8j-p5mr / CVE-2026-48710,
neither of which can be closed without replacing `fastapi==0.95.2`. The manifest itself carries no
rationale — Rule 1 keeps that in one place — so read
[`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) rows `D102` and `D164` before proposing a bump.
`integration/test_route_surface.py` covers the reachable half of the second advisory.

---

## 2. The single import root, and why the working directory matters

**Every backend test imports from `app.*` and nothing else.**

That single root is the headline fix in this suite. The three legacy modules used three mutually
exclusive roots — `app.main`, `services.*` and `backend.tasks` — of which at most one could ever have
resolved, and that is a large part of why not one of them could be collected.

The root is established **structurally**, by configuration and by where you stand, never by code
inside a test file:

1. `pythonpath = .` in [`backend/pytest.ini`](../pytest.ini) puts the directory containing `app/` on
   `sys.path`.
2. You run pytest **from `backend/`**, which is what makes `.` mean `backend/`.

> **No test file may manipulate `sys.path`.** If a new suite needs a path hack to import its subject,
> the suite is being run from the wrong directory. Fix the directory.

### Why the working directory carries that responsibility

Because pytest has no ini setting that can carry it. `rootdir` is **not** a valid ini key — put it in
a config file and pytest answers:

```text
PytestConfigWarning: Unknown config option: rootdir
```

It is a computed value, not a declarable one. So the invocation directory is the mechanism, and
getting it wrong is not a subtle failure. Imports themselves do resolve from the repository root —
`tests/` is a package, so pytest's prepend import mode puts `backend/` on `sys.path` — and that is what
makes the failure quiet rather than obvious: a root-level `pytest` collects all 1096 tests and then
**fails 21 of them** with warnings on every marker, because `backend/pytest.ini` is not the active
config file at that level, so `asyncio_mode = auto` is not in effect and every async test is
mis-handled. Always:

```bash
cd backend && pytest
```

### Package-marker policy

`__init__.py` exists in exactly three places, and nowhere else:

```text
backend/tests/__init__.py
backend/tests/unit/__init__.py
backend/tests/integration/__init__.py
```

All three are empty. They are there so the test packages are explicit and two suites in different
directories may share a module name.

`backend/app/` is deliberately a **PEP 420 implicit namespace tree** with no markers at all, and the
`app/api/routes/` package created by the first authorized production touch has none either, matching
the convention already in the repository. Do not add one — the namespace layout is what `pythonpath`
resolves against.

---

## 3. Layout and markers

```text
backend/
├── pytest.ini                     # the only runner configuration
├── .coveragerc                    # the reported precision the rounded gate compares at
├── requirements-dev.txt           # the only Python manifest
└── tests/
    ├── __init__.py
    ├── conftest.py                # shared infrastructure: prologue, guards, every shim, all fixtures
    ├── factories.py               # deterministic data builders
    ├── coverage_gate.py           # the exact gate — a module, not a test: run after the gated suite
    ├── test_coverage_gate.py      # gate contract: the rounded band, the exact rejection, the CI wiring
    ├── test_dependency_closure.py # environment gate: manifest ⇄ installed, and use ⇒ manifest
    ├── test_guard_contract.py     # infrastructure gate: the guarantees conftest.py makes
    ├── test_dashboard_extract.py  # artifact contract of docs/testing/dashboard-extract.py
    ├── test_docs_contract.py      # the arithmetic the Rule 1 and Rule 2 documents state
    ├── unit/                      # 12 suites: one per production module, plus the egress guard’s own
    │   ├── __init__.py
    │   ├── test_api_dependencies.py
    │   ├── test_core_config.py
    │   ├── test_core_security.py
    │   ├── test_db_bigquery.py
    │   ├── test_db_firestore.py
    │   ├── test_egress_guard.py
    │   ├── test_schema.py
    │   ├── test_services_analytics.py
    │   ├── test_services_llm.py
    │   ├── test_services_twitter.py
    │   ├── test_tasks_response_generator.py
    │   └── test_tasks_tweet_processor.py
    └── integration/               # 3 suites over the HTTP surface that exists
        ├── __init__.py
        ├── conftest.py            # client + dependency_overrides contract
        ├── test_app_lifecycle.py
        ├── test_http_tweets.py
        └── test_route_surface.py
```

### The three layers

**`unit/` — one module per production module, 12 suites.** Eleven have a production module as their
subject; the twelfth, `test_egress_guard.py`, has the suite's own egress guard as its subject and lives
here because it is a unit test like any other. Every external client is patched at the *importing*
module's boundary (§6), so no unit test constructs a Google Cloud client, opens a socket or reads a
clock. This is where the boundary matrices and the error-disposition assertions live.

**`integration/` — 3 suites, the real HTTP surface only.** Exercised through
`app.dependency_overrides`, which is keyed on the `app.db.firestore.get_db` function object. The
implemented surface is three operations on one prefix-less router: `GET /tweets`,
`GET /tweets/{tweet_id}` and `POST /tweets/{tweet_id}/responses`. There is no `/users`, no
`/analytics`, no `/config`, no `/token` and no `/health`, and no route carries the `API_V1_STR`
prefix even though the setting declares `/api/v1`. `test_route_surface.py` asserts that census as a
404 inventory rather than leaving it implied.

**The `tests/` root — five suites whose subject is this repository, not `app/`.** Every test under `unit/`
and `integration/` asserts a production module; these five assert the things those assertions rest on, and
the extractor reports them together as the `Backend other` layer:

| Suite | Subject | Cases |
|---|---|---|
| `test_dependency_closure.py` | `backend/requirements-dev.txt` — every active line an exact pin, every pin the installed version | 72 |
| `test_coverage_gate.py` | `backend/.coveragerc` — the `precision` `--cov-fail-under` compares at, and the band it admits | 62 |
| `test_guard_contract.py` | `conftest.py`'s own guards — credential non-disclosure, endpoint ownership, child-process refusal | 168 |
| `test_dashboard_extract.py` | `docs/testing/dashboard-extract.py` — its `REQUIRED` contract, its twelve-gate frontend minimum, and the per-layer refusal of a partial result stream | 39 |
| `test_docs_contract.py` | the arithmetic `docs/testing/TRACEABILITY-MATRIX.md` and `docs/testing/DASHBOARD-TEMPLATE.md` state, Rule 4's word and bullet caps on `blitzy-deck/executive-summary.html`, and the reporter override every partial-capable `e2e` script pins | 96 |

`test_guard_contract.py` is worth reading first. Every other suite here rests on three promises — that a
failure message never prints a credential, that a loopback port is authorized only while this process holds
it, and that a child process is refused in every phase rather than only inside a test — and each of
those was once true only in the common case. Two of its probes run where no test is running: one at the
module's own scope, which pytest evaluates during collection, and one in a module-scoped finalizer that
runs after the per-test guard attribution has been cleared. Both name a command that exists nowhere, so a
missing guard fails loudly instead of spawning anything. Its child-process half judges an invocation on
**structure** rather than on the text of a rendered command line: `os.system` is refused for every command,
and `subprocess.Popen` is admitted only for a three-member argument vector whose executable resolves
through `realpath` to a trusted `cmd.exe` and whose remaining members are exactly `('/c', 'ver')`, with no
truthy `shell` and no untrusted `executable=` override. Forty-five of its cases are the negative side of
that rule.

The child-process promise is the one that had been narrowest, and it is worth being exact about what it
now covers, because the earlier wording of this paragraph was true of two entry points and false of
eleven. The guard patches **24** process-creation sites in three declared groups: the factories that
carry a command in a known argument and are judged against the allow-list; `_winapi.CreateProcess`,
which needs its own renderer because `subprocess` passes `None` as the application name and the command
in the second argument — and which is the route `subprocess` actually takes on Windows; and 21
unconditional ones, being the eight `os.spawn*`, both `posix_spawn*`, `fork`, `forkpty`, the eight
`exec*`, and `multiprocessing.process.BaseProcess.start`. This suite does not list those sites a second
time: it derives its probe set from the same three tuples the guard declares, and fails if a probe names
a target no group declares or if any group goes unprobed — so the code and this document cannot drift
apart without a red test. All nine entry points that exist on Windows were confirmed to refuse. See
`docs/testing/DECISION-LOG.md` row D311.

### Markers

Two markers are declared in `pytest.ini`, and `--strict-markers` is on by way of `addopts`:

| Marker | Selects |
|---|---|
| `unit` | Isolated unit tests; every external client and boundary is patched. |
| `integration` | Tests driving the FastAPI HTTP surface through starlette's `TestClient`. |

Because `--strict-markers` is active, a typo is a **hard error** rather than a silent selection of
nothing. Add a new marker to `pytest.ini` before you use it.

### The integration client contract

Two details in [`integration/conftest.py`](integration/conftest.py) are load-bearing, and a new
suite that ignores either one will behave strangely:

- **The client is built in a fixture, never at module scope.** The legacy `test_api.py` shared one
  module-level `TestClient` across twelve `unittest.TestCase` methods that ran in alphabetical order,
  so `test_delete_tweet` deleted the record `test_get_tweet` then read. Every fixture in the
  integration layer is function-scoped, so no suite imposes an ordering requirement on another.
- **`TestClient(app)` is constructed *without* the `with` context manager.** Entering it as a context
  manager runs the registered `startup` handler, which calls `get_db()` and then
  `await start_tweet_stream()` — a live Twitter connection (§7). Constructing the client plainly
  leaves both lifecycle handlers registered and never invoked, which is exactly the behaviour
  `test_app_lifecycle.py` asserts. Each client is still `close()`d on teardown, which releases the
  `httpx` transport without invoking a handler.

Requests travel over starlette's in-process ASGI transport, so serving one opens no socket.

---

## 4. Fixture catalogue

All shared infrastructure lives in [`conftest.py`](conftest.py) and, for the HTTP layer only, in
[`integration/conftest.py`](integration/conftest.py). Nothing is copy-pasted between suites, and the
five import shims exist **only** in the parent conftest — no test file installs its own.

### 4.1 The module-scope prologue — not fixtures, and that is the point

The first thing `conftest.py` does, at **module scope**, before pytest has created a single fixture:

| Step | What it does |
|---|---|
| Snapshot | Records the current value of every environment variable it is about to touch, so `pytest_unconfigure` can hand the process its own environment back. |
| Seed the eight required settings | Assigns a placeholder to each `Settings` field declared without a default. |
| Pin the defaulted settings | Assigns each declared default explicitly, so a `.env` on disk or an ambient variable cannot decide a value a suite asserts against. |
| Neutralise the unpinnable names | Deletes `NOTION_API_KEY` (declared `Optional[str] = None`, which no string assignment reproduces) and `TWITTER_CONSUMER_KEY` / `TWITTER_CONSUMER_SECRET` (read by production, declared by nothing), so a real secret exported by the surrounding machine cannot reach a production module. |
| Point credentials at nothing | Sets `GOOGLE_APPLICATION_CREDENTIALS` to a path inside `tests/` that does not exist. |
| Install the `Optional` shim | `builtins.Optional = typing.Optional`. |
| Neutralise ambient Google credentials | Starts a patch on `google.auth.default`. |
| Install the egress guard | Deny-by-default network refusal, in force from here until `pytest_unconfigure`. |

**Why module scope and not an `autouse` fixture.** `app/core/config.py` line 28 executes
`settings = Settings()` at **import**, and eight further production modules build their own
`Settings()` at their own module scope. pytest imports every test module during **collection**, which
happens before any fixture runs. An `autouse` fixture is therefore always too late: by the time it
executes, the settings objects the production code will use for the whole session have already been
constructed. The same ordering argument applies to the `Optional` shim, to the credential patch, and
to the egress guard — `app/db/firestore.py` and `app/db/bigquery.py` each construct a Google Cloud
`Client()` at module scope, which collection triggers.

Two consequences worth internalising:

- **Assignment is unconditional, not `setdefault`.** A real credential present in your shell must not
  be able to win, because a suite running against one is neither deterministic nor offline.
- **The names are upper-case exactly.** `Settings.Config.case_sensitive` is `True`, so
  `secret_key` is not `SECRET_KEY`.

The **eight** fields `app/core/config.py` declares without a default, all of which the prologue
seeds — importing `app.core.config` without any one of them raises a pydantic `ValidationError`:

```text
SECRET_KEY                    TWITTER_ACCESS_TOKEN_SECRET
TWITTER_API_KEY               OPENAI_API_KEY
TWITTER_API_SECRET            GOOGLE_CLOUD_PROJECT
TWITTER_ACCESS_TOKEN          BIGQUERY_DATASET
```

Eight, not nine: `NOTION_API_KEY` is `Optional[str] = None` and is required by nothing.

Every seeded value is an obvious placeholder. **The suite uses no real credential anywhere**, and you
need to export nothing to run it.

### 4.2 The autouse fixtures

Three, and you never request them — they apply to every test.

| Fixture | Scope | What it guarantees |
|---|---|---|
| `verify_settings_singletons` | session | Asserts that the settings objects production code actually reads are the synthetic ones — `app.core.config.settings` plus the independent `Settings()` that `app/main.py`, `app/core/security.py`, the three services and the two tasks each build. Anything the environment could not reach, such as a `backend/.env` that `Settings.Config.env_file` names, is caught here instead of surfacing as an unexplained failure somewhere downstream. It also loads `pydantic` before any test can freeze the clock. |
| `neutralize_google_credentials` | function | **The credential neutraliser.** Replaces `google.auth.default` with a stand-in returning a `MagicMock` credential and the fake project, and patches the `default` name that `app.db.firestore` bound into its own namespace. It *returns* rather than raises, so a code path that reaches for a real client surfaces as a network refusal instead of masquerading as a credential error. |
| `block_network_access` | function | **The socket guard's attribution hook.** The guard itself is installed by the prologue and released only by `pytest_unconfigure`; this fixture names the running test in every refusal. It contributes attribution and nothing else, so no window exists in which egress is permitted. Refused: `socket.connect` / `connect_ex` / `sendto`, `socket.create_connection`, five DNS resolvers, `_overlapped.ConnectEx` on Windows, the gRPC channel factories, and child-process creation. Allowed: `AF_UNIX`, and loopback ports **this process itself bound** — not the whole loopback interface, which under parallel execution would admit another checkout's server. |

### 4.3 The named fixtures

Request these by name.

| Fixture | What it yields | The production defect it exists for |
|---|---|---|
| `pinned_settings_env` | A copy of the name-to-value mapping the prologue pinned. | Lets the config suite assert that the values behind its singleton assertions were *positively established*, rather than asserting that your environment happened to be empty. |
| `firestore_client` | A `MagicMock` standing in for the Firestore client, with `app.db.firestore.get_db` patched to return it. | Unpatched, `get_db` resolves credentials and constructs a real client — see pitfall 2. Covers the whole `add_tweet` / `get_tweet` / `update_tweet` surface. |
| `bigquery_settings` | A `SimpleNamespace` substituted for `app.db.bigquery.Settings`, exposing `GOOGLE_CLOUD_PROJECT`. | **The only unlock for that module.** See below. |
| `tweet_processor_module` | `app.tasks.tweet_processor`, imported under an `LLMService` shim. | The module imports `LLMService` from `app.services.llm_service`, which exposes only the free function `generate_response`, and then instantiates it. |
| `response_generator_module` | A freshly loaded `app.tasks.response_generator`, under `add_response` **and** `LLMService` shims. | Two names it imports are defined nowhere. Line 7 runs `llm_service = LLMService()` at module scope, so the module is evicted from `sys.modules` before and after each test and no two tests share a stand-in whose call counts depend on execution order. |
| `app_module` | `app.main`, under **three** shims: `verify_token`, `TwitterService` and `LLMService`. | Each is imported somewhere in `app.main`'s graph and defined by no production module. The `verify_token` shim is also what makes `app.api.dependencies` importable, so the suite covering that module consumes this fixture. All three are **fail-closed** — they refuse every call — which is what keeps the fixture from authorising an arbitrary bearer token. A test wanting a particular result patches the attribute on the module it is exercising. |
| `frozen_clock` | freezegun's `FrozenDateTimeFactory`, frozen at `2024-01-01 00:00:00`. | Removes wall-clock dependence from the JWT-expiry and date-range assertions. It pre-imports `pydantic`, `app.core.config` and `app.core.security` before freezing, because a *first* import of pydantic under a frozen clock raises `TypeError: metaclass conflict` — pydantic declares a class deriving from `datetime.date`, which freezegun has replaced — and leaves the package half-initialised for the rest of the process. |

#### Why `bigquery_settings` is the only way into `app/db/bigquery.py`

`app/db/bigquery.py` reads `Settings.GOOGLE_CLOUD_PROJECT` as a **class** attribute in two places:
line 7 inside `get_bq_client`, and line 21 in the `table_id` f-string. pydantic v1 strips declared
fields from the class namespace, so both reads raise `AttributeError` and `get_bq_client`,
`run_query` and `insert_tweet_analytics` are all unreachable without a substitution.

Two things people try first, and why neither works:

- **Patching `get_bq_client` alone does not help.** Line 21 reads the class attribute *again*, after
  `get_bq_client` has already returned, so `insert_tweet_analytics` still raises.
- **The second authorized production touch cannot fix it either.** That touch declares *instance*
  fields on `Settings`, and pydantic v1 removes declared fields from the class. No declaration can
  make a class-attribute read succeed.

So the substitution is test-side and deliberate. The unpatched `AttributeError` is itself asserted as
current behaviour by `test_db_bigquery.py`, so the defect is recorded rather than merely worked around.

#### Why the `LLMService` shim must be a `MagicMock`

`tweet_processor_module` installs `unittest.mock.MagicMock` itself as the class — one of only two
permissive shims in the suite, and the reason is the behaviour under test.
`TweetStreamListener.on_status` line 32 feeds `self.llm_service.calculate_doubt_rating(text)` straight
into `Tweet(doubt_rating=...)`, and a `MagicMock` coerces to `1.0` through `__float__`. That is what
keeps a status clearing the popularity gate at a pydantic `ValidationError` carrying **exactly eight**
missing field names — the eight required schema fields the listener never supplies. A fail-closed
sentinel would instead abort in `TweetStreamListener.__init__`, and that documented eight-error outcome
would become unobservable.

### 4.4 The five symbols production imports and nothing defines

A newcomer reading a shim naturally assumes a typo. These are not typos. Each name is imported by
production code and **defined by no production module**:

| Symbol | Imported by | Supplied as |
|---|---|---|
| `Optional` | `app/core/security.py` annotates `expires_delta: Optional[timedelta]` without importing it; `app/api/dependencies.py` inherits the failure. Unshimmed: `NameError: name 'Optional' is not defined`. | `builtins.Optional` in the prologue. |
| `LLMService` | `app/api/routes/tweets.py`, `app/tasks/tweet_processor.py`, `app/tasks/response_generator.py`. `app/services/llm_service.py` exposes only `generate_response`. | Permissive `MagicMock` in `tweet_processor_module` and `response_generator_module`; fail-closed in `app_module`. |
| `add_response` | `app/tasks/response_generator.py`. `app/db/firestore.py` exposes only `db`, `get_db`, `add_tweet`, `get_tweet`, `update_tweet`. | `response_generator_module`. |
| `verify_token` | `app/api/dependencies.py`. `app/core/security.py` exposes only `create_access_token`, `verify_password`, `get_password_hash` and `pwd_context`. | Fail-closed in `app_module`. |
| `TwitterService` | `app/api/routes/tweets.py` (imported and never used). `app/services/twitter_service.py` exposes only `TwitterStreamListener` and `start_twitter_stream`. | Fail-closed in `app_module`. |

Each shim is written to the module that *should* define the name **and** to every already-loaded
module that captured it with `from … import …`, then reset on the way out. A fail-closed shim raises
`MissingProductionSymbolError` if production actually calls it, so an accidental dependency on a
stand-in is loud rather than silent.

### 4.5 Integration-layer fixtures

Declared in [`integration/conftest.py`](integration/conftest.py). It installs no shim and seeds no
environment variable — everything shared comes from the parent conftest.

| Fixture | What it yields |
|---|---|
| `main_module` | The imported `app.main` module. Patch `main_module.get_db`, `.start_tweet_stream` or `.settings` when you need the registered handlers to observe the change. |
| `integration_app` | The `FastAPI` instance `app.main` built at import. Neither wiring function is re-run, so `user_middleware` stays one `CORSMiddleware` entry long and each router is included exactly once. |
| `reset_dependency_overrides` | **Autouse.** Empties `app.dependency_overrides` on entry *and* on exit, so the order tests run in is irrelevant and a test that installs an override directly cannot leave one behind. |
| `client` | A `TestClient` that **re-raises** an exception raised inside a handler, so a test can name the type with `pytest.raises`. |
| `client_no_raise` | The same client with `raise_server_exceptions=False`, so an unhandled handler exception surfaces as `status_code == 500`. Several endpoints need both views (§9). |
| `mock_db` | An unprogrammed `MagicMock` standing in for the object `Depends(get_db)` yields. Program only the call chain your endpoint reaches. |
| `override_get_db` | A callable that installs an object in place of `get_db`, keyed by **object identity** on the function the router captured in its `Depends(get_db)` default. |

```python
def test_lists_tweets(client, mock_db, override_get_db):
    override_get_db(mock_db)
    response = client.get("/tweets")
```

---

## 5. Factory catalogue

[`factories.py`](factories.py) imports nothing but the standard library, declares no fixture, and
performs no I/O, no logging and no clock read. Every default is a literal, so two no-argument calls
compare equal; every keyword you pass is deep-copied on the way in, so no result shares a mutable
object with another result, with the module's defaults, or with your argument. Vary one field at a
time rather than writing a second literal.

### `make_tweet(**overrides) -> dict`

All ten fields `app/schema/tweet.py` declares, so `Tweet(**make_tweet())` constructs:

```text
tweet_id  content  user_id  timestamp  likes_count
retweets_count  doubt_rating  ai_tools  media_urls  quoted_tweet_id
```

`timestamp` is a real `datetime.datetime`, which is the type the field declares. Nine fields are
required; `quoted_tweet_id` carries a declared default of `None`. Rejection cases are produced by
deleting a key, never by inventing a second payload:

```python
make_tweet()                                    # schema-valid
make_tweet(doubt_rating=0.9)                    # one field varied
payload = make_tweet(); del payload["content"]  # rejection case
```

### `make_response(**overrides) -> dict`

Keyed `tweet_id`, `response`, `generated_at`. The first two are the values
`app/tasks/response_generator.py` passes to `add_response`, and `response` is the body key the
responses endpoint returns. **No response schema exists in production**, so this shape claims
conformance to none — do not treat it as a contract.

### `make_analytics_row(kind="tweet", **overrides) -> dict`

One BigQuery result row. The key sets are the single easiest thing in this suite to get wrong,
because they are the SQL **aliases** `app/services/analytics_service.py` selects and then indexes on
the `DataFrame` — *not* the underlying column names:

| `kind` | Keys | Consumed by |
|---|---|---|
| `"tweet"` | `date`, `tweet_count`, `avg_retweets`, `avg_favorites` | `get_tweet_analytics` |
| `"user"` | `date`, `active_users`, `avg_followers`, `avg_friends` | `get_user_analytics` |

`retweet_count` and `favorite_count` appear only as arguments to `AVG()` inside the query text, and
are never row keys. `date` is a `str`. An unknown `kind` raises `ValueError`.

**Empty-result `KeyError` cases come from omitting rows entirely, never from dropping a key.** An
empty list of rows produces a column-less frame, so `get_tweet_analytics` raises `KeyError:
'tweet_count'` and `get_user_analytics` raises `KeyError: 'active_users'`. Also exported:
`FIRST_ANALYTICS_DATE`, `SECOND_ANALYTICS_DATE` and `ANALYTICS_ROW_KINDS`.

### `make_status(**overrides) -> SimpleNamespace`

The tweepy-status duck object both listeners read by **attribute**: `id_str`, `text`,
`user.screen_name`, `created_at`, `retweet_count`, `favorite_count`. `user` is itself a
`SimpleNamespace`; `created_at` is a `datetime`. The two counts are independently overridable, and
`on_status` gates on their **sum** against `POPULARITY_THRESHOLD`, which is 100. An un-overridden
status sums to 20 and so takes the early `return True`.

```python
make_status(retweet_count=50, favorite_count=49)   # below the gate
make_status(retweet_count=50, favorite_count=50)   # clears the gate
make_status(screen_name="skeptic")                 # sets the nested author
make_status(user=None)                             # absent author
```

Passing both `user` and `screen_name` raises `TypeError` rather than silently preferring one.

### The honesty gate

[`unit/test_schema.py`](unit/test_schema.py) validates the factories against the schemas they claim
to satisfy: that `make_tweet` supplies exactly the schema's key set, that the payload constructs, and
that each value and its type survive construction. **If a factory drifts from the schema, that suite
fails** — rather than every other suite silently weakening around a fixture that no longer represents
real data.

---

## 6. Per-dependency mocking strategy

> ### Patch at the importing module's boundary, never at the library
>
> This is the one rule that explains most of the patch targets below. When a module does
> `from x import y`, it binds the **object** `y` into its own namespace at import time. Patching
> `x.y` afterwards rebinds the name in `x` and has **no effect** on the module that already copied it.
> The boundary that matters is the one the code under test actually reads.

| Boundary | Real dependency | What to patch, and how |
|---|---|---|
| Firestore | `google.cloud.firestore.Client` | Patch **`app.db.firestore.get_db`** in every test — use the `firestore_client` fixture. The module-level `db = Client()` constructs lazily and is safe at import, but any *call* is not. |
| BigQuery | `google.cloud.bigquery.Client` | Patch **`app.db.bigquery.Client`** *and* substitute `Settings` via the `bigquery_settings` fixture. The `Settings` stand-in is mandatory, not belt-and-braces (§4.3). |
| BigQuery, at the service layer | `run_query` | Patch **`app.services.analytics_service.run_query`** — *not* `app.db.bigquery.run_query`. |
| OpenAI | `openai.Completion.create` | Patch **`app.services.llm_service.Completion.create`**. Line 1 of that module is `from openai import Completion`, so `openai.Completion` is the wrong target. |
| tweepy, for `tweet_processor` | `tweepy.Stream`, `OAuthHandler`, `API` | `patch.dict(sys.modules, {"tweepy": MagicMock()})`. This works *because* line 53 of `app/tasks/tweet_processor.py` does `import tweepy` **inside** `start_tweet_stream`, so the lookup happens at call time and finds the substituted module. |
| tweepy, for `twitter_service` | `StreamListener`, `OAuthHandler`, `API` | Direct module-attribute patches — `patch.object(twitter_service, "OAuthHandler", ...)` — because that module imported the three names at its own import time. Patching `sys.modules` here would achieve nothing. |
| Google credentials | `google.auth.default` | The autouse `neutralize_google_credentials` fixture. Nothing to do per test. |
| Any socket | OS sockets, DNS, gRPC channels | The autouse egress guard. Nothing to do per test; an unmocked call fails loudly. |
| Clock | `datetime.utcnow`, `datetime.now` | The `frozen_clock` fixture (freezegun). Never `sleep`. |
| Injected database, HTTP layer | the object `Depends(get_db)` yields | `override_get_db(mock_db)` — `app.dependency_overrides`, keyed by object identity. |

### The most instructive example in the suite

`app/services/analytics_service.py` line 2 is:

```python
from app.db.bigquery import run_query
```

That statement copies the function object into `analytics_service`'s namespace. So:

```python
# WRONG — analytics_service already holds the original object; the real
# function runs, reaches BigQuery, and the egress guard refuses the connection.
patch("app.db.bigquery.run_query", return_value=rows)

# RIGHT — rebinds the name the code under test actually reads.
patch("app.services.analytics_service.run_query", return_value=rows)
```

`unit/test_services_analytics.py` asserts this property directly, so the convention cannot rot: one
test checks that `run_query` is bound into the subject module, and another checks that the mock really
did replace the subject module's attribute. If you patch the wrong target the guard will refuse the
egress and tell you which test did it — which is the whole point of having a guard rather than trusting
authorial discipline.

### What is never mocked

Third-party SDK internals are mocked *at the boundary* and never exercised live. The module under test
is never itself mocked — a suite that mocks its own subject asserts nothing.

---

## 7. Pitfalls

Six traps, each of which cost real time to find. Read this section before you write a test, not after.

### Pitfall 1 — Environment seeding must happen at conftest module scope

`app/core/config.py` line 28 runs `settings = Settings()` at **import**, and eight further production
modules build their own `Settings()` at their own module scope. pytest imports every test module during
**collection**, which is before any fixture runs.

**An `autouse` fixture is too late.** By the time it executes, the settings objects production code
will use for the entire session already exist, built from whatever environment happened to be present.
No amount of fixture cleverness works around this: it is an ordering constraint, so it has a
module-scope answer. The same applies to the `Optional` shim, the credential patch and the egress
guard.

If you add a new setting the suite depends on, add it to the prologue's mapping in `conftest.py` — not
to a fixture.

### Pitfall 2 — `google.auth.default()` genuinely resolves, so an unpatched `get_db` reaches real infrastructure

This is not a theoretical risk. In an environment with ambient Google credentials — this container has
them — `google.auth.default()` **succeeds**, `app.db.firestore.get_db()` returns a real Firestore
`Client`, and calling `add_tweet({})` with `get_db` unpatched performs a **genuine Google Cloud round
trip**. Observed result:

```text
NotFound: 404 The database (default) does not exist for project <ambient-project>
```

The project id is redacted. What matters here is the shape of the failure, not which project it named:
a `404` about a **database** rather than a connection error means the request was authenticated,
routed, and answered by Google Cloud. The real id is whatever `google.auth.default()` resolves in the
environment you run this in — print it yourself if you need it, rather than reading it out of a
committed document.

Read that failure carefully. It is not an offline error. A carelessly written test here does **not**
fail on a developer machine without credentials — it silently reaches production infrastructure, and on
a project that does exist it would write there.

This is why the credential neutraliser and the egress guard are autouse and installed at module scope
rather than left to per-test discipline, and why every Firestore test takes the `firestore_client`
fixture. `unit/test_db_firestore.py` even asserts that every test in the module requests it.

### Pitfall 3 — An unpatched stream starter blocks on a live Twitter connection

Both stream starters end in `stream.filter(track=...)`, which blocks. Calling
`app.tasks.tweet_processor.start_tweet_stream()` without patching `tweepy` **hung the interpreter to a
300-second timeout** on a live Twitter connection.

**Never call either stream starter unpatched.** For `tweet_processor`, patch `sys.modules["tweepy"]`;
for `twitter_service`, patch the module attributes (§6). This is also the reason the integration
clients are not entered as context managers: the `startup` handler calls `await start_tweet_stream()`,
so a single `with TestClient(app)` would hang the whole suite.

`app/services/twitter_service.start_twitter_stream` cannot complete for an unrelated reason — it
references `tweepy.Stream` at line 47 without the module ever importing `tweepy`, so it raises
`NameError`. That does **not** make it safe to call casually; the three stages before line 47 still run.

### Pitfall 4 — Never evict `app.db.firestore` from `sys.modules`

This one bites whoever next maintains `conftest.py`, and it fails *silently*.

`app.dependency_overrides` is a dict keyed on the **function object**. The key the integration layer
must use is the `get_db` object that `app/api/routes/tweets.py` captured in its `Depends(get_db)`
defaults when the router was imported. Re-importing `app.db.firestore` creates a **new** function
object, so:

- the override map is keyed on an object no route refers to;
- FastAPI finds no override and calls the **real** `get_db`;
- the test does not error on a missing key — it just stops injecting, and you get an egress refusal or,
  worse, a passing test that proved nothing.

The invariant the conftest maintains: **only `app.tasks.response_generator` is ever evicted from
`sys.modules`.** `app.db.firestore`, `app.schema.tweet`, `app.core.config`, `app.api.routes.tweets` and
`app.main` stay cached for the whole session, and per-test isolation comes from rebinding their shimmed
symbols rather than from reloading them. The `firestore_client` and `app_module` fixtures both import
the capturing modules *first*, while `get_db` is still the real function, precisely to keep that
identity intact.

### Pitfall 5 — A `backend/.env` is read, is gitignored, and must never be needed

`Settings.Config.env_file` names `.env`, so pydantic v1 reads `backend/.env` **whenever that file
exists** — and pydantic v1 reads one through `python-dotenv`, which it does not depend on unless the
`dotenv` extra is installed. `backend/requirements-dev.txt` therefore pins `python-dotenv==0.21.1`
under a `# CONFIG:` marker (`D382`). Without that pin, creating a `.env` — which the root
[`README.md`](../../README.md) §Configuration instructs a developer to do — made the **whole suite
non-collectable**, because `conftest.py`'s `pytest_configure` cannot import `app.core.config` and
refuses the run:

```
UsageError: backend/tests/conftest.py could not import app.core.config, so the backend
settings cannot be verified: ImportError: python-dotenv is not installed, run
'pip install pydantic[dotenv]'
```

Two things follow, and both are properties of the suite rather than advice.

- **The suite does not need a `.env`, and one cannot decide a value inside it.** pydantic v1 resolves a
  field from `os.environ` **before** the `.env` source, and the prologue assigns every managed name by
  unconditional assignment (§4.1), so a `.env` entry for a managed field is outranked. Measured: with a
  `.env` declaring `POPULARITY_THRESHOLD=4242` on disk, the whole suite still passes and
  `tests/unit/test_core_config.py` still reads `100`.
  A `.env` entry for a field the suite expects to be *absent* — `NOTION_API_KEY` is the one — is a
  different matter, because nothing in the environment outranks it. That case is refused rather than
  tolerated, by the session-scoped `verify_settings_singletons` fixture (§4.2) rather than by the
  `pytest_configure` gate, which compares only the assigned fields. Every test errors, each with:

  ```
  AssertionError: app.core.config.settings.NOTION_API_KEY is a str of 19 characters,
  fingerprint 5afb0dd6d7b849df (value withheld); it must be None. NOTION_API_KEY is set
  in the environment or in backend/.env.
  ```

  Note what that message does *not* contain: the value. And note that it is only reachable at all
  because the dotenv pin exists — without it the run dies at configure time instead.
- **`.env` is gitignored** (`D382`). It is the file a real credential gets pasted into, it is never a
  deliverable, and before the rule existed it was committable. If you need one for running the
  application rather than the tests, §1 lists the eight variables it would carry.

### Pitfall 6 — `case_sensitive = True` is inert on Windows, and the suite asserts the declaration rather than the effect

`Settings.Config` declares `case_sensitive = True`, and `tests/unit/test_core_config.py` asserts exactly
that: **the declaration**, not the behaviour it produces. That is deliberate, because the behaviour is
platform-dependent and the declaration is not.

On Windows `os.environ` is itself case-insensitive — setting `qa_LoWeR_Probe` makes `QA_LOWER_PROBE`
readable — so a lowercase `secret_key` satisfies the `SECRET_KEY` field and `popularity_threshold=999`
also sets `POPULARITY_THRESHOLD`. On `ubuntu-latest`, which is the runner
[`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) declares, the same names are distinct
and the declaration is effective.

So: do not write a test that asserts a lowercase name is *rejected*. It would pass on the CI runner and
fail on a Windows developer machine, which is a test whose result depends on the host rather than on the
code. `D383` records the divergence; the production `Config` block is pre-existing and outside the two
authorized touches, so nothing here changes it.

---

## 8. Run commands

**Every command runs from `backend/`** (§2). `addopts` in `pytest.ini` carries `-ra`,
`--strict-markers` and `--junitxml=reports/junit.xml`, and deliberately carries **no** `--cov` flag, so
coverage is always requested at invocation and an ordinary run stays fast.

**One command produces the artifacts, and it is the gated one.** The canonical producer command below
is byte-for-byte what `.github/workflows/ci.yml` runs. Use it whenever a figure is going to be quoted
or a dashboard filled, because the `--cov` scoping *is* the denominator G1 is calibrated against, and a
`coverage.xml` written by a wider run is indistinguishable from a gated one to any later reader:

```bash
cd backend
pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db \
       --cov-report=term-missing --cov-report=xml --cov-report=json \
       --cov-precision=2 --cov-fail-under=90 --junitxml=reports/junit.xml
python tests/coverage_gate.py --coverage-json coverage.json --fail-under 90 \
       --require-scope app/core --require-scope app/services \
       --require-scope app/tasks --require-scope app/db | tee reports/coverage-gate.txt
```

The whole-tree measurement in the table below is still a legitimate thing to run — it is how you find
out where the unreachable branches are — but it must not be the run that fills a panel. The second
command above **refuses** a report whose measured files fall outside the four gated packages, which is
exactly what stops a whole-tree total being labelled G1.

| Purpose | Command |
|---|---|
| Full suite | `pytest` |
| **The canonical producer, and the gate** | the two-command block above |
| Whole-tree measurement, **not** a G1 producer | `pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-report=json --cov-report=lcov` |
| Unit layer only | `pytest tests/unit -m unit` |
| Integration layer only | `pytest tests/integration -m integration` |
| Single file | `pytest tests/unit/test_core_security.py` |
| Single test | `pytest tests/unit/test_core_security.py::test_verify_password_raises_on_unusable_hash` |
| Single parametrised case | `pytest "tests/unit/test_tasks_tweet_processor.py::test_on_status_skips_below_popularity_threshold[50-49]"` |
| Debug | `pytest -vv -s --log-cli-level=DEBUG --showlocals --tb=long` |
| Stop at first failure | `pytest -x --tb=short` |
| **Collection gate** | `pytest --collect-only -q --junitxml=reports/collect-only-junit.xml` |
| Parallel — **runs, but is markedly slower on this host**, see below | `pytest -n auto` |

Quote a parametrised node id — the `[` and `]` are shell metacharacters in most shells.

There is **no watch mode and none is added.** The full suite finishes in roughly eight seconds once the
interpreter's import caches are warm, so a plain re-run is faster than any file watcher would be. The
first run after an install is slower — about nineteen seconds here — because the Google, gRPC and
`importlib.metadata` imports the guard and closure suites reach for are all cold.

### What each command should print

| Command | Expected outcome |
|---|---|
| `pytest` | `1093 passed, 3 skipped` |
| `pytest tests/unit -m unit` | `492 passed, 3 skipped` |
| `pytest tests/integration -m integration` | `150 passed` |
| `pytest tests/test_dependency_closure.py` | `73 passed` |
| `pytest tests/test_coverage_gate.py` | `62 passed` |
| `pytest tests/test_guard_contract.py` | `168 passed` |
| `pytest tests/test_dashboard_extract.py` | `44 passed` |
| `pytest tests/test_docs_contract.py` | `104 passed` |
| `pytest --collect-only -q` | `1096 tests collected`, **zero errors** |
| The gate | `Required test coverage of 90% reached. Total coverage: 93.33%`, then the exact gate's `PASSED` |

The counts close on the whole: 492 + 3 + 150 + 73 + 62 + 168 + 44 + 104 = 1096, the collected total above.

**Those are warm-tree readings, and a first run in a fresh clone is two passes short of them.** Two tests
read a result artifact that `.gitignore` keeps out of version control, and each skips rather than fails
while its artifact has not been produced yet — deliberately, so that this suite stays runnable on its own:

| Skipped on a first run | Reason it prints | What produces the artifact |
|---|---|---|
| `tests/test_coverage_gate.py::test_counts_and_files_are_read_from_the_real_report` | `backend/coverage.json is written by the gated coverage command` | the canonical producer block above, through its `--cov-report=json` |
| `tests/test_docs_contract.py::test_the_published_e2e_census_is_the_retained_streams_own_count` | `e2e/reports/e2e-junit.xml is gitignored and absent in a fresh clone` | `npm test` from `e2e/` |

So a clean clone's first `pytest` reads `1063 passed, 5 skipped`, its
`pytest tests/test_coverage_gate.py` reads `61 passed, 1 skipped` and its
`pytest tests/test_docs_contract.py` reads `89 passed, 1 skipped`; the collected total is unchanged at 1068
and the coverage gate is unaffected, still reading 93.33%. Run the canonical producer block once and the
end-to-end suite once, and every figure above is reproduced exactly. Note that the plain
`--cov-fail-under=90` form on its own does **not** clear the first of the two, because it requests no JSON
report. Those two skips are the one exception to the skip convention stated below: they name an absent
artifact rather than an unimplemented production feature.

Provenance for the table, in the same form used throughout this document:

| | |
|---|---|
| Runner | `pytest` 8.4.2 with `pytest-asyncio` 0.26.0 and `pytest-cov` 6.1.1, installed from `backend/requirements-dev.txt` |
| Runtime | CPython 3.9.13 in `.venv-backend`, Windows |
| Commit | Recorded by the tooling, not transcribed here — run `python docs/testing/dashboard-extract.py` and read §1.0 of its output for the tree your own counts belong to |
| Artifacts | `backend/reports/junit.xml` — root attributes `tests`, `failures`, `errors`, `skipped` — and `backend/coverage.json` for the gate percentage. The layer split above is derived from `classname` prefixes: `tests.unit.`, `tests.integration.`, `tests.test_dependency_closure`, `tests.test_coverage_gate` and `tests.test_guard_contract` |
| Retention | Local-only as run above. The equivalent CI step retains `junit.xml`, both coverage reports and the collection summary as `build-test-evidence`, 30-day retention |

### Collection integrity is a gate in its own right

```bash
cd backend && pytest --collect-only -q --junitxml=reports/collect-only-junit.xml   # ZERO errors
```

For most suites this would be a curiosity. For this one it is *the* meaningful readiness check,
because the historical failure mode here was never a wrong assertion — it was an **import error**. All
three legacy modules died during collection, on three mutually exclusive import roots and a
`SyntaxError`, so the executed assertion count was zero while the repository still looked as though it
had tests. A suite that collects cleanly is a suite whose subjects are all importable. Run this first
when something looks wrong, and treat any error here as blocking.

**It is an automated CI step, not only a local habit.** The `build` job in
[`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs it as its own step immediately
before the backend suite, tees the summary to `backend/reports/collect-only.txt`, and uploads that file
with the rest of the test evidence. The extractor in
[`../../docs/testing/dashboard-extract.py`](../../docs/testing/dashboard-extract.py) reads the collected
count back out of it, so the readiness result survives the run instead of scrolling past in a log — which
is the difference between a documented check and an enforced one. The frontend and end-to-end layers have
the same arrangement, one step each; the root [`README.md`](../../README.md) tabulates all three.

> **Every pytest invocation writes `reports/junit.xml`.** `--junitxml` lives in `addopts`, so it applies
> to *every* run — a collection run, which writes a well-formed report declaring `tests="0"`, and equally
> a single-file or `-k` filtered run, which writes a well-formed report declaring a **non-zero** count
> that is not the suite's. Nothing warns you.
>
> Five things make that safe here rather than merely known. The gate command above repeats `--junitxml`
> to a separate file — the command-line value wins over the `addopts` one — so the probe no longer writes
> the canonical stream at all. The workflow runs the readiness step **before** the suite in any case, so
> the real report is written last. The `Verify backend report artifacts` step requires the stream's case
> count to **equal** the collected count the readiness step recorded, which catches the partial run as
> well as the empty one. The extractor applies the same comparison and withdraws a stream that fails it,
> naming both figures, rather than rendering the smaller one as a measurement. And a zero-case stream is
> still refused outright by both. Locally, if you have run anything narrower than the canonical command,
> re-run it before quoting a figure (`D355`).
>
> `playwright test --list` has the identical defect, handled the same way — see
> [`../../e2e/README.md`](../../e2e/README.md) §3. The frontend readiness command, `npm run test:load`,
> **would** have it — it is a real Jest run, so its configured `jest-junit` reporter would write an
> all-skipped stream over `frontend/reports/jest-junit.xml` — so the script passes
> `--reporters=default`, which replaces the configured reporter list. Verified by hashing that file either
> side of a probe: unchanged.

### On `-n auto`, and why it is not the default

`pytest-xdist` is installed and works — `pytest -n auto` starts, runs to completion and reports the
same `1093 passed, 3 skipped`, and
`-n 2` reaches it in about 9 seconds. It is **not** enabled by default, and on a many-core machine it is
markedly *slower*: on this host `-n auto` took 108 seconds against roughly 11 seconds serial, because
process startup dominates a suite this fast. That figure moves with how busy the host is — separate
readings on this machine span roughly 107 to 250 seconds — so treat the order of magnitude rather than
the number as the point. Nothing in the design depends on execution order, so
parallelism is always safe; it is just rarely worth it. Prefer `-n 4` over `-n auto` if you want it.

**It works for a reason worth knowing, because it did not before.** An xdist worker calls
`platform.platform()` in `pytest_sessionstart`, and on Windows that reaches `win32_ver` →
`_syscmd_ver` → `subprocess.Popen('ver')` — a child process, which the guard refuses. The worker then
aborted with an INTERNALERROR and the run reported "no tests ran". The fix was to prime that cache in the
guard prologue rather than to admit `ver` to the allow-list: `platform.uname()` and `platform.platform()`
fill *separate* caches, and the prologue was only priming the first. So no command was permitted to make
parallelism work. See `docs/testing/DECISION-LOG.md` row D315.

### Observability of the test system, and where the artifacts land

Per the **Observability** rule, here is the ledger of what this suite reuses versus what it adds. The
subject is the test system, which is the deliverable being built; the *production* code's
instrumentation gaps are recorded as gaps in §12 rather than filled, because filling them would mean
unauthorized production change.

**Reused** — already in the repository, left intact and repointed only where a path moved:

- the two Codecov upload steps in `.github/workflows/ci.yml`, and both of their flags, `backend` and
  `frontend`.

**Added:**

| Addition | Where it is configured | What it gives you |
|---|---|---|
| JUnit XML reporting | `--junitxml=reports/junit.xml` in `addopts`, with `junit_family = xunit2` | A machine-readable result per test. Each `<testcase>` carries `classname` and `name`, which together reconstruct the pytest node id — so a result, a log line and a skip reason all lead back to one test. |
| Correlation identifiers | A log-record factory in `conftest.py`, printed by `log_cli_format` / `log_format` in `pytest.ini` | Every `logging.LogRecord` — from production code, from pytest, from any library — carries `test_id` (the node id) and `correlation_id` (a short stable 8-hex digest of it). Live log lines read `INFO [65ac3815] httpx: …`. The digest is a hash, so the same test yields the same id on every run and on every machine. A record emitted outside a test reads `session`. |
| Captured logs on failures only | `junit_logging = log`, `junit_log_passing_tests = false` | A failing or skipped `<testcase>` carries its captured log; a passing one does not, so the artifact stays diagnostic without becoming a transcript. |
| Extra coverage reporters | `--cov-report=json`, `--cov-report=lcov` at invocation | Machine-readable coverage beside the cobertura XML the Codecov step consumes. |
| The collectability gate | `pytest --collect-only -q --junitxml=reports/collect-only-junit.xml` | The readiness check described above, writing its own result stream so it cannot replace the suite's. |
| The exact coverage gate | `tests/coverage_gate.py`, run after the gated suite | Compares the integer counts in `coverage.json` — `covered * 100 >= 90 * statements`, exact rational arithmetic — and refuses a report measured over a scope other than the four gated packages. Its reading is retained as `reports/coverage-gate.txt` and is what the dashboard's K5b reports; `--cov-fail-under` rounds before it compares, so it is not the binding verdict. |

Verify all of it on disk — the **Observability** rule is not satisfied by configuration alone. Run the
canonical producer command from §8, which is the one CI runs, and then list what it wrote:

```bash
cd backend
mkdir -p reports
pytest --collect-only -q --junitxml=reports/collect-only-junit.xml | tee reports/collect-only.txt
pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db \
       --cov-report=term-missing --cov-report=xml --cov-report=json \
       --cov-precision=2 --cov-fail-under=90 --junitxml=reports/junit.xml
python tests/coverage_gate.py --coverage-json coverage.json --fail-under 90 \
       --require-scope app/core --require-scope app/services \
       --require-scope app/tasks --require-scope app/db | tee reports/coverage-gate.txt
ls reports/junit.xml reports/collect-only.txt reports/coverage-gate.txt coverage.xml coverage.json
```

Run the readiness command **first**, as above and as CI does. `--collect-only` writes the reporters named
in `addopts`, which is why the command repeats `--junitxml` to a separate file: with the redirect, running
it afterwards costs nothing; without it, it would leave a zero-case stub where `reports/junit.xml` belongs.
Add `--cov-report=lcov` if an external lcov viewer needs `coverage.lcov`; the canonical command does not
request it, and neither does CI.

| Artifact | Path | Written by | Retained by CI |
|---|---|---|---|
| JUnit XML | `backend/reports/junit.xml` | `addopts`, every run that does not redirect it | yes — `build-test-evidence`, 30 days |
| Collection summary | `backend/reports/collect-only.txt` | the readiness step's `tee` | yes — `build-test-evidence` |
| Collection result stream | `backend/reports/collect-only-junit.xml` | the readiness step's own `--junitxml`, so the `addopts` value cannot reach `junit.xml` | yes — `build-test-evidence`, with the directory |
| Exact-gate reading | `backend/reports/coverage-gate.txt` | `tests/coverage_gate.py` piped through `tee` | yes — `build-test-evidence` |
| Cobertura XML | `backend/coverage.xml` | `--cov-report=xml` — also the file the `backend`-flagged Codecov step uploads | yes |
| Coverage JSON | `backend/coverage.json` | `--cov-report=json` — the only per-module producer, so the dashboard depends on it | yes |
| Coverage LCOV | `backend/coverage.lcov` | `--cov-report=lcov` | **no** — the CI command does not request this reporter |
| Coverage database | `backend/.coverage` | `pytest-cov` | no — an intermediate, not evidence |

Two workflow steps read `junit.xml` before the Codecov upload and fail with an explicit annotation if it
is missing, empty, or declares a case count other than the number of tests collection found — so neither a
collection-time stub nor a partial run can be published as the suite.

Every one of those paths is in `.gitignore`, so running the suite never dirties the working tree — a local
run leaves them in your tree and nowhere else, which is the whole difference the last column records. A
dashboard template for these numbers lives at
[`docs/testing/DASHBOARD-TEMPLATE.md`](../../docs/testing/DASHBOARD-TEMPLATE.md).

---

## 9. Coverage targets, and the ceilings that are not gaps

### The target and the gate

**≥90% line coverage on `app/core`, `app/services`, `app/tasks` and `app/db`,** enforced by the runner:

```bash
cd backend && pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-fail-under=90
```

Currently **93.33%** across those four packages — 195 statements, 13 missed. Percentages are stated to
**two decimals** throughout, because that is the precision the gate compares at; see the exactness note
below, and treat any backend figure quoted here as a whole number as stale.

| Package | Coverage | Module | Coverage |
|---|---|---|---|
| `app/core` | 100.00% (47/47) | `app/core/config.py` | 100.00% |
| | | `app/core/security.py` | 100.00% |
| `app/db` | 100.00% (45/45) | `app/db/bigquery.py` | 100.00% |
| | | `app/db/firestore.py` | 100.00% |
| `app/services` | 94.12% (48/51) | `app/services/analytics_service.py` | 100.00% |
| | | `app/services/llm_service.py` | 100.00% |
| | | `app/services/twitter_service.py` | 85.00% |
| `app/tasks` | 80.77% (42/52) | `app/tasks/response_generator.py` | 60.00% |
| | | `app/tasks/tweet_processor.py` | 93.75% |
| **Aggregate — the gated total** | **93.33% (182/195)** | | |

**Only the aggregate is gated.** The per-package and per-module columns are measurements without verdicts
of their own, which is why `app/tasks` can sit at 80.77% while the gate passes — the gate is one
comparison over one total, not four comparisons. That is a deliberate choice, not an oversight: the
shortfall in `app/tasks` is the unreachable region documented below, and the alternative is chasing
branches no test can execute. The same split is presented in
[`DASHBOARD-TEMPLATE.md`](../../docs/testing/DASHBOARD-TEMPLATE.md) §6.1 with the same labelling.

Where these numbers come from, so you can re-derive rather than trust them:

| | |
|---|---|
| Command | `cd backend && pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-fail-under=90 --cov-report=json` |
| Runner | `pytest` 8.4.2, `pytest-cov` 6.1.1, `coverage` 7.10.7 |
| Runtime | CPython 3.9.13 in `.venv-backend`, Windows |
| Commit | Recorded by the tooling — `python docs/testing/dashboard-extract.py` prints the branch and commit of the tree it read in §1.0, so the figure and its tree travel together instead of the hash being copied into this row |
| Artifacts | `backend/coverage.json` — the per-package and per-module figures above are its `totals.percent_covered` values; `backend/coverage.xml` carries the aggregate only, because four `--cov` paths collapse to a single `<package name=".">` with bare basenames |
| Retention | Local-only as run above; the equivalent CI step retains both files as `build-test-evidence` |

The baseline this replaced was **0% executed coverage across all 14 backend production modules** — not
an estimate, a consequence of all three legacy modules failing at collection. (The coverage table now
lists 17 files, because the first authorized production touch turned one extension-less `routes` file
into a four-module package.)

### Scope the gate to those four packages — never to the whole `app` tree

This is not stylistic caution, it is arithmetic you can reproduce:

```text
pytest --cov=app --cov-fail-under=90
→ TOTAL 288 26 90.97%   — 2.36 points below the gated scope, and only 0.97 above the bar

pytest --cov=app --cov-fail-under=91
→ ERROR: Coverage failure: total of 90.97 is less than fail-under=91.00   — and exits 1
```

The whole tree lands at **90.97%** — 288 statements, 26 missed — while the four named packages reach 93.33%
with real headroom. The entire difference is the unreachable regions listed below, so the wider scope buys
no quality and spends its whole margin on branches no test can execute: it clears 90 by less than a point,
and any new unreachable line in a route module would drop it under. Widening the gate's scope would force
someone to chase those branches without changing production code, which is precisely the scope expansion
the programme forbids — and `tests/coverage_gate.py` refuses a whole-tree report outright for the same
reason, so the wider denominator cannot be quietly substituted. The reasoning is recorded in
[`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) §7.

### `--cov-fail-under` is a rounded comparison, so the binding gate is a second command

Out of the box the comparison is **not exact**, and the failure mode is the worst kind: the run prints
`FAIL` and exits **0**.

coverage.py's check is `round(total, precision) < fail_under`, and `precision` defaults to **0**. So the
whole tree's 90.97% rounds to 91 at that precision and satisfies `>= 91`, while pytest-cov's message
compares the *unrounded* value and correctly reports failure — the pair in the block above. A threshold of
91 silently tolerated anything from **90.5%** upward: half a percentage point of undetected regression,
reported as a failure and exiting as a success.

`backend/.coveragerc` narrows that band:

```ini
[report]
precision = 2
```

`precision` governs both the reported figure and the value the threshold is compared against, so setting
it to 2 makes the printed number and the gated number agree and shrinks the tolerance from half a point
to a hundredth. It is a config file rather than an addition to `pytest.ini` because `pytest.ini` cannot
host a `[report]` section, and `backend/` had no `.coveragerc`, `setup.cfg` or `pyproject.toml` for
coverage to read. `.github/workflows/ci.yml` repeats `--cov-precision=2` on the backend command so the
resolution is legible at the invocation site, and `pytest.ini` carries no coverage option at all, so a
bare `pytest` neither measures nor gates.

**Narrowing is not closing, and it cannot be closed by configuration.** Rounding is still rounding at
every precision: at 2 decimals a total anywhere in `[89.995, 90)` rounds to `90.00` and passes a 90
threshold; at 4 decimals the band is `[89.99995, 90)`. There is no finite precision at which
`--cov-fail-under=90` means "at least 90".

So the binding verdict is a second command, and it does not round at all:

```bash
python tests/coverage_gate.py --coverage-json coverage.json --fail-under 90 \
       --require-scope app/core --require-scope app/services \
       --require-scope app/tasks --require-scope app/db
```

It reads the integer counts out of `coverage.json` and compares `covered * 100 >= threshold *
statements` over `Fraction`, so the question it answers is a question about two integers and has no
representable-value problem to have. It also refuses a report whose measured files fall outside the four
named packages, or one in which a named package contributed no measured file — which is what stops a
whole-tree total being read as a gated one. Exit statuses are `0` pass, `1` gate failed, `2` report
missing or unreadable, and its reading is retained as `reports/coverage-gate.txt`.

Every row below is reproducible on this tree today, not a recollection of an earlier one:

| Command | Outcome |
|---|---|
| `pytest --cov=app --cov-precision=0 --cov-fail-under=91` | prints `FAIL Required test coverage of 91% not reached. Total coverage: 90.97%` and **exits 0** — the original defect, still demonstrable because 90.97 rounds to 91 |
| `pytest --cov=app --cov-fail-under=91` | `ERROR: Coverage failure: total of 90.97 is less than fail-under=91.00`, **exits 1** — the same tree, at the committed precision |
| `coverage_gate.py --fail-under 93.34` on `coverage.json` | **exits 1**: `total coverage 93.3333% is below the required 93.34% - compared as 182 * 100 >= 93.34 * 195, which is false` |
| `coverage_gate.py --fail-under 90` on a synthetic `17999/20000` report | **exits 1**: `89.9950% is below the required 90% - compared as 17999 * 100 >= 90 * 20000` — the total `--cov-fail-under=90` admits |
| `coverage_gate.py` on a whole-`app` report | **exits 1**, naming all eight measured files outside the gated scope before it reports the total at all |

The fourth row is the whole point of the second command: that report passes the rounded gate and fails
the exact one, and it is the exact one CI runs last.

Two consequences to carry:

- **Quote backend coverage to two decimals**, or as the integer pair. A figure written as a whole number
  was produced before this and does not describe either gate.
- **The whole-tree scope is unambiguous too** — it fails the rounded gate and is refused outright by the
  exact one. The four-package scope is still the right gate for the reason above.

`D226` and `D252` in [`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) record the precision choice
and its alternatives, and the row that supersedes them records the exact gate; §12 below carries what
remains unaddressed.

### Documented ceilings — assert them as current behaviour, do not chase them

Each of these is a production defect, not a hole in the suite. The suite asserts the behaviour that
*does* happen; the corresponding entry appears in §12 and in
[`TRACEABILITY-MATRIX.md`](../../docs/testing/TRACEABILITY-MATRIX.md) §G.

| Ceiling | Why no test can reach past it |
|---|---|
| `start_twitter_stream` is dead code | `app/services/twitter_service.py` line 1 imports only `StreamListener`, `OAuthHandler` and `API` — never `tweepy` itself — so line 47's `tweepy.Stream(...)` always raises `NameError`. The lines after it can never execute in any environment. The suite asserts the `NameError` and the three stages that do run. |
| The 404 branch of `GET /tweets/{tweet_id}` is unreachable | The handler does `db.query(Tweet).filter(Tweet.id == tweet_id)`, and the pydantic `Tweet` has no `id` attribute, so `AttributeError` is raised *before* any lookup and the response is **HTTP 500**. Asserted both ways: `pytest.raises` with `client`, and `status_code == 500` with `client_no_raise`. |
| The startup and shutdown handler bodies never run | Registered at `app/main.py` lines 26 and 35, but the clients are not entered as context managers (§3, pitfall 3). The suite asserts that both are *registered* and that neither is *invoked*. |
| The doubt-rating gate does not exist | `DOUBT_RATING_THRESHOLD` is declared as `0.7` and is referenced by **no production code anywhere**. Only the constant is assertable; the gate the design documents describe was never implemented. |
| There is no 422-for-invalid-body path | No implemented endpoint accepts a request body, so the requirement has no subject. `test_http_tweets.py` asserts that absence explicitly. Query-parameter validation *is* covered, because `GET /tweets` declares two integer query parameters, `skip` and `limit`. |

Recording a ceiling is not the same as excusing one. Each is asserted, so if someone later implements
the missing behaviour the assertion fails and forces the test to be updated deliberately.

---

## 10. How to extend the suite

### Naming conventions

| Thing | Convention | Example |
|---|---|---|
| Unit module | `test_<layer>_<subject>.py`, mirroring the `app/` layout | `app/services/llm_service.py` → `unit/test_services_llm.py` |
| Integration module | `test_<surface>.py` | `integration/test_http_tweets.py` |
| Test function | `test_<operation>` or `test_<operation>_<scenario>` | `test_update_tweet_returns_false_when_the_update_fails` |
| Fixture supplying a stand-in | `mock_<entity>` | `mock_db` |
| Parametrised case id | A short lower-case label, or the values themselves | `[50-49]`, `[runtimeerror]`, `[empty-dict]` |

Prefer a long, specific function name over a short one plus a comment. The name is what a failing CI
run shows you.

### Style rules

- **Functions and fixtures, never `unittest.TestCase`.** Class-based grouping is what produced the
  legacy suite's alphabetical-ordering hazard.
- **`unittest.mock` for mocking.** `pytest-mock` is deliberately absent — it would add a dependency for
  no capability the standard library lacks, and it would diverge from the idiom already here.
- **One behaviour per test.** If the name needs "and", split it.
- **`@pytest.mark.parametrize` for boundary matrices,** never a loop inside one assertion, so each case
  reports independently and a failure names the input.
- **Every assertion needs a real oracle.** An assertion that passes for any plausible implementation is
  worse than no assertion, because it reads like coverage. The two legacy tautologies —
  `assertIn(sentiment, ["positive","negative","neutral"])` and `0 <= rate <= 1` — were deleted rather
  than migrated for exactly this reason. Derive expected values from production behaviour or from a
  factory; never recompute them in the test.
- **No wall clock, no sleep.** Use `frozen_clock`.

### Where new shared setup goes

| You need | Put it in |
|---|---|
| A fixture used by more than one module | `conftest.py` (or `integration/conftest.py` if it is HTTP-only) |
| Test data of any shape | `factories.py`, as a builder taking `**overrides` |
| A stand-in for a symbol production imports but never defines | `conftest.py`, as a fixture — **never** in a test file |
| Something used by exactly one module | That module, as a local fixture |

Nothing is copy-pasted between suites. If you find yourself pasting setup, it belongs in `conftest.py`.

### Adding a unit suite for a production module

1. Create `unit/test_<layer>_<subject>.py`. No `sys.path` work, no `__init__.py` to add.
2. `import app.<layer>.<subject> as subject` — always the `app.*` root.
3. Identify the module's external boundaries by reading its **import statements**, then choose a patch
   target for each: the name as *this* module binds it, not the library path (§6).
4. If the module imports a symbol nothing defines, check §4.4 — a shim probably exists already. If it
   is a sixth such symbol, add it to the conftest's shim map rather than patching locally.
5. Write the happy path, then the boundary matrix, then the negative side of every conditional a
   fixture can reach, then an explicit assertion on error *disposition* — swallowed or propagated. This
   codebase does both, inconsistently, so it must be asserted per function rather than assumed.
6. Add `pytest.ini` marker usage only for markers that already exist there.
7. Run the collection gate, then the suite, then the four-package gate.

### What not to do

- **Do not implement a missing product feature to make a test pass.** No new router, no new endpoint,
  no auth, no `add_response`, no `TwitterService`. If a test needs something production lacks, the test
  is asserting an intention rather than the code.
- **Assert current behaviour even where it contradicts the design documents.** `update_tweet` swallows
  and returns `False`; `insert_tweet_analytics` propagates; `llm_service.generate_response` swallows an
  OpenAI failure but *not* an empty completion list; `analytics_service` propagates a query error
  unchanged. All four are asserted as written.
- **Do not "fix" a defect you find while adding a test.** Add it to §12 instead. Two production touches
  were pre-authorized for this programme and no third is; both are recorded in
  [`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) §22.
- **Never skip silently.** A skip must carry a `reason` naming the unimplemented production feature, so
  the skip is a record rather than a silence:

  ```python
  @pytest.mark.skip(reason="app/tasks/tweet_processor.py implements no deduplication.")
  ```

- **Do not relax the gate to make a change fit.** If new production code lowers coverage below 90%,
  cover it.

---

## 11. Legacy suite disposition

The three legacy modules are **deleted** in this change. They were treated as intent documentation
rather than as a working baseline, so their intent survives in two places: the table below and
[`TRACEABILITY-MATRIX.md`](../../docs/testing/TRACEABILITY-MATRIX.md), which carries the per-function
detail in both directions.

### The census

| Legacy module | Lines | Functions | Rewritten | Skipped | Removed |
|---|---|---|---|---|---|
| `backend/tests/test_api.py` | 86 | 12 | 2 | 0 | 10 |
| `backend/tests/test_services.py` | 62 | 6 | 1 | 0 | 5 |
| `backend/tests/test_tasks.py` | 68 | 7 | 4 | 3 | 0 |
| **Total** | **216** | **25** | **7** | **3** | **15** |

Both sums close on the same number without recounting a row: functions **12 + 6 + 7 = 25**, and
dispositions **7 + 3 + 15 = 25**. Six of the 25 had `pass` bodies. And **every one of the 25 failed at
collection rather than at assertion** — three mutually exclusive import roots, a module-level
`TestClient(app)` executed at import, and a genuine `SyntaxError` in the routes file. The executed
assertion count was zero.

### The 7 rewritten

Migrated against the real surface: `test_get_tweet` became the `GET /tweets/{tweet_id}` integration
case that asserts the `AttributeError`-to-500 reality; `test_get_tweet_analytics`'s intent became the
aggregation unit tests; `test_generate_response`'s OpenAI mocking idiom was preserved with a corrected
patch target; and the four patch-based `test_tasks.py` cases — including both `*_error_handling` cases,
whose error-propagation intent was worth keeping — became the tweet-processor and response-generator
suites against real symbols.

### The 3 skipped, and the feature each names

| Legacy function | Now | Reason string |
|---|---|---|
| `test_process_tweet_with_media` | `unit/test_tasks_tweet_processor.py::test_on_status_with_media` | `app/tasks/tweet_processor.py` implements no media handling. |
| `test_process_tweet_deduplication` | `unit/test_tasks_tweet_processor.py::test_on_status_deduplication` | `app/tasks/tweet_processor.py` implements no deduplication. |
| `test_generate_response_rate_limiting` | `unit/test_tasks_response_generator.py::test_generate_response_rate_limiting` | Neither `app/tasks/response_generator.py` nor `app/services/llm_service.py` implements rate limiting. |

These are the three skips a green run reports on a warm tree, and the only three that name a feature. A
first run in a fresh clone reports two more, which name an absent gitignored artifact rather than a missing
feature; both are listed under [What each command should print](#what-each-command-should-print) and both
disappear once the gated coverage command and the end-to-end suite have each run once. Each of the three
above is written out in full, so implementing the feature is a matter of removing one decorator.

### Why the 15 were removed rather than migrated

- **Ten from `test_api.py`** targeted `/users`, `/analytics`, `/config`, `DELETE /tweets/{id}`,
  `POST /tweets/`, and 401 auth paths. **None of those routes exists**, and creating them would be
  implementing a missing product feature, which the programme forbids. Their absence is now asserted
  positively as the 404 census in `integration/test_route_surface.py`, which is strictly more
  informative than a test that would have failed.
- **Five from `test_services.py`** instantiated `TwitterService`, `LLMService` and `AnalyticsService`
  and called `process_tweets`, `process_sentiment` and `calculate_engagement_rate`. **None of those
  classes or methods exists**; the service modules expose free functions only. Two of the five were
  also the oracle-free tautologies described in §10. The replacement suites assert that the legacy
  names are *absent*, so the divergence is recorded rather than forgotten.

### Two divergences worth naming

- `test_get_user_analytics` asserted the key `"total_users"`. `analytics_service.get_user_analytics`
  returns **`total_active_users`** — so the legacy name was wrong twice over, and
  `unit/test_services_analytics.py` now asserts both the real key set and the absence of the legacy key.
- `test_update_config` used `PUT /config`, where the design documents specify `PATCH`.

Both are moot: no config router exists.

---

## 12. Suggested next tasks

**None of the following is fixed here.** Every item was found while building the suite and is out of
scope for remediation by instruction — in scope only for documentation. They are recorded so the next
person does not have to rediscover them, and the full register with per-item context is
[`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) §23. The security exposures among them — unauthenticated route handlers, f-string-interpolated BigQuery SQL, the JWT expiry and verification gaps, and the dependency advisories the pins hold in place — are written up individually in [`SECURITY-GAPS.md`](../../docs/testing/SECURITY-GAPS.md), with the clause that put each out of reach and what has to be done. Where the suite asserts the current broken
behaviour, fixing the production code will fail a test, which is deliberate: the assertion is a tripwire
that forces the change to be made consciously.

### Configuration and settings

- `Settings.GOOGLE_CLOUD_PROJECT` is read as a **class** attribute in two places in
  `app/db/bigquery.py` (lines 7 and 21). Under pydantic v1 that can never resolve — declared fields are
  stripped from the class namespace. Reading it off an instance would fix both call sites.
- `settings.openai_engine` is read in lower case (`app/services/llm_service.py` line 19) while
  `Settings.Config.case_sensitive` is `True`, so it can never resolve. There is no such field under any
  casing.
- `settings.TWITTER_CONSUMER_KEY` and `TWITTER_CONSUMER_SECRET` are read by both stream starters, but
  the declared fields are `TWITTER_API_KEY` and `TWITTER_API_SECRET`.
- `DOUBT_RATING_THRESHOLD` is declared as `0.7` and referenced by no production code, so the
  doubt-rating gate the design documents describe does not exist.
- `create_access_token` hardcodes a 15-minute expiry and ignores `ACCESS_TOKEN_EXPIRE_MINUTES = 30`.
- `API_V1_STR` is declared as `/api/v1` and no route is prefixed with it.

### Backend behaviour

- `app/db/firestore.py` has no `add_response`, although `app/tasks/response_generator.py` imports it.
- `response_generator.generate_response` awaits `firestore.get_tweet`, which is synchronous —
  `TypeError: object dict can't be used in 'await' expression`.
- `process_pending_responses` calls `get_tweet(response_status="pending")` against a signature taking a
  single positional parameter.
- `twitter_service.start_twitter_stream` references `tweepy.Stream` without the module importing
  `tweepy`, so it always raises `NameError` — the function is dead code.
- `TweetStreamListener.on_status` builds a `Tweet` from seven field names the schema declares none of,
  producing an eight-error `ValidationError` for every tweet that clears the popularity gate. That is
  the ingestion path: no tweet can currently be stored.
- `GET /tweets/{tweet_id}` filters on `Tweet.id`, which the pydantic model does not have, so it returns
  HTTP 500 and its 404 branch is unreachable.
- SQLAlchemy `Session` type hints and `db.query(...)` calls are issued against a Firestore-backed
  dependency in `app/api/routes/tweets.py`.
- Analytics SQL is assembled by f-string interpolation of caller-supplied date strings — an injection
  exposure as well as a validation gap. The suite pins the current behaviour with negative cases so a
  future parameterisation is a deliberate, test-visible change.
- Inverted and malformed date ranges are accepted with no validation and interpolated verbatim.
- **Fifteen** `# HUMAN ASSISTANCE NEEDED` placeholder comments remain, spread across **ten** of the
  seventeen modules under `backend/app/` — `main.py`, `api/routes/tweets.py`, `core/security.py`,
  `db/bigquery.py`, `db/firestore.py`, all three `services/*.py`, and both `tasks/*.py`. The seven
  without one are `api/dependencies.py`, `core/config.py`, the two schemas, and the three bare-router
  modules. Note that `api/routes/tweets.py` **does** carry one: it came across with the endpoint bodies
  when the extension-less routes file became a package. Repository-wide the marker appears **28** times
  across 22 production modules — the fifteen here plus thirteen in twelve frontend modules — with one
  more in each of `ci.yml`, `cd.yml`, `docker-compose.yml` and `nginx.conf`; see `D191`, which is where
  that census is recorded. Each marks code its original author flagged as unreviewed, and each one this
  suite covers is now covered by assertions on what the code actually does rather than on what it was
  meant to do.

### Observability of the production code

Recorded per the **Observability** rule, which asks that gaps be documented rather than silently left.
Filling any of these means changing production code, which this programme is not authorized to do.

- There is **zero** use of the standard library's `logging` anywhere in `backend/app` — no `import
  logging`, no `getLogger`, not one call. The suite's correlation ids therefore decorate framework and
  library records only; there is no application record to correlate. Adding a logger per module is the
  single highest-value change on this list, and the correlation machinery is already waiting for it.
- The only diagnostic output in the entire backend is **two** `print()` calls, at `app/db/bigquery.py`
  line 26 and `app/services/llm_service.py` line 28. Both are asserted by the suite through captured
  stdout, because that is the observable behaviour today. Converting either to a log call will fail
  those assertions, which is the intended tripwire.
- There is no metrics endpoint and no tracing of any kind.
- The health checks in `infrastructure/docker/docker-compose.yml` and `.github/workflows/cd.yml` target
  a `/health` route that **does not exist**; `integration/test_route_surface.py` asserts its 404.

### CI, dependencies and hygiene

- The `flake8 .`, `mypy .` and `npm run lint` steps in `ci.yml` are broken independently of testing —
  no linter is declared anywhere and the sources do not typecheck. They are deliberately untouched;
  only the test steps and their immediate install prerequisites were changed.
- **`pytest -n` cannot start on Windows**, for the reason set out in §8: an xdist worker's
  `platform.platform()` runs `Popen('ver', shell=True)` and the subprocess guard's allow-list admits only
  the `cmd /c ver` form. Two ways to close it, both a decision for whoever owns the guard's contract:
  extend `ALLOWED_CHILD_PROCESS_COMMANDS` with an equally exact pattern for the bare `ver` command line,
  or drop `pytest-xdist` from the manifest and the documented commands. Nothing is gated on it either
  way — the serial suite is the suite, and CI runs serially on Linux.
- **No lockfile exists anywhere in the repository**, so no install is byte-reproducible, and the three
  packages mitigate that to different degrees. The backend is fully exact-pinned: all **25** active lines of
  `requirements-dev.txt` are `==`, and `test_dependency_closure.py` fails if any one of them is not, if the
  parsed-pin count does not equal the active-line count, or if an installed version differs. It closes the
  other direction too — every third-party module the suite actually reaches, whether by `import` or by a
  patch target named as a string, must be provided by a pinned distribution — which is what the two gRPC
  pins satisfy. That is **72** cases in all. `e2e/package.json`
  exact-pins all three of its direct dependencies. **`frontend/package.json` is only partly pinned**: the 11
  devDependencies this testing work introduced are exact, while the 17 pre-existing declarations — 7 runtime
  and 10 development — stay at their baseline caret ranges, because the authorized change boundary for that
  file is devDependencies and test scripts. So the frontend's direct graph is *not* closed by its manifest
  alone, and `frontend/src/test-utils/dependency-closure.test.ts` enforces exactly that split rather than
  claiming more (`D172`). A frontend install is therefore still free to drift within those ranges;
  only a committed lockfile closes it.
- `--cov-fail-under` compares `round(total, precision)` against the threshold, and `precision`
  defaults to 0 — so a 90 threshold used to tolerate 89.5% and a run could print `FAIL` while exiting
  0. `backend/.coveragerc` sets `[report] precision = 2`, which is the resolution pytest-cov reports
  the total in, and that narrows the tolerance to `[89.995, 90)` — but no finite precision removes it,
  because the comparison is a rounded one at every precision. **`tests/coverage_gate.py` closes it**
  by comparing integer counts instead: `covered * 100 >= threshold * statements`, evaluated over
  `Fraction`, so 89.995% and 89.9999% are rejected. `tests/test_coverage_gate.py` asserts both halves
  of that split — that the rounded comparison admits those totals, that the exact gate rejects them,
  and that `.coveragerc` declares neither `fail_under` nor `[run] source` so the threshold and the
  measured scope stay command-line arguments. **This item is closed**, and remains listed only so the
  reasoning survives: the residual band is no longer a tolerated one.
- The root `README.md` describes an unrelated product — a static code analysis tool — and is
  deliberately left **byte-for-byte intact** apart from one strictly additive `## Testing` section. The
  same applies to the `frontend/package.json` name and the leftover Create React App
  `frontend/public/index.html`. Correcting the product identity is a real task, but it is a content
  decision for the repository's owners rather than a side effect of adding tests.
- **Closed, and recorded here because it was previously escalated:** `python-jose[cryptography]` was
  pinned at 3.3.0, which is affected by CVE-2024-33663 (algorithm and key confusion) and CVE-2024-33664
  (compressed-JWE decompression bomb), both fixed in 3.4.0. The manifest was held at 3.3.0 on the
  reading that AAP §0.6.1's table is a frozen specification; it is not — §0.1.4 freezes the endpoint
  shapes, the `Settings` field names, the Redux store shape, the zod contracts and the `api.ts`
  signatures, and names no dependency version. **The pin is now `==3.5.0`**, which is what the warmed
  environment actually installed, and the closure suite fails if the installed version differs. Neither
  CVE was reachable from any test here — `app/core/security.py` only encodes and decodes HS256 with an
  explicit key, so no JWE is decrypted and no OpenSSH ECDSA key is loaded — so the exposure had always
  been to *future* production use; it is now removed rather than documented.
- `starlette==0.27.0` carries a reachable Host-header advisory that cannot be closed without replacing
  `fastapi==0.95.2`. The behaviour is pinned by the Host census in
  `integration/test_route_surface.py`; the production mitigation — `TrustedHostMiddleware` in
  `app/main.py` — needs an authorization this programme does not have.
