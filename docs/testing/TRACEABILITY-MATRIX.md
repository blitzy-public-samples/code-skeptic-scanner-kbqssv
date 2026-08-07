# Testing Traceability Matrix

Bidirectional mapping between the constructs the test suite covers and the implementations that cover them.
Every row is traversable in both directions: from a production construct to the test artifact that exercises
it, and from each test artifact back to the construct it stands for.

## Document coverage

| Section | Direction | Subject | Rows |
|---------|-----------|---------|------|
| §A | Frontend caller → backend route | Every HTTP request a module under `frontend/src/` issues, the route it reaches, the outcome the backend produces today, and the handler that models it | 8 |
| §B | msw handler → caller and route | Every handler exported by `frontend/src/test-utils/handlers.ts` | 8 |
| §C | Backend route → frontend callers | Every route the backend implements or is called at | 5 |
| §D | Divergence → the suite obliged to assert it | Every mismatch §A records | 12 |

Coverage of the mapped set is complete: all four routes registered in `ROUTE_CONTRACTS` and all eight
exported handlers appear in both directions, and every divergence in §A has a row in §D. The reasoning
behind each choice is in `docs/testing/DECISION-LOG.md` §1; this document records what is true, not why it
was chosen.

## How the outcomes in this document were obtained

Backend outcomes were measured against the assembled application, not read from the design documents:
`TestClient(app, raise_server_exceptions=False)` with `app.db.firestore.get_db` replaced by a stand-in, one
request per row. Frontend request shapes were measured by driving the real service functions through
msw 1.3.5 under Jest 29 and jsdom and reading back the intercepted URL, path parameters and body.

`REACT_APP_API_BASE_URL` is unset under Jest and `frontend/src/services/api.ts` interpolates it without a
fallback, so every URL below begins with the literal four-character string `undefined`, which jsdom resolves
against `http://localhost`.

---

## §A Frontend caller → backend route

| # | Caller | Request it emits | Backend route and contract | Outcome the backend produces today | Handler that models it | Divergences (see §D) |
|---|--------|------------------|----------------------------|------------------------------------|------------------------|----------------------|
| A1 | `services/api.ts` `fetchTweets(page, limit)` | `GET undefined/tweets?page=<page>&limit=<limit>` | `GET /tweets`, query `skip: int = 0`, `limit: int = 100`, returns `List[Tweet]` | `200` with the list when both coerce to `int` | isolation `GET */tweets` → 200 with three tweets; `currentBehaviorTweetsHandler()` → 200 | X1, X2 |
| A2 | `services/twitterService.ts` `getLatestTweets(count)` | `GET undefined/tweets?page=<count>&limit=undefined` — calls the two-parameter `fetchTweets` with one argument | same route | `422` `{"detail":[{"loc":["query","limit"],"msg":"value is not a valid integer","type":"type_error.integer"}]}` | isolation → 200; `currentBehaviorTweetsHandler()` → 422 with that exact body | X3 |
| A3 | `components/Dashboard` `RealTimeFeed`, mount effect and 30 s interval | `GET undefined/tweets?page=undefined&limit=undefined` — calls `getLatestTweets()` with no argument | same route | `422`, `loc` naming `limit` | isolation → 200; `currentBehaviorTweetsHandler()` → 422 | X3, X4 |
| A4 | `services/api.ts` `fetchTweetById(tweetId)` | `GET undefined/tweets/<tweetId>`, no query, no body | `GET /tweets/{tweet_id}`, returns `Tweet`, raises `HTTPException(404)` when absent | `500`, body `Internal Server Error`, content type `text/plain; charset=utf-8` — the handler reads `Tweet.id`, which the pydantic model does not declare | isolation `GET */tweets/:tweetId` → 200 echoing the path parameter; `currentBehaviorTweetByIdHandler()` → that 500 | X5, X6 |
| A5 | `services/twitterService.ts` `getTweetDetails(tweetId)` | wraps A4 | same route | same `500` | same as A4 | X5, X7 |
| A6 | `services/api.ts` `generateResponse(tweetId)` | `POST undefined/generate-response`, `application/json`, body `{"tweetId":"<tweetId>"}`; reads `data.generatedResponse` | none — no router declares this path | `404` `{"detail":"Not Found"}` | isolation `POST */generate-response` → 200 `{generatedResponse}`; `currentBehaviorGenerateResponseHandler()` → that 404 | X8, X9 |
| A7 | `services/llmService.ts` `generateTweetResponse(tweetId)` | wraps A6; replaces any rejection with `Error('Failed to generate tweet response')` | none | `404`, seen by the caller as the replacement error | same as A6 | X8, X10 |
| A8 | none — no module under `frontend/src/` requests it | `POST undefined/tweets/<tweetId>/responses`, no query, no body | `POST /tweets/{tweet_id}/responses`, no request body, returns a dict keyed `response` | `500`, body `Internal Server Error`, from the same `Tweet.id` access | isolation `POST */tweets/:tweetId/responses` → 200 `{response}`; `currentBehaviorTweetResponsesHandler()` → that 500 | X5, X11 |

Two frontend call sites issue **no HTTP request at all** and therefore have no row above and no handler:

| Call site | What happens instead |
|-----------|----------------------|
| `components/TweetManagement` `TweetList` → `getTweets(filters, page)` | `services/twitterService.ts` does not export `getTweets`, so the call raises `TypeError` before any request is attempted. The component catches it and logs `Error fetching tweets:`. |
| `components/Analytics` and `components/Configuration` → `@/services/analyticsService`, `@/services/configService` | Neither module exists. Both are redirected to the pure, network-free stand-ins under `frontend/src/test-utils/stubs/`. No backend router serves these concerns: the analytics and config routers are empty. |

## §B msw handler → the caller and route it stands for

| # | Exported handler | Layer | Route pattern | Stands for | Answers |
|---|------------------|-------|---------------|------------|---------|
| B1 | `frontendIsolationHandlers[0]` (alias `handlers[0]`) | isolation, test-only | `GET */tweets` | A1, A2, A3 | `200` with `makeDefaultTweets()`; `599` when the request fails screening |
| B2 | `frontendIsolationHandlers[1]` | isolation, test-only | `GET */tweets/:tweetId` | A4, A5 | `200` with one tweet whose `tweet_id` echoes the path parameter; `599` on screening failure |
| B3 | `frontendIsolationHandlers[2]` | isolation, test-only | `POST */tweets/:tweetId/responses` | A8 | `200` `{response: DEFAULT_TWEET_RESPONSE}`; `599` on screening failure |
| B4 | `frontendIsolationHandlers[3]` | isolation, test-only | `POST */generate-response` | A6, A7 | `200` `{generatedResponse: DEFAULT_GENERATED_RESPONSE}`; `599` on screening failure |
| B5 | `currentBehaviorTweetsHandler()` | current backend behaviour | `GET */tweets` | A1, A2, A3 | `200` when `skip` and `limit` coerce to `int`, otherwise `422` naming the first failing parameter |
| B6 | `currentBehaviorTweetByIdHandler()` | current backend behaviour | `GET */tweets/:tweetId` | A4, A5 | `500` `Internal Server Error`, `text/plain; charset=utf-8`, for every id |
| B7 | `currentBehaviorTweetResponsesHandler()` | current backend behaviour | `POST */tweets/:tweetId/responses` | A8 | `500` `Internal Server Error`, `text/plain; charset=utf-8` |
| B8 | `currentBehaviorGenerateResponseHandler()` | current backend behaviour | `POST */generate-response` | A6, A7 | `404` `{"detail":"Not Found"}` |

`currentBackendBehaviorHandlers()` returns B5–B8 as a fresh array; it introduces no route of its own.

Supporting exports and what they are for: `ROUTE_CONTRACTS` (the four contract records the screening runs
on), `recordedRequests` / `lastRecordedRequest` / `resetRecordedRequests` (the intercepted-request log a
suite asserts exact query, path and body values from), `allowedRequestOrigins` / `allowRequestOrigin` /
`resetAllowedRequestOrigins` (the origin allow-list), `CONTRACT_VIOLATION_STATUS` /
`CONTRACT_VIOLATION_DETAIL` (the screening failure response), `BACKEND_SERVER_ERROR_STATUS` /
`BACKEND_SERVER_ERROR_BODY` / `BACKEND_TEXT_CONTENT_TYPE` / `BACKEND_NOT_FOUND_STATUS` /
`BACKEND_NOT_FOUND_BODY` / `BACKEND_UNPROCESSABLE_STATUS` / `backendIntegerCoercionErrorBody` (the measured
backend values), `makeDefaultTweets` / `makeDefaultTweetsJson` / `DEFAULT_GENERATED_RESPONSE` /
`DEFAULT_TWEET_RESPONSE` / `SerializedTweet` (the isolation payloads and their wire shape).

## §C Backend route → frontend callers and covering suites

| # | Backend route | Frontend callers | Covered by |
|---|---------------|------------------|------------|
| C1 | `GET /tweets` | A1, A2, A3 | backend integration suite for the real route; frontend service and component suites through B1 and B5 |
| C2 | `GET /tweets/{tweet_id}` | A4, A5 | backend integration suite asserts the `500` and the unreachable `404`; frontend suites through B2 and B6 |
| C3 | `POST /tweets/{tweet_id}/responses` | none | backend integration suite; B3 and B7 exist because the backend implements the route |
| C4 | `POST /generate-response` | A6, A7 | no backend coverage is possible — the path is not routed. Its `404` is asserted through B8 |
| C5 | `/users…`, `/analytics…`, `/config…` | none | the routers are empty; their `404` responses are asserted by the backend route-surface suite against the real application, not by any msw handler |

## §D Divergence → the suite obliged to assert it

Each row is a difference between what the frontend emits or expects and what the backend does. None is
corrected in production: the two authorised production touches do not cover any of them, and implementing
the missing behaviour is out of scope. Each is therefore an assertion obligation.

| # | Divergence | Where it is visible | Obligation |
|---|------------|---------------------|------------|
| X1 | `page` is not a declared backend parameter, so `GET /tweets` ignores it | `services/api.ts` line 8 vs `routes/tweets.py` line 12 | the API service suite asserts the exact emitted URL; the backend integration suite asserts the route's `skip`/`limit` semantics separately |
| X2 | `skip`, the parameter the backend paginates on, is never sent | same | the backend integration suite asserts `skip` from the server side; no frontend test may claim pagination works |
| X3 | `limit` reaches the backend as the literal string `undefined`, which fails `int` coercion | `twitterService.getLatestTweets` passes one argument to the two-parameter `fetchTweets` | the twitterService suite asserts the emitted `limit=undefined`; a suite installing B5 asserts the resulting `422` body |
| X4 | `page` also reaches the backend as `undefined` from the Dashboard | `components/Dashboard` line 10 calls `getLatestTweets()` with no argument | the Dashboard component suite asserts the emitted query, and that the mount fetch and the 30 s interval both emit it |
| X5 | `Tweet.id` is read on a pydantic model that declares no `id`, so both tweet-detail routes raise | `routes/tweets.py` lines 18 and 27 | the backend integration suite asserts `500` with `TestClient(app, raise_server_exceptions=False)` and `pytest.raises` with the default client |
| X6 | the `404` branch of `GET /tweets/{tweet_id}` is unreachable because X5 raises first | `routes/tweets.py` lines 19–20 | the backend integration suite documents the branch as unreachable; no handler models it |
| X7 | `twitterService` declares its own `Tweet` as `{id, text}` while both the backend and the frontend schema use `{tweet_id, content, …}`, and nothing transforms between them | `services/twitterService.ts` lines 3–8 | the twitterService suite asserts the values actually returned, not the declared interface |
| X8 | `POST /generate-response` does not exist; the nearest implemented route is `POST /tweets/{tweet_id}/responses` | `services/api.ts` line 22 | the API service suite treats the route as a frontend-isolation contract only; a suite installing B8 asserts the `404` |
| X9 | that route takes its id from a JSON body and reads the reply under `generatedResponse`, where the implemented route takes a path parameter and returns `response` | `services/api.ts` lines 23–24 vs `routes/tweets.py` line 36 | the API service suite asserts the emitted body and the unwrapped key |
| X10 | `llmService.generateTweetResponse` discards the original error and rethrows `Error('Failed to generate tweet response')` | `services/llmService.ts` line 12 | the llmService suite asserts that exact message, so the `404` cause is provably lost |
| X11 | no module requests `POST /tweets/{tweet_id}/responses`, so the backend's only write-shaped route has no frontend caller | absence in `frontend/src/services/` | recorded here; no frontend suite may imply the route is exercised from the UI |
| X12 | `frontend/src/schema/tweetSchema.ts` types `timestamp` as `z.date()`, which no JSON payload can satisfy, while the wire value is an ISO-8601 string | `schema/tweetSchema.ts` vs the serialised handler payloads | the tweetSchema suite asserts that a string `timestamp` is rejected; `makeDefaultTweetsJson()` is the value the service suites compare against |
