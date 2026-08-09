# End-to-end suite

This directory holds the Playwright end-to-end layer and the Vite harness it runs against. Two claims are
worth keeping apart, because only one of them is "self-contained":

- **What this layer owns.** Every file it needs to boot a browser and serve a page lives under `e2e/` — the
  HTML entry, the route table, the store, the Vite config, the stubs, the specs. Nothing under `frontend/`
  or `backend/` is modified, and **neither the frontend dev server nor the backend has to be running.**
  That is the sense in which the harness stands alone: it does not depend on an application this
  repository cannot start.
- **What it reads.** It is *not* isolated from `frontend/`. The whole point of the layer is to drive the
  real components, so the harness imports four modules out of `frontend/src/components`, reaches
  `frontend/src/store` and `frontend/src/services` through the `@/*` alias, and pins ten bare specifiers —
  `react`, `react-dom`, `react-dom/client`, `react-redux`, `react-router-dom`, `@reduxjs/toolkit` among
  them — into `frontend/node_modules` so exactly one copy of React exists. **`cd frontend && npm install`
  is therefore a prerequisite of this suite**, as section 2 says: install `frontend` before `e2e`.

So: production source and installed dependencies are build **inputs**; the production application is not a
runtime **dependency**.

What it deliberately does *not* mean is that `e2e/` stands alone. The harness exists precisely so that
the specs drive the **real** frontend components, so `frontend/src/` is a build input: the harness
resolves `@/*` into it, reads the four extension-less component files through a virtual module, imports
the two Redux slices and the three service modules, and aliases `react`, `react-dom`, `react-redux`,
`react-router-dom` and `@reduxjs/toolkit` into `frontend/node_modules` so exactly one copy of React
exists. Practical consequences: **install `frontend` before `e2e`**, and a change to a component or a
slice can turn a spec red without any file under `e2e/` having moved. What `e2e/` supplies on its own is
the *entry point* — an HTML document, a route table and a valid store — because the repository has none
that works.

What `e2e/` does not own is the code under test. The harness imports the real component modules from
`frontend/src` and resolves ten runtime packages out of `frontend/node_modules`, so both are **required
read-only build inputs**: `frontend` must be installed before this package, and with `frontend/`
uninstalled no route renders. Section 2 states the order and lists the packages.

Thirty-one tests across five specs: four route specs covering the four routed workspaces, plus one that
asserts the request-isolation property the other four rest on. Read section 1 first — it explains why
this layer supplies its own entry point instead of starting the application, which is the single fact
that makes the rest of the design legible.

Two prerequisites, and only two: the `frontend` install above, and a Chromium build provisioned out of
band — nothing here downloads one. Sections 2 and 3 cover both and take a fresh clone to a green run.
The links below are for depth, not prerequisites.

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
| [`package.json`](./package.json) | Manifest and the eight scripts — the two run forms, the list and report forms, the headed and debug forms, the harness server, and the two browser gates. Three exact-pinned dev dependencies, nothing else |
| [`scripts/require-browser.js`](./scripts/require-browser.js) | The **resolving** browser gate behind `browsers:require`: searches four routes, validates, canonicalises, hashes, publishes the path and its SHA-256, refuses a build below `--min-major`, and fails when there is none. Downloads nothing |
| [`scripts/verify-browser.js`](./scripts/verify-browser.js) | The **confirming** browser gate behind `browsers:verify`: prints the absolute path a run will launch, or names both routes it checked and the exact path each was checked at. Exits non-zero when neither route holds a launchable file, and — when `browsers:require` has published a digest — when the file no longer matches it. Downloads nothing |
| [`playwright.config.ts`](./playwright.config.ts) | Runner: spec discovery, reporters, artifact paths, egress denial, and the `webServer` that starts the harness |
| [`vite.harness.config.ts`](./vite.harness.config.ts) | Harness dev server: module resolution, the virtual-module plugin, the filesystem guard, the fail-closed API surface. Its "Harness origin" section is also the one place the host and port are resolved, and it exports `BASE_PORT`, `HARNESS_HOST`, `HARNESS_PORT` and `HARNESS_ORIGIN` so the runner, the fixtures and the server cannot disagree |
| [`harness/index.html`](./harness/index.html) | The HTML entry the repository does not otherwise have |
| [`harness/main.tsx`](./harness/main.tsx) | The route table, the Redux store, and the `<main>` landmark |
| [`harness/stubs/`](./harness/stubs/) | Stand-ins for three modules the frontend imports but that do not exist |
| [`tests/`](./tests/) | Five specs: one per route, plus [`isolation.spec.ts`](./tests/isolation.spec.ts), which asserts that a spec's own route claims the harness origin and no other |
| [`tests/harness-fixtures.ts`](./tests/harness-fixtures.ts) | Shared fixtures: the automatic egress abort, the un-intercepted-request ledger, and `consumeAbortedRequestUrls()` for the one spec whose subject is a refusal |
| [`fixtures/`](./fixtures/) | JSON payloads specs fulfil requests with |

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
declares `node>=16`. **1.45.0** is the first release that declares `node>=18`, and the current line
(1.62.1 at the time of writing) declares `node>=20`, so no upgrade is available without moving the
declared Node ceiling first.

A newer Node also runs this suite: it was last exercised end to end on **Node v22.23.1 / npm 10.9.8**,
green. Every pinned package declares an open-ended minimum, so a higher Node is compatible. Node 16 is
what CI declares; anything from 16 upward works locally.

### Install, in this order

The order is a dependency, not a preference. Run both legs even if you only intend to touch `e2e/`.
Both lines are run **from the repository root**, and the parentheses keep each `cd` inside a subshell so
the second line still starts there — copy them as one block:

```
(cd frontend && npm install)
(cd e2e && npm install)
```

Neither `npm install --prefix frontend` nor `npm --prefix frontend install` is an alternative: `npm
install` reads the manifest of the directory it is invoked from and `--prefix` does not change that in
either position, so with no root `package.json` both fail with `ENOENT ... open .../package.json`.
`npm --prefix <dir> run <script>` *does* resolve the manifest at `<dir>`, which is why the command table
in section 3 uses that form.

**`frontend` must come first**, and it is a build-input dependency rather than a convention. The
harness resolves ten runtime packages —
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

Expect `npm warn deprecated` lines on both legs, and `npm audit` findings. Neither package commits a
`package-lock.json`, so `npm install` rather than `npm ci` is the documented command; both manifests
exact-pin their direct dependencies instead. See `D93` and `D275`.

### The browser prerequisite

**No script in this package downloads a browser, and none should be added.** `@playwright/test` 1.44.1
is affected by CVE-2025-59288: its browser downloader does not verify the TLS chain of the host it
fetches from. The remedy taken here is to provision only from a channel that signs what it ships. See
`D111`, `D129` and `D264` — the last superseded by `D300`, `D301` and `D319` — for the alternatives that were rejected and
the residual risk that was accepted.

So the browser is a **prerequisite, obtained from your platform's own trusted channel**. Two steps:
get one, then prove the suite can launch it. Pick the row for the machine you are on — every command
here installs a signed artifact through a package manager or a vendor installer, and none of them is
Playwright's downloader:

| Platform | Provision with | Lands at |
| --- | --- | --- |
| Debian / Ubuntu | `sudo apt-get install -y google-chrome-stable` with Google's signing key configured, or `sudo apt-get install -y chromium` | `/usr/bin/google-chrome`, `/usr/bin/chromium` |
| RHEL / Fedora | `sudo dnf install -y google-chrome-stable` or `sudo dnf install -y chromium` | `/usr/bin/google-chrome`, `/usr/bin/chromium` |
| macOS | `brew install --cask google-chrome`, or the installer from google.com/chrome | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` |
| Windows | `choco install googlechrome`, or the vendor installer | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| GitHub-hosted CI | **nothing to install.** The `ubuntu-latest` runner image already ships `google-chrome-stable`, built into the image from Google's signed repository | `/usr/bin/google-chrome` |
| Any of the above | a Chromium build already sitting in Playwright's own cache, however it got there | `<cache>/chromium-*/…` |

Then let the gate decide whether a run can proceed, and let it fail if nothing is there:

```
cd e2e
npm run browsers:require
```

**`browsers:require` is the gate.** It runs
[`scripts/require-browser.js`](./scripts/require-browser.js), which resolves a browser in this order and
stops at the first hit:

1. **`PLAYWRIGHT_CHROMIUM_EXECUTABLE`**, which `playwright.config.ts` passes through as
   `launchOptions.executablePath`. An explicit value is authoritative in *both* directions: it is used
   when it works, and it is an **error** when it does not, never silently replaced by something else. A
   blank or undefined variable falls through to the next route.
2. **`CHROME_BIN`**, the conventional variable a CI image or a developer sets to name a browser, treated
   exactly like route 1 — authoritative both ways.
3. **A vendor install** at one of the paths in the table above for this platform.
4. **The build in Playwright's own cache**, at the exact path `chromium.executablePath()` reports for
   this pin — here `chromium-1117`, browser version `125.0.6422.26`. That call is the only correct source
   for this route: Playwright loads the build matching its own pinned revision and nothing else, and it
   is the only thing that knows where `PLAYWRIGHT_BROWSERS_PATH` points — including the value `0`, which
   relocates the cache inside the `playwright-core` package. Place a build there from a verified
   artifact; nothing in this package will fetch it for you.

It downloads nothing, and **exits non-zero when there is no usable browser** — or when one is found but
cannot be read — listing the provisioning commands for the platform it is running on. On success it
prints the route it took, the path it resolved, the **canonical** path with symlinks resolved, the
executable's SHA-256, and a note for anything about it that this user could overwrite.

On every route it writes **both** `PLAYWRIGHT_CHROMIUM_EXECUTABLE=<canonical path>` and
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256=<digest>` to `$GITHUB_ENV` when that variable is set, which is how
one CI step resolves the browser and every later step launches exactly the file that step read. The digest
is the point of the canonicalisation: validating a *path* and then launching it later establishes nothing,
because a path is a mutable pointer — `/usr/bin/google-chrome` is a symlink on most distributions, and a
binary this user can replace can be swapped in between. `playwright.config.ts` recomputes the digest and
refuses a mismatch before the launch, so both ends of that window are tied together.
Both are published in GitHub’s delimited multi-line form with a random delimiter, so a resolved
path can never be read as workflow syntax, and a path carrying a line break is refused rather than
published. The digest is printed whether or not it can be published, so a local run with no
`GITHUB_ENV` can bind its own launch by setting the variable by hand.

Set either variable by hand when you want a specific binary. Both can be set in the usual
three ways:

```
# POSIX shells (bash, zsh)
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/google-chrome
```

```
# PowerShell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

```
REM Windows cmd.exe
set PLAYWRIGHT_CHROMIUM_EXECUTABLE=C:\Program Files\Google\Chrome\Application\chrome.exe
```

The same three forms apply to the optional `CLONE_INDEX` override in the next section. On Windows the
path contains a space, so quote it in PowerShell and leave it unquoted after `set` in `cmd.exe`, where
quotes would become part of the value.

`browsers:require` also reads the resolved build's own `--version`, so the run records *which*
browser it got and not only where it came from. `--min-major <n>` additionally refuses a resolved
build whose major version is below `n`:

```
npm run browsers:require -- --min-major 120
```

**Exit 0** means a usable browser was resolved. **Exit 1** means none was, or an explicitly named one is
unusable, or the resolved build is below the required major version; the message names the routes it
tried, the exact path each was looked for at, and the provisioning commands for the platform it is
running on.

**`browsers:verify` is the narrower reporter over the same provision**, not a weaker version of the gate.
It runs [`scripts/verify-browser.js`](./scripts/verify-browser.js), which checks two filesystem locations
— an explicit `PLAYWRIGHT_CHROMIUM_EXECUTABLE` and, only if that is unset, the cache path
`chromium.executablePath()` reports — and **also exits non-zero when neither is launchable**. It simply
does not search the vendor install locations and publishes nothing, and when a digest *was*
published it confirms the executable against that too, which gives it a second way to fail.
**Both are fail-closed, and neither fetches anything.** Use `browsers:require` to decide
whether a run can proceed; use `browsers:verify` to see what a run *without* an explicit executable would
load. A path that exists but is a directory, or a file that is not executable, fails either one.

Neither script runs `playwright install --dry-run chromium`, which is what this package used under the
`browsers:verify` name before. That command prints the install location it *would* use and exits **0
whether or not anything is there** — measured in a container whose cache held no Chromium, it exited 0
while `fs.existsSync(chromium.executablePath())` was `false`. A check that cannot fail is not a check,
and it is worse than none, because a pipeline that ran it looked green while every test was about to fail
at launch.

If no browser is in place and you skip the gate, every test fails identically at launch with
`browserType.launch: Executable doesn't exist at <path>`, naming the cache directory route 4 expected.

**CI resolves the browser rather than hardcoding it.** The `e2e` job pins no path: it sets only
`E2E_MIN_CHROMIUM_MAJOR: '120'`, runs `browsers:require -- --min-major "$E2E_MIN_CHROMIUM_MAJOR"` so the
resolver searches the four routes in order and refuses an unusably old build, tees that reading to
`reports/browser.txt`, then prints the pinned runner's own version and runs `browsers:verify` against the
executable the gate published. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` as a repository or environment
variable to pin a specific artifact; leave it unset and the resolver finds the runner image's own
`google-chrome-stable` — at route 2 if the image exports `CHROME_BIN`, otherwise at route 3, where
`/usr/bin/google-chrome` heads the Linux candidate list. Either way the resolved path and version are
recorded. No step downloads a browser, so a missing one is a visible environment failure rather than a
silent, unverified fetch.

### Nothing else is required

- **No environment variables.** The suite reads none, apart from the optional overrides in this
  section and the next.
- **No backend.** Nothing starts `uvicorn`, and no spec talks to a real API. Every request the UI makes
  is answered by `page.route` interception in the spec that made it.
- **No real credential is read, and no request leaves the harness origin.** Both are worth stating
  precisely rather than as an absolute, because the precise version is what has actually been tested.
  What is enforced: a Chromium launched with egress disabled at the browser layer, a context-wide
  `page.route` that aborts and ledgers any request to a host other than `127.0.0.1:<port>`, a harness
  server that answers an unintercepted API path `503` instead of proxying it, and a middleware that
  refuses its own dev-server control paths. What is *not* claimed: the harness talks to itself over a
  real loopback socket, so this is a boundary rather than an absence of networking; and the four
  credential-shaped values the configuration spec types are synthetic literals asserted synthetic by a
  gate, not an assurance that no credential-shaped string exists anywhere in the run. The residual and
  the reasoning are in section 4 and in
  [`../docs/testing/SECURITY-GAPS.md`](../docs/testing/SECURITY-GAPS.md).
- **No separate server to start.** `playwright.config.ts` starts the harness through its `webServer`
  block and stops it when the run ends. Section 3 covers running it standalone, which is only for
  manual inspection.

### The origin: host, port, and parallel checkouts

The harness binds `127.0.0.1` — a literal address rather than `localhost`, which resolves to either
`127.0.0.1` or `::1` depending on the host's resolver order.

The "Harness origin" section of [`vite.harness.config.ts`](./vite.harness.config.ts) resolves the port
once and exports it; [`playwright.config.ts`](./playwright.config.ts) imports it from there rather than
resolving one of its own, so the server and the runner can never disagree. Resolution order, first
match wins:

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
pinned runner, and each names a **local** binary rather than going through bare `npx`, which falls
back to the registry when the local executable is missing.

**What "executed as written" covers, and what it does not.** The non-interactive forms have been run
verbatim on this checkout and their outcome is recorded in section 8: `npm test`, `npm run test:list`,
`npm run browsers:require` (including with `--min-major` and against a deliberately bogus executable),
`npm run browsers:verify`, `./node_modules/.bin/playwright --version`, and single-spec and
single-title `playwright test` invocations. The three **interactive** forms — `test:headed`,
`test:debug` and `report` — have not been exercised here and cannot be, since each waits on a human
or serves until interrupted. They are listed because they are the right tool while writing a spec,
not because a run of them is being reported.

### The suite

| Run from | Command | Does |
| --- | --- | --- |
| `e2e` | `npm test` | The whole suite. Starts the harness, runs 31 tests, stops the harness |
| repository root | `npm --prefix e2e test` | The same run, without changing directory |
| `frontend` | `npm run test:e2e` | The same run, chained through `npm --prefix ../e2e run test` |
| `e2e` | `npm run test:headed` | The same run with a visible browser window. Interactive |
| `e2e` | `npm run test:debug` | The same run under the Playwright inspector. Interactive |

**The CI form is the first one**: `.github/workflows/ci.yml` sets `working-directory: e2e` and runs
`npm test`. That resolves `playwright` through `node_modules/.bin`, so the runner is the version this
package pins and no registry lookup is possible. `npx playwright test` inside `e2e/` resolves the same
binary today, but `npx` is online-capable by design, and naming the script instead fails closed —
see `D113` and `D257`.

### Readiness

| Run from | Command | Does |
| --- | --- | --- |
| `e2e` | `npm run test:list` | Lists the 31 tests and exits. Launches no browser |

This is the layer's readiness check, and CI runs it as its own step **before** the browser-provisioning
gate, precisely because it needs no browser: a host with no browser still leaves a retained readiness
result rather than nothing at all. Its output is captured to `reports/list-tests.txt`, which the
dashboard's extractor reads.

The script pins `--reporter=line`, and that matters: a plain `playwright test --list` writes the
configured reporters, so it **overwrites** `reports/e2e-junit.xml` and `playwright-report/` with an
all-skipped stub — `tests="31" skipped="31"` on the current census — that no consumer can distinguish from
a run in which nothing executed. See `D254`.

The `frontend` form takes no extra arguments: `npm run test:e2e -- --list` is rewritten to
`npm --prefix ../e2e run test --list`, npm consumes the flag itself, and the full suite runs instead of
listing. Use one of the `e2e`-local forms when you need to pass anything.

### Targeted runs

| Run from | Command | Does |
| --- | --- | --- |
| `e2e` | `npm run test:list` | Lists the 31 tests and exits. The collection check for this layer; needs no browser. Use it rather than a bare `playwright test --list`, which writes the configured reporters and replaces your last result stream with an all-skipped stub |
| `e2e` | `npm test -- tests/dashboard.spec.ts` | One spec |
| `e2e` | `npm test -- -g "renders an empty tweet-list container"` | One test by title |
| `e2e` | `npm run test:headed -- -g "<title>"` | One test, visible |
| repository root | `npm --prefix e2e test -- -g "<title>"` | The same, without changing directory. The `--` is required: without it npm consumes the flag and the whole suite runs |

Every form goes through a `package.json` script, so the runner is always
`e2e/node_modules/.bin/playwright`; anything after `--` is passed straight to it.

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

`.github/workflows/ci.yml` used to do exactly that, and used to install browsers with
`npx playwright install --with-deps chromium` — both of the forms this section and section 2 rule out.
Neither remains: the workflow now sets `working-directory: e2e`, runs `npm test`, and verifies a
pre-provisioned browser without fetching. `D257` records the change and `H16` in
[`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md) carries its
verification.

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

Three to six tests per route spec, plus fifteen in `isolation.spec.ts` — thirty-one in total, **none of
them a skip**, so a green run reads **31 passed, 0 skipped**. Which test pins which behaviour is
recorded in
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
- **`/analytics`** renders its heading and its `<canvas>` on every response that does not opt in.
  `harness/stubs/analyticsService.ts` rejects by default, which holds the component on its
  caught-failure branch and keeps it from constructing a chart. Three of the four tests in
  `analytics.spec.ts` rely on that: assert the heading and the canvas, never a painted chart.

  The fourth opts in, by fulfilling the trend route with the stub's `x-harness-forward-trend-series`
  header, and asserts the opposite: the component reaches `new Chart(...)`, Chart.js reports a chart
  part no module registered, the error escapes the passive effect uncaught, and the route comes down.
  That is why forwarding is opt-in rather than the default — it is destructive, and only the test that
  asserts the destruction wants it. It is an active test, not a skip: this is the **only** layer where
  the missing-`Chart.register` ceiling can be observed at all, because a real browser hands the
  component a live 2D context, where jsdom fails earlier on the context itself. The jsdom side is
  covered by `frontend/src/components/Analytics.test.tsx`, which substitutes the constructor instead.

### The interception contract

Each spec installs its own `page.route` handlers **before** navigating, and **every pattern is anchored
to the harness origin**. Import `HARNESS_ORIGIN` from [`tests/harness-fixtures.ts`](./tests/harness-fixtures.ts)
and build each pattern from it:

```
`${HARNESS_ORIGIN}/tweets*`
`${HARNESS_ORIGIN}/undefined/tweets*`
```

**Anchoring is a safety requirement, not a style.** Playwright resolves a `page.route` a spec adds
*before* the context-wide rule the `noEgress` fixture installs, so the spec's pattern wins. A
host-agnostic `'**/tweets*'` matches that path on **any** origin, which means a request the guard exists
to abort — say the same path on `https://example.com` — would instead be *fulfilled* by the spec's own
handler with the spec's own fixture. The test then passes while asserting nothing about where the
request went, and the guard never records it. `tests/isolation.spec.ts` drives exactly this contrast for
all four intercepted request shapes, so the property is asserted rather than assumed.

Tweet fetches need **two** patterns, and registering both is deliberate rather than defensive. The axios
base URL in `frontend/src/services/api.ts` evaluates to the literal string `"undefined"`, so requests go
to `/undefined/tweets?page=undefined&limit=undefined`: `` `${HARNESS_ORIGIN}/tweets*` `` matches a
configured base URL and `` `${HARNESS_ORIGIN}/undefined/tweets*` `` matches the unset one by naming that
segment explicitly. The narrow pattern is what documents the defect at the point of interception — a
spec that registered only the other one would keep passing if the base URL were ever fixed, and would
say nothing about which URL it had asserted. The harness preserves the defect on purpose — see
section 6.

The other two endpoints belong to the harness stubs:

| Request | Pattern | Fulfilled with |
| --- | --- | --- |
| `GET /undefined/tweets` | `` `${HARNESS_ORIGIN}/undefined/tweets*` `` | `[]` for render assertions; `fixtures/tweets.json` for the missing-`TweetCard` ceiling test |
| `GET /api/trends` | `` `${HARNESS_ORIGIN}/api/trends*` `` | [`fixtures/trends.json`](./fixtures/trends.json), or a 500 for the failure path, or that fixture plus `x-harness-forward-trend-series: 1` for the chart-construction test |
| `POST /api/config/twitter` | `` `${HARNESS_ORIGIN}/api/config/twitter` `` | `{}` with 200 or a rejecting status |

The one host-agnostic pattern in this layer is the `context.route('**/*')` inside the `noEgress` fixture
itself, which is the catch-all that aborts foreign origins. That one is meant to match everything; a
pattern in a spec is not.

### The API surface fails closed

A request to a known endpoint that no spec intercepted is **not** forwarded and **not** quietly 404'd.
The harness answers it `503` with a body naming the remedy:

```
{"error":"harness-api-not-intercepted",
 "request":"GET /undefined/tweets?page=1&limit=10",
 "remedy":"page.route(`${HARNESS_ORIGIN}/undefined/tweets*`, route => route.fulfill({ json: [] }))"}
```

The remedy it prints is anchored, for the reason above: a remedy copied out of an error message is the
most likely pattern to end up in a new spec, so `vite.harness.config.ts` spells every one of them with
`${HARNESS_ORIGIN}`.

It also logs the same line to the dev-server output under a `[harness-api-not-intercepted]` prefix. On
top of that, the `noEgress` fixture in [`tests/harness-fixtures.ts`](./tests/harness-fixtures.ts) keeps a
ledger and **fails any spec that forgot an intercept**, so a missing handler is a named failure rather
than an empty render. A forgotten intercept therefore cannot be mistaken for a passing test.

### The browser's own diagnostics are a verdict, not an attachment

The second automatic fixture in `harness-fixtures.ts`, `browserDiagnostics`, records every console
message and every uncaught page error, attaches the whole ledger to the test whatever the outcome, and
**fails the test at teardown for any `console.error` or `pageerror` the test did not declare**.

The declaration is the point. Recording diagnostics and attaching them proves nothing on its own: a
test that asserts a heading passes just as well with a React teardown error and a rejected promise in
the console as without them, so an attachment nobody reads is not an assertion. A test that expects a
failure declares it:

```
browserDiagnostics.allow(/console\.error: Error fetching tweets:/);
```

which is additive, scoped to that test, and makes the *absence* of everything else part of the verdict.
Each entry is also reviewable on its own — a claim about what this route does wrong today, sitting next
to the assertion about what it does right. Console notices below `error` are recorded as evidence and
never fail a test, because the dev server and React both emit them.

Two conveniences keep the declarations honest rather than broad. `resourceFailure(status)` builds the
pattern for Chrome's own network notice about a non-2xx response, keyed to the status the spec chose, so
a response arriving with a different status still fails. And where the same defect surfaces in more than
one wording — React logs `Warning: React.jsx: type is invalid` and throws
`Element type is invalid` — the spec declares each wording separately rather than one loose pattern
covering both.

Egress is denied below the route layer as well. `playwright.config.ts` launches Chromium with
`--host-resolver-rules`, `--proxy-server` and `--proxy-bypass-list` set so that no hostname resolves
except the harness origin and every other request is routed at a closed port, and the same file's
`noEgress` fixture adds a context-wide abort that attributes any refusal to the test that caused it.
Service Workers are blocked, because `page.route` does not see their requests. See `D114` and `D128`.

### Specs are independent

`fullyParallel` is on and no spec depends on another's state: each installs its own routes, navigates
its own page, and asserts only what it rendered. Viewport, timezone (`UTC`) and locale (`en-US`) are
pinned in the config so nothing varies with the host. Run them in any order, or a single one alone.

## 5. Observability of this layer

Rule 2 asks what already existed and was reused, and what was added to fill a gap. Stating that split
for the repository as a whole is
[`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md)'s job; this section
covers only this layer's contribution, and does not restate the dashboard's metric contract.

**Reused.** At repository level, the two Codecov upload steps that already existed in
`.github/workflows/ci.yml` — the same step, the same action, and the same `backend` and `frontend` flag
names. Their `file:` paths were repointed at the manifests the suites actually write; the flags were
not touched. This layer adds no coverage series of its own and touches neither step.

**Added by this layer**, none of which had any equivalent before:

| Artifact | Path | Written |
| --- | --- | --- |
| HTML report | `e2e/playwright-report/index.html` | Every run. Opened with `npm run report` |
| JUnit XML result stream | `e2e/reports/e2e-junit.xml` | Every run. Each `<testcase>` carries its spec file and test title |
| Traces, screenshots, video | `e2e/test-results/` | On failure only — `trace: { mode: 'retain-on-failure', sources: false }`, `only-on-failure`, `retain-on-failure` |
| Harness dev-server log | the run's own output | `webServer` pipes stdout and stderr, which is what surfaces the `[harness-api-not-intercepted]` lines |

All three paths are matched by the repository [`.gitignore`](../.gitignore), so no run dirties the tree.
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

Create `tests/<name>.spec.ts`. Import `test`, `expect` and `HARNESS_ORIGIN` from
[`./harness-fixtures`](./tests/harness-fixtures.ts) — **not** from `@playwright/test` and not from
`../playwright.config`, neither of which declares a fixture. That one module is what installs the egress
guard, the un-intercepted-request ledger and the browser-diagnostics verdict:

```
import { expect, HARNESS_ORIGIN, test } from './harness-fixtures';
```

Then install every `page.route` handler **before** `page.goto`, anchor each pattern to
`${HARNESS_ORIGIN}` (section 4 explains why that is load-bearing), and reuse a payload from
[`fixtures/`](./fixtures/) rather than inlining one.

### A fixture

Add JSON to [`fixtures/`](./fixtures/). A tweet payload here is the **ten-key wire shape** — what an API
would put on the network — and carries every one of the ten keys both `frontend/src/schema/tweetSchema.ts`
and `backend/app/schema/tweet.py` name: `tweet_id`, `content`, `user_id`, `timestamp`, `likes_count`,
`retweets_count`, `doubt_rating`, `ai_tools`, `media_urls`, `quoted_tweet_id`. A fixture that drifts from
those key names weakens every assertion that reads it.

Two differences from the schemas are deliberate, and a fixture author needs both:

- **`timestamp` is an ISO 8601 string, which the frontend schema rejects.**
  `frontend/src/schema/tweetSchema.ts` types it `z.date()`, and no JSON value can satisfy that — so this
  payload is valid over the wire and invalid under `tweetSchema.parse`. That is the production defect, not
  a fixture error; `frontend/src/schema/tweetSchema.test.ts` asserts the rejection. The backend's pydantic
  model does accept the string, because it coerces.
- **`quoted_tweet_id` must be present, with `null` for absent.** The frontend field is nullable but not
  optional, so omitting the key fails `parse` while `null` passes. The backend model allows the key to be
  omitted entirely. Include it and set it to `null`.

Neither difference is normalised away anywhere: the wire shape is what the components actually receive,
and the in-memory shape a Redux test uses is built separately by
`frontend/src/test-utils/factories.ts`.

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
browser needs network access and system packages. Executing the suite in a real browser, **and confirming
that a failure leaves usable evidence behind**, were therefore recorded as one implementation-time
acceptance step in [`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md)
section 7. That step has two halves and both have now been performed. They are reported separately below,
because a green run says nothing about whether a red one is diagnosable.

**Half one — the suite, green, in a real browser.**

| | |
| --- | --- |
| Result | **31 passed, 0 skipped, 0 failed, 0 flaky** — exit 0, 17.4 s wall (`time="17.405289"` in the JUnit record) |
| Per spec | `analytics` 4 tests / 0 skipped · `configuration` 6 / 0 · `dashboard` 3 / 0 · `isolation` 15 / 0 · `tweets` 3 / 0 |
| Runner | `@playwright/test` 1.44.1, one `chromium` project, 1 worker |
| Browser | **Google Chrome 151.0.7922.76**, provisioned out of band and named with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`; the Playwright cache held no Chromium |
| Runtime | Node v22.23.1 / npm 10.9.8; harness `VITE v4.5.14` on `127.0.0.1:4197` (`CLONE_INDEX=024`) |
| Artifacts | `reports/e2e-junit.xml` (`tests="31" failures="0" skipped="0" errors="0"`), `playwright-report/index.html` (465,930 bytes), `test-results/.last-run.json` = `{"status":"passed","failedTests":[]}` |
**That step has since been performed, and this is its outcome.** The full suite ran in a real browser.
Everything needed to re-derive the figures is in the table, because a result nobody can reproduce is an
assertion rather than evidence:

| | |
| --- | --- |
| Command | `npm test`, run from `e2e/` with `CI=true`, which selects `workers: 1` and `retries: 2` — the same configuration the workflow runs under |
| Result | **31 passed, 0 skipped, 0 failed, 0 flaky** — exit 0 |
| Per spec | `analytics` 4 tests / 0 skipped · `configuration` 6 / 0 · `dashboard` 3 / 0 · `isolation` 15 / 0 · `tweets` 3 / 0. Thirty-one in total and **nothing skipped** |
| Runner | `@playwright/test` **1.44.1**, one `chromium` project, 1 worker. Confirmed by `./node_modules/.bin/playwright --version` reporting `Version 1.44.1` |
| Browser | **Google Chrome 151.0.7922.76**, provisioned out of band, with `PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256` bound to it, resolved by `browsers:require` and recorded as `Browser resolved from PLAYWRIGHT_CHROMIUM_EXECUTABLE: C:\Program Files\Google\Chrome\Application\chrome.exe`. Nothing in the run downloaded anything; the Playwright cache held no Chromium |
| Runtime | Node v22.23.1 / npm 10.9.8, Windows; harness `VITE v4.5.14` on `127.0.0.1:<4173 + CLONE_INDEX>` |
| Commit | Recorded by the tooling rather than written here — `python ../docs/testing/dashboard-extract.py` prints the branch and commit of the tree it read in its §1.0 block, so re-run it beside the suite and quote that |
| Artifacts | `reports/e2e-junit.xml` (root `tests="31" failures="0" skipped="0" errors="0"`), `playwright-report/index.html` (about 456 KB, its exact size moving with the run), `test-results/.last-run.json` = `{"status":"passed","failedTests":[]}`, `reports/list-tests.txt` reporting `Total: 31 tests in 5 files`, and `reports/browser.txt` carrying the resolved executable, its version and the runner version |
| Retention | All of them are uploaded by the `e2e` job — as `e2e-test-evidence` at 30 days and `playwright-report` at **7**, both `if-no-files-found: error`. A **local** run leaves them in the working tree only, where `.gitignore` keeps them out of version control, so they are not in this repository |

**Where the failure evidence comes from.** `trace`, `screenshot` and `video` are all configured
on-failure only, so a green run retains none of them and `e2e/test-results/` is legitimately empty. They
have been observed twice: once incidentally, in a run where one test timed out under host contention, and
once deliberately — see "What a green run leaves out" below, which is also where the retention consequences
are set out. CI uploads that directory as `e2e-failure-artifacts` with `if-no-files-found: warn` for
exactly this reason — `error` would fail a passing run.

**One reproducibility note.** `npm test` without `CI=true` lets Playwright derive the worker count from
the host. On a heavily contended machine that is enough to push a test past its 30-second budget: on
this host, sharing it with nineteen sibling checkouts, `configuration.spec.ts › posts the four typed
credentials …` timed out once that way and passed on every serial run. If you see a timeout rather than
an assertion failure, re-run with `CI=true` or `--workers=1` before treating it as a defect.

**What a green run leaves out, and how that gap was closed.** A passing run triggers none of the
failure-conditional settings, so `test-results/` holds only `.last-run.json` and the paragraph above is the
only reason to believe a trace would be there. That was closed deliberately rather than argued: a throwaway
spec was made to fail on purpose, Playwright wrote `trace.zip`, `test-failed-1.png` and `video.webm` beside
it, and the zip was opened and its entries listed. The same exercise established the effect of
`sources: false` two ways — with sources enabled the archive carries an extra `src@<sha>.txt` entry holding
the whole spec file, and with it disabled that entry is absent. The probe spec was then deleted.

That matters beyond diagnosis. A trace, a filmstrip, a screenshot and a video all record whatever the
browser showed, `components/Configuration` renders two of its four credential fields as `type="text"`, and
Playwright 1.44 offers no masking for automatic failure evidence — so those values are retained verbatim
whenever that spec fails, and no configuration removes them. What is done instead: every attachment is
redacted to key names, value presence, length and a digest; the trace no longer embeds this suite's source;
CI keeps the two evidence artifacts for 7 days rather than 30; and the first test in
`tests/configuration.spec.ts` fails if any literal it types stops being recognisably synthetic, which is the
only point at which a real credential could enter that evidence.

Every test executes; nothing in this layer is skipped. The chart-construction ceiling used to be the one
exception, on the grounds that the harness stub rejected on every path — it now has an opt-in forwarding
header (section 4), so that test drives the component into `new Chart(...)` and asserts the unregistered
chart part, the uncaught escape and the unmount that follows.

**Both the diagnostics verdict and the chart ceiling were negatively validated.** Each of these was
perturbed one at a time, the suite re-run in the same browser, and the file restored byte-for-byte:

| Perturbation | Expected | Observed |
| --- | --- | --- |
| A `console.error` injected into `harness/main.tsx` | a spec that declared nothing fails | failed, naming the injected text |
| An uncaught error thrown from a timer in `harness/main.tsx` | same, recorded as `pageerror:` | failed, naming it |
| The forwarding header removed from the chart test | the ceiling is no longer reached | that test failed |
| The header sent with the wrong value | the stub refuses to forward | that test failed |
| That same unrelated uncaught error, against the two specs that expect one of their own | the declared patterns key on message text, not on kind, so it is still undeclared | both failed, naming the injected error rather than absorbing it |
| A declared `allow(...)` removed from a spec that needs it | its expected record becomes a failure | failed, `Declared patterns: (none)` |

The first two of those are the false-pass class this fixture exists to close: before it, a spec attached
its diagnostics and asserted nothing about them, so an injected error changed nothing about the verdict.
Adopting the fixture also surfaced three real undeclared errors that the previous per-spec recorders had
been attaching and ignoring — Chrome's non-2xx network notice on two routes, and React's duplicate-`key`
warning on the feed, the last of which is now asserted rather than tolerated.

Re-run either half yourself with the commands in section 3; nothing above depends on state this
repository does not carry. Two limits remain, and both are listed in section 9: only `chromium` is
exercised, and the browser is a prerequisite rather than something a script here obtains.

## 9. Suggested next tasks

Everything in this section is **out of scope and deliberately not fixed.** Where a defect is asserted by
a test, repairing it will turn a passing test red on purpose —
[`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md) records which test
pins which defect, so check it before attempting any of these. The security exposures among them — and the ones this layer cannot see, in the application and in the deployment files — are written up individually in [`../docs/testing/SECURITY-GAPS.md`](../docs/testing/SECURITY-GAPS.md), with the clause that put each out of reach and what has to be done.

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
    construction fails in every environment including a real browser, and because `renderCharts` carries
    no `try`/`catch` the failure escapes a passive effect and unmounts the route. One test here asserts
    exactly that, through the stub's opt-in forwarding header, so **repairing this will turn that test
    red on purpose** — it would then need to assert a painted chart instead.
13. The axios base URL evaluates to the literal string `"undefined"`, so every request is issued to
    `undefined/tweets?...` — which is why the interception contract names that segment explicitly in a
    second pattern rather than relying on the broad one alone.

**Would close an accessibility or credential-handling gap this layer characterises**

Each of the four is asserted as current behaviour by `tests/analytics.spec.ts` or
`tests/configuration.spec.ts` and by the matching Jest suite, so closing one turns a passing test red on
purpose — check `../docs/testing/TRACEABILITY-MATRIX.md` §G rows G9-G12 first. All four need an edit to a
`frontend/src` module, which is why none was attempted here.

14. `Analytics` renders a bare `<canvas id="trendChart">` with no `role`, accessible name, description or
    fallback content, so the whole of the analytics content is absent from the accessibility tree — the
    heading is all a screen reader is offered. Give it a meaningful name and description, or a table or
    textual summary of the series, then query it by role and name.
15. Neither `TweetManagement`'s loading indicator nor `Dashboard`'s 30-second polled feed declares a live
    region, so a fetch starting, a fetch finishing and an update arriving are all silent. Use
    `role="status"` on the indicator and `role="log"` with `aria-live="polite"` on the feed, and assert the
    announcement contract.
16. `Configuration`'s credential save has no pending state: the control is never disabled, never carries
    `aria-busy`, and a second activation mid-flight issues a **second** credential write and a **second**
    dialog. Track submission state, disable the control while the write is open, and cover
    keyboard and double-activation.
17. `Configuration` renders `API Key` and `Access Token` as `type="text"`, so both are on screen in clear
    text while only the `Secret`-suffixed fields are masked, and no field declares an `autocomplete`
    policy. Mask every credential field and state an intentional autofill policy.

**This layer specifically**

18. Only `chromium` is exercised. Add a second and third browser project once the declared Node ceiling
    lifts, since the Playwright releases that broaden browser support require `node>=18`.
19. `e2e/package.json` declares no `engines` field, so nothing mechanically enforces the Node floor the
    pins assume.
20. No lockfile exists for any package, so no install is byte-reproducible. Committing one is unblocked
    and would let CI return to `npm ci`; today the exact pins in each manifest, plus a dependency-closure
    test, stand in for it. What stands in is uneven: this package and `backend/requirements-dev.txt` are
    exact throughout, but `frontend/package.json` is exact for only the 11 devDependencies the test
    programme owns — its other 17 declarations are caret ranges frozen to the pre-existing baseline, so a
    frontend install can still drift within them (`D172`).
21. **Closed.** The `e2e` job in `.github/workflows/ci.yml` no longer installs a browser, no longer
    invokes the runner from the repository root, and **no longer hardcodes a browser path**: it runs
    `npm install`, then `npm run browsers:require -- --min-major "$E2E_MIN_CHROMIUM_MAJOR"`, then
    `browsers:verify`, then `npm test`, all under `working-directory: e2e`. The resolver searches the four
    routes in order and publishes what it found through `$GITHUB_ENV` — the canonical path together with
    `PLAYWRIGHT_CHROMIUM_EXECUTABLE_SHA256`, which the launch re-checks — so the path launched is the path
    logged, and a build below the version floor fails the job with its version in the message. What
    remains open is narrower: **that job has never run on a hosted runner**, so its reliance on the runner
    image carrying a Chrome at one of the vendor paths is reasoned rather than observed, and the rest is
    upstream: `@playwright/test` >= 1.55.1 carries the fix for CVE-2025-59288 and requires `node>=18`, so
    the downloader stops being a hazard only once the declared Node ceiling lifts. See `D212`, `D267`, and
    `D264` as superseded by `D300`, `D301` and `D319`.
22. `.github/workflows/cd.yml` contains a post-deployment health-check step whose body is entirely
    comments, so it passes vacuously and gates nothing, and `docker-compose.yml` health-checks a
    `/health` route the application never declares.

**Repository-wide, and independent of testing**

23. The `flake8`, `mypy` and `npm run lint` steps in `ci.yml` are broken independently of this work — no
    linter or type checker is declared anywhere in the repository.
24. The application has no metrics endpoint, no tracing, no correlation identifier on any production
    path, and no structured logging: two modules report failures with `print`, and nothing under
    `backend/app/` imports `logging` at all.
25. `README.md` describes an unrelated static-analysis product, and `frontend/package.json` is named
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
| `D93`, `D159`, `D275` | Why no lockfile is committed, why `npm install` rather than `npm ci`, and why the install is no longer suppressed at source |
| `D111`, `D129`, `D236` | Why no script downloads a browser, and why `browsers:verify` fails rather than reporting and always passing |
| `D319` | Why the validated browser is bound to the launched one by digest, and why route 3 cannot be |
| `D321` | Why every same-origin request the harness serves is recorded as a census |
| `D237` | Why CI runs the suite from `e2e/` through `npm test` instead of from the repository root |
| `D112` | Why `reuseExistingServer` is `false` unconditionally |
| `D114`, `D128` | Why egress is denied at two layers, and why only one origin is bypassed |
| `D123` | Why the harness is started through the pinned local binary with an explicit port |
| `D130`, `D276` | Why the host and port are resolved in exactly one module, and why that module is now the harness config |
| `D264`, superseded by `D300`, `D301` and `D319` | Why `browsers:require` is the gate and `browsers:verify` the narrower reporter that also fails closed, why the cache route asks Playwright for its own executable path rather than scanning, why `CHROME_BIN` is honoured, and why CI sets a version floor instead of a hardcoded path |
| `D308`, whose census figure is re-measured by `D353` | Why the Chart.js registration failure is asserted in this layer rather than recorded as an unverified ceiling, and why the spec census carries no skip at all |
| `D277`, `D286` | Why the extended `test`/`expect` a spec imports live in one fixture module rather than in the runner config |
| `D278` | Why the CI job resolves a preinstalled browser instead of installing one |

Which spec covers which construct, in both directions, is in
[`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md). The coverage and
test-health metric contract is
[`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md)'s.
