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

**The CI workflow installs this tree as `npm install --ignore-scripts`.** Three lifecycle scripts would
otherwise run — `esbuild`'s postinstall here and in `e2e/`, and `msw`'s — and none of them is needed: the
suites were re-run in full on a tree deleted and rebuilt with that flag, and esbuild's JS API and CLI and
`msw/node` all work on it (`D411`). Locally either form is fine; the flag is what stops a floating
transitive resolution executing code in the pipeline. The pip side of the same step is pinned and
wheels-only for the same reason.

**`npm ci` will not work here, and that is deliberate.** No `package-lock.json` is committed (`D93`,
`D159`), and `npm ci` refuses to run without a lockfile, so the CI workflow uses `npm install` too. The
lockfile that `npm install` writes is **ignored**, at the anchored path `frontend/package-lock.json`
(`D380`): with the decision not to commit it standing, it is output of a documented command rather than
a deliverable, and leaving it untracked-and-unignored meant every documented install dirtied a clean
tree. The rule is anchored rather than bare so a lockfile committed at any other path stays visible,
and `git add -f frontend/package-lock.json` is what reverses the decision — deliberately, which is the
point. The reproducibility cost of shipping without one is real, is what `D381` measures, and is the
first entry in §[10](#10-suggested-next-tasks).

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
- **`EBADENGINE` on Node 16 — four packages in this tree, one more under `e2e/`.** Every one arrives
  **transitively**: no direct declaration in either manifest excludes Node 16, and on Node v22.23.1
  none of them is excluded at all, which is why the verification named above saw no `EBADENGINE`
  line. Audited by walking every installed `package.json` and evaluating
  `semver.satisfies(target, engines.node)`:

  | Package | Declares | Arrives through |
  |---|---|---|
  | `@testing-library/dom@10.4.1` | `>=18` | `@testing-library/user-event@14.6.3`, whose `^14.4.3` is a frozen baseline range (`D171`); `@testing-library/react@14.3.1` correctly resolves its own `@testing-library/dom@9.3.4`, which declares `>=14` |
  | `@inquirer/external-editor@1.0.3` | `>=18` | `msw@1.3.5` → `inquirer@8.2.7` |
  | `postcss-load-config@6.0.1` | `>= 18` | the floating `tailwindcss ^3.3.2`, resolving `3.4.19`, whose own range is `^4.0.2 \|\| ^5.0 \|\| ^6.0` |
  | `node-releases@2.0.53` | `>=18` | the `browserslist`/`autoprefixer` chain — present in `frontend/` and in `e2e/` |

  **The `msw` row is the one worth reading twice.** `msw` is pinned at `1.3.5` *because* the 2.x line
  requires `node>=18` (`D180`), and its own transitive tree now reaches a `>=18` package anyway. So the
  pin still does what it was chosen for — the direct dependency supports Node 16 — while the installed
  closure no longer does. That is a property of shipping without a lockfile, not of the pin.

  **What this means in practice.** The pins are all still correct and none has drifted: an
  `EBADENGINE` warning naming a **direct** test dependency would mean a pin no longer matches the
  runtime, and there is none. What the table shows instead is that a floating transitive graph has
  moved underneath four frozen declarations. It is not fixable from inside this file's authorized
  surface — AAP §0.8.1 scopes `frontend/package.json` to devDependencies and test scripts, so no
  `engines` field and no `overrides` block may be added here, and AAP §0.6.2 decides against
  committing a lockfile, which is the only thing that would freeze the graph. `D381` records the
  measurement, the three ways out and which of them an owner has to choose; the root
  [`README.md`](../README.md) §Suggested next tasks carries the same ask.

### The seven commands

All seven are declared in [`package.json`](./package.json) and all are run from `frontend/`.

| Command | Runs | Use it for |
| --- | --- | --- |
| `npm test` | `jest` | The everyday run. No coverage, so it is the fastest full pass. |
| `npm run test:watch` | `jest --watch` | Iterating on one suite. Needs a git checkout to diff against. |
| `npm run test:coverage` | `jest --coverage` | A local coverage report plus the `coverageThreshold` gate. |
| `npm run test:ci` | `jest --ci --coverage --watchAll=false` | **What CI runs.** Coverage, the gate, and every artifact in §[7](#7-coverage-gates-and-artifacts). |
| `npm run test:list` | `jest --listTests` | **Discovery.** Which files a run would pick up. It imports nothing, so a module that no longer loads is listed exactly like a healthy one. **Also a CI step**, ahead of `test:load`. |
| `npm run test:load` | `jest --ci --watchAll=false --runInBand --reporters=default -t "__readiness_probe_that_matches_no_test__"` | **The readiness gate.** Transforms and imports every suite and everything in its import graph, then runs no test body. Exits non-zero when one fails to load. **Also a CI step**, ahead of `test:ci`; see §[9](#9-observability-of-this-suite). |
| `npm run test:e2e` | `npm --prefix ../e2e run test` | Hands off to the Playwright suite. Every e2e command goes through the `e2e` package, never `npx` from the repository root (`D49`). |

### Targeted runs

Every example below goes through a `package.json` script, so the runner is always
`frontend/node_modules/.bin/jest`. Anything after `--` is passed straight to it.

```bash
npm test -- src/store/tweetSlice.test.ts          # one file
npm test -- -t "does not refetch at 29999 ms"     # one test, by name
npm run test:list                                 # discovery only: which files match, nothing loaded
npm run test:load                                 # loads and transforms every file, runs no test body
```

The last of those is the readiness gate described in §[9](#9-observability-of-this-suite); `test:list`
is not, because it resolves no import. Use the scripts rather than assembling the flags by hand: the
readiness script carries `--reporters=default`, and without it the probe's own all-skipped result would be
written over `reports/jest-junit.xml` by the configured `jest-junit` reporter. Both are scripts rather than
ad-hoc invocations, so the command you run locally is the command CI runs.

The `-t` pattern matches the full test name — every enclosing `describe` title and the leaf title,
joined by single spaces. That is exactly the string the JUnit report puts in `<testcase name>`
(§[7](#7-coverage-gates-and-artifacts)), so a failing report tells you what to select on.

**Escape it first.** `-t` is `testNamePattern`, a *regular expression*, not a literal — so a name copied
out of a report is only a usable pattern once its regex metacharacters are escaped. Most of this suite's
names carry the parentheses their `describe` title uses, and unescaped parentheses are read as a capture
group, which selects nothing:

```bash
# Selects nothing: the parentheses are a capture group, and Jest reports every test skipped.
npm test -- -t "RealTimeFeed (src/components/Dashboard) renders the feed heading inside the wrapper element"

# Selects exactly that test.
npm test -- -t "RealTimeFeed \(src/components/Dashboard\) renders the feed heading inside the wrapper element"

# Needs no escaping, because the name carries no metacharacter.
npm test -- -t "does not refetch at 29999 ms"
```

A leaf title is usually the shorter and safer thing to select on, since the enclosing `describe` is where
the parenthesised file path lives. The escaping requirement is `D367`.

One thing a targeted run costs you: the `jest-junit` reporter is declared in
[`jest.config.js`](./jest.config.js), so a one-file or `-t` filtered run writes `reports/jest-junit.xml`
with only the cases it ran. That is a **partial** stream sitting where the suite's results belong, and it
is refused rather than published — `docs/testing/dashboard-extract.py` compares it against the test
identities `test:load` registered and withdraws it by name, exiting 1 under `--require-all`. If you see
that message, `npm run test:ci` reproduces the whole stream. See `D404`.

### Parallelism

`jest.config.js` declares `maxWorkers: 1`, so there is no pool. That is the end state of two attempts at
the same advisory, and the order matters if you are thinking of raising it. Capping Jest's default —
`Math.max(1, Math.min(4, os.cpus().length - 1))`, one worker per core less one but never more than four —
was implemented and measured first, and on this 64-core host it did take `npm run test:ci` from 65 s
**with** the *"a worker process has failed to exit gracefully"* warning to 22–27 s without it across three
runs. But the warning came back on two runs in three once the host was loaded, because it is not a
function of worker count: a pool is torn down with a fixed 500 ms grace period per child, so whether a
child makes it is decided by OS scheduling. One worker removes the pool and the whole class of outcome,
and it subsumes the cap — one is below any ceiling. There are 24 suites, and every surplus worker still
boots a jsdom environment and an msw `setupServer` whose teardown is what printed the warning. See `D405`
for the cap and `D366` for the value the file carries.

### Snapshots

There are none, anywhere, and none should be added. Nothing is ever written back to the tree
implicitly, which is what makes `--ci` safe to use as the default rather than a special mode.

### Determinism: one process, one deadline

Two keys in [`jest.config.js`](./jest.config.js) exist so that a run's *outcome* does not depend on the
machine it runs on. They are in the config rather than on a script, so `npm test`, `test:coverage`,
`test:ci` and a bare `npx jest` all inherit them and the command you run locally is the command CI runs.

| Key | Value | What it buys |
| --- | --- | --- |
| `maxWorkers` | `1` | No child process. Jest takes its in-band path as soon as `maxWorkers <= 1`, so a worker pool is never created and never has to be torn down. |
| `testTimeout` | `30000` | Headroom over Jest's 5 s default for the component suites, which drive `user-event` through several `waitFor` boundaries. |

Neither is a throughput decision, and the worker one is worth understanding before you change it. Jest
ends a worker pool by sending each child a stop message and giving it a **fixed 500 ms** to exit; a child
that misses that window is killed and reported as `A worker process has failed to exit gracefully and
has been force exited`. The delay is a constant inside `jest-worker` — no configuration key extends it —
so on a contended host that warning is decided by how quickly the OS schedules a child, not by anything
a test does. Running in band removes the pool, and with it that whole class of outcome.

It is not covering for a leak. `--detectOpenHandles` reports none,
[`src/test-utils/setup-jest.ts`](./src/test-utils/setup-jest.ts) closes the msw server in `afterAll`, and
Jest gives each test file its own module registry and its own jsdom environment in band exactly as it does
in a worker — so per-file isolation is the same either way, which is why the suite passes in reverse file
order. Raise `maxWorkers` and you reintroduce a load-dependent warning; the sizing of both numbers, and
what was rejected, is `D366`.

## 2. What is under test, and the one principle that explains the assertions

### The shape of it

Twenty production modules live under `src/`, across `schema/`, `store/`, `services/`, `utils/`,
`components/` and `pages/`, plus the two entry modules `app.tsx` and `index.tsx`. Nineteen of them are
in the coverage denominator; `src/app.tsx` is excluded because it cannot be mounted at all
(§[7](#ceilings-not-gaps)). Before this suite existed, **none** of them was executed by a test.

Every suite is colocated beside its subject as `<Name>.test.ts` or `<Name>.test.tsx`. There are 24 of
them, in seven families:

| Family | Files | Subjects |
| --- | --- | --- |
| Schema | 2 | `src/schema/*.ts` — zod contracts |
| Store | 3 | `src/store/*.ts` — slices and the store module |
| Services | 3 | `src/services/*.ts` — the HTTP layer |
| Utils | 2 | `src/utils/*.ts` — formatting and dates |
| Components | 4 | `src/components/*` — the four extension-less modules |
| Pages | 5 | `src/pages/*.tsx` - one per module, plus a second file for `TweetManagement` |
| Test infrastructure | 5 | `src/test-utils/*.test.ts` — contract suites over the harness itself |

`src/pages/TweetManagement` carries two files rather than one, and the split is deliberate.
`TweetManagement.test.tsx` renders the real page - it is the only one of the four that mounts - while
`TweetManagement.callbacks.test.tsx` drives the callbacks it hands its child. Reaching those needs
`jest.mock('@/components/TweetManagement')`, which is hoisted and module-wide, so putting it in the first
file blanks the render that file exists to assert. Each file's docstring names the other; the reasoning is
`D229`.

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
| [`src/test-utils/factories.ts`](./src/test-utils/factories.ts) | The deterministic fixture builders the two schema suites validate. |

`setup-jest.ts` registers exactly four things and nothing else:

1. `delete process.env.REACT_APP_API_BASE_URL`, emitted **ahead of its own imports** so nothing
   reachable from the file can read the variable first.
2. The `@testing-library/jest-dom` matchers.
3. `server.listen(...)`, called **synchronously while the module is evaluating** — not from
   `beforeAll`. Jest evaluates a test module and every import-time side effect in its graph before it
   runs `beforeAll`, and `services/api.ts` runs code at module scope while both list components fetch
   on mount, so anything deferred to `beforeAll` would already have reached a socket (`D108`).
4. A global `afterEach`, bound by reference to `runSharedAfterEach` from
   [`src/test-utils/reset-shared-state.ts`](./src/test-utils/reset-shared-state.ts). That function asserts
   no isolation breach was recorded, then — in a `finally`, so a failing test still hands the next one
   clean state — calls `resetSharedTestState()`, which does `server.resetHandlers()`,
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
for one test with `server.use(...)`. The oracle for what each factory answers is the backend itself —
`backend/tests/integration/test_route_surface.py` measures the status, body and content type these
handlers reproduce (`D174`) — and the per-route caller-to-backend mapping is in
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

**A `server.use(...)` override names its origin in full too, and that is not a stylistic preference.**
A wildcard override such as `rest.get('*/tweets', …)` answers the path on *any* host, and because it
answers, `onUnhandledRequest` never fires — so the one mechanism that would report a request leaving for
a foreign origin is bypassed by the very handler that was supposed to be scoped to one test. There is a
test for this: `src/test-utils/setup-jest.test.ts` installs an override against the allowed origin and
then drives the same path on a remote one, asserting the override recorded nothing, the request was never
performed, and the breach is in the ledger as `kind: 'unhandled-request'` with the exact URL. The reason
that test exists is that this file's own override had been written host-agnostically, which made the suite
most responsible for the guarantee the one contradicting it (`D322`).

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
codebase, though they lose it in different ways, and the difference matters when you write the oracle:

| Caller | What it does with the error |
| --- | --- |
| `twitterService.getLatestTweets` / `getTweetDetails` | logs it, then `throw error` — the **original** object, so an `AxiosError` arrives at the caller as an `AxiosError` |
| `llmService.generateTweetResponse` | logs it, then throws a **replacement**: `new Error('Failed to generate tweet response')`. The original is only in the log |
| `TweetList` (`src/components/TweetManagement`) | catches and logs; nothing propagates |
| `RealTimeFeed` (`src/components/Dashboard`) | catches nothing at all, leaving an unhandled rejection |

Assert accordingly: a `getLatestTweets` test can match the transport error's own message, a
`generateTweetResponse` test must expect the fixed replacement string and can never see the cause.
What survives all four is the ledger entry, and the global `afterEach` throws on it — so the test that
caused the escape is the test that fails (`D136`).

This is required rather than defensive. Before interception was in place, an unmocked axios call opened
a real socket and produced `Error: connect ECONNREFUSED 127.0.0.1:80`, and because the rejection
settled *after* the test that started it, it failed a **later, unrelated test**. That is a
no-real-network violation and a genuine order-dependence bug at the same time.

The same ledger backs request screening: every handler checks the request against its entry in
`ROUTE_CONTRACTS`, and in layer 1 a request that deviates — an unknown or absent query key, a
placeholder path parameter, an unexpected body — is answered with status **599** and a body listing the
violations, never with a success status (`D3`, `D4`).

### The per-test cleanup, and how its own contract is proven

Everything a test may change is discarded by one function,
[`resetSharedTestState()`](./src/test-utils/reset-shared-state.ts): the msw runtime handler array, both
pieces of `handlers.ts` module state (the request log and the isolation ledger), and
`REACT_APP_API_BASE_URL`. `runSharedAfterEach()` in the same module wraps it — ledger assertion in a
`try`, the reset in a `finally` — and `setup-jest.ts` registers *that* as the global `afterEach`. You do
not call either one; the hook does.

It lives in its own module for a reason worth understanding before you extend it. A contract of the form
"state a test changes is gone before the next test sees it" is tempting to prove by changing something in
one test and looking for it in the next — and that proof is worthless, because it depends on the order
the tests are declared in. Split the pair, reorder it, or run either half with `-t` and it passes while
measuring nothing, which is exactly the order dependence the reliability checklist in
§[8](#reliability-checklist) forbids. Exported as a function, the same contract is provable inside a
single test: **change one thing, call the cleanup, assert it is gone** — reading the state back and
re-emitting the request whose outcome the change would have altered.
[`setup-jest.test.ts`](./src/test-utils/setup-jest.test.ts) is written that way throughout, and every one
of its tests passes standalone. What a single test cannot see — whether `setup-jest.ts` registers that
cleanup at all — it checks separately, by loading `setup-jest.ts` into an isolated module registry with
the Jest hook globals captured and asserting the registered `afterEach` **is** `runSharedAfterEach` by
identity (`D238`).

Two consequences for your own suites. If you add a new piece of mutable state to `handlers.ts`, put its
reset inside `resetHandlerState()` — that is the one call site the cleanup reaches, so nothing else needs
editing. And if you find yourself proving anything with a pair of tests, stop: make each test
self-contained instead.

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
import { fetchTweets } from './api';

it('surfaces a server error', async () => {
  server.use(
    rest.get('http://localhost/undefined/tweets', (req, res, ctx) =>
      res(ctx.status(500), ctx.text('Internal Server Error')),
    ),
  );

  const caught = await fetchTweets(1, 10).catch((error: unknown) => error);

  expect(caught).toMatchObject({ response: { status: 500 } });
});
```

The global `afterEach` removes it again, so nothing leaks into the next test. Reach for
`unsetBaseBackendHandlers()` or `configuredBaseBackendHandlers({ … })` instead when you want the
disposition the real backend produces rather than one you invented.

### Driving a configured base URL

Because `api.ts` reads the variable once at module scope, assigning it inside a test changes nothing
observable. Use the loader — `importWithConfiguredBase`, exported by
[`src/test-utils/handlers.ts`](./src/test-utils/handlers.ts) beside the `CONFIGURED_BASE_URL` it applies
— which sets the variable, discards the module registry and *then* imports:

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

Every figure below is a measurement rather than a target, so it carries where it came from. Re-measure
before quoting any of it — a number that outlives the tree it was taken on is a claim, not evidence.

| | |
| --- | --- |
| Command | `npm run test:ci` from `frontend/`, which is `jest --ci --coverage --watchAll=false` |
| Runner | `jest` 29.7.0 with `ts-jest` 29.4.12 and `jest-environment-jsdom` 29.5.0, installed from [`package.json`](./package.json) |
| Runtime | Node v22.23.1 / npm 10.9.8, Windows |
| Artifacts | `frontend/reports/jest-junit.xml` for the counts (root `tests="383" failures="0" errors="0"`, 24 `<testsuite>` children) and `frontend/coverage/coverage-summary.json` for every percentage in the table |
| Commit | Recorded by the tooling, not written here: `python ../docs/testing/dashboard-extract.py` prints the branch and commit of the tree it read in its §1.0 block, so re-run it beside the suite and quote that rather than a hash copied into prose |

Suites: 3 skipped, 21 passed, 21 of 24 total. Tests: 24 skipped, 359 passed, 383 total. 0 snapshots.

The 24 skips are the three page suites that cannot mount, and every one of them carries its own
blocker reason — the skip is per test, not a blanket `describe.skip`, so a skipped identity still
appears in `reports/jest-junit.xml` with the missing export named. Jest's *summary* line nevertheless
counts a suite whose every test is pending as a skipped suite, which is why "3 skipped" appears above
even though all three files are collected, transformed and executed to their `describe` bodies.

| Scope | Statements | Branches | Functions | Lines |
| --- | --- | --- | --- | --- |
| `src/schema` **(gated)** | 100% (4/4) | 100% (0/0) | 100% (0/0) | 100% (4/4) |
| `src/services` **(gated)** | 100% (38/38) | 100% (0/0) | 100% (6/6) | 100% (34/34) |
| `src/store` **(gated)** | 100% (39/39) | 100% (1/1) | 100% (11/11) | 100% (37/37) |
| `src/components` | 100% (85/85) | 100% (5/5) | 100% (25/25) | 100% (80/80) |
| `src/utils` | 100% (29/29) | 100% (21/21) | 100% (4/4) | 100% (29/29) |
| `src/pages` | 41.57% (37/89) | 40% (2/5) | 20% (4/20) | 43.02% (37/86) |
| `src/index.tsx` | 0% (0/11) | 100% (0/0) | 0% (0/1) | 0% (0/11) |
| **Whole denominator** | **78.64% (232/295)** | **90.62% (29/32)** | **74.62% (50/67)** | **78.64% (221/281)** |

All three gated scopes are at 100% on every metric, twenty points clear of the 80 threshold. The last two
addressable gaps have since been closed: `src/store/tweetSlice.ts` reached 100% once the `fetchTweets`
thunk's own happy path was driven (the module's missing `api` export is injected for the duration of that
describe block and removed afterwards), and `src/pages/TweetManagement.tsx` went from 66.66% to **100%** on
all four metrics once its callbacks were invoked from the second page file. Everything still short of 100%
is a ceiling, below - `src/pages` is held down by the three page modules that cannot mount at all, and
`src/index.tsx` calls a React 17 API under React 18.

The gate is live — verified by re-running with `./src/pages` thresholded at 80 through a command-line
override, which exits **1** with
`Jest: "./src/pages" coverage threshold for statements (80%) not met: 41.57%`.

### Artifacts

`npm run test:ci` writes the first six; the seventh comes from the readiness step. Other files depend on
these exact paths, so do not relocate them.

| Path | Written by | Consumed by |
| --- | --- | --- |
| `frontend/coverage/coverage-final.json` | the `json` coverage reporter | the `frontend`-flagged Codecov upload step in `ci.yml` |
| `frontend/coverage/lcov.info` and `coverage/lcov-report/` | `lcov` | local HTML browsing, most IDE gutters |
| `frontend/coverage/coverage-summary.json` | `json-summary` | the dashboard in [`../docs/testing/DASHBOARD-TEMPLATE.md`](../docs/testing/DASHBOARD-TEMPLATE.md) |
| `frontend/coverage/cobertura-coverage.xml` | `cobertura` | CI coverage annotators |
| `frontend/reports/jest-junit.xml` | the `jest-junit` reporter, on a real suite run only | CI test reporting |
| `frontend/reports/load-tests.txt` | the readiness step's `tee` around `npm run test:load` — written by CI, and by the documented local sequence | the readiness row of the dashboard's extractor |

`'json'` has to stay in `coverageReporters`: it is the reporter that writes `coverage-final.json`, which
is the file the pre-existing `frontend`-flagged Codecov step asks for (`D36`). That step's path was
repointed to `./frontend/coverage/coverage-final.json`, because it runs from the repository root —
see §[9](#9-observability-of-this-suite).

The JUnit report carries a stable identity for every test, which is what lets a CI result be matched
back to a source location and to the requests that test made:

- `<testsuite name>` and `<testcase classname>` — the `rootDir`-relative test file with forward slashes,
  e.g. `src/store/tweetSlice.test.ts`.
- `<testcase name>` — every enclosing `describe` title plus the leaf title, joined by single spaces.
  It is Jest's own `currentTestName`, so it is the string to select a test by; because `-t` is a regular
  expression, escape its metacharacters before using it as a pattern
  (§[1](#targeted-runs), `D367`).
- `<testcase file>` — the same path in the platform's own separator style, which is what CI annotators
  read.

Those come from **template functions** rather than `'{filepath}'` strings, because a string cannot
normalise a path separator and `{title}` expands to the leaf title alone (`D157`). The other half of the
same identity is `currentTestId()` in [`src/test-utils/handlers.ts`](./src/test-utils/handlers.ts),
which stamps every intercepted request with that exact string — so if you change either the reporter
options or that helper, change both (`D158`, `D273`, `D285`).

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
| Three of four page modules cannot mount | `useAppDispatch` / `useAppSelector` are not exported by `src/store/index.ts`. `src/pages/Dashboard.test.tsx` (8 tests), `src/pages/Configuration.test.tsx` (10) and `src/pages/Analytics.test.tsx` (6) are written, collected and skipped **per test**, each skip naming the missing export and the line that raises; `src/pages/TweetManagement.test.tsx` runs (`D215`). |
| The tweet-rendering branch of both list components | `TweetCard` is imported by `src/components/Dashboard` and by `src/components/TweetManagement` — the latter **from itself** — and is defined nowhere. A non-empty list yields React's "Element type is invalid … got: undefined". The suites assert that diagnostic rather than silencing it (`D156`). |
| Chart.js construction in `src/components/Analytics` | It imports the tree-shakeable `{ Chart }` and never calls `Chart.register`, so a working chart can never be produced — in a real browser either. What *is* produced there is a failure, and it is asserted: see the section below for which layer observes which part. |

### The missing `Chart.register` is a ceiling, and it is asserted one layer up

Be precise about this one, because it is easy to overstate in either direction. Four behaviours are
asserted by executing tests, and no part of the ceiling is left unevidenced:

| Behaviour | Where | State |
| --- | --- | --- |
| The subject constructs one chart, on `canvas#trendChart`, with the configuration it owns | `Analytics.test.tsx`, with `Chart` replaced by an inert spy | **Asserted** |
| The subject constructs no chart when `getTrendData` resolves falsy, and swallows and logs a rejection without reaching `renderCharts` | `Analytics.test.tsx` | **Asserted** |
| The real `chart.js` is entered once, jsdom reports it cannot supply a 2D rendering context, nothing propagates, and the component is still mounted with its canvas | `Analytics.test.tsx`, one case that puts the real library back | **Asserted** |
| Chart.js reporting a scale or controller that no module registered, the error escaping the unwrapped effect, and React unmounting the component | `e2e/tests/analytics.spec.ts` test 4, in real Chrome | **Asserted** |

The split follows from what each environment can supply. Observing the registration failure needs a real
canvas context *and* a resolved trend series in the same run. Under jsdom there is no 2D context, and
jsdom says so before Chart.js looks anything up in its registry — so that notice, not the registration,
is what the real-library case here observes, and this suite asserts exactly that. The E2E layer has a
browser and therefore a context, and its fourth test opts into `e2e/harness/stubs/analyticsService.ts`'s
`x-harness-forward-trend-series` header so a well-formed series reaches `renderCharts`. It then asserts
the unregistered-part error, that it arrived as an uncaught page error, and that the **whole React root**
came down with it — the harness's `<main>` landmark included and `#root` left empty, because no error
boundary exists anywhere above the component.

So neither layer hides the other's gap and neither should be described as covering the other's part:
**jsdom pins the context notice, the browser pins the registration failure.** Forwarding stays opt-in
because it is destructive at page scope rather than route scope, and only the test asserting the
destruction wants it (`D327`).

### The four chart paths, kept apart

`src/components/Analytics` has one `try`/`catch` and it wraps only the `getTrendData` call. Nothing
wraps `new Chart(...)`. Four outcomes are therefore distinct, and conflating them is the single easiest
mistake to make in this folder. All four are asserted; the fourth is out of reach under jsdom, so it is
asserted in a real browser instead:

| Path | What happens | Where it is asserted |
| --- | --- | --- |
| A controlled `Chart` constructor | `src/components/Analytics.test.tsx` substitutes the constructor, so nothing fails at all. The configuration object the component builds is the subject. | `src/components/Analytics.test.tsx` |
| jsdom with the real library | `chart.js` cannot acquire a 2D context from jsdom's canvas and **returns early itself**. Nothing is thrown, so nothing is caught; the component stays mounted with its heading and canvas intact. | `src/components/Analytics.test.tsx`, and the E2E render check |
| The trend request rejects | The `getTrendData` `catch` runs, `chartData` stays null, and `renderCharts` is never entered — a path that never reaches Chart.js. | `src/components/Analytics.test.tsx`, `e2e/tests/analytics.spec.ts` |
| A real browser with a working canvas | `Chart.register` was never called, so construction raises **outside any `catch`**, the raise propagates out of the effect and React unmounts `TrendCharts`. | `e2e/tests/analytics.spec.ts` test 4, which opts into the harness stub's forwarding header for exactly this, and not reachable from jsdom (`D216`, superseded by `D327`, which records the promotion from ceiling to assertion). |

**Do not install `jest-canvas-mock`, and do not add a `ResizeObserver` stub.** They look like the
obvious fix and they make the result strictly worse — they move the suite from the second row to the
fourth. With the canvas mock alone Chart.js reaches `ReferenceError: ResizeObserver is not defined`,
and with both it reaches `Error: "linear" is not a registered scale`, which escapes to React and
**unmounts** `TrendCharts`, leaving nothing to assert. Unshimmed, the component stays mounted — because
`chart.js` bails out on its own, not because anything caught a failure — which is how
`src/components/Analytics` measures 100% today. The evidence is in `D92`.

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
- [ ] No order dependence. **Every test passes standalone**, in the full run, and with `--runInBand` —
      check the first of those with `npm test -- <file> -t "<the exact test name>"`, which runs one test
      and skips the rest. In particular, never prove a cleanup or reset with a pair of tests where the second
      inspects what the first left behind; call the shared helper inside one test instead
      (§[5](#the-per-test-cleanup-and-how-its-own-contract-is-proven)).
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
| A dependency change makes a suite fail to resolve | The eleven suite-owned devDependencies must stay exact pins, and the seventeen baseline declarations must stay byte-identical to the frozen baseline (`D171`). Re-run `npm install` after any edit to `package.json`. |
| A test passes alone and fails in the full run | An isolation breach. Check for a `server.use(...)` you expected to persist, module state outside `src/test-utils/`, or a real timer left running. |

## 9. Observability of this suite

The Observability rule asks that a deliverable record what it reused and what it added. For this
folder:

**Reused.** The two Codecov upload steps that already existed in
[`../.github/workflows/ci.yml`](../.github/workflows/ci.yml), the action they call, and their `backend`
and `frontend` flags — none of which changed. The frontend step already asked for
`coverage-final.json`, which is why `'json'` is a required entry in `coverageReporters` rather than an
optional extra.

**Repointed, not reused unchanged.** That step's `file:` path *was* changed: `./coverage/coverage-final.json`
became `./frontend/coverage/coverage-final.json`. The step runs with the job's default working
directory, which is the repository root, while the run that produces the file happens under
`frontend/` — so the original path named a file that never exists and the upload would have found
nothing. The backend step was repointed the same way, `./coverage.xml` to `./backend/coverage.xml`. Both
are test-step prerequisites under the authorized CI surface; the flags are what Codecov keys on and they
are untouched, so no dashboard history is orphaned by the move.

**Added.** The `jest-junit` reporter (`D36`, `D37`, `D157`, `D316`) — configured with `addFileAttribute` and `reportTestSuiteErrors`, and deliberately **without** `includeConsoleOutput`, because this suite drives production code that logs objects and that option filled the retained artifact with `<system-out>` sections carrying raw logged values and absolute host paths, in a file CI uploads unconditionally. The correlation it was added for is already carried by `classname`, `name` and the `file` attribute. Also four coverage reporters beyond Jest's
default — `lcov`, `json`, `json-summary` and `cobertura`, alongside `text-summary` for the console. The
per-test correlation identity described in §[7](#artifacts), and the request log in `handlers.ts` that
stamps the same identity on every intercepted request (`D83`). Together these are this suite's metrics
surface (`D193`).

**The readiness gate.** Two checks, and they prove different things — do not substitute one for the
other.

`npm run test:list` (`jest --listTests`) is **discovery only**. It walks `roots` against `testMatch` and prints the files
it would run — **24** on this run, exit 0, the same 24 the readiness probe below loads. It loads nothing, transforms nothing and resolves no import,
so it cannot tell you the suite is loadable: a file with a broken import or a failing transform is
listed exactly like a healthy one.

The load-and-execution gate is `npm run test:load` — a non-watch, single-process run whose name filter
matches nothing:

```bash
jest --ci --watchAll=false --runInBand --reporters=default -t "__readiness_probe_that_matches_no_test__"
```

Jest can only know a test's name after it has transformed the file, executed it at module scope and run
its `describe` callbacks, so this transforms and loads all **24** files, evaluates every module in their
import graphs, registers all **383** test identities, then runs zero test bodies. On this run it exits
**0** in about 13 seconds reporting `Test Suites: 24 skipped, 0 of 24 total` and
`Tests: 383 skipped, 383 total`, retained at `frontend/reports/load-tests.txt`, which the dashboard
extractor reads and requires.

Two flags earn their place. `--runInBand` states the single-process run on the command line rather than
inheriting it: `maxWorkers: 1` in [`jest.config.js`](./jest.config.js) already puts every run in that path
(§[1](#determinism-one-process-one-deadline)), and the flag keeps this probe correct if that key is ever
raised — a worker pool would otherwise add a teardown warning to the retained output that has nothing to do
with readiness.
`--reporters=default` **replaces** the configured reporter list, and without it this probe is a real Jest
run whose `jest-junit` reporter overwrites `reports/jest-junit.xml` with its own all-skipped stream: a file
declaring `tests="383" failures="0"` in which every case is skipped, which no consumer can distinguish
from a run in which nothing executed — the same zero-information stub `pytest --collect-only` and
`playwright test --list` each write. Measured both ways: with the flag, that file's SHA-256 is unchanged
either side of a probe; without it, it changed.

Negative-validated: adding one unresolvable import to `src/utils/formatUtils.test.ts` turns the probe into
exit **1** with `Cannot find module '../does-not-exist-readiness-probe' from 'src/utils/formatUtils.test.ts'`
and `Test Suites: 1 failed, 24 skipped, 1 of 25 total`, while `test:list` on the same perturbation still
lists all 24 files and exits **0** — which is the whole argument for the gate being the probe rather than
the census, and the reason the two are separate checks. The import was removed again immediately and the
file restored byte-for-byte.

A clean `npm run test:ci` remains the full check — it is the only one of the three that executes an
assertion.

**No production instrumentation was added.** Nothing under `src/` gained a logger, a metric, a trace
hook or a health endpoint. The production instrumentation gaps are recorded in the decision log
(`D194`) and are not addressed by this work.

## 10. Suggested next tasks

**None of the following were performed.** This work was bounded to test code plus two pre-authorized
production touches, and **both of those are in `backend/`, not here**. No production source under
`frontend/src/` was modified at all; the only pre-existing file changed in this folder is
[`package.json`](./package.json), and only its `devDependencies` and test scripts.

The security exposures among them — the unmasked credential fields, the unencoded path segment in `api.ts`, and the advisories carried by the pinned `react-router`, `esbuild`, `cookie` and `postcss` versions — are written up individually in [`../docs/testing/SECURITY-GAPS.md`](../docs/testing/SECURITY-GAPS.md), with the clause that put each out of reach and what has to be done.

Each item is a real defect or gap found while building the suite, with the impact of leaving it alone.
Every one is traceable to [`../docs/testing/DECISION-LOG.md`](../docs/testing/DECISION-LOG.md) — the
cited handle, or its noted-but-not-fixed register.

| # | Task | Impact of not doing it | Trace |
| --- | --- | --- | --- |
| 1 | Commit a `package-lock.json` and restore `npm ci` in CI. | No install is reproducible; the manifest and the installed graph have already diverged once. | `D93`, `D159` |
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
| 18 | Give the analytics chart an accessible name and a text alternative — `role="img"` with `aria-label`, or a data table beside the canvas. | The whole of the analytics content is invisible to a screen reader: the canvas carries no naming attribute and a canvas has no implicit role. | `D217`, `G9` |
| 19 | Make the loading indicator and the polled feed announce themselves — `role="status"` on the indicator, `aria-live` on `div.real-time-feed`. | A non-sighted user is told neither that a fetch is in flight nor that the feed replaced itself, which it does every 30 000 ms. | `D217`, `G10` |
| 20 | Hold pending state across the credential save: `disabled` plus `aria-busy` on the button while the write is open. | A second activation mid-flight issues a second identical credential write and a second dialog; nothing in the UI indicates the first is still running. | `D217`, `G11` |
| 21 | Render `API Key` and `Access Token` as `type="password"` and declare an `autocomplete` policy on all four fields. | Two of four credentials are shown in clear text and are offered to the browser's generic autofill; masking currently follows the field's name, not its sensitivity. | `D217`, `G12` |
| 22 | Attach a rejection handler to the polled feed, render an error state with `role="alert"`, and add backoff with a failure ceiling. | Measured in real Chrome against a failing endpoint over a 757-second session: **26 failed requests, 26 unhandled promise rejections, a strict 1:1, and `rejectionhandled` 0** — none was ever handled. `src/components/Dashboard` calls its async fetch as a bare statement and hands the same function to `setInterval`, so both call sites discard the promise; `twitterService.getLatestTweets` does catch, but it logs and re-throws, so it suppresses nothing. The interval never lengthens (13 periods averaging 30000.238 ms, 4.2 ms spread) and never stops, and the page shows the heading and nothing else throughout — every one of ten failure words absent from the document, `[role=alert]`/`[role=status]`/`[aria-live]`/`[aria-busy]` all absent, zero DOM mutations after mount, byte-identical screenshots nine minutes apart. A total outage is therefore indistinguishable from an empty feed, to a user and to browser-side monitoring alike. The suite asserts the schedule's invariance; the leak itself is browser evidence rather than a test, because jest-circus attributes a real unhandled rejection to the running test. | `D411`, `SECURITY-GAPS.md` row 33 |
| 23 | Bound the four credential fields' length, in the markup and again on the server. | None of them declares `maxlength`, `minlength`, `pattern`, `size` or `name`, and Chrome reflects `maxLength === -1` accordingly. A 5000-character value entered by a **real paste** survives intact — proven against a control paste into `<input maxlength="10">` that truncated to 10 — and is submitted whole at `content-length: 5109`, answered without any length complaint. React also mirrors every controlled value into the DOM `value` **content attribute**, so `document.body.outerHTML` carries the full 5000 characters and both `type="password"` values in clear text. | `SECURITY-GAPS.md` rows 26 and 28 |
| 24 | Coerce `timestamp` at the API boundary rather than leaving `tweetSchema` unable to parse a server record. | `safeParse` of the record the backend genuinely emits fails on **exactly one** field — `invalid_type`, expected `date`, received `string`, path `["timestamp"]` — and coercing that one field makes the whole record parse with all ten keys unchanged, so the schema's field names already agree with the server's exactly and the mismatch is one of type alone. Worse than a rejection: the emitted string carries **no timezone designator**, so `new Date()` parses it as *local* time and the instant reconstructed depends on the reader's zone. The offset-bearing form the server emits for an aware value behaves the same way, which is why the fix belongs at the boundary and not in a per-field special case. | `D413` |

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
