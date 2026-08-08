# End-to-end suite

This directory holds the Playwright end-to-end layer and the Vite harness it runs against. It is
self-contained: everything the suite needs to boot a browser and drive the real UI components lives
under `e2e/`, and **no file under `frontend/` or `backend/` is modified, imported as a build input, or
required to be running.**

Twelve tests across four specs cover the four routed workspaces. Read section 1 first — it explains why
this layer supplies its own entry point instead of starting the application, which is the single fact
that makes the rest of the design legible.

You need nothing else to get started: sections 2 and 3 alone take a fresh clone to a green run. The
links below are for depth, not prerequisites.

## Where things live

| For | Go to |
| --- | --- |
| The repository entry point, and the cross-cutting Testing section that indexes all three suites | [`../README.md`](../README.md) |
| The frontend Jest suite — transforms, module mapping, the msw contract, `renderWithProviders` | [`../frontend/TESTING.md`](../frontend/TESTING.md) |
| The backend pytest suite — fixtures, import root, credential and socket guards | [`../backend/tests/`](../backend/tests/) |
| **Why** any choice below was made — alternatives weighed, risks accepted | [`../docs/testing/DECISION-LOG.md`](../docs/testing/DECISION-LOG.md) |
| Which test covers which construct, in both directions | [`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md) |
| The coverage and test-health dashboard | [`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md) |

Rationale is not duplicated here by design. This document covers **what** the layer is, **how** to run
and extend it, and **what breaks**. Every "why" belongs to the decision log; section 10 lists the rows
that matter most for this folder.

### Files in this directory

| Path | Role |
| --- | --- |
| [`package.json`](./package.json) | Manifest and the six scripts. Three exact-pinned dev dependencies, nothing else |
| [`playwright.config.ts`](./playwright.config.ts) | Runner: spec discovery, reporters, artifact paths, egress denial, and the `webServer` that starts the harness |
| [`vite.harness.config.ts`](./vite.harness.config.ts) | Harness dev server: module resolution, the virtual-module plugin, the filesystem guard, the fail-closed API surface |
| [`harness-origin.ts`](./harness-origin.ts) | The one place the host and port are resolved. Imported by both configs, so they cannot disagree |
| [`harness/index.html`](./harness/index.html) | The HTML entry the repository does not otherwise have |
| [`harness/main.tsx`](./harness/main.tsx) | The route table, the Redux store, and the `<main>` landmark |
| [`harness/stubs/`](./harness/stubs/) | Stand-ins for three modules the frontend imports but that do not exist |
| [`tests/`](./tests/) | The four specs, one per route |
| [`tests/harness-fixtures.ts`](./tests/harness-fixtures.ts) | Shared fixtures: the automatic egress abort and the un-intercepted-request ledger |
| [`fixtures/`](./fixtures/) | JSON payloads specs fulfil requests with |
| `.npmrc` | `package-lock=false` — see `D93` and `D159` |

## 1. Why this folder exists

### The application cannot be served

This is not a preference. A verbatim copy of `frontend/` under a default Vite server was probed, and
every route into the real application is closed:

- **`GET /` returns 404.** There is no HTML entry at the Vite root. The only `index.html` is
  `frontend/public/index.html`, served verbatim as a static asset — a Create React App leftover that
  still carries unsubstituted `%PUBLIC_URL%` tokens, a `<title>` of "Personal Finance Tracker", and no
  script tag for the application entry.
- **`npm run build` in `frontend/` fails at both legs.** `tsc` reports
  `TS6053: File 'tsconfig.node.json' not found`; `vite build` reports
  `Could not resolve entry module "index.html"`.
- **Every `.tsx` transform fails.** `frontend/tsconfig.json` declares a project reference to a
  `tsconfig.node.json` that does not exist, and esbuild's `loadTsconfigJsonForFile` throws `ENOENT` on
  it for every `.tsx` file it loads.
- **`GET /src/components/Dashboard` returns 500.** The file has no extension, so no JSX loader can be
  inferred for it.
- **`GET /tweets` returns 404.** There is no SPA history fallback.
- **`frontend/src/app.tsx` cannot render even if it were reachable.** It imports `{ store }` from a
  module whose reducer is invalid, imports a `setupInterceptors` symbol that nothing exports, and
  default-imports `TweetManagement`, which has only a named export.

None of that is repaired here. Repairing any of it means writing production files, which this work is
not authorized to do.

### What the harness does instead

The E2E layer supplies its own entry point. [`harness/index.html`](./harness/index.html) and
[`harness/main.tsx`](./harness/main.tsx) declare a route table that mirrors the one in
`frontend/src/app.tsx` and mount the same four component modules over a valid store — and the harness
**never mounts `app.tsx`**, because that module cannot render.

The consequence is worth stating plainly, and the traceability matrix states it too: **this layer
exercises the components, not the real application entry.** No passing result here should be read as
covering `frontend/src/app.tsx`.

Everything the harness needs in order to reach `frontend/src` is resolution configuration — aliases, a
virtual module id, three stubs and three appended exports. Nothing is copied, generated into, or
written back to `frontend/`. See `D40` for the decision and its accepted risk.

## 2. Setup: clean machine to green suite

### Runtime

**Node 16.x, npm 8.x** is the declared floor-and-ceiling of the toolchain. The ceiling comes from the
`.github/workflows/ci.yml` matrix (`node-version: [16.x]`), and that matrix is what selected every pin
in this package — most visibly `@playwright/test` at **1.44.1**, the last release whose `engines` field
declares `node>=16`. Release 1.45.3 and later require `node>=18`.

A newer Node also runs this suite: it was last exercised end to end on **Node v22.23.1 / npm 10.9.8**,
green. Every pinned package declares an open-ended minimum, so a higher Node is compatible. Node 16 is
what CI declares; anything from 16 upward works locally.

### Install, in this order

The order is a dependency, not a preference. Run both legs even if you only intend to touch `e2e/`.

```
cd frontend
npm install
```

```
cd e2e
npm install
```

**`frontend` must come first.** The harness resolves ten runtime packages —
`react-dom/client`, `react/jsx-dev-runtime`, `react/jsx-runtime`, `react-router-dom`,
`@reduxjs/toolkit`, `react-redux`, `react-dom`, `react`, `axios` and `chart.js` — to absolute paths
inside `frontend/node_modules`, and additionally lists `react`, `react-dom`, `react-redux`,
`react-router-dom` and `@reduxjs/toolkit` in `resolve.dedupe` so exactly one copy of each is in the
graph. Two copies of React produce an "Invalid hook call" at the first render. With `frontend/`
uninstalled, the harness has nothing to alias to and no route renders.

Five of those packages — `react-router-dom`, `@reduxjs/toolkit`, `react-redux`, `zod` and `dayjs` —
were imported by the frontend source but declared in no manifest until the test work added them to
`frontend/package.json`.

The `e2e` leg installs three packages and their transitive tree: `@playwright/test` 1.44.1,
`vite` 4.5.14 and `@vitejs/plugin-react` 4.0.4. All three are exact-pinned.

Expect `npm warn deprecated` lines on both legs, and `npm audit` findings. Neither leg writes a
`package-lock.json`: `.npmrc` in each package sets `package-lock=false`, and `npm install` rather than
`npm ci` is the documented command. See `D93` and `D159`.

### The browser prerequisite

**No script in this package downloads a browser, and none should be added.** `@playwright/test` 1.44.1
is affected by CVE-2025-59288: its browser downloader does not verify the TLS chain of the host it
fetches from. The remedy taken here is to provision only from an artifact verified out of band. See
`D111` and `D129` for the alternatives that were rejected and the residual risk that was accepted.

So the browser is a **prerequisite you satisfy before running the suite**, by either route:

1. **A Chromium build in Playwright's own cache.** Report what the runner expects, without fetching
   anything:

   ```
   cd e2e
   npm run browsers:verify
   ```

   That runs `playwright install --dry-run chromium` and prints the exact build and the exact directory
   it will be loaded from — for this pin, `chromium version 125.0.6422.26` under
   `<cache>/chromium-1117`. It downloads nothing and always exits 0, so it is safe in any pipeline.

2. **An executable you name explicitly.** Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to the full path of a
   Chromium or Chrome binary and `playwright.config.ts` passes it through as `launchOptions.executablePath`:

   ```
   PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chrome
   ```

   This is the route to use on a host that has a system browser but no Playwright cache.

If neither is in place, every test fails identically at launch with
`browserType.launch: Executable doesn't exist at <path>`. That message names the directory route 1
expects, so it tells you which route you are missing.

### Nothing else is required

- **No environment variables.** The suite reads none, apart from the optional overrides in this
  section and the next.
- **No backend.** Nothing starts `uvicorn`, and no spec talks to a real API. Every request the UI makes
  is answered by `page.route` interception in the spec that made it.
- **No credentials, and no network.** Egress is denied at two layers, described in section 4.
- **No separate server to start.** `playwright.config.ts` starts the harness through its `webServer`
  block and stops it when the run ends. Section 3 covers running it standalone, which is only for
  manual inspection.

### The origin: host, port, and parallel checkouts

The harness binds `127.0.0.1` — a literal address rather than `localhost`, which resolves to either
`127.0.0.1` or `::1` depending on the host's resolver order.

[`harness-origin.ts`](./harness-origin.ts) resolves the port once and both configs import it, so the
server and the runner can never disagree. Resolution order, first match wins:

| Source | Effect |
| --- | --- |
| `HARNESS_PORT` | Used verbatim |
| `E2E_PORT` | The same thing under the name the CI job uses; accepted so one contract covers both spellings |
| `CLONE_INDEX` | An offset added to the base port. `CLONE_INDEX=002` resolves to `4175` |
| none set | The base port, `4173` |

Leading zeros are accepted. A value that is not a base-10 non-negative integer, or that lands outside
1024-65535, falls through to the next source rather than binding a port the harness cannot serve on.

**Set `CLONE_INDEX` when several checkouts of this repository share one host.** A TCP port is
host-global, the harness uses `strictPort`, and `reuseExistingServer` is `false` unconditionally — so a
port already held fails the run loudly instead of quietly attaching your specs to somebody else's
server. That is deliberate: see `D112`.

## 3. Commands

Every command below is a script in [`package.json`](./package.json) or a direct invocation of the
pinned runner, and every one has been executed as written. Each names a **local** binary rather than
going through bare `npx`, which falls back to the registry when the local executable is missing.

### The suite

| Run from | Command | Does |
| --- | --- | --- |
| `e2e` | `npm test` | The whole suite. Starts the harness, runs 12 tests, stops the harness |
| repository root | `npm --prefix e2e test` | The same run, without changing directory |
| `frontend` | `npm run test:e2e` | The same run, chained through `npm --prefix ../e2e run test` |
| `e2e` | `npm run test:headed` | The same run with a visible browser window |
| `e2e` | `npm run test:debug` | The same run under the Playwright inspector. Interactive |

Under CI the fourth form is the one to use, with `working-directory: e2e` and the command
`npx playwright test` — inside the package, `npx` resolves the pinned local runner.

The `frontend` form takes no extra arguments: `npm run test:e2e -- --list` is rewritten to
`npm --prefix ../e2e run test --list`, npm consumes the flag itself, and the full suite runs instead of
listing. Use one of the `e2e`-local forms when you need to pass anything.

### Targeted runs

| Run from | Command | Does |
| --- | --- | --- |
| `e2e` | `npx playwright test --list` | Lists the 12 tests and exits. The collection check for this layer; needs no browser |
| `e2e` | `npx playwright test tests/dashboard.spec.ts` | One spec |
| `e2e` | `npx playwright test -g "renders an empty tweet-list container"` | One test by title |
| `e2e` | `npx playwright test --headed -g "<title>"` | One test, visible |

### The harness on its own

```
cd e2e
npm run harness
```

Serves the harness with no browser and no specs, for manual inspection — at `http://127.0.0.1:4173/`
by default, or at the port your `CLONE_INDEX` / `E2E_PORT` / `HARNESS_PORT` resolves to. It runs in the
foreground until interrupted. You do **not** need this to run the suite; `playwright.config.ts` starts
and stops its own instance.

Note when probing it by hand: request a route with an HTML `Accept` header. Vite's history fallback is
`Accept`-sensitive, so `curl http://127.0.0.1:4173/tweets` with a default `Accept: */*` returns 404
while a browser gets 200. See section 6.

### Reading the results

```
cd e2e
npm run report
```

Serves the HTML report at `http://localhost:9323` and blocks until interrupted. The report is written
by every run, so this only opens what is already on disk.

### Forms that do not work

**Do not run `npx playwright test --config e2e/playwright.config.ts` from the repository root.** There
is no runner installed at the root, so `npx` resolves nothing local and reaches for the registry
instead — it either refuses outright (`npx canceled due to missing packages`) or silently downloads a
different, unpinned Playwright and runs your suite on it. Use one of the five forms in the table above;
all of them resolve the runner this package pins. `playwright.config.ts` derives every path from
`__dirname` rather than the working directory, which is what makes all five equivalent.

### Interactive commands, deliberately excluded

`npx playwright test --ui` and `npx playwright codegen` both require a human at a terminal. They are
useful while writing a spec and are deliberately not part of any documented or automated flow, so
nothing in CI can block on them. `npm run test:debug` is listed above for the same reason it is not
scripted into CI — it opens the inspector and waits. `PWDEBUG=1` is the environment-variable
equivalent of that flag.

## 4. What the suite covers

### The four routed workspaces

[`harness/main.tsx`](./harness/main.tsx) mounts the real component modules from
`frontend/src/components`. Note the export kinds — three defaults and one named — and that all four
subjects are extension-less **files**, not directories:

| Route | Component | Subject | Export | Spec |
| --- | --- | --- | --- | --- |
| `/` | `RealTimeFeed` | `frontend/src/components/Dashboard` | default | [`tests/dashboard.spec.ts`](./tests/dashboard.spec.ts) |
| `/tweets` | `TweetList` | `frontend/src/components/TweetManagement` | **named** | [`tests/tweets.spec.ts`](./tests/tweets.spec.ts) |
| `/analytics` | `TrendCharts` | `frontend/src/components/Analytics` | default | [`tests/analytics.spec.ts`](./tests/analytics.spec.ts) |
| `/configuration` | `TwitterAPISettings` | `frontend/src/components/Configuration` | default | [`tests/configuration.spec.ts`](./tests/configuration.spec.ts) |

Three tests per spec, twelve in total. Which test pins which behaviour is recorded in
[`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md), not here.

The store is built in the harness from the two slice reducers in `frontend/src/store` — their
**default** exports. It is not `frontend/src/store/index.ts`, whose named imports the slices never
declare, leaving it with no valid reducer. The two props the route table passes (`filters` and
`dateRange`) are declared at module scope so each keeps one identity for the life of the page; a fresh
object per render would re-fire the effects that depend on it.

### Two of the four routes render a shell only

This is a property of the components, and the specs assert it rather than working around it:

- **`/`** renders its heading and nothing else. Every member of a non-empty tweet collection is
  rendered by `TweetCard`, which is defined nowhere and therefore `undefined` — an invalid element type
  that unmounts the route. Specs fulfil the collection request with `[]`; the non-empty
  [`fixtures/tweets.json`](./fixtures/tweets.json) exists only for the one test that documents this
  ceiling.
- **`/analytics`** renders its heading and its `<canvas>`. `harness/stubs/analyticsService.ts` rejects
  on every path, which holds the component on its caught-failure branch and keeps it from constructing
  a chart. Assert the heading and the canvas, never a painted chart.

### The interception contract

Each spec installs its own `page.route` handlers **before** navigating. Tweet fetches need **two**
patterns:

```
'**/tweets*'
'**/undefined/tweets*'
```

The second is not defensive. The axios base URL in `frontend/src/services/api.ts` evaluates to the
literal string `"undefined"`, so requests are issued to `/undefined/tweets?page=undefined&limit=undefined`,
and only a pattern carrying that segment matches. The harness preserves this on purpose — see section 6.

The other two endpoints belong to the harness stubs:

| Request | Pattern | Fulfilled with |
| --- | --- | --- |
| `GET /undefined/tweets` | `**/undefined/tweets*` | `[]` for render assertions; `fixtures/tweets.json` for the ceiling test |
| `GET /api/trends` | `**/api/trends*` | [`fixtures/trends.json`](./fixtures/trends.json), or a 500 for the failure path |
| `POST /api/config/twitter` | `**/api/config/twitter` | `{}` with 200 or a rejecting status |

### The API surface fails closed

A request to a known endpoint that no spec intercepted is **not** forwarded and **not** quietly 404'd.
The harness answers it `503` with a body naming the remedy:

```
{"error":"harness-api-not-intercepted",
 "request":"GET /undefined/tweets?page=1&limit=10",
 "remedy":"page.route('**/undefined/tweets*', route => route.fulfill({ json: [] }))"}
```

and logs the same line to the dev-server output under a `[harness-api-not-intercepted]` prefix. On top
of that, [`tests/harness-fixtures.ts`](./tests/harness-fixtures.ts) keeps a ledger and **fails any spec
that forgot an intercept**, so a missing handler is a named failure rather than an empty render. A
forgotten intercept therefore cannot be mistaken for a passing test.

Egress is denied below the route layer as well. `playwright.config.ts` launches Chromium with
`--host-resolver-rules`, `--proxy-server` and `--proxy-bypass-list` set so that no hostname resolves
except the harness origin and every other request is routed at a closed port, and
`harness-fixtures.ts` adds a context-wide abort that attributes any refusal to the test that caused it.
Service Workers are blocked, because `page.route` does not see their requests. See `D114` and `D128`.

### Specs are independent

`fullyParallel` is on and no spec depends on another's state: each installs its own routes, navigates
its own page, and asserts only what it rendered. Viewport, timezone (`UTC`) and locale (`en-US`) are
pinned in the config so nothing varies with the host. Run them in any order, or a single one alone.

## 5. Observability of this layer

Rule 2 asks what already existed and was reused, and what was added to fill a gap. For the repository
as a whole that split is
[`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md)'s to state; this
section covers only this layer's contribution, and does not restate the dashboard's metric contract.

**Reused.** At repository level, the two Codecov upload steps that already existed in
`.github/workflows/ci.yml`, together with their `backend` and `frontend` flag names, which are kept
exactly as they were. This layer adds no coverage series of its own and does not touch those flags.

**Added by this layer**, none of which had any equivalent before:

| Artifact | Path | Written |
| --- | --- | --- |
| HTML report | `e2e/playwright-report/index.html` | Every run. Opened with `npm run report` |
| JUnit XML result stream | `e2e/reports/e2e-junit.xml` | Every run. Each `<testcase>` carries its spec file and test title |
| Traces, screenshots, video | `e2e/test-results/` | On failure only — `retain-on-failure`, `only-on-failure`, `retain-on-failure` |
| Harness dev-server log | the run's own output | `webServer` pipes stdout and stderr, which is what surfaces the `[harness-api-not-intercepted]` lines |

All four paths are matched by the repository [`.gitignore`](../.gitignore), so no run dirties the tree.
CI uploads `e2e/playwright-report/` as a build artifact.

**Correlation.** A result is tied to its evidence by test title: the same title identifies the
`<testcase>` in the JUnit stream, the entry in the HTML report, and the directory under
`test-results/`. No separate identifier is minted.

**Tracing.** The Playwright trace is this repository's only genuine cross-boundary trace, because this
layer is the only place a request actually crosses a boundary — browser to intercepted API. It records
each request with its timing alongside the DOM snapshots, and it is retained on failure locally as well
as under CI, so a failure is diagnosable from the artifact without a reproduction.

**Checked and absent.** The application itself has no metrics endpoint, no tracing and no correlation
identifier on any production path, and the health checks in `infrastructure/docker/docker-compose.yml`
and `.github/workflows/cd.yml` target a `/health` route the application never declares. Those gaps were
checked, recorded in the decision log and listed in section 9. **None was implemented**: closing any of
them is production work outside the two changes this effort was authorized to make.

## 6. Common pitfalls

Each of these cost real time to establish. They are ordered by how likely you are to hit them.

**The four component subjects are extension-less files, and only a virtual module id reaches them.**
`vite.harness.config.ts` resolves each one to a NUL-prefixed id (`\0extless:<real path>`) whose `load`
hook reads the real file and hands it to `transformWithEsbuild` under a synthetic `.tsx` name. A
`?extless` query suffix and a `<path>.extless.tsx` id were both tried and both fail: Vite normalises the
id back to the real on-disk path and the `load` hook never fires. Renaming the files is not an option
here — they are production files.

**`resolve.alias` runs before `enforce: 'pre'` plugins.** By the time the resolver sees a component
import it may already be the aliased absolute path rather than `@/components/X`, so the resolver matches
**both** forms. If you add a subject and match only the bare specifier, it will resolve in some import
positions and not others.

**Vite's history fallback is `Accept`-sensitive.** A route request carrying `Accept: */*` — the default
for `curl` and most scripted clients — returns 404, while the same URL in a browser returns 200 and the
harness entry. When probing by hand, send `Accept: text/html`. A 404 from `/tweets` is almost never the
harness being broken.

**`frontend/tsconfig.json` points at a `tsconfig.node.json` that does not exist**, and that dangling
reference breaks every `.tsx` transform under a stock Vite server. The harness supplies
`esbuild.tsconfigRaw` inline and so never reads the file. Do not remove that option expecting the
project tsconfig to take over.

**`frontend/src/services/api.ts` reads `process.env` at module scope**, which a browser does not
provide. The harness supplies `define` entries for it. Two details matter: the declaration order is
load-bearing, because the dev client assigns these keys onto the global object in order and
`process.env` must come first or it would replace the object the keys under it were just written onto;
and `REACT_APP_API_BASE_URL` is deliberately left as the `undefined` literal, which preserves the
base URL production computes today. That is why the tweet endpoint is `/undefined/tweets` and why specs
need the second route pattern. Do not "fix" it — the defect is under test.

**Three modules the frontend imports do not exist**: `@/services/analyticsService`,
`@/services/configService` and `../schema/configSchema`. The harness redirects each to a file in
[`harness/stubs/`](./harness/stubs/), guarded by an existence check, so if a real module ever lands it
takes precedence over the stub automatically.

**Three named exports the frontend imports are never declared**: `api` from `services/api`, `getTweets`
from `services/twitterService`, and `TweetCard` from `components/TweetManagement` — which
`TweetManagement` imports **from itself**. A missing named export is a link-time error in native ESM, so
the module would not load at all. The harness appends those three names to the end of the real module's
source text, each valued `undefined`, which is exactly what the same import already carries under Jest
and CommonJS — so the importer reaches the same branch here as it does there. Nothing in the source text
is rewritten. `setupInterceptors` needs no such shim: only `app.tsx` imports it, and the harness never
mounts `app.tsx`.

**`server.fs.allow` must list every root the graph reaches.** The Vite root is `e2e/harness` and
`fs.strict` is on, so without explicit entries for `frontend/src` and `frontend/node_modules` the server
would refuse every frontend module. Five roots are allowed: the harness directory, the pre-bundle
cache, Vite's own client runtime, `frontend/src` and `frontend/node_modules`. Serving anything else
takes one more entry — and the same list drives the filesystem guard, so adding a root widens both
deliberately rather than by accident.

**`TweetCard` is undefined, so a non-empty tweet list breaks the render.** React throws
`Element type is invalid ... got: undefined` and the route unmounts. Fulfil collection requests with
`[]` for any assertion about the surrounding shell.

**`Analytics` never registers its Chart.js parts.** It imports the tree-shakeable `{ Chart }` export and
no module calls `Chart.register`, so chart construction cannot succeed — in this harness or in a real
browser. Assert the heading and the `<canvas>` element, not a rendered chart.

**`TwitterAPISettings` calls `alert()` on both success and failure.** Playwright auto-dismisses dialogs,
so the message vanishes unless the spec registers a `page.on('dialog', ...)` handler **before** the
action that triggers it.

**The harness port is `strictPort`.** A port already in use fails the start outright rather than quietly
moving to another one, and `reuseExistingServer` is `false`, so a stale server is never adopted. On a
shared host, set `CLONE_INDEX` (section 2) instead of hunting for whatever is holding the port.

## 7. Adding to this layer

### A route

Add one `<Route>` entry to the table at the bottom of [`harness/main.tsx`](./harness/main.tsx). If the
target is another extension-less file, add its name to the component array in
[`vite.harness.config.ts`](./vite.harness.config.ts) so the virtual-module resolver covers it. If it
needs a runtime package that is not yet aliased, add that package to the frontend-package list, and to
`resolve.dedupe` as well if more than one copy of it would break anything.

### A spec

Create `tests/<name>.spec.ts`. Import `test` and `expect` from
[`./tests/harness-fixtures.ts`](./tests/harness-fixtures.ts) rather than from `@playwright/test`
directly — that is what installs the egress guard and the un-intercepted-request ledger. Install every
`page.route` handler **before** `page.goto`, and reuse a payload from [`fixtures/`](./fixtures/) rather
than inlining one.

### A fixture

Add JSON to [`fixtures/`](./fixtures/). Keep a tweet payload's shape aligned with the ten fields
declared by both `frontend/src/schema/tweetSchema.ts` and `backend/app/schema/tweet.py`:
`tweet_id`, `content`, `user_id`, `timestamp`, `likes_count`, `retweets_count`, `doubt_rating`,
`ai_tools`, `media_urls`, `quoted_tweet_id`. A fixture that drifts from those schemas weakens every
assertion that reads it.

### A stub

Add the module to [`harness/stubs/`](./harness/stubs/) and one entry to the stub map in
`vite.harness.config.ts`. The mapping is existence-guarded, so it applies only while the real module is
absent.

### A missing export

If a frontend module imports a name nothing declares, add it to the compatibility-export map in
`vite.harness.config.ts` rather than editing the source. Keep the value `undefined` unless you have a
reason not to: that is what the same import carries under Jest, and matching it keeps the two suites
observing the same branch.

### The one hard rule

**No change to any file under `frontend/` or `backend/` is permitted from this folder.** Everything this
layer needs is expressible as resolution configuration, a stub, or an appended export. If something
appears to need a production edit, it belongs in section 9 as a suggested next task — not in a commit
from here.

## 8. Verification status

Stated plainly, because it is easy to overstate.

**At planning time, no test in this layer had been executed in a real browser.** The harness itself and
every version in the stack were verified — all four routes answered 200, every module URL in the graph
answered 200, and the dev-server log was error-free — but no spec had ever driven a browser. Two
reasons: the browser automation subagent was unavailable in the planning environment, and provisioning a
browser needs network access and system packages. Executing the suite in a real browser was therefore
recorded as an implementation-time acceptance step, in
[`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md) section 7.

**That step has since been performed, and this is its outcome.** The full suite ran in a real browser:

| | |
| --- | --- |
| Result | **11 passed, 1 skipped, 0 failed** — exit 0, 8.5s |
| Runner | `@playwright/test` 1.44.1, one `chromium` project |
| Browser | Provisioned out of band and named with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; the Playwright cache held no Chromium |
| Runtime | Node v22.23.1 / npm 10.9.8 |
| Artifacts | `playwright-report/index.html`, `reports/e2e-junit.xml` (`tests=12 failures=0 skipped=1 errors=0`), `test-results/` |

The one skip is deliberate and carries its reason in the spec:
`tests/analytics.spec.ts` → *"does not paint a chart because Chart.register is never called"*. Reaching
the chart-construction branch needs a resolved trend series, and the harness stub rejects on every path,
so **this layer cannot observe that failure** — `frontend/src/components/Analytics.test.tsx` mocks the
service and covers it instead. The skip is a record of a boundary, not a gap.

Re-run it yourself with the commands in section 3; nothing above depends on state this repository does
not carry. Two limits remain, and both are listed in section 9: only `chromium` is exercised, and the
browser is a prerequisite rather than something a script here obtains.

## 9. Suggested next tasks

Everything in this section is **out of scope and deliberately not fixed.** Where a defect is asserted by
a test, repairing it will turn a passing test red on purpose —
[`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md) records which test
pins which defect, so check it before attempting any of these.

**Would let the real application be served, and retire most of this harness**

1. There is no `frontend/vite.config.ts` and no HTML entry at the Vite root, so the dev server answers
   `/` with 404 and `npm run build` fails at both legs — `tsc` on the dangling reference, then Rollup on
   the missing entry module.
2. `frontend/tsconfig.json` declares a project reference to a nonexistent `tsconfig.node.json`, which
   breaks **every** `.tsx` transform under Vite.
3. `frontend/public/index.html` is a Create React App leftover carrying unsubstituted `%PUBLIC_URL%`
   tokens, an unrelated product title, and no script tag for the application entry.
4. The four component subjects are extension-less files rather than modules with a `.tsx` extension,
   which is why a virtual module id is needed to load them at all.

**Would let the harness mount `frontend/src/app.tsx` instead of its own route table**

5. `src/store/index.ts` imports `{ tweetReducer }` and `{ configReducer }`, which the slices never
   export; the store silently has no valid reducer and `getState()` returns `{}`.
6. `src/services/api.ts` exports neither `api` nor `setupInterceptors`, both of which `src/app.tsx`
   imports.
7. `TweetCard` is imported by two components — `TweetManagement` imports it from itself — and is defined
   nowhere, so any non-empty tweet list renders an invalid-element-type error.
8. `src/services/twitterService.ts` imports `getTweets`, which is not exported, and calls the
   two-parameter `fetchTweets` with a single argument.
9. `useAppDispatch` and `useAppSelector` are imported by three page modules and exported by nothing.
10. All four `src/pages/*.tsx` modules are orphaned: `src/app.tsx` routes only to `src/components/*`, so
    no route reaches a page module.
11. `src/index.tsx` calls `ReactDOM.render`, a React 17 API, under React 18.

**Would make assertions here stronger**

12. `Analytics` imports the tree-shakeable `{ Chart }` and never calls `Chart.register`, so chart
    construction fails in every environment including a real browser. Closing this is what would let the
    skipped test in section 8 run.
13. The axios base URL evaluates to the literal string `"undefined"`, so every request is issued to
    `undefined/tweets?...` — which is why the interception contract needs two patterns instead of one.

**This layer specifically**

14. Only `chromium` is exercised. Add a second and third browser project once the declared Node ceiling
    lifts, since the Playwright releases that broaden browser support require `node>=18`.
15. `e2e/package.json` declares no `engines` field, so nothing mechanically enforces the Node floor the
    pins assume.
16. No lockfile exists for any package, so no install is byte-reproducible. Committing one is unblocked
    and would let CI return to `npm ci`; today the exact pins in each manifest, plus a dependency-closure
    test, stand in for it.
17. The `e2e` job in `.github/workflows/ci.yml` still installs browsers with
    `playwright install --with-deps chromium` and invokes the runner from the repository root — the two
    forms sections 2 and 3 identify as unusable here. Aligning that job with the working forms is a
    workflow change, not a test change.
18. `.github/workflows/cd.yml` contains a post-deployment health-check step whose body is entirely
    comments, so it passes vacuously and gates nothing, and `docker-compose.yml` health-checks a
    `/health` route the application never declares.

**Repository-wide, and independent of testing**

19. The `flake8`, `mypy` and `npm run lint` steps in `ci.yml` are broken independently of this work — no
    linter or type checker is declared anywhere in the repository.
20. The application has no metrics endpoint, no tracing, no correlation identifier on any production
    path, and no structured logging: two modules report failures with `print`, and nothing under
    `backend/app/` imports `logging` at all.
21. `README.md` describes an unrelated static-analysis product, and `frontend/package.json` is named
    `data-visualization-dashboard` — a second unrelated identity. Both stale identities are left
    byte-for-byte intact by design.

## 10. Where "why" lives

This document explains mechanics. Every design decision behind it, with the alternatives that were
weighed and the risk each choice accepts, is in
[`../docs/testing/DECISION-LOG.md`](../docs/testing/DECISION-LOG.md) — section 4 covers this harness and
runner, section 10 its security hardening and determinism guarantees, and section 14 the observability of
its own HTTP. The rows this folder leans on most:

| Row | Question it answers |
| --- | --- |
| `D40` | Why a harness-owned route table instead of mounting `frontend/src/app.tsx` |
| `D41` | Why a NUL-prefixed virtual module id, and why the two simpler ids do not work |
| `D42` | Why missing named exports are appended as `undefined` rather than implemented |
| `D93`, `D159` | Why no lockfile is committed, and why `npm install` rather than `npm ci` |
| `D111`, `D129` | Why no script downloads a browser, and what `browsers:verify` replaces |
| `D112` | Why `reuseExistingServer` is `false` unconditionally |
| `D114`, `D128` | Why egress is denied at two layers, and why only one origin is bypassed |
| `D123` | Why the harness is started through the pinned local binary with an explicit port |
| `D130` | Why the host and port are resolved in exactly one module |

Which spec covers which construct, in both directions, is in
[`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md). The coverage and
test-health metric contract is
[`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md)'s.
