?# Testing Traceability Matrix

Bidirectional mapping between the constructs the test suite covers and the implementations that cover them.
Every row is traversable in both directions: from a production construct to the test artifact that exercises
it, and from each test artifact back to the construct it stands for.

## Document coverage

| Section | Direction | Subject | Rows |
|---------|-----------|---------|------|
| §A | Frontend caller → backend route | Every HTTP request a module under `frontend/src/` issues, the path it lands on, the outcome the backend produces for that path today, the outcome the same call gets once the base URL is configured, and the handler that models each | 8 |
| §B | msw handler → caller and route | Every handler exported by `frontend/src/test-utils/handlers.ts` | 7 |
| §C | Backend route → frontend callers | Every route the backend implements or is called at, plus the prefix every emitted request carries and no route declares | 6 |
| §D | Divergence → the suite obliged to assert it | Every mismatch §A records, plus the two behaviours the security-gate remediation added | 16 |
| §E | Legacy test → its replacement, and replacement → legacy test | All 25 functions of the three deleted legacy modules, in both directions | 25 + 3 |
| §F | Test artifact → the construct it covers | Every file of the new suite, and the production construct or infrastructure obligation behind it | 75 |
| §G | Coverage ceiling → the assertion that stands in for it | Every branch no test can execute without changing production | 8 |
| §H | Harness guarantee → the artifact that enforces it | Every determinism, credential, egress and isolation guarantee the three suites rest on, and the file that implements it | 15 |

Coverage of the mapped set is complete: all four routes registered in `ROUTE_CONTRACTS` and every exported
handler set appear in both directions; every divergence in §A has a row in §D; all 25 legacy test
functions appear in §E with a disposition, and §E's reverse table maps each replacement suite back to the
legacy functions it absorbs; and every file listed as in scope for this milestone appears in §F. The
reasoning behind each choice is in `docs/testing/DECISION-LOG.md`. Every guarantee in §H names the artifact that enforces it and the evidence it was verified with. This document records what is true, not
why it was chosen.

## How the outcomes in this document were obtained

Backend outcomes were measured against the assembled application, not read from the design documents:
`TestClient(app, raise_server_exceptions=False)`, one request per row, each run twice — once with
`app.db.firestore.get_db` left alone and once with it replaced by a SQLAlchemy-shaped stand-in. Frontend
request shapes were measured by driving the real service functions through msw 1.3.5 under Jest 29 and jsdom
and reading back the intercepted URL, path parameters and body.

**The base URL decides the outcome before anything else does.** `REACT_APP_API_BASE_URL` is unset under Jest —
`frontend/src/test-utils/setup-jest.ts` deletes it — and `frontend/src/services/api.ts` interpolates it without
a fallback, so every URL a caller builds begins with the literal four-character string `undefined`, which jsdom
resolves against `http://localhost` into the path prefix `/undefined`. `app/main.py` mounts its one populated
router at the root, so the declared paths are `/tweets`, `/tweets/{tweet_id}` and
`/tweets/{tweet_id}/responses` and nothing lives under `/undefined`. Every request the application emits today
is therefore **unrouted**, and starlette's router answers `404 {"detail":"Not Found"}` before a query value is
coerced or `Depends(get_db)` resolves. X16 carries that divergence and
`backend/tests/integration/test_route_surface.py` asserts it server-side, for all four paths and for a
well-formed and a malformed query string alike.

So §A states two outcomes per row: what the emitted request gets **today**, and what the same call gets once
the base URL is configured to an origin the backend serves — which is the only disposition under which the
route's own behaviour is observable at all. A suite that means to assert the second re-imports its subject
through `frontend/src/test-utils/configured-base.ts`.

The database stand-in matters for exactly one cell. `GET /tweets` is the only route whose outcome depends on
it: with the real `get_db` a routed, validly-parameterised request answers `500`, and `200` is what it answers
once the dependency is replaced. The `422` is **not** one of those cells — parameter coercion precedes the
endpoint, so it is returned either way. X13 records the dependency dependence, X3 the coercion failure, and
B6 and B7 model the two dispositions separately.

---

## §A Frontend caller → backend route

| # | Caller | Request it emits | Backend route and contract | Outcome today, base unset | Outcome with the base configured | Handler that models each | Divergences (see §D) |
|---|--------|------------------|----------------------------|---------------------------|----------------------------------|--------------------------|----------------------|
| A1 | `services/api.ts` `fetchTweets(page, limit)` | `GET undefined/tweets?page=<page>&limit=<limit>` → path `/undefined/tweets` | `GET /tweets`, query `skip: int = 0`, `limit: int = 100`, returns `List[Tweet]` | `404` `{"detail":"Not Found"}`, `application/json` — unrouted path | `500` `Internal Server Error`, `text/plain; charset=utf-8` — `db.query(Tweet)` on the Firestore `Client`; `200` with the list under a SQLAlchemy-shaped `get_db` override | isolation → 200 with three tweets (a fixture); `unsetBaseBackendHandlers()` → 404; `configuredBaseBackendHandlers()` → 500; `…({dependencyOverridden: true})` → 200 | X1, X2, X13, X16 |
| A2 | `services/twitterService.ts` `getLatestTweets(count)` | `GET undefined/tweets?page=<count>&limit=undefined` — calls the two-parameter `fetchTweets` with one argument | same route | `404` — the malformed `limit` is never reached | `422` `{"detail":[{"loc":["query","limit"],"msg":"value is not a valid integer","type":"type_error.integer"}]}`, with **or without** the `get_db` override: coercion precedes the endpoint | isolation → 200; `unsetBaseBackendHandlers()` → 404; `configuredBaseBackendHandlers()` → 422 with that exact body under either disposition | X3, X13, X16 |
| A3 | `components/Dashboard` `RealTimeFeed`, mount effect and 30 s interval | `GET undefined/tweets?page=undefined&limit=undefined` — calls `getLatestTweets()` with no argument | same route | `404` | `422`, one record naming `limit`; `page` is undeclared and ignored, so it contributes none | isolation → 200; `unsetBaseBackendHandlers()` → 404; `configuredBaseBackendHandlers()` → 422 | X3, X4, X16 |
| A4 | `services/api.ts` `fetchTweetById(tweetId)` | `GET undefined/tweets/<tweetId>`, no query, no body | `GET /tweets/{tweet_id}`, returns `Tweet`, raises `HTTPException(404)` when absent | `404` `{"detail":"Not Found"}` — the **router** refusing the path, not the handler's absent-tweet branch | `500`, body `Internal Server Error`, `text/plain; charset=utf-8`, for every id either way — the handler reads `Tweet.id`, which the pydantic model does not declare | isolation → 200 echoing the path parameter; `unsetBaseBackendHandlers()` → 404; `configuredBaseBackendHandlers()` → that 500 | X5, X6, X16 |
| A5 | `services/twitterService.ts` `getTweetDetails(tweetId)` | wraps A4 | same route | same `404` | same `500` | same as A4 | X5, X7, X16 |
| A6 | `services/api.ts` `generateResponse(tweetId)` | `POST undefined/generate-response`, `application/json`, body `{"tweetId":"<tweetId>"}`; reads `data.generatedResponse` | none — no router declares this path | `404` `{"detail":"Not Found"}` | `404`, unchanged: the path does not exist under any base, so this is the one row configuring the base does not move | isolation → 200 `{generatedResponse}`; `unsetBaseBackendHandlers()` and `configuredBaseBackendHandlers()` → that 404 | X8, X9, X16 |
| A7 | `services/llmService.ts` `generateTweetResponse(tweetId)` | wraps A6; replaces any rejection with `Error('Failed to generate tweet response')` | none | `404`, seen by the caller as the replacement error | same `404`, same replacement error | same as A6 | X8, X10 |
| A8 | none — no module under `frontend/src/` requests it | `POST undefined/tweets/<tweetId>/responses`, no query, no body | `POST /tweets/{tweet_id}/responses`, no request body, returns a dict keyed `response` | `404` `{"detail":"Not Found"}` | `500`, body `Internal Server Error`, from the same `Tweet.id` access | isolation → 200 `{response}`; `unsetBaseBackendHandlers()` → 404; `configuredBaseBackendHandlers()` → that 500 | X5, X11, X16 |

Two things the columns above are careful about, because conflating either is how a wrong client route comes to
look integrated:

- The **isolation** column is a fixture. No route in it answers `200` on the real application under any base.
- A `404` in the "today" column and the `404` written into `app/api/routes/tweets.py` are different facts. The
  first is the router refusing an unrouted path; the second is a handler branch that is unreachable, because
  `Tweet.id` raises first (G5). No handler models the second.

Neither layer registers a wildcard path segment: every pattern names its origin, its base path prefix and its
route path in full, so a request under any other prefix matches nothing and becomes an isolation-ledger entry
rather than a response. §B gives the registered patterns.

Two frontend call sites issue **no HTTP request at all** and therefore have no row above and no handler:

| Call site | What happens instead |
|-----------|----------------------|
| `components/TweetManagement` `TweetList` → `getTweets(filters, page)` | `services/twitterService.ts` does not export `getTweets`, so the call raises `TypeError` before any request is attempted. The component catches it and logs `Error fetching tweets:`. |
| `components/Analytics` and `components/Configuration` → `@/services/analyticsService`, `@/services/configService` | Neither module exists. Both are redirected to the pure, network-free stand-ins under `frontend/src/test-utils/stubs/`. No backend router serves these concerns: the analytics and config routers are empty. |

## §B msw handler → the caller and route it stands for

| # | Exported handler | Layer | Registered pattern | Stands for | Answers |
|---|------------------|-------|--------------------|------------|---------|
| B1 | `frontendIsolationHandlers[0..1]` (alias `handlers[0..1]`) | isolation, test-only | `GET http://localhost/undefined/tweets` and `GET http://127.0.0.1/undefined/tweets` | A1, A2, A3 | `200` with `makeDefaultTweets()`; `599` when the request fails screening |
| B2 | `frontendIsolationHandlers[2..3]` | isolation, test-only | `GET <origin>/undefined/tweets/:tweetId`, one per allowed origin | A4, A5 | `200` with one tweet whose `tweet_id` echoes the path parameter; `599` on screening failure |
| B3 | `frontendIsolationHandlers[4..5]` | isolation, test-only | `POST <origin>/undefined/tweets/:tweetId/responses`, one per allowed origin | A8 | `200` `{response: DEFAULT_TWEET_RESPONSE}`; `599` on screening failure |
| B4 | `frontendIsolationHandlers[6..7]` | isolation, test-only | `POST <origin>/undefined/generate-response`, one per allowed origin | A6, A7 | `200` `{generatedResponse: DEFAULT_GENERATED_RESPONSE}`; `599` on screening failure |
| B5 | `unsetBaseBackendHandlers()` | what the application answers for the paths it emits today | all four route paths under `<origin>/undefined`, one handler per route per allowed origin — eight | A1–A8 | `404` `{"detail":"Not Found"}`, `application/json`, for every one, whatever the query values, for the reason X16 records |
| B6 | `configuredBaseBackendHandlers()` | what it answers once the base URL is configured, dependency **not** overridden | the same four route paths under `<origin>` with no prefix — the backend's own paths | A1–A8 | `GET /tweets`: `422` naming **every** declared `int` parameter that fails coercion, in declaration order, otherwise `500` `Internal Server Error` `text/plain; charset=utf-8`. Both tweet-detail routes: that same `500`. `POST /generate-response`: `404` |
| B7 | `configuredBaseBackendHandlers({ dependencyOverridden: true })` | the same, **under** `app.dependency_overrides[get_db]` | as B6 | A1–A8 | identical to B6 except that a `GET /tweets` request which passes coercion answers `200` with the tweet list. The `422` is unchanged, because coercion precedes the endpoint |

Each layer-2 factory returns an array, so a call site spreads it — `server.use(...unsetBaseBackendHandlers())`.
B5 and B6/B7 are **alternatives, not additions**: a request carries one base URL, so a suite installs the set
matching the base its subject was loaded under, and a suite wanting B6 or B7 re-imports its subject through
`frontend/src/test-utils/configured-base.ts` first. B6 and B7 are the same factory under its one option.

`<origin>` is each entry in `ALLOWED_REQUEST_ORIGINS`, `http://localhost` and `http://127.0.0.1`. No pattern
carries a wildcard segment: the base path prefix is named in full, which is what makes a mis-set base URL — or
a client reaching the backend's path while still unconfigured — match nothing, reach `onUnhandledRequest` and
become an isolation violation rather than a response. See §H rows H7 and H15.

Supporting exports and what they are for: `ROUTE_CONTRACTS` (the four contract records the screening runs
on, each carrying its route `path`, both per-base outcomes and its mismatches), `UNSET_BASE_PATH_SEGMENT` /
`UNSET_BASE_PATH_PREFIX` / `CONFIGURED_BASE_URL` / `CONFIGURED_BASE_PATH_PREFIX` (the two base URLs and the
path prefix each produces), `recordedRequests` / `lastRecordedRequest` / `resetRecordedRequests` (the
intercepted-request log a suite asserts exact query, path, base and body values from),
`ALLOWED_REQUEST_ORIGINS` / `allowedRequestOrigins`
(the frozen origin allow-list and its accessor; there is deliberately no mutator — see `DECISION-LOG.md`
D103, and D136, which supersedes the mutable allow-list D116 had kept),
`ConfiguredBaseBackendOptions` (B6 versus B7), `IsolationViolationKind` / `IsolationViolation` / `recordedIsolationViolations` /
`resetIsolationViolations` / `recordUnhandledRequest` / `assertNoIsolationViolations` (the non-swallowable
violation ledger for an out-of-scope origin, an unhandled request or a contract deviation),
`CONTRACT_VIOLATION_STATUS` /
`CONTRACT_VIOLATION_DETAIL` (the screening failure response), `BACKEND_SERVER_ERROR_STATUS` /
`BACKEND_SERVER_ERROR_BODY` / `BACKEND_TEXT_CONTENT_TYPE` / `BACKEND_NOT_FOUND_STATUS` /
`BACKEND_NOT_FOUND_BODY` / `BACKEND_UNPROCESSABLE_STATUS` / `BACKEND_INTEGER_ERROR_MESSAGE` /
`BACKEND_INTEGER_ERROR_TYPE` / `BACKEND_TWEETS_INT_PARAMETERS` / `backendIntegerCoercionErrorBody` (the measured
backend values, the two parameters the route declares in declaration order, and the 422 body builder that takes
a list because fastapi reports every failure rather than the first), `makeDefaultTweets` /
`makeDefaultTweetsJson` / `DEFAULT_GENERATED_RESPONSE` /
`DEFAULT_TWEET_RESPONSE` / `SerializedTweet` (the isolation payloads and their wire shape).

## §C Backend route → frontend callers and covering suites

| # | Backend route | Frontend callers | Covered by |
|---|---------------|------------------|------------|
| C1 | `GET /tweets` | A1, A2, A3 — none of which reaches it today | backend integration suite for the real route, including the `422` per malformed parameter and the two-record declaration order; frontend suites through B1 (fixture), B5 (the 404 the callers actually get) and B6/B7 (the route's own behaviour under a configured base) |
| C2 | `GET /tweets/{tweet_id}` | A4, A5 — likewise unrouted today | backend integration suite asserts the `500` and the unreachable handler `404`; frontend suites through B2, B5 and B6 |
| C3 | `POST /tweets/{tweet_id}/responses` | none | backend integration suite; B3, B5 and B6 exist because the backend implements the route |
| C4 | `POST /generate-response` | A6, A7 | no backend coverage is possible — the path is not routed under any base. Its `404` is asserted through B5 and B6, and by the backend route-surface census |
| C5 | `/users…`, `/analytics…`, `/config…` | none | the routers are empty; their `404` responses are asserted by the backend route-surface suite against the real application, not by any msw handler |
| C6 | `/undefined/…` — the prefix every emitted request carries | A1–A8, all of them | no route exists to cover: the backend route-surface suite asserts the `404` and the `{"detail":"Not Found"}` body for all four emitted paths, with and without a query string, and that no declared route lives under the prefix; the frontend asserts the same values through B5 |

## §D Divergence → the suite obliged to assert it

Each row is a difference between what the frontend emits or expects and what the backend does. None is
corrected in production: the two authorised production touches do not cover any of them, and implementing
the missing behaviour is out of scope. Each is therefore an assertion obligation.

| # | Divergence | Where it is visible | Obligation |
|---|------------|---------------------|------------|
| X1 | `page` is not a declared backend parameter, so `GET /tweets` ignores it | `services/api.ts` line 8 vs `routes/tweets.py` line 12 | the API service suite asserts the exact emitted URL; the handler-contract suite asserts a request carrying `page=undefined` is unaffected by it; the backend integration suite asserts the route's `skip`/`limit` semantics separately |
| X2 | `skip`, the parameter the backend paginates on, is never sent | same | the backend integration suite asserts `skip` from the server side; no frontend test may claim pagination works |
| X3 | `limit` reaches the backend as the literal string `undefined`, which fails `int` coercion | `twitterService.getLatestTweets` passes one argument to the two-parameter `fetchTweets` | the twitterService suite asserts the emitted `limit=undefined`, and — under a configured base — the resulting `422` body **with and without** the `get_db` override, because coercion precedes the endpoint; the handler-contract suite asserts the multi-parameter form in declaration order; the backend integration suite asserts both server-side |
| X4 | `page` also reaches the backend as `undefined` from the Dashboard | `components/Dashboard` line 10 calls `getLatestTweets()` with no argument | the Dashboard component suite asserts the emitted query, and that the mount fetch and the 30 s interval both emit it |
| X5 | `Tweet.id` is read on a pydantic model that declares no `id`, so both tweet-detail routes raise | `routes/tweets.py` lines 18 and 27 | the backend integration suite asserts `500` with `TestClient(app, raise_server_exceptions=False)` and `pytest.raises` with the default client |
| X6 | the `404` branch of `GET /tweets/{tweet_id}` is unreachable because X5 raises first | `routes/tweets.py` lines 19–20 | the backend integration suite documents the branch as unreachable; no handler models it |
| X7 | `twitterService` declares its own `Tweet` as `{id, text}` while both the backend and the frontend schema use `{tweet_id, content, …}`, and nothing transforms between them | `services/twitterService.ts` lines 3–8 | the twitterService suite asserts the values actually returned, not the declared interface |
| X8 | `POST /generate-response` does not exist; the nearest implemented route is `POST /tweets/{tweet_id}/responses` | `services/api.ts` line 22 | the API service suite treats the route as a frontend-isolation contract only; the llmService suite asserts the `404` through B5, and the handler-contract suite asserts it survives configuring the base URL |
| X9 | that route takes its id from a JSON body and reads the reply under `generatedResponse`, where the implemented route takes a path parameter and returns `response` | `services/api.ts` lines 23–24 vs `routes/tweets.py` line 36 | the API service suite asserts the emitted body and the unwrapped key |
| X10 | `llmService.generateTweetResponse` discards the original error and rethrows `Error('Failed to generate tweet response')` | `services/llmService.ts` line 12 | the llmService suite asserts that exact message, so the `404` cause is provably lost |
| X11 | no module requests `POST /tweets/{tweet_id}/responses`, so the backend's only write-shaped route has no frontend caller | absence in `frontend/src/services/` | recorded here; no frontend suite may imply the route is exercised from the UI |
| X12 | `frontend/src/schema/tweetSchema.ts` types `timestamp` as `z.date()`, which no JSON payload can satisfy, while the wire value is an ISO-8601 string | `schema/tweetSchema.ts` vs the serialised handler payloads | the tweetSchema suite asserts that a string `timestamp` is rejected; `makeDefaultTweetsJson()` is the value the service suites compare against |
| X13 | `GET /tweets` cannot answer `200` as assembled: `get_tweets` calls `db.query(Tweet)` on the Firestore `Client` that `get_db` yields, and that client has no `query`, so a routed request that passes coercion answers `500` until a test replaces the dependency | `routes/tweets.py` line 12 vs `db/firestore.py` `get_db` | a suite installing B6 asserts the unoverridden `500`; the pagination contract is asserted only through B7, under `app.dependency_overrides[get_db]` with a SQLAlchemy-shaped fake, and no suite may present that `200` as the assembled application's behaviour. The `422` is deliberately **not** on this row: it is returned under either disposition, which the handler-contract and twitterService suites both assert |
| X14 | the slash redirect's absolute `location` is built from the unvalidated `Host` request header, and no middleware refuses a value: `POST /tweets/` with `Host: attacker.example` answers `307` to `http://attacker.example/tweets`, and `attacker.example/evil` reaches the `location` path as well. The request-level face of GHSA-86qp-5c8j-p5mr / CVE-2026-48710 on the pinned starlette 0.27.0 | `app/main.py` line 41 adds `CORSMiddleware` and nothing else, so no `TrustedHostMiddleware` stands between the request and starlette's router | the backend route-surface suite asserts nine `Host` spellings reflected into the `location`, that none is refused, that the origin tracks the header rather than the client's base URL, and that the middleware set is exactly `{CORSMiddleware}`; installing the mitigation is a production change outside the two authorised touches (D145) |
| X15 | a tweet id carrying path syntax silently retargets the request: `fetchTweetById('tweet 1/../7')` interpolates the id verbatim, and the URL parser then removes the preceding segment, so the network receives `/undefined/tweets/7` and the caller is answered with whatever that path returns | `services/api.ts` line 14 interpolates the id with neither validation nor `encodeURIComponent` | the API service suite asserts three observation points - the pre-adapter string against a mocked `axios`; the normalised pathname over the real adapter, where the `200` and the returned record are the isolation fixture's rather than the backend's; and the same call under a configured base, where the retargeted path is `/tweets/7`, a path the backend routes, so the substitution selects a real route. The id is not encoded or repaired on production's behalf (D149) |
| X16 | `REACT_APP_API_BASE_URL` is unset and interpolated without a fallback, so every request the application emits carries the literal path prefix `/undefined` — a prefix no router declares. The whole client surface is therefore unrouted and answers `404 {"detail":"Not Found"}`, before any query value is coerced and before `Depends(get_db)` resolves | `services/api.ts` line 5 vs `app/main.py`, which mounts its populated router at the root with no prefix | the backend route-surface suite asserts the `404`, the body and the JSON content type for all four emitted paths, that the status is unchanged by a well-formed or malformed query string, and that no declared route lives under the prefix; the frontend handler-contract suite asserts the same values through B5; and each of the three service suites asserts the `404` its own subject receives. Every route's own behaviour is asserted separately under a configured base, and no suite presents a configured-base outcome as what the application does today |

## §E Legacy suite migration

The three legacy modules — `backend/tests/test_api.py` (86 lines), `test_services.py` (62) and
`test_tasks.py` (68) — held 25 test functions, six with empty bodies, and all three failed at collection:
`test_api.py` imported `app.main` (unresolvable until the routes package existed) and additionally could not
be parsed, `test_services.py` imported a root `services`, and `test_tasks.py` imported a root `backend`. Net
executed assertions: zero. All three are deleted; every function is dispositioned below. The reasoning is
`DECISION-LOG.md` §6.

**Disposition counts: 7 rewritten, 3 skipped with a reason, 15 removed with a reason.**

### §E.1 Legacy function → its replacement

| # | Legacy module | Legacy function | Disposition | Replacement, or the reason there is none |
|---|---------------|-----------------|-------------|------------------------------------------|
| E1 | `test_api.py` | `test_create_tweet` — `POST /tweets/` expecting 201 | REMOVED | No `POST /tweets/` exists; the implemented write-shaped route is `POST /tweets/{tweet_id}/responses`, and no endpoint accepts a request body. Creating one would be implementing a missing product feature. |
| E2 | `test_api.py` | `test_get_tweet` — `GET /tweets/1` expecting 200 with `content` | REWRITTEN | `tests/integration/test_http_tweets.py`, which asserts what the route really does: it reads `Tweet.id` on a pydantic model that declares none, so it raises and answers **500**, and its 404 branch is unreachable (§D X5, X6; §G G5). |
| E3 | `test_api.py` | `test_delete_tweet` — `DELETE /tweets/1` expecting 204 | REMOVED | No `DELETE` route exists on any path. |
| E4 | `test_api.py` | `test_create_user` — `POST /users/` expecting 201 | REMOVED | `users.py` declares a bare `APIRouter()` with no endpoint; the path answers 404, asserted once in `tests/integration/test_route_surface.py`. |
| E5 | `test_api.py` | `test_get_user` — `GET /users/1` expecting 200 | REMOVED | Same as E4. |
| E6 | `test_api.py` | `test_update_user` — `PUT /users/1` expecting 200 | REMOVED | Same as E4. |
| E7 | `test_api.py` | `test_get_tweet_analytics` — `GET /analytics/tweets` expecting `total_tweets` | REWRITTEN | The route does not exist (404, asserted in `test_route_surface.py`), but the intent — aggregate tweet analytics — is covered at the layer that implements it: `tests/unit/test_services_analytics.py` asserts `get_tweet_analytics`'s `total_tweets`, `avg_daily_tweets`, `avg_retweets`, `avg_favorites` and `daily_breakdown` against controlled `run_query` rows. |
| E8 | `test_api.py` | `test_get_user_analytics` — `GET /analytics/users` expecting `total_users` | REWRITTEN | Route absent as in E7; the intent is covered by `test_services_analytics.py` against `get_user_analytics`, which returns `total_active_users` — the legacy key `total_users` was wrong independently of the missing route. |
| E9 | `test_api.py` | `test_get_config` — `GET /config` expecting `max_tweet_length` | REMOVED | `config.py` declares a bare `APIRouter()`; the path answers 404 (asserted in `test_route_surface.py`), and no `max_tweet_length` setting exists anywhere. |
| E10 | `test_api.py` | `test_update_config` — `PUT /config` expecting 200 | REMOVED | Same as E9. The design documents specify `PATCH` rather than `PUT`, so the legacy method was also wrong; both are moot. |
| E11 | `test_api.py` | `test_unauthorized_access` — expecting 401 from `POST /tweets/` | REMOVED | No route is protected: no dependency in `app/api/routes/` requires authentication, and no token endpoint exists. The 401 paths that *do* exist are in `app/api/dependencies.py` and are asserted directly by `tests/unit/test_api_dependencies.py`. |
| E12 | `test_api.py` | `test_authorized_access` — empty body | REMOVED | Empty, and its subject (an authentication mechanism) is unimplemented. Not converted to a skip because E11 already records the absence of route-level auth. |
| E13 | `test_services.py` | `test_fetch_tweets` — empty body, `TwitterService.fetch_tweets` | REMOVED | Neither `TwitterService` nor `fetch_tweets` exists. `app/services/twitter_service.py` exposes `TwitterStreamListener` and `start_twitter_stream` only, both covered by `tests/unit/test_services_twitter.py`. |
| E14 | `test_services.py` | `test_process_tweets` — `TwitterService.process_tweets` | REMOVED | Same subject as E13; no such class or method. |
| E15 | `test_services.py` | `test_generate_response` — patched `services.llm_service.openai.Completion.create` | REWRITTEN | `tests/unit/test_services_llm.py`, keeping the mocking idiom with a corrected target: the module does `from openai import Completion`, so the patch target is `app.services.llm_service.Completion.create`. Covers all five verified outcomes of `generate_response`. |
| E16 | `test_services.py` | `test_process_sentiment` — `assertIn(sentiment, ["positive","negative","neutral"])` | REMOVED | `process_sentiment` does not exist, and the assertion has no oracle: it passes for any implementation. |
| E17 | `test_services.py` | `test_calculate_engagement_rate` — `0 <= rate <= 1` | REMOVED | `AnalyticsService.calculate_engagement_rate` does not exist, and the assertion has no oracle. |
| E18 | `test_services.py` | `test_generate_report` — empty body | REMOVED | No report-generation function exists in `app/services/analytics_service.py`, which exposes `get_tweet_analytics` and `get_user_analytics` only. |
| E19 | `test_tasks.py` | `test_process_tweet` — patched `backend.tasks.save_tweet_to_db` | REWRITTEN | `tests/unit/test_tasks_tweet_processor.py`. `process_tweet` maps to `TweetStreamListener.on_status`; `save_tweet_to_db` maps to `app.db.firestore.add_tweet`. The suite drives a parametrised popularity matrix and asserts both the return value and `add_tweet.call_count`. |
| E20 | `test_tasks.py` | `test_generate_response` — patched `get_tweet_from_db`, `generate_ai_response`, `save_response_to_db` | REWRITTEN | `tests/unit/test_tasks_response_generator.py`. `get_tweet_from_db` → `app.db.firestore.get_tweet`; `generate_ai_response` → `app.services.llm_service.generate_response`; `save_response_to_db` has **no production equivalent** — `add_response` is imported by `response_generator` but defined nowhere, and is supplied as a conftest shim (§F F5, §G G8). |
| E21 | `test_tasks.py` | `test_process_tweet_error_handling` — expects an exception to propagate | REWRITTEN | `test_tasks_tweet_processor.py` preserves the error-disposition intent, asserting what production actually does: a status clearing the popularity gate raises a pydantic `ValidationError` with eight field errors, and `add_tweet` is never called on any path. |
| E22 | `test_tasks.py` | `test_generate_response_error_handling` — expects an exception to propagate | REWRITTEN | `test_tasks_response_generator.py`: a falsy `get_tweet` raises `ValueError("Tweet with id … not found")`, and a dict result raises `TypeError: object dict can't be used in 'await' expression` because `firestore.get_tweet` is synchronous. |
| E23 | `test_tasks.py` | `test_process_tweet_with_media` — empty body | SKIPPED | `pytest.mark.skip` naming the unimplemented feature: no media handling exists anywhere in `app/`. |
| E24 | `test_tasks.py` | `test_generate_response_rate_limiting` — empty body | SKIPPED | `pytest.mark.skip` naming the unimplemented feature: no rate-limiting logic exists anywhere in `app/`. |
| E25 | `test_tasks.py` | `test_process_tweet_deduplication` — empty body | SKIPPED | `pytest.mark.skip` naming the unimplemented feature: no deduplication logic exists anywhere in `app/`. |

### §E.2 Replacement suite → the legacy functions it absorbs

| Replacement | Absorbs | Also covers, with no legacy antecedent |
|-------------|---------|----------------------------------------|
| `tests/integration/test_http_tweets.py` | E2 | `GET /tweets` happy path through `dependency_overrides`; `POST /tweets/{id}/responses`; the unreachable-404 assertion in both `pytest.raises` and `status_code == 500` form |
| `tests/integration/test_route_surface.py` | the 404 half of E4–E6, E7–E10 | the absence of `API_V1_STR` prefixing on every implemented route |
| `tests/unit/test_services_llm.py` | E15 | the `AttributeError` a real `Tweet` produces, the swallowed-failure fallback string, and the `IndexError` an empty `choices` list produces outside the `try` |
| `tests/unit/test_services_analytics.py` | E7, E8 | empty-result-set `KeyError`s, the interpolated `BETWEEN` clause, the three date ranges the subject neither validates nor neutralizes — inverted, malformed, and one carrying SQL metacharacters (D144) — and exception propagation |
| `tests/unit/test_services_twitter.py` | E13, E14 | `TwitterStreamListener` behaviour and the `NameError` that makes `start_twitter_stream` dead code |
| `tests/unit/test_tasks_tweet_processor.py` | E19, E21 | the exact `stream.filter(track=…)` kwargs with `tweepy` patched, and `DOUBT_RATING_THRESHOLD` as a constant with no gate behind it |
| `tests/unit/test_tasks_response_generator.py` | E20, E22 | the `process_pending_responses` keyword `TypeError` |
| `tests/unit/test_api_dependencies.py` | E11 | both 401 paths, the discarded original exception, and the unused `get_db` import |

## §F Test artifact → the construct it covers

Every file in this milestone's scope. "Production construct" names what the artifact exercises or unblocks;
an artifact that covers infrastructure rather than a production symbol says so.

| # | Artifact | Covers |
|---|----------|--------|
| F1 | `backend/pytest.ini` | Single `app.*` import root (`pythonpath = .`), `testpaths`, `asyncio_mode`, strict markers, the two warning filters, JUnit XML, and the correlated log formats |
| F2 | `backend/requirements-dev.txt` | The pinned runtime and test stack the suite executes against |
| F3 | `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/integration/__init__.py` | Package markers; `backend/app/` deliberately stays a PEP 420 namespace tree |
| F4 | `backend/tests/conftest.py` — module prologue | `app/core/config.py`'s module-scope `Settings()` and the eight fields it declares without a default; `app/core/security.py`'s missing `Optional` import; ambient `google.auth.default` resolution |
| F5 | `backend/tests/conftest.py` — shim fixtures | The five symbols production imports but never defines: `Optional`, `verify_token` (`app/api/dependencies.py`), `TwitterService` and `LLMService` (`app/api/routes/tweets.py`, `app/tasks/tweet_processor.py`), `add_response` (`app/tasks/response_generator.py`) |
| F6 | `backend/tests/conftest.py` — `block_network_access`, `neutralize_google_credentials` | Infrastructure: the demonstrated live-egress risk in `app/db/firestore.py` and the blocking `stream.filter` in both stream starters |
| F7 | `backend/tests/conftest.py` — `firestore_client`, `bigquery_settings` | `app/db/firestore.get_db`; `app/db/bigquery`'s class-attribute read of `Settings.GOOGLE_CLOUD_PROJECT`, which nothing else can unlock |
| F8 | `backend/tests/conftest.py` — `frozen_clock` | `app/core/security.create_access_token`'s hardcoded 15-minute default |
| F9 | `backend/tests/conftest.py` — correlation section | Infrastructure: per-test `test_id`/`correlation_id` on every log record |
| F10 | `backend/tests/factories.py` | The `Tweet` schema's ten fields, the analytics row shape both queries read, and the tweepy status duck type `on_status` consumes |
| F11 | `backend/tests/integration/conftest.py` | `app/main.py`'s wiring and lifecycle registration; the `dependency_overrides` identity contract on `app.db.firestore.get_db` |
| F12 | `backend/tests/unit/test_core_config.py` | `app/core/config.py`: both threshold constants, the eight required fields, the pydantic class-access `AttributeError`, and the four authorized testability fields |
| F13 | `backend/tests/unit/test_core_security.py` | `app/core/security.py`: bcrypt round trip, `UnknownHashError`, and every JWT expiry branch under a frozen clock |
| F14 | `backend/tests/unit/test_api_dependencies.py` | `app/api/dependencies.py`: `oauth2_scheme` and both 401 paths of `get_current_user` |
| F15 | `backend/app/api/routes/tweets.py` | Authorized production touch #1: the three existing endpoints, parameters reordered (`DECISION-LOG.md` D50–D51) |
| F16 | `backend/app/api/routes/{users,analytics,config}.py` | Authorized production touch #1: the module names `app/main.py` imports; each declares a bare router and no endpoint |
| F17 | `backend/app/core/config.py` | Authorized production touch #2: the four undeclared fields read at runtime (D52) |
| F18 | `frontend/package.json` | The Jest toolchain and the five imported-but-undeclared runtime packages |
| F19 | `frontend/jest.config.js` | Infrastructure: the dual transform, the twelve `moduleNameMapper` entries in four groups, the coverage denominator and gate, and the JUnit reporter that emits the canonical test identity — `/`-separated file as `classname`, ancestor titles and leaf title as `name` |
| F20 | `frontend/jest.transform.extensionless.js` | The four extension-less component **files** under `frontend/src/components/` |
| F21 | `frontend/src/test-utils/setup-jest.ts` | Infrastructure: jest-dom matchers, the removal of `REACT_APP_API_BASE_URL`, and the whole msw lifecycle — interception started at module scope, then `assertNoIsolationViolations()` followed by `server.resetHandlers()`, `resetHandlerState()` and the base-URL delete in one `afterEach` |
| F22 | `frontend/src/test-utils/msw-server.ts` | Infrastructure: the single `setupServer` instance per test file |
| F23 | `frontend/src/test-utils/handlers.ts` | The four routes `frontend/src/` requests, in an isolation layer and a current-behaviour layer, the latter split by dependency disposition for `GET /tweets`; §A–§D of this document |
| F24 | `frontend/src/test-utils/render.tsx` | `src/store/tweetSlice.ts` and `src/store/configSlice.ts` default reducers, and the router context the components need |
| F25 | `frontend/src/test-utils/factories.ts` | The two zod schemas, which validate it in turn |
| F26 | `frontend/src/test-utils/stubs/analyticsService.ts` | `@/services/analyticsService`, imported by `src/components/Analytics` and non-existent |
| F27 | `frontend/src/test-utils/stubs/configService.ts` | `@/services/configService`, imported by `src/components/Configuration` and non-existent |
| F28 | `frontend/src/test-utils/stubs/configSchema.ts` | `../schema/configSchema`, imported by `src/store/configSlice.ts` and non-existent |
| F29 | `e2e/package.json` | The pinned Playwright, Vite and plugin-react versions, and every documented E2E command |
| F30 | `e2e/harness-origin.ts` | Infrastructure: the one clone-specific origin both the server and the runner read |
| F31 | `e2e/playwright.config.ts` | Infrastructure: spec discovery, the owned `webServer`, artifact retention and both reporters |
| F32 | `e2e/vite.harness.config.ts` | The four extension-less component files (virtual ids), the three non-existent specifiers (stubs), the three undeclared exports (compat), the three bare specifiers (aliases), and the three API paths the mounted components request — answered `503` `harness-api-not-intercepted` unless a spec intercepted them (H13) |
| F33 | `e2e/harness/index.html` | The HTML entry the repository does not have |
| F34 | `e2e/harness/main.tsx` | The four routed components over a **valid** store; deliberately not `src/app.tsx` |
| F35 | `e2e/harness/stubs/analyticsService.ts` | `@/services/analyticsService` for the harness, holding `TrendCharts` on its caught-failure path via `UnrenderableTrendSeriesError`, and rejecting a drifted fixture separately as `TrendSeriesContractError` |
| F36 | `e2e/harness/stubs/configService.ts` | `@/services/configService` for the harness |
| F37 | `e2e/harness/stubs/configSchema.ts` | `../schema/configSchema` for the harness |
| F38 | `e2e/fixtures/trends.json` | The trend series payload the analytics route requests |
| F39 | `.gitignore` | Infrastructure: every artifact the four suites produce, each rule reaching no further than the location that produces it |
| F40 | `docs/testing/DECISION-LOG.md` | Rule 1: the rationale behind every contestable choice |
| F41 | `docs/testing/TRACEABILITY-MATRIX.md` | Rule 1: this document, including the 25-function migration in §E |
| F42 | `backend/tests/unit/test_schema.py` | `app/schema/tweet.py` — ten declared fields, nine required, `quoted_tweet_id` nullable-not-optional — and `app/schema/user.py`'s five required fields; `Extra.ignore` dropping an undeclared keyword; the seven names `Tweet` does not declare, which are what four production failures rest on; and `make_tweet()` in `backend/tests/factories.py`, which this suite validates |
| F43 | `backend/tests/unit/test_db_firestore.py` | `app/db/firestore.py` — `add_tweet` returning element 1's `id`, `get_tweet` returning `None` for a missing document, `update_tweet` returning `False` on a silently swallowed write failure, the module-level `db`, the absent `add_response`, and `get_tweet` being synchronous (the fact the response-generator `TypeError` rests on) |
| F44 | `backend/tests/unit/test_db_bigquery.py` | `app/db/bigquery.py` — the two **class**-attribute reads of `Settings.GOOGLE_CLOUD_PROJECT` that make all three functions raise as shipped, then `get_bq_client`, `run_query` and `insert_tweet_analytics` under the `bigquery_settings` stand-in, including the `True`/`False` return discipline, the `print` on the errors-returned path and the propagated raise |
| F45 | `backend/tests/unit/test_services_llm.py` | `app/services/llm_service.py` `generate_response` across all five outcomes its `try` boundary admits, the swallowed API failure versus the propagated `IndexError`, the lower-case `settings.openai_engine` read that can never resolve, and the absent `LLMService` class the conftest shim stands in for |
| F46 | `backend/tests/unit/test_services_twitter.py` | `app/services/twitter_service.py` — `TwitterStreamListener.on_status`'s nine-error `ValidationError`, `start_twitter_stream`'s two terminal states (`AttributeError` on the undeclared consumer fields, then `NameError` on the unimported `tweepy`), and the absent `TwitterService` class with the three method names the legacy suite asserted |
| F47 | `backend/tests/unit/test_services_analytics.py` | `app/services/analytics_service.py` — both aggregations' five returned keys, the numeric reductions, the `to_dict('records')` daily breakdown, the interpolated `BETWEEN` clause and dataset, the empty-set `KeyError`s, total propagation, the unvalidated inverted range, and the absence of `total_users` and `AnalyticsService` |
| F48 | `backend/tests/unit/test_tasks_tweet_processor.py` | `app/tasks/tweet_processor.py` — the `POPULARITY_THRESHOLD` boundary matrix on the sum of both counts, the eight-error `ValidationError` above the gate, `add_tweet`'s call count of zero on every path, `start_tweet_stream`'s tweepy wiring and `track` keywords, and `Settings.DOUBT_RATING_THRESHOLD` being read by no production module |
| F49 | `backend/tests/unit/test_tasks_response_generator.py` | `app/tasks/response_generator.py` — the `ValueError` for a missing tweet, the `TypeError` from awaiting the synchronous `firestore.get_tweet`, `process_pending_responses`'s unexpected-keyword `TypeError`, and both functions being coroutine functions |
| F50 | `backend/tests/integration/test_http_tweets.py` | `app/api/routes/tweets.py` — `GET /tweets` with its declared `skip`/`limit` defaults, an empty result set and a response-model failure; and the `Tweet.id` `AttributeError` that makes `GET /tweets/{tweet_id}` and `POST /tweets/{tweet_id}/responses` answer 500 with their 404 guard unreachable |
| F51 | `backend/tests/integration/test_route_surface.py` | The assembled route table of `app/main.py` — seven routes of which three are the application's own, the three bare routers, the 404 census for `/users`, `/analytics`, `/config`, `/health` and `/token`, the unused `API_V1_STR` prefix, the census of the four paths the frontend actually emits under the `/undefined` prefix (X16) including that a query string does not change the outcome and that no declared route lives under it, `HEAD` behaviour on `APIRoute` versus `Route`, and the absent request-body (and therefore 422) surface |
| F52 | `backend/tests/integration/test_app_lifecycle.py` | `app/main.py`'s assembly — `configure_cors` over the empty `ALLOWED_ORIGINS`, the single `CORSMiddleware` entry and its four options, `include_routers` wiring four modules of which three contribute nothing, the framework-default `title`, the second independent `Settings()`, and the startup/shutdown handlers registered but never run |
| F53 | `frontend/src/utils/formatUtils.test.ts` | `src/utils/formatUtils.ts` — `formatNumber`'s thousands grouping, preserved leading minus and mangled fractional output, and both branches of `truncateText` at the `maxLength` boundary |
| F54 | `frontend/src/utils/dateUtils.test.ts` | `src/utils/dateUtils.ts` — `formatDate`'s delegation to dayjs across a date-only pattern, a date-and-time pattern and a numeric input, and all six `getTimeAgo` arms with both sides of every plural ternary under a frozen clock |
| F55 | `frontend/src/schema/tweetSchema.test.ts` | `src/schema/tweetSchema.ts` — the ten-field contract, `z.date()` rejecting the wire-form string an API would return, `quoted_tweet_id` nullable-not-optional, and unknown-key stripping; and `makeTweet()` in `src/test-utils/factories.ts`, which this suite gates |
| F56 | `frontend/src/schema/userSchema.test.ts` | `src/schema/userSchema.ts` — all five fields required, `created_at` as `z.date()` rejecting an ISO string, and unknown-key stripping; and `makeUser()` in `src/test-utils/factories.ts` |
| F57 | `frontend/src/store/tweetSlice.test.ts` | `src/store/tweetSlice.ts` — the initial state, `addTweet`, `updateTweet`'s index-0 overwrite on a shape with no `id`, and the thunk's `pending`/`fulfilled`/`rejected` transitions including the `api`-is-undefined rejection that never reaches a transport |
| F58 | `frontend/src/store/configSlice.test.ts` | `src/store/configSlice.ts` — `updateConfig`'s top-level-only merge and its reset of `error`, and `setError`'s status transition |
| F59 | `frontend/src/store/index.test.ts` | `src/store/index.ts` — the two reducer names neither slice exports, the `combineReducers` reports on `console.error`, construction succeeding anyway, `getState()` returning `{}`, a dispatched slice action changing nothing, and the module's two exports |
| F60 | `frontend/src/services/api.test.ts` | `src/services/api.ts` — the literal `undefined/` base URL, the URL each of the three functions constructs, the `response.data.generatedResponse` unwrap, rejections reaching the caller untransformed, the `404` each emitted request actually receives, and — under a configured base — the route-level `500` a validly-parameterised collection request and a tweet-detail request both reach |
| F61 | `frontend/src/services/twitterService.test.ts` | `src/services/twitterService.ts` — `getLatestTweets` calling the two-parameter `fetchTweets` with one argument, `getTweetDetails`, the log-then-rethrow-the-original disposition, the `404` both subjects receive today, and — under a configured base — the `422` the one-argument call earns under either `get_db` disposition versus the route-level `500` the detail call reaches |
| F62 | `frontend/src/services/llmService.test.ts` | `src/services/llmService.ts` `generateTweetResponse` — the verbatim pass-through on success, and the log-then-throw-a-replacement disposition that discards the original error |
| F63 | `frontend/src/components/Dashboard.test.tsx` | `src/components/Dashboard` `RealTimeFeed` — the heading, the argument-less mount fetch, the 29,999-versus-30,000 ms poll boundary, `clearInterval` on unmount, and the undefined `TweetCard` ceiling |
| F64 | `frontend/src/components/TweetManagement.test.tsx` | `src/components/TweetManagement` `TweetList` — the empty `.tweet-list` container, the exact `getTweets is not a function` log, the swallowed failure that leaves the component mounted, and the scroll handler's equality condition |
| F65 | `frontend/src/components/Analytics.test.tsx` | `src/components/Analytics` `TrendCharts` — the heading, `canvas#trendChart`, the `dateRange` handed to `getTrendData`, and the caught chart-construction failure that leaves the component mounted (the unreachable chart branch of §G) |
| F66 | `frontend/src/components/Configuration.test.tsx` | `src/components/Configuration` `TwitterAPISettings` — the four labelled controlled inputs, the exact object handed to `updateTwitterAPIConfig` on submit, and the alert on both dispositions |
| F67 | `frontend/src/test-utils/jest-transform-extensionless.test.ts` | Infrastructure: the output contract of `frontend/jest.transform.extensionless.js` — the emitted map naming the real extension-less file, the synthetic name appearing nowhere, CommonJS with the automatic JSX runtime, and mappings and source text carried through |
| F68 | `frontend/src/test-utils/setup-jest.test.ts` | Infrastructure: the per-test isolation contract of `frontend/src/test-utils/setup-jest.ts` — the frozen allowed-origin list, and the ledger, runtime handler array and request log each proven reset between tests by an ordered pair |
| F69 | `e2e/fixtures/tweets.json` | The tweet payload a spec fulfils `**/undefined/tweets*` with, in the ten-field wire form with ISO-string timestamps |
| F70 | `blitzy-deck/references/blitzy-reveal-theme.css` | Rule 4: the canonical theme path the executive deck loads — palette, typography, the four slide types, the component classes, the Mermaid container and the table styles |
| F71 | `frontend/src/test-utils/junit-correlation.test.ts` | Infrastructure: the canonical test identity — the `jest-junit` templates in `frontend/jest.config.js` and `currentTestId()` in `frontend/src/test-utils/handlers.ts`, held to one form |
| F72 | `frontend/.npmrc`, `e2e/.npmrc` | Infrastructure: the no-committed-lockfile decision, suppressed at source rather than ignored |
| F73 | `frontend/src/test-utils/dependency-closure.test.ts` | Infrastructure: the npm counterpart of `backend/tests/test_dependency_closure.py`. Covers no production symbol - it asserts `frontend/package.json` as a partition of the eleven test devDependencies this work owns (exact pin, the version the plan names, installed at exactly it) and the seventeen declarations it may not change (byte-identical to the frozen baseline specifier, installed at a version that specifier admits), that the partition is exhaustive and disjoint, that `e2e/package.json` declares exact versions throughout, and that `.gitignore` carries no active `package-lock.json` rule |
| F74 | `frontend/src/test-utils/handlers.test.ts` | Infrastructure: the response contract of `frontend/src/test-utils/handlers.ts`' two layer-2 factories, held to the values measured against the assembled application - the four-route `404` census under the emitted base, `404` regardless of query values, the single and multi-parameter `422` bodies in declaration order, the accepted and refused coercion forms, the unoverridden `500` and overridden `200`, the `/generate-response` `404` under either base, the recorded base per disposition, and that a request under a prefix no layer names is left unmatched, ledgered and never performed |
| F75 | `frontend/src/test-utils/configured-base.ts` | Infrastructure: the one place a suite re-imports its subject with `REACT_APP_API_BASE_URL` set, so the module-scope read in `src/services/api.ts` line 5 picks it up - the precondition for every configured-base assertion in §A and §D |

## §G Coverage ceiling → the assertion that stands in for it

Branches no test can execute without changing production. Each is asserted as current behaviour rather
than chased; `DECISION-LOG.md` §7 records how the gates are scoped around them.

| # | Ceiling | Why it cannot be executed | What is asserted instead |
|---|---------|---------------------------|--------------------------|
| G1 | `frontend/src/app.tsx` cannot be mounted | Imports the invalid store, imports a never-exported `setupInterceptors`, and default-imports a named-only export | Excluded from `collectCoverageFrom`; the E2E harness declares its own route table instead |
| G2 | Three of the four `src/pages/*.tsx` modules cannot mount | `useAppDispatch`/`useAppSelector` are imported from `src/store/index.ts`, which exports neither | A test per page, three of them skipped with a reason naming the missing hook |
| G3 | The tweet-rendering branch of both list components | `TweetCard` is imported by `Dashboard` and by `TweetManagement` **from itself**, and defined nowhere | The empty-collection render, plus the `Element type is invalid … got: undefined` failure confirmed in a real browser and recorded here |
| G4 | Chart construction in `src/components/Analytics` | The tree-shakeable `{ Chart }` is imported and `Chart.register` is never called, so construction throws in any environment with a canvas | The caught-failure path: heading and canvas render, the rejection is logged, the component stays mounted |
| G5 | The 404 branch of `GET /tweets/{tweet_id}` | `Tweet.id` is read on a pydantic model that declares no `id`, so it raises first | HTTP 500 via `raise_server_exceptions=False`, and the raised `AttributeError` via `pytest.raises` |
| G6 | A 422 for an invalid request body | No implemented endpoint accepts a request body | Recorded as a gap; the 422 that *is* reachable comes from query coercion on `GET /tweets` |
| G7 | The `DOUBT_RATING_THRESHOLD` gate | The constant is referenced by no production code anywhere | The constant's value, plus this record that no gate consumes it |
| G8 | `start_twitter_stream` past its first `tweepy` reference, and `add_response` | The module imports only `StreamListener`, `OAuthHandler` and `API`, so `tweepy.Stream` raises `NameError`; `add_response` is imported by `response_generator` but defined nowhere | The `NameError` itself, and a conftest shim for `add_response` recorded as a divergence |


## §H Harness guarantee → the artifact that enforces it

§A–§D map the mock to the application. This section maps the properties the suites *rest on* — no real
credential, no real host, no shared state, no unpinned dependency — to the file that enforces each one and to
the observation that showed it working. Every row is traversable in both directions: from a guarantee to its
artifact, and from each artifact to the guarantee it exists for.

| # | Guarantee | Artifact that enforces it | How it was verified | Reasoning |
|---|-----------|---------------------------|---------------------|-----------|
| H1 | Every version the backend manifest pins is the version actually installed | `backend/requirements-dev.txt` (pins) and `backend/tests/test_dependency_closure.py` (a parametrised assertion per `==` pin, plus a guard that the pin list is non-empty) | 25 pins asserted against `importlib.metadata.version`, all matching; the environment satisfies the manifest offline (`uv pip install --dry-run --offline -r backend/requirements-dev.txt` reports no changes) and `uv pip check` reports every installed package compatible. Negatively validated in the direction that matters: with `python-jose` pinned at the AAP's `3.3.0` while `3.5.0` was installed, the gate failed with a message naming the distribution, the pin and the installed version - which is how that drift was found | D101, D144 |
| H2 | No ambient credential or setting reaches the code under test; the `Settings` singleton holds synthetic values | `backend/tests/conftest.py` module prologue (unconditional assignment of the eight required fields, removal of every defaulted and undeclared name) and the session-scoped `verify_settings_singletons` | A run with ambient `SECRET_KEY`, `POPULARITY_THRESHOLD=5` and `NOTION_API_KEY` exported passed 53 tests and reported no leak. Negatively validated: restoring `os.environ.setdefault` with an ambient `SECRET_KEY` made every test in `test_core_security.py` error through the singleton assertion | D104, D118, D119 |
| H3 | The pytest process is left exactly as it was found — no seeded variable, no credential path, no injected builtin, no replaced log-record factory survives | `backend/tests/conftest.py` `pytest_unconfigure`: environment snapshot restored, the Google credential patch stopped, `builtins.Optional` deleted when it was originally absent, the egress guard released, and the base log-record factory reinstalled | The ambient-environment run above observed the managed variables back at their pre-run values and `builtins.Optional` absent afterwards; an in-process probe confirmed `logging.getLogRecordFactory()` is the original again once the session ends | D104, D135 |
| H4 | No backend test reaches the network — including during collection, inside a fixture, and after a fixture has been released — and no loopback port this process did not bind | `backend/tests/conftest.py` `_EgressGuard`, installed as the last step of the module prologue and released only in `pytest_unconfigure`: DNS resolvers, `connect` / `connect_ex` / `sendto`, `create_connection`, the gRPC channel factories, the Windows proactor connect paths, and network-capable child processes while a test runs; loopback is admitted only for AF_UNIX, a portless target, or a port recorded by the `socket.socket.bind` wrapper | 32 probes. `app.db.firestore.add_tweet({})` refused; a literal-IP async connect refused with no lookup involved; a collection-time `socket.create_connection(('firestore.googleapis.com', 443))` refused with `UnmockedNetworkAccessError`; `TestClient` and `socket.socketpair` still work, a listener this process bound is still connectable, and a **foreign** loopback port (4173) is refused through `connect`, `create_connection` and `sendto` alike | D25, D105, D121 |
| H5 | A production symbol that does not exist can never authorize a request or silently succeed | `backend/tests/conftest.py` `MISSING_SYMBOLS` fail-closed sentinels for `verify_token`, `TwitterService`, `LLMService` and `add_response`, written into the defining module and every loaded consumer and restored over any per-test replacement | `tests/unit/test_api_dependencies.py::test_get_current_user_is_fail_closed_without_a_patch` asserts `MissingProductionSymbolError` with no patch installed; the two 401 assertions still hold with the shim patched explicitly. The obsolete parallel symbol table that described the same four symbols a second way is deleted, so only this mechanism exists | D21, D22, D106, D134 |
| H6 | No integration test inherits another's dependency overrides, and no `TestClient` outlives its test | `backend/tests/integration/conftest.py`: `client` and `client_no_raise` as yield fixtures that `close()`, and an autouse fixture clearing `app.dependency_overrides` before and after every test | A probe installing an override directly — not through the opt-in fixture — confirmed it does not reach the next test | D107 |
| H7 | No frontend request escapes to a real host, including one issued while a test module is still being evaluated | `frontend/src/test-utils/setup-jest.ts` (`server.listen({ onUnhandledRequest })` at setup-module scope, `assertNoIsolationViolations()` then state reset in a global `afterEach`) and `frontend/src/test-utils/handlers.ts` (frozen `ALLOWED_REQUEST_ORIGINS`, no mutator, absolute per-origin patterns that also name their base path prefix in full, ledger entries for an out-of-scope origin) | 11 Jest assertions in `setup-jest.test.ts`, including one proving an import-time request is intercepted, one proving the allow-list cannot be widened (`push` throws), and one proving a request to a non-loopback origin matches no handler, is never performed, and lands in the ledger as `kind: 'unhandled-request'`. Negatively validated: moving `listen()` back into `beforeAll` made the module-scope probe report `ESCAPED AxiosError: Network Error` | D103, D108, D136 |
| H8 | Every dependency this testing work introduced is declared as an exact version and installed at exactly it; every declaration the work may **not** change is byte-identical to the frozen baseline and installed at a version that declaration admits; and no `.gitignore` rule can suppress the lockfile that would otherwise carry the integrity closure | `e2e/package.json` (exact pins throughout, 3 entries — a file this work created in full), `frontend/package.json` (the 11 test devDependencies pinned; the 7 runtime and 10 pre-existing development declarations left at their baseline ranges, which is the change boundary the frozen plan sets), `frontend/src/test-utils/dependency-closure.test.ts` (three partition cases, a pin-shape and an installed-version case per suite-owned entry, an unchanged-specifier and an admits-installed case per baseline entry, a non-empty guard per manifest, and a case asserting the absence of a `package-lock.json` ignore rule) and `.gitignore` (that rule removed) | 65 cases pass; `npm ls --depth=0` exits 0 in both packages with no invalid, missing or extraneous entry. Negatively validated three ways: re-pinning `axios` to `1.19.0` failed the unchanged-specifier case naming both strings, loosening `msw` to `^1.3.5` failed the exact-pin case, and adding an ungoverned devDependency failed the partition case. Not covered, deliberately: the transitive graph, for which no integrity-hashed reference exists without a lockfile, and an exact installed version for the baseline set, whose ranges legitimately admit a newer release | D109, D146, D147, D148, D171, D172 |
| H15 | A request addressed under a path prefix no layer names cannot be answered, so a mis-set or unconfigured base URL is a failure rather than a silent success | `frontend/src/test-utils/handlers.ts` (every pattern names its origin, its base path prefix and its route path in full — no wildcard segment anywhere — so an unnamed prefix reaches `onUnhandledRequest`) and `frontend/src/test-utils/handlers.test.ts` (the case that drives one) | A `GET http://localhost/api/v1/tweets` with the layer-2 set installed matched no handler, was recorded in the ledger as `kind: 'unhandled-request'`, never reached the request log, and failed the test through the shared `afterEach`. Negatively validated on the seam this replaced: with the router `404` turned into a `500`, 12 cases across the four affected suites failed | D169, D170 |
| H9 | The e2e browser cannot reach a non-harness origin, from a page, a popup or a worker | `e2e/playwright.config.ts` `launchOptions.args` (`--proxy-bypass-list=<-loopback>` plus the exact harness `host:port`, and a host-resolver rule excluding only the harness host, so Chromium's implicit all-loopback proxy bypass is removed) and `e2e/tests/harness-fixtures.ts` `noEgress` (context-wide abort with teardown attribution) | An in-page `fetch('https://api.openai.com/v1/models')` was blocked and named in the failing test's output as `1 request(s) outside the harness origin`; a `window.open` popup to the same URL landed on `chrome-error://chromewebdata/` with the URL recorded | D114, D128 |
| H10 | No Service Worker exists to make requests interception cannot see | `e2e/playwright.config.ts` `use.serviceWorkers: 'block'` | `navigator.serviceWorker.register(...)` returns `undefined`, `getRegistrations()` is empty, `controller` is `null`, and the blocking warning is emitted — Playwright implements the option by replacing `register` with a resolving stub (`playwright-core` `browserContext.js` line 110) | D114 |
| H11 | The harness dev server serves only the harness module graph, and refuses alternate Windows spellings of a path | `e2e/vite.harness.config.ts` `harnessFilesystemGuard` (raw and fully decoded screening for NTFS ADS syntax and 8.3 short names on every request path, allowed-root and deny-pattern checks on the resolved path) with `server.fs.strict`, `allow`, `deny`, `host: '127.0.0.1'` and `strictPort` | 13 cases, no failures: every legitimate `/@fs/` module 200 and every ADS, single-colon, percent-encoded, short-name, outside-root and `/__open-in-editor` attempt 403. Against the pre-fix guard, `/.env::$DATA` and `/.env::$DATA?raw` returned 200 with contents; both are 403 now. All four harness routes render | D110, D115 |
| H12 | The harness process and the browser both come from pinned local artifacts, no automated path can download a browser, and the server under test is always the one this configuration started | `e2e/playwright.config.ts` (`webServer.command` naming `node ./node_modules/vite/bin/vite.js`, `reuseExistingServer: false`, optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE`) and `e2e/package.json` (every script a local binary; `browsers:verify` a dry run; **no** `install:browsers` script, so no script reaches the downloader CVE-2025-59288 concerns) | The harness starts as `VITE v4.5.14` on `127.0.0.1:4173` with no `npx` involved; `npm run browsers:verify` exits 0 without fetching and reports the pre-verified `chromium-1117` install location; a repository-wide grep finds no remaining invocation of `playwright install` outside prose | D111, D112, D113, D129 |
| H13 | A spec that fails to intercept an API request its route needs cannot pass | `e2e/vite.harness.config.ts` (`HARNESS_API_SURFACE` answered `503` `harness-api-not-intercepted` with the required `page.route` snippet, never a success default) and `e2e/tests/harness-fixtures.ts` (the same request recorded in `unInterceptedApiRequests` and raised at teardown) | With all three intercepts removed, `/` was answered `503` on `GET /undefined/tweets`, the dev server logged the omission, and the test **failed at teardown naming the URL** — while its heading assertion still passed, which is why the ledger and not the status is what enforces this. With the intercepts installed, all four routes render and both ledgers are empty | D126, D131 |
| H14 | Every test a run publishes is identified uniquely, and by the same string in the report and in the request ledger | `frontend/jest.config.js` (`jest-junit` template functions: `/`-separated `{filepath}` as `classname` and suite name, ancestor titles plus leaf title as `name`, `ancestorSeparator` the single space Jest joins them with), `frontend/src/test-utils/handlers.ts` (`currentTestId`, stamped on every ledger entry and violation line) and `frontend/src/test-utils/junit-correlation.test.ts` (12 cases holding both to one form) | Over the whole 17-suite run, all 191 `<testcase>` elements carry distinct `classname`+`name` pairs and not one `classname` or suite name contains a backslash; the ledger entry of an intercepted request equals `currentTestId()` exactly. Against the pre-fix templates the same three service suites emitted 7 colliding identities out of 40 cases, and 11 of the 12 contract cases fail | D144, D145 |
