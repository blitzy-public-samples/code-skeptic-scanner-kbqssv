# Frontend test suite

Everything you need to run, read and extend the Jest suite in this folder. The bar this document is
held to is that you can go from a clean machine to a green suite — and then to a suite with your own
test in it — without asking anyone a question.

Read this once before you write your first test here. The suite is deliberately unusual in four
places, and each of them will look like a bug until you know why it is there:

1. Four of the component modules are **files with no extension**, so there are two Jest transformers
   (§[3](#3-the-dual-transformer-arrangement)).
2. Twelve `moduleNameMapper` entries stand in for imports that do not resolve, and their **order is
   load-bearing** (§[4](#4-module-resolution-every-modulenamemapper-entry)).
3. HTTP is intercepted with origin-confined msw handlers that **ledger** anything they do not cover,
   rather than letting it reach a socket (§[5](#5-the-http-interception-contract-msw)).
4. The render helper builds **its own** Redux store and never imports `src/store/index.ts`
   (§[6](#6-the-test-store-why-renderwithproviders-builds-its-own)).

Above all: **these tests assert what the code does today, defects included.** Several assertions look
wrong on first reading and are not. §[2](#2-what-is-under-test-and-the-one-principle-that-explains-the-assertions)
lists the ones most likely to trip you.

## Where things live

This document covers the `frontend/` folder only. It does not repeat what the documents below already
say, so follow the link rather than assuming the answer is here.

| For | Go to |
| --- | --- |
| The cross-cutting view: all three install legs, the top-level commands, the whole artifact inventory | [`../README.md`](../README.md) → *Testing* |
| The backend pytest suite — fixtures, import root, credential and socket guards | [`../backend/tests/README.md`](../backend/tests/README.md) |
| The Playwright suite, the Vite harness it serves, and the browser prerequisite | [`../e2e/README.md`](../e2e/README.md) |
| **Why** any choice below was made — alternatives weighed, risks accepted | [`../docs/testing/DECISION-LOG.md`](../docs/testing/DECISION-LOG.md) |
| Which test covers which construct, in both directions | [`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md) |
| The coverage and test-health dashboard | [`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md) |

Rationale is not duplicated here by design. This document tells you **what** the setup is and **how**
to work inside it; the decision log is the single place that answers **why this and not that**. Its
rows carry stable `D…` handles that never get reused or renumbered, so where a question is likely to
come up, the relevant handle is cited inline — for example `D30`. Look it up there.

## 1. Setup: clean machine to green suite

### Runtime

[`../.github/workflows/ci.yml`](../.github/workflows/ci.yml) declares `node-version: [16.x]`. That is
the repository's only authoritative statement about Node, so it is the version the test
devDependencies were selected against: `msw@1.3.5` because the 2.x line requires `node>=18`
(`D180`), `jest-junit@16.0.0` because 17.0.0 requires `node>=20` (`D182`), and `ts-jest@29.4.12`,
`jest@29.7.0` and `jest-environment-jsdom@29.5.0` as the 29.x ceilings.

Every one of those pins declares an **open-ended minimum**, so the suite is not confined to Node 16.
It was last verified green on **Node v22.23.1 with npm 10.9.8**, which is what the container this was
written in runs. Both statements matter: 16.x is what CI documents, and a newer Node works.

What is *not* supported is changing one side without the other. Dropping below any pin's declared
minimum, or raising Node on the assumption that the pins will follow, is a change to the toolchain and
needs the pins revisited.

### Install

```bash
cd frontend
npm install
```

**`npm ci` will not work here, and that is deliberate.** No `package-lock.json` is committed, and
[`.npmrc`](./.npmrc) in this folder carries `package-lock=false` so one is never even generated —
suppressed at the source rather than hidden behind an ignore rule (`D93`, `D159`). Confirm it with
`npm config get package-lock`, which answers `false`. `npm ci` refuses to run without a lockfile, so
the CI workflow uses `npm install` too. The reproducibility cost of this is real and is the first
entry in §[10](#10-suggested-next-tasks).

Install the `frontend` tree **before** the `e2e` tree: the harness aliases React out of
`frontend/node_modules` so exactly one copy exists (`D48`). See [`../e2e/README.md`](../e2e/README.md).

### Install noise you should expect

- **`npm warn deprecated …`** for a handful of transitive packages (`inflight`, `glob@7`, `abab`,
  `domexception`, `uuid@8` and similar). All arrive underneath Jest and jsdom. Harmless.
- **`npm audit` findings.** The seventeen dependency declarations outside this work's authorized
  surface are pinned at the repository's frozen baseline ranges rather than at exact versions, so a
  caret range can admit a release with an advisory against it. This is a known, escalated residual,
  not something to fix on your own initiative — `D171` records it and `D172` records the gate that
  keeps it from widening quietly.
- **`EBADENGINE` for `postcss-load-config@6.0.1` — on Node 16 only.** That package declares
  `engines.node: ">= 18"` and arrives transitively through the floating `tailwindcss ^3.3.2`. It is
  pre-existing, has nothing to do with the test stack, and is deliberately not fixed. On Node ≥18 it
  does not appear at all, which is why the Node v22.23.1 verification named above saw no `EBADENGINE`
  line.

An `EBADENGINE` warning naming a **test** package is a different matter: it means a pin has drifted
and the toolchain no longer matches the runtime. Investigate that one.

### The five commands

All five are declared in [`package.json`](./package.json) and all are run from `frontend/`.

| Command | Runs | Use it for |
| --- | --- | --- |
| `npm test` | `jest` | The everyday run. No coverage, so it is the fastest full pass. |
| `npm run test:watch` | `jest --watch` | Iterating on one suite. Needs a git checkout to diff against. |
| `npm run test:coverage` | `jest --coverage` | A local coverage report plus the `coverageThreshold` gate. |
| `npm run test:ci` | `jest --ci --coverage --watchAll=false` | **What CI runs.** Coverage, the gate, and every artifact in §[7](#7-coverage-gates-and-artifacts). |
| `npm run test:e2e` | `npm --prefix ../e2e run test` | Hands off to the Playwright suite. Every e2e command goes through the `e2e` package, never `npx` from the repository root (`D49`). |

### Targeted runs

```bash
npx jest src/store/tweetSlice.test.ts          # one file
npx jest -t "does not refetch at 29999 ms"     # one test, by name
npx jest --listTests                           # every file Jest can collect, and nothing else
```

The `-t` pattern matches the full test name — every enclosing `describe` title and the leaf title,
joined by single spaces. That is exactly the string the JUnit report puts in `<testcase name>`
(§[7](#7-coverage-gates-and-artifacts)), so you can copy a name out of a failing report and pass it
straight to `-t`.

### Snapshots

There are none, anywhere, and none should be added. Nothing is ever written back to the tree
implicitly, which is what makes `--ci` safe to use as the default rather than a special mode.

## 2. What is under test, and the one principle that explains the assertions

### The shape of it

Twenty production modules live under `src/`, across `schema/`, `store/`, `services/`, `utils/`,
`components/` and `pages/`, plus the two entry modules `app.tsx` and `index.tsx`. Nineteen of them are
in the coverage denominator; `src/app.tsx` is excluded because it cannot be mounted at all
(§[7](#ceilings-not-gaps)). Before this suite existed, **none** of them was executed by a test.

Every suite is colocated beside its subject as `<Name>.test.ts` or `<Name>.test.tsx`. There are 23 of
them, in seven families:

| Family | Files | Subjects |
| --- | --- | --- |
| Schema | 2 | `src/schema/*.ts` — zod contracts |
| Store | 3 | `src/store/*.ts` — slices and the store module |
| Services | 3 | `src/services/*.ts` — the HTTP layer |
| Utils | 2 | `src/utils/*.ts` — formatting and dates |
| Components | 4 | `src/components/*` — the four extension-less modules |
| Pages | 4 | `src/pages/*.tsx` |
| Test infrastructure | 5 | `src/test-utils/*.test.ts` — contract suites over the harness itself |

The last family is worth knowing about before you change anything under `src/test-utils/`. Those five
suites hold the harness to its own contract: `handlers.test.ts` and `junit-correlation.test.ts`
(`D174`, `D158`), `jest-transform-extensionless.test.ts` (`D140`), `setup-jest.test.ts`, and
`dependency-closure.test.ts`, which asserts the manifest against the installed tree (`D172`). If you
edit the transformer, the handlers, the setup file, the reporter options or `package.json`, one of
those five is where you will hear about it.

### Tests assert current behaviour, including defects

This is the governing principle, and it is not negotiable within this suite's scope. Where the
implementation is wrong, the test **pins the wrong behaviour** so that a future fix is a visible,
deliberate change rather than a silent one. The defects are recorded in the decision log's
noted-but-not-fixed register and projected into §[10](#10-suggested-next-tasks).

Do not "fix" any of these tests. Each one is encoding a bug on purpose:

| Assertion that looks wrong | Why it is correct today |
| --- | --- |
| `formatNumber(1234.5678)` is `'1,234.5,678'` | The grouping regular expression in `src/utils/formatUtils.ts` groups the fractional digits too. |
| `getLatestTweets(5)` requests `undefined/tweets?page=5&limit=undefined` | `src/services/twitterService.ts` calls the two-parameter `fetchTweets` with one argument, and the base URL is the literal string `undefined` (§[5](#why-the-base-url-is-the-string-undefined)). |
| `tweetSlice.updateTweet` overwrites index 0 | It compares `tweet.id === action.payload.id` on a shape that has no `id`, so `undefined === undefined` matches the first element every time. |
| `tweetSchema` rejects a string `timestamp` | The field is `z.date()`, so no raw JSON payload can ever satisfy the schema. |
| `src/store/index.ts` does not throw despite having no valid reducer | Redux logs and carries on (§[6](#6-the-test-store-why-renderwithproviders-builds-its-own)). |
| Rendering either list component with a non-empty list logs React's "Element type is invalid" | `TweetCard` is imported by two components and defined nowhere (§[7](#ceilings-not-gaps)). |

### The pages are orphaned

`src/app.tsx` routes only to `@/components/*` — it never references `@/pages/*`. All four page
modules are therefore unreachable in the running application. They are tested anyway because they are
in scope, and three of the four cannot mount at all; see §[7](#ceilings-not-gaps).

## 3. The dual-transformer arrangement

### The problem

These four modules contain TSX and have **no file extension**:

```text
src/components/Dashboard
src/components/TweetManagement
src/components/Analytics
src/components/Configuration
```

They are files, not directories. No transformer can infer a JSX loader from a name with no extension,
so a default ts-jest setup either refuses them or hands them to the wrong loader.

### The mechanism

[`jest.config.js`](./jest.config.js) declares **two** `transform` entries, matched in declaration
order, with the extension-less key first:

```js
transform: {
  'src[\\\\/]components[\\\\/](Dashboard|TweetManagement|Analytics|Configuration)$':
    '<rootDir>/jest.transform.extensionless.js',
  '^.+\\.[jt]sx?$': ['ts-jest', { tsconfig: TSCONFIG, diagnostics: false }],
},
```

[`jest.transform.extensionless.js`](./jest.transform.extensionless.js) constructs ts-jest's
`TsJestTransformer` directly — `require('ts-jest').createTransformer` is not a function in the pinned
29.4.12 (`D31`) — and re-invokes it under a **synthetic** filename, `sourcePath + '.tsx'`, from which
ts-jest infers the loader. One inner transformer is shared per worker. **The real files are never
renamed, and the synthetic name never leaves the transformer** (`D30`).

Two further properties are worth knowing because they are easy to break:

- **The emitted source map names the real file.** After compiling, the wrapper rewrites `file` and
  every `sources` entry that names the synthetic path back to the real extension-less path — in an
  inline data-URL payload, base64 or percent-encoded, and in a separate `map` field alike.
  `mappings`, `names` and `sourcesContent` are passed through untouched, so every coverage count
  derived from the map is unchanged (`D138`). This is why those four files report real coverage
  instead of vanishing from the report.
- **The cache key carries its own namespace,** `:extensionless:real-source-identity`, appended to the
  inner key so cached artifacts can never collide with the primary transformer's (`D139`). If you
  change what `process` returns, bump that suffix or a stale entry will be reused.

The wrapper also fails loudly rather than silently degrading: if the installed ts-jest does not expose
`process` and `getCacheKey`, it throws a `TypeError` naming the pin to restore.

### Constraints you must respect

- **Do not rename these files, give them extensions, or turn them into directories.** Reconciling
  them is a production change and is out of this suite's scope; it is listed in
  §[10](#10-suggested-next-tasks).
- **Adding a fifth extension-less component means three edits, not one:** the `transform` key, the
  matching `moduleNameMapper` group (§[4](#4-module-resolution-every-modulenamemapper-entry)), and
  `collectCoverageFrom`, where the four paths are listed explicitly because no `*.{ts,tsx}` glob can
  match them (`D71`).

### Why both transforms carry an inline `tsconfig`

Neither transformer reads a tsconfig file. Both pass compiler options inline —
`jsx: 'react-jsx'`, `module: 'commonjs'`, `esModuleInterop: true`, `allowJs: true`,
`target: 'ES2020'`, and additionally `isolatedModules: true` in the wrapper.

The reason is that [`tsconfig.json`](./tsconfig.json) ends with a project reference to
`./tsconfig.node.json`, **which does not exist**. Any tool that resolves the real tsconfig fails with
an `ENOENT` out of esbuild's tsconfig loader. That single dangling reference is why Vite cannot
transform even one `.tsx` file in this project while Jest transforms all of them: Jest never reads the
file (`D32`).

Do not edit `tsconfig.json`, and do not create `tsconfig.node.json` to "tidy this up". Both are
outside this work's authorized surface, and the second is in
§[10](#10-suggested-next-tasks) as a follow-up.

### Why diagnostics are off

`diagnostics: false` is not laziness. The sources do not typecheck: `strict: true` is on, and several
modules import symbols that are never exported anywhere. With diagnostics on, essentially every suite
fails to compile and you learn nothing about behaviour.

Turning diagnostics on to "improve rigour" will break the suite. If you want type checking, the
follow-up in §[10](#10-suggested-next-tasks) that repairs the tsconfig and the missing exports is the
change that makes it possible.

## 4. Module resolution: every `moduleNameMapper` entry

Twelve entries, in the order they appear in [`jest.config.js`](./jest.config.js). The order is part of
the configuration, not an accident — see the warning after the table.

| # | Pattern | Maps to | Serves |
| --- | --- | --- | --- |
| 1 | `^@/components/Dashboard$` | `<rootDir>/src/components/Dashboard` | `src/pages/Dashboard.tsx` importing `RealTimeFeed` |
| 2 | `^@/components/TweetManagement$` | `<rootDir>/src/components/TweetManagement` | `src/pages/TweetManagement.tsx`, plus `src/components/Dashboard` and `src/components/TweetManagement` both importing `TweetCard` |
| 3 | `^@/components/Analytics$` | `<rootDir>/src/components/Analytics` | `src/pages/Analytics.tsx` importing `TrendCharts` |
| 4 | `^@/components/Configuration$` | `<rootDir>/src/components/Configuration` | `src/pages/Configuration.tsx` importing `TwitterAPISettings` |
| 5 | `^@/services/analyticsService$` | `<rootDir>/src/test-utils/stubs/analyticsService.ts` | `src/components/Analytics` importing `getTrendData`; `src/pages/Analytics.tsx` importing `getAnalyticsData` |
| 6 | `^@/services/configService$` | `<rootDir>/src/test-utils/stubs/configService.ts` | `src/components/Configuration` importing `updateTwitterAPIConfig`; `src/pages/Configuration.tsx` importing `getConfig` and `updateConfig` |
| 7 | `^\.\./schema/configSchema$` | `<rootDir>/src/test-utils/stubs/configSchema.ts` | `src/store/configSlice.ts` importing the `Config` type — a **relative** specifier, which is the form the real importer uses |
| 8 | `^@/schema/configSchema$` | `<rootDir>/src/test-utils/stubs/configSchema.ts` | The same stub reached through the alias, so a new importer using `@/` resolves too |
| 9 | `^app/schema/tweet$` | `<rootDir>/src/schema/tweetSchema.ts` | `src/services/api.ts` importing `Tweet` |
| 10 | `^app/schema/user$` | `<rootDir>/src/schema/userSchema.ts` | `src/services/api.ts` importing `User` |
| 11 | `^app/services/api$` | `<rootDir>/src/services/api.ts` | `src/services/twitterService.ts` importing `fetchTweets` and `fetchTweetById` |
| 12 | `^@/(.*)$` | `<rootDir>/src/$1` | Everything else, mirroring `tsconfig.json`'s `paths` entry |

Three things to take from that table:

- **Rows 5 to 8 point at modules that do not exist** — three specifiers across four rows, because
  `configSchema` is matched in both forms. `@/services/analyticsService`, `@/services/configService`
  and `../schema/configSchema` are imported by production source and are not in the repository. They
  are stubbed under `src/test-utils/stubs/` and **must not be created under `src/`** — writing them
  would be implementing a missing feature, which is out of scope (`D33`).
- **Rows 9 to 11 are bare specifiers that TypeScript's `paths` does not cover.** They are handled by
  configuration precisely so that no production import statement has to be edited.
- **Rows 1 to 4 exist because the `@/` alias alone cannot reach an extension-less file.** They work
  together with `moduleFileExtensions`, below.

### Ordering: first match wins

`moduleNameMapper` is evaluated in **declaration order, and the first matching pattern wins.**

Rows 5, 6 and 8 all begin with `@/`, so the generic `^@/(.*)$` in row 12 **must stay last.** Move it
up and it will swallow those specifiers, mapping `@/services/analyticsService` to
`src/services/analyticsService` — a path that does not exist — and the Analytics and Configuration
suites will fail with "Cannot find module". The same applies to rows 1 to 4.

If you add an entry, add it **above** row 12 unless you genuinely want the alias to handle it.

### `moduleFileExtensions` and the empty string

```js
moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node', '']
```

The trailing empty string is what lets Jest resolve a module whose filename has no extension at all.
It is **last** on purpose: Jest tries the extensions in order, so a bare path can never shadow a real
`.ts` or `.tsx` file that sits next to it. Keep it in that position.

## 5. The HTTP interception contract (msw)

No suite in this folder is allowed to open a socket. Interception is structural, not a convention you
have to remember.

### Layout

| File | Responsibility |
| --- | --- |
| [`src/test-utils/handlers.ts`](./src/test-utils/handlers.ts) | Every request handler, the request log, and the isolation ledger. Registers handlers only — it constructs no server and installs no hook. |
| [`src/test-utils/msw-server.ts`](./src/test-utils/msw-server.ts) | One `setupServer(...handlers)` instance. Importing it has **no side effect**. |
| [`src/test-utils/setup-jest.ts`](./src/test-utils/setup-jest.ts) | The single `setupFilesAfterEnv` entry. Owns the whole lifecycle. |
| [`src/test-utils/configured-base.ts`](./src/test-utils/configured-base.ts) | Loads a subject with the API base URL configured (§[below](#driving-a-configured-base-url)). |

`setup-jest.ts` registers exactly four things and nothing else:

1. `delete process.env.REACT_APP_API_BASE_URL`, emitted **ahead of its own imports** so nothing
   reachable from the file can read the variable first.
2. The `@testing-library/jest-dom` matchers.
3. `server.listen(...)`, called **synchronously while the module is evaluating** — not from
   `beforeAll`. Jest evaluates a test module and every import-time side effect in its graph before it
   runs `beforeAll`, and `services/api.ts` runs code at module scope while both list components fetch
   on mount, so anything deferred to `beforeAll` would already have reached a socket (`D108`).
4. A global `afterEach` that asserts no isolation breach was recorded, then — in a `finally`, so a
   failing test still hands the next one clean state — calls `server.resetHandlers()`,
   `resetHandlerState()` and deletes the base-URL variable again. `afterAll` closes the server.

Deliberately **not** registered there: Chart.js canvas or `ResizeObserver` shims, any global
replacement of or spy on `console.*`, global fake timers, an `alert` stub, Testing Library global
configuration, and any seeding of environment variables. React and Redux diagnostics are left intact
because several suites assert on them.

### Two layers of handlers

| Export | In the default array? | What it answers |
| --- | --- | --- |
| `frontendIsolationHandlers`, aliased as `handlers` | **Yes** | Nominal-success fixtures, so a component or service suite runs without a socket. |
| `unsetBaseBackendHandlers()` | No | What the assembled FastAPI application returns today with the base URL unset. |
| `configuredBaseBackendHandlers({ dependencyOverridden })` | No | What it returns with the base URL configured, with and without a replaced database dependency. |

The default array is layer 1 only. It is a **test fixture, not a model of the backend**: a suite that
exercises only layer 1 has covered no integration, and every `200` it returns is a fixture rather than
an outcome the backend produces. When you need the real disposition, install the matching layer-2 set
for one test with `server.use(...)`. `handlers.test.ts` is the oracle for what each factory answers
(`D174`), and the per-route caller-to-backend mapping is in
[`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md).

### Origin and path confinement

Every pattern is registered as an **absolute, fully spelled-out URL**: an entry of
`ALLOWED_REQUEST_ORIGINS` — `http://localhost` and `http://127.0.0.1`, the origins jsdom serves the
suite from — then the base path prefix that layer is about, then the route path. **No pattern carries a
leading wildcard segment**, so nothing can absorb the base prefix and no layer can answer a request
whose prefix it does not name. Each layer therefore registers two handlers per route, one per allowed
origin (`D169`).

The allow-list is a frozen constant with no mutator, on purpose: a process-global allow-list that one
test can widen is exactly the order-dependent state this layer exists to eliminate. A suite that
deliberately drives some other origin registers a handler for that exact URL with `server.use(...)`
for the duration of one test.

#### Why the base URL is the string `undefined`

`src/services/api.ts` reads `process.env.REACT_APP_API_BASE_URL` **once, at module scope**, and
interpolates it into a template literal with no fallback. With the variable unset — which
`setup-jest.ts` guarantees — the base is the literal nine-character string `undefined`, so every
request the application emits carries a leading `/undefined` path segment, which jsdom resolves
against the document origin into `http://localhost/undefined/tweets?…`. That is why the patterns spell out
`/undefined` explicitly, and it is why a mis-set base URL is visible instead of silently successful.

### Unhandled requests are ledgered, then refused

`onUnhandledRequest` is a **callback**, not the `'error'` string. It appends the request to an
isolation ledger and *then* calls `print.error()`, which reports it and raises so msw never performs
it.

The ordering is the point. An error raised inside the request lifecycle is lost by every caller in this
codebase: `getLatestTweets` and `generateTweetResponse` log and rethrow a *replacement* error, the
`TweetList` component catches and logs, and `RealTimeFeed` catches nothing at all and leaves an
unhandled rejection. What survives is the ledger entry, and the global `afterEach` throws on it — so
the test that caused the escape is the test that fails (`D136`).

This is required rather than defensive. Before interception was in place, an unmocked axios call opened
a real socket and produced `Error: connect ECONNREFUSED 127.0.0.1:80`, and because the rejection
settled *after* the test that started it, it failed a **later, unrelated test**. That is a
no-real-network violation and a genuine order-dependence bug at the same time.

The same ledger backs request screening: every handler checks the request against its entry in
`ROUTE_CONTRACTS`, and in layer 1 a request that deviates — an unknown or absent query key, a
placeholder path parameter, an unexpected body — is answered with status **599** and a body listing the
violations, never with a success status (`D3`, `D4`).

### The four routes, and who calls them

Exactly four routes are handled and no others — no `/users`, `/analytics`, `/config` or `/health`
(`D11`).

| Route | Called by |
| --- | --- |
| `GET /tweets` | `api.ts` `fetchTweets(page, limit)`; `twitterService.ts` `getLatestTweets(count)`; `components/Dashboard` via `getLatestTweets()` with **no** argument |
| `GET /tweets/:tweetId` | `api.ts` `fetchTweetById(tweetId)`; `twitterService.ts` `getTweetDetails(tweetId)` |
| `POST /generate-response` | `api.ts` `generateResponse(tweetId)` — JSON body `{ "tweetId": … }`, resolves `data.generatedResponse`; `llmService.ts` `generateTweetResponse(tweetId)` |
| `POST /tweets/:tweetId/responses` | **Nothing under `src/`.** It is registered because the backend implements it; for a frontend suite it is a convenience, not a requirement. |

Note the asymmetry in the last two rows: `POST /generate-response` is what the frontend calls and the
backend declares **nowhere**, while `POST /tweets/:tweetId/responses` is what the backend implements
and no frontend module calls. Both are pinned as they are; neither is reconciled here (`D15`).

### The request log

Assert the request you emitted, not just the response you got back. `handlers.ts` records every
intercepted request and exposes `recordedRequests()` and `lastRecordedRequest()`, each entry stamped
with the test that made it — `<test file> > <full test name>`, the same identity the JUnit report
carries (`D83`). Reset is automatic in the global `afterEach`; do not call it yourself.

### Two standing rules

1. **Never mock the component or module under test.** Replace the transport, not the subject. Mocking
   `axios` or `api.ts` deletes the behaviour several oracles exist to assert — the literal `undefined/`
   base URL, the query-string assembly, the response unwrapping (`D152`). The component suites mock the
   *service* modules their subject depends on, never the subject.
2. **Add per-test behaviour with `server.use(...)`, never by editing the shared defaults.** The
   `afterEach` discards it for you. Editing `handlers.ts` changes every suite at once.

### API version

msw is pinned to the **1.x** line, so the API is `rest.get(...)` / `rest.post(...)` with
`(req, res, ctx) => res(ctx.status(…), ctx.json(…))` resolvers, and `setupServer` takes handlers as
individual arguments. It is **not** the 2.x `http.*` API — 2.x requires `node>=18` (`D180`). Copying a
snippet from current msw documentation will not work here.

### How to add a handler

Inside the test that needs it, and always with an absolute URL that names the origin and the
`/undefined` prefix — a relative or wildcard pattern will not match what the application actually
emits:

```ts
import { rest } from 'msw';
import { server } from '../test-utils/msw-server';

it('surfaces a server error', async () => {
  server.use(
    rest.get('http://localhost/undefined/tweets', (req, res, ctx) =>
      res(ctx.status(500), ctx.text('Internal Server Error')),
    ),
  );
  // … drive the subject and assert
});
```

The global `afterEach` removes it again, so nothing leaks into the next test. Reach for
`unsetBaseBackendHandlers()` or `configuredBaseBackendHandlers({ … })` instead when you want the
disposition the real backend produces rather than one you invented.

### Driving a configured base URL

Because `api.ts` reads the variable once at module scope, assigning it inside a test changes nothing
observable. Use the loader, which sets the variable, discards the module registry and *then* imports:

```ts
const api = await importWithConfiguredBase(() => import('./api'));
```

Two consequences to know (`D173`): the returned module — and the `axios` instance inside it — is a
**fresh** one, so a `jest.spyOn(axios, …)` installed on your own import does not affect it; drive those
cases through msw instead. And no cleanup is needed, because the global `afterEach` owns the
variable's lifecycle.

## 6. The test store: why `renderWithProviders` builds its own

### The defect

`src/store/index.ts` imports `{ tweetReducer }` and `{ configReducer }`. Neither
`src/store/tweetSlice.ts` nor `src/store/configSlice.ts` exports those names — both export their
reducer as a **default**. Both imports therefore evaluate to `undefined`.

### The consequence

`configureStore` does **not** throw. Redux logs `"Store does not have a valid reducer..."`,
`getState()` returns `{}`, and the module's runtime exports are exactly `setupStore` and `store`.
`src/store/index.test.ts` asserts precisely that, which is why the module reports full coverage while
being non-functional.

`useAppDispatch` and `useAppSelector` are not exported by the store either, although three page modules
import them — which is why three of the four page suites are skipped
(§[7](#ceilings-not-gaps)).

### The rule that follows

[`src/test-utils/render.tsx`](./src/test-utils/render.tsx) builds its store from the two slices'
**default reducer exports** and **does not import `src/store/index.ts`** (`D34`). Any suite that
rendered through the real store would be asserting against an empty state tree.

So: **never import `src/store/index.ts` from a suite** except in `src/store/index.test.ts`, whose
subject it is.

### `renderWithProviders`

```ts
renderWithProviders(ui, route = '/', options = {})
// options: { preloadedState?, store?, renderOptions? }
// returns: Testing Library's RenderResult & { store }
```

- Wraps `ui` in the Redux `Provider` (outermost) and then a `MemoryRouter` with
  `initialEntries: [route]`, mirroring how `src/app.tsx` nests them. A `MemoryRouter` rather than a
  `BrowserRouter`, so a suite picks its entry route through `route` and `window.history` is never
  touched.
- `preloadedState` is per slice **and partial within each slice**: each partial is merged onto that
  slice's own initial state, so seeding one field never blanks the others. The initial state is
  re-derived on every call, so no object is shared between stores.
- Pass an existing `store` when your suite dispatches before rendering; otherwise a fresh one is built
  per call, and no state crosses between tests.
- Middleware, enhancers and devtools stay at `configureStore`'s defaults, so the serializability check
  is **live**: dispatching a `makeTweet()` fixture, whose `timestamp` is a `Date`, logs Redux Toolkit's
  warning and fails nothing. That warning is expected.

`makeStore(preloadedState?)` is exported separately for suites that need a store without rendering.

Shared setup lives only in `src/test-utils/`. Do not copy any of it into a suite.

## 7. Coverage, gates and artifacts

### The enforced gate

Jest's `coverageThreshold` enforces **≥80% statements, branches, functions and lines** on three
scopes — and the runner fails the build, rather than the number merely being reported to Codecov:

```js
coverageThreshold: {
  './src/store':    { statements: 80, branches: 80, functions: 80, lines: 80 },
  './src/schema':   { statements: 80, branches: 80, functions: 80, lines: 80 },
  './src/services': { statements: 80, branches: 80, functions: 80, lines: 80 },
}
```

There is deliberately **no global threshold group** (`D35`). A global gate would fail on `src/pages`
and on the component ceilings below, none of which a test can close without changing production code.
Coverage is still *measured* for the whole `collectCoverageFrom` set, so a regression outside the three
gated scopes is visible in the report even though it does not fail the run.

### Measured on this run

Figures below are from a single `npm run test:ci` on Node v22.23.1, which exited **0**. Re-measure
before quoting them anywhere — do not carry them forward as if they were permanent. Percentages are
**truncated** to two decimals, which is what Istanbul and Jest's threshold reporting do; rounding them
instead will put you one hundredth away from what the runner prints.

Suites: 3 skipped, 20 passed, 20 of 23 total. Tests: 24 skipped, 307 passed, 331 total. 0 snapshots.

| Scope | Statements | Branches | Functions | Lines |
| --- | --- | --- | --- | --- |
| `src/schema` **(gated)** | 100% (4/4) | 100% (0/0) | 100% (0/0) | 100% (4/4) |
| `src/services` **(gated)** | 100% (38/38) | 100% (0/0) | 100% (6/6) | 100% (34/34) |
| `src/store` **(gated)** | 97.43% (38/39) | 100% (1/1) | 100% (11/11) | 97.29% (36/37) |
| `src/components` | 100% (85/85) | 100% (5/5) | 100% (25/25) | 100% (80/80) |
| `src/utils` | 100% (29/29) | 100% (21/21) | 100% (4/4) | 100% (29/29) |
| `src/pages` | 34.83% (31/89) | 20% (1/5) | 5% (1/20) | 36.04% (31/86) |
| `src/index.tsx` | 0% (0/11) | 100% (0/0) | 0% (0/1) | 0% (0/11) |
| **Whole denominator** | **76.27% (225/295)** | **87.5% (28/32)** | **70.14% (47/67)** | **76.15% (214/281)** |

All three gated scopes clear the threshold with margin. The two figures short of 100% elsewhere that a
test *could* move are `src/store/tweetSlice.ts` at 95.45% statements and `src/pages/TweetManagement.tsx`
at 66.66%; everything else short of 100% is a ceiling, below.

The gate is live — verified by re-running with `./src/pages` thresholded at 80 through a command-line
override, which exits **1** with
`Jest: "./src/pages" coverage threshold for statements (80%) not met: 34.83%`.

### Artifacts

`npm run test:ci` writes all six. Other files depend on these exact paths, so do not relocate them.

| Path | Written by | Consumed by |
| --- | --- | --- |
| `frontend/coverage/coverage-final.json` | the `json` coverage reporter | the `frontend`-flagged Codecov upload step in `ci.yml` |
| `frontend/coverage/lcov.info` and `coverage/lcov-report/` | `lcov` | local HTML browsing, most IDE gutters |
| `frontend/coverage/coverage-summary.json` | `json-summary` | the dashboard in [`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md) |
| `frontend/coverage/cobertura-coverage.xml` | `cobertura` | CI coverage annotators |
| `frontend/reports/jest-junit.xml` | the `jest-junit` reporter | CI test reporting |

`'json'` has to stay in `coverageReporters`: it is the reporter that writes `coverage-final.json`, which
is the file the existing Codecov step already uploads (`D36`).

The JUnit report carries a stable identity for every test, which is what lets a CI result be matched
back to a source location and to the requests that test made:

- `<testsuite name>` and `<testcase classname>` — the `rootDir`-relative test file with forward slashes,
  e.g. `src/store/tweetSlice.test.ts`.
- `<testcase name>` — every enclosing `describe` title plus the leaf title, joined by single spaces.
  Valid as a `jest -t` pattern verbatim.
- `<testcase file>` — the same path in the platform's own separator style, which is what CI annotators
  read.

Those come from **template functions** rather than `'{filepath}'` strings, because a string cannot
normalise a path separator and `{title}` expands to the leaf title alone (`D157`).
`src/test-utils/junit-correlation.test.ts` holds the reporter options and the emitted shape to that
contract (`D158`), so if you change the reporter options, expect that suite to tell you.

Both `frontend/coverage/` and `frontend/reports/` are ignored by the repository-root
[`.gitignore`](../.gitignore), so a test run leaves nothing to commit. Verify with
`git check-ignore -v frontend/coverage/coverage-final.json`.

### Ceilings, not gaps

The following cannot be covered by any test without changing production code, which is out of scope.
They are **asserted as current behaviour** where an assertion is possible, and they are the reason
there is no global coverage threshold. Do not spend time chasing them.

| Ceiling | Why |
| --- | --- |
| `src/app.tsx` — excluded from the denominator, permanently 0% | It imports the invalid store, imports a `setupInterceptors` that is never exported, and default-imports a module that only has a named export. It cannot be mounted (`D71`). |
| `src/index.tsx` — 0% | It calls `renderApp()` at module scope, so importing it would execute a full `ReactDOM.render` against the real store. No test imports it. |
| Three of four page modules cannot mount | `useAppDispatch` / `useAppSelector` are not exported by `src/store/index.ts`. `src/pages/Dashboard.test.tsx` (8 tests), `src/pages/Configuration.test.tsx` (10) and `src/pages/Analytics.test.tsx` (6) are written and skipped with reasons naming the missing export; `src/pages/TweetManagement.test.tsx` runs. |
| The tweet-rendering branch of both list components | `TweetCard` is imported by `src/components/Dashboard` and by `src/components/TweetManagement` — the latter **from itself** — and is defined nowhere. A non-empty list yields React's "Element type is invalid … got: undefined". The suites assert that diagnostic rather than silencing it (`D156`). |
| Chart.js construction in `src/components/Analytics` | It imports the tree-shakeable `{ Chart }` and never calls `Chart.register`, so construction can never succeed — in a real browser either. The suite asserts the caught failure instead. |

### Do not add the Chart.js shims

**Do not install `jest-canvas-mock`, and do not add a `ResizeObserver` stub.** They look like the
obvious fix for the Analytics component and they make the result strictly worse: with the canvas mock
alone Chart.js reaches `ReferenceError: ResizeObserver is not defined`, and with both it reaches
`Error: "linear" is not a registered scale`, which escapes to React and **unmounts** `TrendCharts`,
leaving nothing to assert. Unshimmed, the component stays mounted with its heading and canvas intact —
which is how `src/components/Analytics` measures 100% today. The evidence is in `D92`.

## 8. Adding a suite

### Recipe

1. **Colocate it** beside its subject as `<Subject>.test.ts`, or `.test.tsx` for anything that renders.
2. **Import the subject by its real specifier.** If it does not resolve, check §[4](#4-module-resolution-every-modulenamemapper-entry)
   before touching any source file — configuration is the correct place to fix a resolution problem
   here.
3. **Render through `renderWithProviders`,** not Testing Library's bare `render`, so your subject gets
   the store and router it expects (§[6](#renderwithproviders)).
4. **Mock the services your subject depends on, never the subject.** `jest.mock('@/services/…')` plus
   `jest.mocked(fn)` is the idiom the four component suites use.
5. **Override HTTP with `server.use(...)`** inside the test that needs it. Anything you do not cover
   fails that test by name (§[5](#unhandled-requests-are-ledgered-then-refused)).
6. **Use `jest.useFakeTimers()` with `advanceTimersByTime`** for anything interval-driven. Advance the
   timers and flush pending microtasks as **separate** steps — an interval callback that starts a fetch
   needs both before the DOM settles (`D154`).
7. **Use `findBy…` / `waitFor` for asynchronous DOM.** Never a sleep.
8. **Run it, then run the whole suite.** A test that passes alone and fails in the full run is an
   isolation bug, and it is yours.

### Reliability checklist

Audit your own suite against this before opening it for review:

- [ ] No real network. Nothing reaches a socket, and no unhandled-request ledger entry is produced.
- [ ] No wall-clock dependence. Fake timers or fixed fixture dates, never `Date.now()` drift and never
      a sleep.
- [ ] No order dependence. It passes standalone, in the full run, and with `--runInBand`.
- [ ] No snapshots.
- [ ] Shared setup only in `src/test-utils/`. Nothing copy-pasted between suites.
- [ ] Every assertion has a real oracle. Expected values are literals or fixture-derived — **never
      recomputed by the test**, which would only assert that the test agrees with itself.
- [ ] One behaviour per test, so a failure names what broke.
- [ ] Any skip carries a reason naming the unimplemented production feature that makes it unrunnable.

### Fixtures stay honest

[`src/test-utils/factories.ts`](./src/test-utils/factories.ts) exports `makeTweet(overrides)`,
`makeUser(overrides)` and `makeFeedTweet(overrides)`, plus the fixed timestamps
`FIXED_TWEET_TIMESTAMP` and `FIXED_USER_CREATED_AT` and their `Date` accessors
`fixedTweetTimestamp()` and `fixedUserCreatedAt()`. Every factory takes an optional partial of its
subject and defaults to `{}`, so an edge case is produced by overriding one field rather than by
writing a second literal, and a fresh object is returned on every call.

`src/schema/tweetSchema.test.ts` and `src/schema/userSchema.test.ts` parse the factory output through
the **real zod schemas**. That makes those two suites the honesty gate for the fixtures: if you change a
factory and it stops satisfying its schema, a test fails immediately instead of every other suite
quietly weakening. If you change a factory, expect to hear from them.

### Common pitfalls

Every one of these has already cost someone time in this codebase.

| Symptom | Cause and fix |
| --- | --- |
| `Unexpected token '<'` in a component suite | The extension-less `transform` key is not matching your module. Check §[3](#the-mechanism); the key matches the four names exactly and anchors on `$`. |
| "Cannot find module `@/services/analyticsService`" (or `configService`) | The generic `^@/(.*)$` mapper entry has been moved ahead of the stub entries. It must stay last (§[ordering](#ordering-first-match-wins)). |
| `TweetList` renders nothing, or its effect loops forever | It is a **named** export and needs a `filters` prop. Reuse **one** `filters` object across renders — a fresh object identity on every render retriggers the effect indefinitely. |
| `TrendCharts` fails to render | It is a **default** export and `dateRange` is required. |
| `window.alert is not implemented` | jsdom does not implement it. Spy it: `jest.spyOn(window, 'alert').mockImplementation(() => undefined)`, and restore it afterwards — the Configuration suite does exactly this. |
| A string `timestamp` fails `tweetSchema` | The field is `z.date()`. Pass `fixedTweetTimestamp()`, not the ISO string. Serialised, wire-shaped tweets come from `makeDefaultTweetsJson()` in `handlers.ts`. |
| Omitting `quoted_tweet_id` fails `tweetSchema` | It is **nullable, not optional**. Pass `null` explicitly. |
| A `jest.spyOn(axios, …)` has no effect | You are asserting a module loaded through `importWithConfiguredBase`, which returns a fresh instance. Drive it through msw (§[configured base](#driving-a-configured-base-url)). |
| A Redux Toolkit serializability warning in the console | Expected. A `makeTweet()` fixture's `timestamp` is a `Date`; the check is deliberately left on and the warning fails nothing. |
| `dependency-closure.test.ts` fails after you touched `package.json` | Intended. The eleven suite-owned pins must stay exact, and the seventeen baseline declarations must stay byte-identical to the frozen baseline (`D172`). |
| A test passes alone and fails in the full run | An isolation breach. Check for a `server.use(...)` you expected to persist, module state outside `src/test-utils/`, or a real timer left running. |

## 9. Observability of this suite

The Observability rule asks that a deliverable record what it reused and what it added. For this
folder:

**Reused, unchanged.** The two Codecov upload steps that already existed in
[`../.github/workflows/ci.yml`](../.github/workflows/ci.yml), and their `backend` and `frontend` flags.
The frontend step's `file:` path already pointed at `coverage/coverage-final.json`, which is why
`'json'` is a required entry in `coverageReporters` rather than an optional extra.

**Added.** The `jest-junit` reporter (`D36`, `D37`, `D157`), and four coverage reporters beyond Jest's
default — `lcov`, `json`, `json-summary` and `cobertura`, alongside `text-summary` for the console. The
per-test correlation identity described in §[7](#artifacts), and the request log in `handlers.ts` that
stamps the same identity on every intercepted request (`D83`). Together these are this suite's metrics
surface (`D193`).

**The readiness gate.** `npx jest --listTests` is the meaningful readiness check: it exits 0 and lists
every collectable test file — **23** on this run — proving the whole graph resolves before any
assertion runs. A resolution or transform regression shows up there first, and much more clearly than
in a failing assertion. A clean `npm run test:ci` is the full check.

**No production instrumentation was added.** Nothing under `src/` gained a logger, a metric, a trace
hook or a health endpoint. The production instrumentation gaps are recorded in the decision log
(`D194`) and are not addressed by this work.

## 10. Suggested next tasks

**None of the following were performed.** This work was bounded to test code plus two pre-authorized
production touches, and **both of those are in `backend/`, not here**. No production source under
`frontend/src/` was modified at all; the only pre-existing file changed in this folder is
[`package.json`](./package.json), and only its `devDependencies` and test scripts.

Each item is a real defect or gap found while building the suite, with the impact of leaving it alone.
Every one is traceable to [`../docs/testing/DECISION-LOG.md`](../docs/testing/DECISION-LOG.md) — the
cited handle, or its noted-but-not-fixed register.

| # | Task | Impact of not doing it | Trace |
| --- | --- | --- | --- |
| 1 | Commit a `package-lock.json` and restore `npm ci` in CI (this also means removing `package-lock=false` from [`.npmrc`](./.npmrc)). | No install is reproducible; the manifest and the installed graph have already diverged once. | `D93`, `D159` |
| 2 | Move `@reduxjs/toolkit`, `react-redux`, `react-router-dom`, `zod` and `dayjs` from `devDependencies` into `dependencies`. | Production source imports all five at runtime, so a production install omits them. | register, §*Build, CI and repository hygiene* |
| 3 | Add `eslint` and `eslint-config-react-app`. | The `lint` script and the `ci.yml` lint step cannot run at all — no linter is declared anywhere. | `D187` |
| 4 | Create `tsconfig.node.json`, or remove the dangling project reference from `tsconfig.json`. | `npm run build` fails and no Vite-based transform can process a single `.tsx` file. | `D32` |
| 5 | Add a Vite config and an HTML entry at the Vite root. | The app cannot be served: `GET /` returns 404 and `npm run build` fails at both legs. Only the e2e harness renders the UI. | `D40` |
| 6 | Replace `ReactDOM.render` in `src/index.tsx` with React 18's `createRoot`. | A React 17 API under React 18; concurrent features are unavailable and the call is deprecated. | register, §*Frontend behaviour* |
| 7 | Fix `src/store/index.ts` to import the slices' default reducers, and export `useAppDispatch` / `useAppSelector`. | The real store has no valid reducer and `getState()` returns `{}`; three page suites stay skipped. | `D34` |
| 8 | Implement or remove `TweetCard`. | Both list components crash on a non-empty list, so their tweet-rendering branch is untestable. | `D156` |
| 9 | Call `Chart.register`, or import from `chart.js/auto`, in `src/components/Analytics`. | Chart construction always fails, in the browser as well as in jsdom. | `D92` |
| 10 | Export `getTweets` from `src/services/twitterService.ts`, and `api` / `setupInterceptors` from `src/services/api.ts`. | `TweetList` and `src/index.tsx` import symbols that resolve to `undefined` and fail at call time. | `D42` |
| 11 | Pass both arguments in `getLatestTweets`, and compare a field the tweet shape actually has in `tweetSlice.updateTweet`. | Requests carry `limit=undefined`; `updateTweet` overwrites the wrong tweet every time. | register, §*Frontend behaviour* |
| 12 | Fix `formatNumber` so it does not group the fractional digits. | `formatNumber(1234.5678)` renders `'1,234.5,678'` to users. | register, §*Frontend behaviour* |
| 13 | Define `REACT_APP_API_BASE_URL`, or move to a Vite-style env var. | Every request goes to the literal host segment `undefined` and is unrouted. | `D169` |
| 14 | Reconcile the four extension-less component files into properly named modules. | The second transformer, four mapper entries and four explicit `collectCoverageFrom` paths exist only to work around this, and all of them could then be deleted. | `D30` |
| 15 | Correct the stale `"name": "data-visualization-dashboard"` in `package.json` and the "Personal Finance Tracker" title in `public/index.html`. | Two product identities in this folder, neither of which is this product. | register, §*Build, CI and repository hygiene* |
| 16 | Reconcile the `POST /generate-response` / `POST /tweets/{id}/responses` mismatch. | The frontend calls a path the backend does not declare, and the backend implements one nothing calls — so no response can ever be generated. | `D10`, `D15` |
| 17 | Turn `diagnostics` back on once items 4, 7 and 10 land. | The suite compiles without type checking, so a type error reaches review unaided. | `D32` |

## 11. Where "why" lives

This document is the *what* and the *how*. Four user-specified rules bear on it, and each is answered
by pointing somewhere rather than by argument here:

- **Explainability.** Rationale is not in this file and not in code comments. Alternatives and accepted
  risks live in [`../docs/testing/DECISION-LOG.md`](../docs/testing/DECISION-LOG.md), cited above by
  its stable `D…` handles. Which test covers which construct is in
  [`../docs/testing/TRACEABILITY-MATRIX.md`](../docs/testing/TRACEABILITY-MATRIX.md); this folder had
  no legacy tests to migrate, so it contributes the test-to-construct direction of that matrix.
- **Observability.** Answered for this suite in §[9](#9-observability-of-this-suite), with the
  dashboard in [`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md).
- **Onboarding & continued development.** This document, scoped to `frontend/`, with the cross-cutting
  view in [`../README.md`](../README.md), the backend suite in
  [`../backend/tests/README.md`](../backend/tests/README.md) and the Playwright suite in
  [`../e2e/README.md`](../e2e/README.md).
- **Executive presentation.** The deck reports this suite's coverage, so every figure published here
  must be one that was actually measured. Re-measure before you change a number in
  §[7](#measured-on-this-run).

Comments inside test and configuration files state **what the code does** and what a suite asserts;
they do not carry rationale (`D148`). If a comment and this document ever disagree, the code is
authoritative and one of the two is stale — fix it.

