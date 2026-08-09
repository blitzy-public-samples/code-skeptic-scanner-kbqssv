# Backend test suite

Everything you need to run, understand, and extend the tests under `backend/tests`.

This suite is the first executable test coverage this repository has ever had. It asserts what the
production code **actually does today**, including the places where that diverges from the design
documents, because a test that asserts an intention the code does not implement fails for the wrong
reason and teaches nobody anything.

**Current state:** 774 tests collected, 771 passing, 3 skipped with reasons, 93.33% line coverage on
the four gated packages. `pytest --collect-only -q` reports zero errors.

Those are measurements from CPython 3.9.13 with `backend/requirements-dev.txt` installed, taken against
commit `8a255fb`, out of `backend/reports/junit.xml` and `backend/coverage.json`. Every figure in this
document carries that provenance in the section that quotes it, and none of it is a target — re-run
before quoting any of it on a later commit. §8 lists the artifacts and which of them a CI run retains.

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
| `python-jose[cryptography]==3.3.0` | The value AAP §0.6.1 declares, and the JWT implementation the whole token surface runs on. It is affected by CVE-2024-33663 (algorithm and key confusion) and CVE-2024-33664 (compressed-JWE decompression bomb), both fixed in 3.4.0; neither is reachable here, because the suite only encodes and decodes HS256 with an explicit key. Raising the pin changes a frozen specification, so the exposure is escalated as an open item rather than closed here — see the suggested next tasks in §12. |

The rest of the manifest is the test stack (`pytest-asyncio`, `pytest-cov`, `coverage`, `freezegun`,
`pytest-xdist`) plus the runtime stack the tests exercise. `starlette==0.27.0` carries an in-file
comment recording two advisories that cannot be closed without replacing `fastapi==0.95.2`; read the
comment before proposing a bump.

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
makes the failure quiet rather than obvious: a root-level `pytest` collects all 774 tests and then
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
├── requirements-dev.txt           # the only Python manifest
└── tests/
    ├── __init__.py
    ├── conftest.py                # shared infrastructure: prologue, guards, every shim, all fixtures
    ├── factories.py               # deterministic data builders
    ├── test_dependency_closure.py # environment gate: installed versions == manifest pins
    ├── test_guard_contract.py     # infrastructure gate: the three guarantees conftest.py makes
    ├── unit/                      # 11 suites, one per production module
    │   ├── __init__.py
    │   ├── test_api_dependencies.py
    │   ├── test_core_config.py
    │   ├── test_core_security.py
    │   ├── test_db_bigquery.py
    │   ├── test_db_firestore.py
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

**`unit/` — one module per production module, 11 suites.** Every external client is patched at the
*importing* module's boundary (§6), so no unit test constructs a Google Cloud client, opens a socket
or reads a clock. This is where the boundary matrices and the error-disposition assertions live.

**`integration/` — 3 suites, the real HTTP surface only.** Exercised through
`app.dependency_overrides`, which is keyed on the `app.db.firestore.get_db` function object. The
implemented surface is three operations on one prefix-less router: `GET /tweets`,
`GET /tweets/{tweet_id}` and `POST /tweets/{tweet_id}/responses`. There is no `/users`, no
`/analytics`, no `/config`, no `/token` and no `/health`, and no route carries the `API_V1_STR`
prefix even though the setting declares `/api/v1`. `test_route_surface.py` asserts that census as a
404 inventory rather than leaving it implied.

Every test in the tree belongs to one of those two layers; nothing sits at the `tests/` root but the
shared infrastructure — `conftest.py`, `factories.py` and the package marker.

**`test_guard_contract.py` — 77 tests at the `tests/` root.** Its subject is `conftest.py` itself. Every
other suite here rests on three promises — that a failure message never prints a credential, that a
loopback port is authorized only while this process holds it, and that a child process is refused in
every phase rather than only inside a test — and each of those was once true only in the common case.
Two of its probes run where no test is running: one at the module's own scope, which pytest evaluates
during collection, and one in a module-scoped finalizer that runs after the per-test guard attribution
has been cleared. Both name a command that exists nowhere, so a missing guard fails loudly instead of
spawning anything.

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

Four traps, each of which cost real time to find. Read this section before you write a test, not after.

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

---

## 8. Run commands

**Every command runs from `backend/`** (§2). `addopts` in `pytest.ini` carries `-ra`,
`--strict-markers` and `--junitxml=reports/junit.xml`, and deliberately carries **no** `--cov` flag, so
coverage is always requested at invocation and an ordinary run stays fast.

| Purpose | Command |
|---|---|
| Full suite | `pytest` |
| Coverage measurement | `pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-report=json --cov-report=lcov` |
| **The gate** | `pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-fail-under=90` |
| Unit layer only | `pytest tests/unit -m unit` |
| Integration layer only | `pytest tests/integration -m integration` |
| Single file | `pytest tests/unit/test_core_security.py` |
| Single test | `pytest tests/unit/test_core_security.py::test_verify_password_raises_on_unusable_hash` |
| Single parametrised case | `pytest "tests/unit/test_tasks_tweet_processor.py::test_on_status_skips_below_popularity_threshold[50-49]"` |
| Debug | `pytest -vv -s --log-cli-level=DEBUG --showlocals --tb=long` |
| Stop at first failure | `pytest -x --tb=short` |
| **Collection gate** | `pytest --collect-only -q` |
| Parallel | `pytest -n auto` |

Quote a parametrised node id — the `[` and `]` are shell metacharacters in most shells.

There is **no watch mode and none is added.** The full suite finishes in roughly six seconds, so a
plain re-run is faster than any file watcher would be.

### What each command should print

| Command | Expected outcome |
|---|---|
| `pytest` | `771 passed, 3 skipped` |
| `pytest tests/unit -m unit` | `483 passed, 3 skipped` |
| `pytest tests/integration -m integration` | `150 passed` |
| `pytest tests/test_dependency_closure.py` | `41 passed` |
| `pytest tests/test_coverage_gate.py` | `20 passed` |
| `pytest tests/test_guard_contract.py` | `77 passed` |
| `pytest --collect-only -q` | `774 tests collected`, **zero errors** |
| The gate | `Required test coverage of 90% reached. Total coverage: 93.33%` |

The counts close on the whole: 483 + 3 + 150 + 41 + 20 + 77 = 774.

Provenance for the table, in the same form used throughout this document:

| | |
|---|---|
| Runner | `pytest` 8.4.2 with `pytest-asyncio` 0.26.0 and `pytest-cov` 6.1.1, installed from `backend/requirements-dev.txt` |
| Runtime | CPython 3.9.13 in `.venv-backend`, Windows |
| Commit | Measured against `8a255fb`. Check it out and re-run to reproduce every count in the table |
| Artifacts | `backend/reports/junit.xml` — root attributes `tests`, `failures`, `errors`, `skipped` — and `backend/coverage.json` for the gate percentage. The layer split above is derived from `classname` prefixes: `tests.unit.`, `tests.integration.` and `tests.test_dependency_closure` |
| Retention | Local-only as run above. The equivalent CI step retains `junit.xml`, both coverage reports and the collection summary as `build-test-evidence`, 30-day retention |

### Collection integrity is a gate in its own right

```bash
cd backend && pytest --collect-only -q      # must report ZERO errors
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

> **`--collect-only` overwrites `reports/junit.xml` with a zero-case stub.** `--junitxml` lives in
> `addopts`, so it applies to *every* invocation — including a collection run, which writes a well-formed
> report declaring `tests="0"`. Nothing warns you. Run the gate after a suite and your result stream is
> replaced by a file that reads as a clean run of nothing.
>
> Three things make that safe here rather than merely known. The workflow runs the readiness step
> **before** the suite, so the real report is written last. The `Verify backend report artifacts` step
> rejects a `tests="0"` stream outright, with an error message that names this cause. And the extractor
> refuses the same stream rather than rendering it as zeros. Locally, just re-run the suite afterwards.
>
> `playwright test --list` has the identical defect, handled the same way — see
> [`../../e2e/README.md`](../../e2e/README.md) §3. `jest --listTests` does **not**: it leaves
> `frontend/reports/jest-junit.xml` byte-identical, verified by hashing it either side of a run.

### On `-n auto`

`pytest-xdist` is installed and works — `pytest -n auto` reports the same `771 passed, 3 skipped`. It
is **not** enabled by default, and on a many-core machine it is markedly *slower*: on this host it
spawned 49 workers and took 81 seconds against roughly 6 seconds serial, because process startup
dominates a suite this fast. Nothing in the design depends on execution order, so parallelism is always
safe; it is just rarely worth it. Prefer `-n 4` over `-n auto` if you want it.

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
| The collectability gate | `pytest --collect-only -q` | The readiness check described above. |

Verify all of it on disk — the **Observability** rule is not satisfied by configuration alone:

```bash
cd backend
pytest --cov=app --cov-report=xml --cov-report=json --cov-report=lcov
ls reports/junit.xml coverage.xml coverage.json coverage.lcov
```

| Artifact | Path | Written by | Retained by CI |
|---|---|---|---|
| JUnit XML | `backend/reports/junit.xml` | `addopts`, every run | yes — `build-test-evidence`, 30 days |
| Collection summary | `backend/reports/collect-only.txt` | the readiness step's `tee` | yes — `build-test-evidence` |
| Cobertura XML | `backend/coverage.xml` | `--cov-report=xml` — also the file the `backend`-flagged Codecov step uploads | yes |
| Coverage JSON | `backend/coverage.json` | `--cov-report=json` — the only per-module producer, so the dashboard depends on it | yes |
| Coverage LCOV | `backend/coverage.lcov` | `--cov-report=lcov` | **no** — the CI command does not request this reporter |
| Coverage database | `backend/.coverage` | `pytest-cov` | no — an intermediate, not evidence |

Two workflow steps read `junit.xml` before the Codecov upload and fail with an explicit annotation if it
is missing, empty, or declares zero test cases, so a collection-time stub can never be published as a run.

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
| Commit | Measured against `8a255fb`, which is also the commit that introduced `backend/.coveragerc` and so the first at which these figures are gated at two decimals |
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
→ FAIL Required test coverage of 90% not reached. Total coverage: 89.93%
```

The whole tree lands at **90.97%** — 288 statements, 26 missed — while the four named packages reach 93.33%
with real headroom. The entire difference is the unreachable regions listed below. Widening the gate's
scope would not raise quality; it would force someone to chase branches that no test can execute
without changing production code, which is precisely the scope expansion the programme forbids. The
reasoning is recorded in [`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) §7.

> **The rounding edge that used to make this number ambiguous, and how it is closed.** coverage.py
> rounds the total to the configured precision *before* comparing it to the threshold, and that
> precision defaults to **zero decimal places**. At the default, the run above printed `FAIL` and still
> **exited 0**: 89.93 rounds to 90 and satisfies `>= 90`, while pytest-cov's message compares the
> unrounded value. A 90 threshold therefore tolerated anything from 89.5% upward — a gate that reports
> failure and returns success, which is the worst state a CI gate can be in.
>
> `backend/.coveragerc` now declares **`[report] precision = 2`**, which is the value pytest-cov
> reads when no `--cov-precision` flag is given, so every invocation is gated at that resolution -
> including a developer's. `.github/workflows/ci.yml` repeats the flag on the backend command so the
> gate is legible at the invocation site, and `backend/pytest.ini` deliberately carries no coverage
> option at all, so a bare `pytest` neither measures nor gates. The comparison happens at the resolution the number is reported in, so 89.99% fails
> a 90 threshold. Reproduce both halves:
>
> ```text
> pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-precision=0 --cov-fail-under=92
> → FAIL Required test coverage of 92% not reached. Total coverage: 91.79%   — and exits 0
>
> pytest --cov=app/core --cov=app/services --cov=app/tasks --cov=app/db --cov-fail-under=92
> → ERROR: Coverage failure: total of 91.79 is less than fail-under=92.00   — and exits 1
> ```
>
> The first line is the old behaviour, kept here as the demonstration; the second is what the committed
> configuration does. 89.93% and 91.79% are the totals this tree measured when the defect was reproduced;
> the same commands read 90.97% and 93.33% today, and either pair demonstrates the same thing. The scoped
> gate passes a 90 threshold either way — the point is that it
> now passes for a reason you can check. See `DECISION-LOG.md` row D226.
### `--cov-fail-under` needed configuration before it meant what it says

Out of the box the comparison is **not exact**, and the failure mode is the worst kind: the run prints
`FAIL` and exits **0**.

coverage.py's check is `round(total, precision) < fail_under`, and `precision` defaults to **0**. So
89.93 rounded to zero decimals is 90, which satisfies `>= 90`, while pytest-cov's message compares the
*unrounded* value and correctly reports failure. A threshold of 90 silently tolerated anything from
**89.5%** upward — half a percentage point of undetected regression, reported as a failure and exiting as
a success.

`backend/.coveragerc` closes it:

```ini
[report]
precision = 2
```

That is the whole fix. `precision` governs both the reported figure and the value the threshold is
compared against, so setting it to 2 makes the gate exact to a hundredth and makes every number the run
prints agree with the number it gated on. It is a config file rather than an addition to `pytest.ini`
because `pytest.ini` cannot host a `[report]` section, and `backend/` had no `.coveragerc`, `setup.cfg` or
`pyproject.toml` for coverage to read.

Reproducible before and after, on the same tree:

| Command | Before `.coveragerc` | After |
|---|---|---|
| `pytest --cov=app --cov-fail-under=90` | prints `FAIL … Total coverage: 89.93%`, **exits 0** | `ERROR: Coverage failure: total of 89.93 is less than fail-under=90.00`, **exits 1** |
| The gated command at `--cov-fail-under=91.79` | — | exits **0** |
| The gated command at `--cov-fail-under=91.80` | — | exits **1** |

The last two rows are the point: the boundary now sits exactly where the measured total sits, to a
hundredth, with no tolerance band on either side.

Two consequences to carry:

- **Quote backend coverage to two decimals.** A figure written as a whole number was produced before this
  and does not describe the gate. That is why the tables in this document read `88.89%` rather than `89%`.
- **The whole-tree scope is now unambiguous too** — it fails, and it exits 1. The four-package scope is
  still the right gate for the reason above, but it is no longer the only *self-consistent* one.

`D252` in [`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) records the choice and its alternatives;
§12 below carries what remains unaddressed.

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

These are the three skips a green run reports. Each is written out in full, so implementing the feature
is a matter of removing one decorator.

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
[`DECISION-LOG.md`](../../docs/testing/DECISION-LOG.md) §23. Where the suite asserts the current broken
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
- **No lockfile exists anywhere in the repository**, so no install is byte-reproducible, and the three
  packages mitigate that to different degrees. The backend is fully exact-pinned: all 25 active lines of
  `requirements-dev.txt` are `==`, and `test_dependency_closure.py` fails if any one of them is not, if the
  parsed-pin count does not equal the active-line count, or if an installed version differs. `e2e/package.json`
  exact-pins all three of its direct dependencies. **`frontend/package.json` is only partly pinned**: the 11
  devDependencies this testing work introduced are exact, while the 17 pre-existing declarations — 7 runtime
  and 10 development — stay at their baseline caret ranges, because the authorized change boundary for that
  file is devDependencies and test scripts. So the frontend's direct graph is *not* closed by its manifest
  alone, and `frontend/src/test-utils/dependency-closure.test.ts` enforces exactly that split rather than
  claiming more (`D172`). A frontend install is therefore still free to drift within those ranges;
  only a committed lockfile closes it.
- `--cov-fail-under` compares `round(total, precision)` against the threshold, and `precision`
  defaults to 0 — so a 90 threshold used to tolerate 89.5% and a run could print `FAIL` while exiting
  0. `backend/.coveragerc` now sets `[report] precision = 2`, which is the resolution pytest-cov
  reports the total in, and `tests/test_coverage_gate.py` asserts the whole chain: the file's value,
  the value `coverage.Coverage` derives from it, that 89.5/89.93/89.99 fail at 2 and pass at 0, and
  that the file declares neither `fail_under` nor `[run] source` so the threshold and the measured
  scope stay command-line arguments. The residual band no finite precision removes — a total in
  `[89.995, 90)` — is asserted too: it is admitted, and it also prints as `90.00`, so the exit status
  and the message can never disagree.
- The root `README.md` describes an unrelated product — a static code analysis tool — and is
  deliberately left **byte-for-byte intact** apart from one strictly additive `## Testing` section. The
  same applies to the `frontend/package.json` name and the leftover Create React App
  `frontend/public/index.html`. Correcting the product identity is a real task, but it is a content
  decision for the repository's owners rather than a side effect of adding tests.
- **Escalated, not closed:** `python-jose[cryptography]==3.3.0` is affected by CVE-2024-33663
  (algorithm and key confusion) and CVE-2024-33664 (compressed-JWE decompression bomb), both fixed in
  3.4.0. 3.3.0 is the version AAP §0.6.1 declares, and the manifest is held to it rather than raised,
  because changing a frozen specification is a decision its owner makes. Neither CVE is reachable from
  any test here — `app/core/security.py` only encodes and decodes HS256 with an explicit key, so no JWE
  is decrypted and no OpenSSH ECDSA key is loaded — so the exposure is to *future* production use of
  this dependency. Raising the pin to 3.4.0 or later, with the AAP amended to match, is the task.
- `starlette==0.27.0` carries a reachable Host-header advisory that cannot be closed without replacing
  `fastapi==0.95.2`. The behaviour is pinned by the Host census in
  `integration/test_route_surface.py`; the production mitigation — `TrustedHostMiddleware` in
  `app/main.py` — needs an authorization this programme does not have.
