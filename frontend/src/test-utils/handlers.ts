/**
 * msw request handlers for the frontend Jest suite, in two separately named layers.
 *
 * This module registers handlers only. It constructs no server, makes no lifecycle call and registers no
 * Jest hook: `src/test-utils/setup-jest.ts` owns the lifecycle and resets this module's mutable state - the
 * request log and the isolation ledger - after each test.
 *
 * See `frontend/TESTING.md` for how a suite consumes it, `docs/testing/DECISION-LOG.md` rows D1-D16, D103,
 * D136 and D137 for why it is shaped this way, and `docs/testing/TRACEABILITY-MATRIX.md` for the per-route
 * caller-to-backend mapping.
 *
 * ## Layer 1 - {@link frontendIsolationHandlers}, exported also as {@link handlers}
 *
 * TEST-ONLY nominal-success responses, so a component or service suite can run without a socket. They are
 * **not** a model of the backend: a suite that exercises only these has covered no integration, and every
 * `200` below is a fixture rather than an outcome the backend produces.
 *
 * ## Layer 2 - what the assembled application returns today, per base URL
 *
 * The base URL comes first, because it decides whether a request is routed at all.
 * `services/api.ts` line 5 reads `process.env.REACT_APP_API_BASE_URL` with no fallback, so under Jest -
 * where `src/test-utils/setup-jest.ts` deletes the variable - every request carries the literal path segment
 * `/undefined` ahead of the route path. `backend/app/main.py` includes one router with endpoints, and it
 * declares `/tweets`, `/tweets/{tweet_id}` and `/tweets/{tweet_id}/responses` with **no** prefix. So a
 * request emitted today matches no route, and starlette's router answers it before any dependency resolves
 * or any query value is coerced.
 *
 * | Route path                         | Isolation fixture | Emitted today, base unset ({@link UNSET_BASE_PATH_PREFIX}) | Base configured to {@link CONFIGURED_BASE_URL}, unoverridden `get_db` | ... under a SQLAlchemy-shaped `get_db` override |
 * |------------------------------------|-------------------|------------------------------------------------------------|-----------------------------------------------------------------------|------------------------------------------------|
 * | `GET /tweets`                      | 200 + 3 tweets    | 404 `{"detail":"Not Found"}`                               | 422 when `skip` or `limit` is not an int, otherwise 500 `Internal Server Error` | 422 on the same values, otherwise 200 + the list |
 * | `GET /tweets/{tweet_id}`           | 200 + 1 tweet     | 404 `{"detail":"Not Found"}`                               | 500 `Internal Server Error`                                           | 500 (raises at `Tweet.id`)                     |
 * | `POST /tweets/{tweet_id}/responses`| 200 + `response`  | 404 `{"detail":"Not Found"}`                               | 500 `Internal Server Error`                                           | 500 (raises at `Tweet.id`)                     |
 * | `POST /generate-response`          | 200 + `generatedResponse` | 404 `{"detail":"Not Found"}`                       | 404 - no router declares the path under any base                      | 404, routing fails first                       |
 *
 * {@link unsetBaseBackendHandlers} reproduces the third column and {@link configuredBaseBackendHandlers} the
 * fourth and fifth, the latter selected by its `dependencyOverridden` option. A suite installs the set
 * matching the disposition it means to assert; neither is part of the default array. Every value in the table
 * is asserted from the server side by `backend/tests/integration/test_route_surface.py` and
 * `test_http_tweets.py`, which are the oracle a change to this table must agree with.
 *
 * The 422 is **not** conditional on the dependency: fastapi coerces the declared query parameters before it
 * calls the endpoint, so a request carrying `limit=undefined` is refused whichever object `Depends(get_db)`
 * yields, and it reports **every** failing parameter in declaration order - `skip` before `limit` - rather
 * than only the first.
 *
 * ## Request screening and the request log
 *
 * Every handler in both layers screens the request against the contract in {@link ROUTE_CONTRACTS} and
 * records it in the log that {@link recordedRequests} returns, so a suite asserts the exact query, path and
 * body it emitted rather than inferring correctness from a 200.
 *
 * In layer 1 a request that deviates from its contract - an unknown or absent query key, a placeholder path
 * parameter, an unexpected body - is answered with {@link CONTRACT_VIOLATION_STATUS} and a body listing the
 * violations, never with a success status. In layer 2 the violations are recorded and the response is
 * whatever the backend returns for that request, including for a request no caller should emit: reproducing
 * that is the point of the layer, so a deviation there is a log entry rather than a ledger entry.
 *
 * ## Origin and path confinement
 *
 * Every handler is registered as an **absolute, fully spelled-out** pattern: an entry of
 * {@link ALLOWED_REQUEST_ORIGINS} - the explicitly handled loopback origins, `http://localhost` and
 * `http://127.0.0.1` - then the base path prefix the layer is about, then the route path. No pattern carries
 * a leading `*` segment, so nothing absorbs the base prefix and no layer can answer a request whose prefix it
 * does not name. Each layer therefore registers two handlers per route.
 *
 * A request to any other origin, or to the right origin under a prefix no handler names, matches **nothing**:
 * it reaches msw's `onUnhandledRequest`, which `src/test-utils/setup-jest.ts` uses to append an
 * `'unhandled-request'` entry to the isolation ledger and then raise, so the request is reported and never
 * performed. That is what makes a mis-set base URL visible instead of silently successful.
 *
 * The allow-list is a frozen constant with no mutator. A suite that explicitly drives an absolute
 * non-loopback URL registers a handler for that exact URL with `server.use(...)` for the duration of one
 * test.
 *
 * A status alone would not be enough, because an error raised inside the request lifecycle can be lost before
 * any assertion sees it: the two services rethrow a *replacement* error, `components/TweetManagement` catches
 * and logs, and `components/Dashboard` catches nothing and leaves an unhandled rejection. Every violation is
 * therefore also appended to a ledger, and {@link assertNoIsolationViolations} throws on it from
 * `runSharedAfterEach` in `src/test-utils/reset-shared-state.ts` - the global `afterEach` that
 * `src/test-utils/setup-jest.ts` registers - which fails the test that caused it.
 *
 * ## API version
 *
 * msw 1.x: handlers are built with `rest`, resolvers have the form
 * `(req, res, ctx) => res(ctx.status(...), ctx.json(...))`.
 */

import { rest } from 'msw';
import type { ResponseComposition, RestContext, RestHandler } from 'msw';

import { makeTweet } from './factories';

type TweetFixture = ReturnType<typeof makeTweet>;

/** After JSON serialisation `timestamp` is an ISO-8601 string, so this is the shape a caller receives. */
export type SerializedTweet = Omit<TweetFixture, 'timestamp'> & {
  timestamp: string;
};

/**
 * One `TweetFixture` in the shape it takes on the wire. The array members are rebuilt, so the returned
 * object shares nothing with the tweet it was derived from.
 */
function serializeTweet(tweet: TweetFixture): SerializedTweet {
  return {
    ...tweet,
    ai_tools: [...tweet.ai_tools],
    media_urls: [...tweet.media_urls],
    timestamp: tweet.timestamp.toISOString(),
  };
}

/** Returned under the `generatedResponse` key, which both `generateResponse` and `generateTweetResponse` resolve to. */
export const DEFAULT_GENERATED_RESPONSE =
  'Benchmark the assistant on your own repository before drawing a conclusion.';

/** Returned under the `response` key, as the backend's tweet-responses route does. */
export const DEFAULT_TWEET_RESPONSE = 'Draft reply stored for review.';

/**
 * The tweets the tweet-collection handler returns. Every element comes from `makeTweet`, so all three
 * satisfy `tweetSchema` in full, and elements 1 and 2 override a different subset of fields so a suite can
 * tell them apart by index.
 *
 * The tweets are rebuilt on every call, so each request is handed its own objects and a suite that mutates a
 * response changes nothing for the next one.
 *
 * @returns Three freshly built, schema-valid tweets.
 */
export function makeDefaultTweets(): TweetFixture[] {
  return [
    makeTweet(),
    makeTweet({
      tweet_id: 'tweet-2',
      content: 'Every AI pair-programming demo I have seen quietly skips the debugging.',
      user_id: 'user-2',
      likes_count: 5,
      retweets_count: 1,
      doubt_rating: 0.35,
      ai_tools: ['ChatGPT'],
    }),
    makeTweet({
      tweet_id: 'tweet-3',
      content: 'The assistant wrote the test and the bug. Impressive symmetry.',
      user_id: 'user-3',
      likes_count: 0,
      retweets_count: 0,
      doubt_rating: 0.95,
      ai_tools: ['Copilot', 'ChatGPT'],
      media_urls: ['https://example.invalid/media/tweet-3.png'],
      quoted_tweet_id: 'tweet-1',
    }),
  ];
}

/**
 * `makeDefaultTweets()` in the shape it takes on the wire, with every `timestamp` an ISO-8601 string; this
 * is what `fetchTweets` resolves to, so it is the value a suite asserts the resolved payload against.
 *
 * @returns Three freshly built tweets in their serialised form.
 */
export function makeDefaultTweetsJson(): SerializedTweet[] {
  return makeDefaultTweets().map(serializeTweet);
}

/* ------------------------------------------------------------------------------------------------------ *
 * The two base URLs a suite can put `services/api.ts` on, and the path prefix each one produces.
 * ------------------------------------------------------------------------------------------------------ */

/**
 * What `${API_BASE_URL}` interpolates to when `REACT_APP_API_BASE_URL` is unset: the four-character string
 * `undefined`, because `services/api.ts` line 5 reads the variable with no fallback.
 */
export const UNSET_BASE_PATH_SEGMENT = 'undefined';

/**
 * The path prefix that segment becomes once jsdom resolves the relative URL against the document -
 * `undefined/tweets` becomes `http://localhost/undefined/tweets`.
 *
 * No backend router declares a path under it, so this prefix is why every request the application emits today
 * is answered `404`.
 */
export const UNSET_BASE_PATH_PREFIX = `/${UNSET_BASE_PATH_SEGMENT}`;

/**
 * The value a suite assigns to `REACT_APP_API_BASE_URL` to put the client on the backend's own paths.
 *
 * An origin with no path, and a loopback one. The backend mounts its router at the root with no prefix -
 * `Settings.API_V1_STR` is declared and used by nothing - so a base carrying a path segment would be unrouted
 * exactly as `/undefined` is; and this origin is inside {@link ALLOWED_REQUEST_ORIGINS}, so the origin
 * confinement above still holds.
 *
 * @see importWithConfiguredBase - the loader below, which applies it before importing the subject.
 * @see docs/testing/DECISION-LOG.md - row D173.
 */
export const CONFIGURED_BASE_URL = 'http://localhost';

/** The path prefix {@link CONFIGURED_BASE_URL} produces: none. Requests land on the backend's own paths. */
export const CONFIGURED_BASE_PATH_PREFIX = '';

/**
 * Loads a module graph with `REACT_APP_API_BASE_URL` set to {@link CONFIGURED_BASE_URL}, so a suite can observe
 * `services/api.ts` addressing the backend's own paths instead of the unrouted `/undefined` prefix it emits by
 * default:
 *
 *     const api = await importWithConfiguredBase(() => import('./api'));
 *     await expect(api.fetchTweets(2, 10)).rejects.toMatchObject({ response: { status: 500 } });
 *
 * `frontend/src/services/api.ts` reads `process.env.REACT_APP_API_BASE_URL` **once, at module scope**, into
 * the constant it prefixes every request with, so the variable has to be in place *before* the module is
 * required: an assignment inside a test changes nothing observable. This sets it, discards the module
 * registry and imports, in that order.
 *
 * The returned module - and everything it imports, including a second `axios` instance - is a **fresh**
 * instance, distinct from the one the calling test file imported at its top. So a `jest.spyOn(axios, …)`
 * installed on the suite's own import does not affect it: drive these cases through msw, which intercepts at
 * the transport the fresh instance also uses. The request log and the msw server are unaffected, because this
 * module and `./msw-server` are already loaded when this runs.
 *
 * - a `jest.spyOn(axios, …)` installed on the suite's own `axios` import does not affect the returned module,
 *   so drive these cases through msw, which intercepts at the transport the fresh instance also uses;
 * - module state is not shared with the suite's own imports. Nothing in `services/` holds state, and this
 *   module and `./msw-server` are already loaded when this runs, so the request log and the msw server the
 *   suite asserts on are the same objects either way.
 *
 * No cleanup is needed or done here: the `afterEach` in `./setup-jest` deletes `REACT_APP_API_BASE_URL` after
 * every test, so the next test's subject reads it as unset again. That hook is the single owner of the
 * variable's lifecycle.
 *
 * `load` is a callback, so the import stays a static-looking `import()` in the calling file: the specifier
 * resolves relative to that file and stays visible to the transformer.
 *
 * @typeParam T - The module's shape, usually written as `typeof import('./api')`.
 * @param load - Imports the subject. Called after the variable is set and the registry is reset. A callback
 *   rather than a specifier string, so the `import()` stays in the calling file and resolves relative to it.
 * @returns Whatever `load` resolves to: the freshly evaluated module.
 * @see configuredBaseBackendHandlers - the handler set that answers the paths this base produces.
 */
export async function importWithConfiguredBase<T>(load: () => Promise<T>): Promise<T> {
  process.env.REACT_APP_API_BASE_URL = CONFIGURED_BASE_URL;
  jest.resetModules();
  return load();
}

/* ------------------------------------------------------------------------------------------------------ *
 * The responses the assembled FastAPI application returns today.
 * ------------------------------------------------------------------------------------------------------ */

/** Status Starlette answers with when a route handler raises; both tweet-detail routes reach it. */
export const BACKEND_SERVER_ERROR_STATUS = 500;

/** Body of that response: Starlette's plain-text default, not JSON. */
export const BACKEND_SERVER_ERROR_BODY = 'Internal Server Error';

/** Content type of that response. */
export const BACKEND_TEXT_CONTENT_TYPE = 'text/plain; charset=utf-8';

/** Status FastAPI answers with for a path it does not route. */
export const BACKEND_NOT_FOUND_STATUS = 404;

/** Body of that response. */
export const BACKEND_NOT_FOUND_BODY: { readonly detail: string } = { detail: 'Not Found' };

/** Status FastAPI answers with when a declared query parameter fails coercion. */
export const BACKEND_UNPROCESSABLE_STATUS = 422;

/** pydantic v1's message for a value it cannot coerce to `int`. */
export const BACKEND_INTEGER_ERROR_MESSAGE = 'value is not a valid integer';

/** pydantic v1's error type for the same failure. */
export const BACKEND_INTEGER_ERROR_TYPE = 'type_error.integer';

/** One entry of a FastAPI 422 `detail` array. */
export interface BackendValidationError {
  readonly loc: readonly [string, string];
  readonly msg: string;
  readonly type: string;
}

/**
 * The 422 body FastAPI returns when one or more declared `int` query parameters cannot be coerced: one
 * `detail` record per failing parameter, each `loc` naming it.
 *
 * Takes a list: validation does **not** stop at the first failure, so a request whose `skip` and `limit` are
 * both malformed is answered with two records. The caller passes them in the order the endpoint declares
 * them, which is the order fastapi reports.
 *
 * @param parameters - Names of the failing query parameters, in declaration order.
 * @see backend/tests/integration/test_http_tweets.py -
 *   `test_get_tweets_reports_both_invalid_query_values_in_declaration_order`, the server-side assertion of the
 *   same body.
 */
export function backendIntegerCoercionErrorBody(parameters: readonly string[]): {
  readonly detail: readonly BackendValidationError[];
} {
  return {
    detail: parameters.map((parameter) => ({
      loc: ['query', parameter],
      msg: BACKEND_INTEGER_ERROR_MESSAGE,
      type: BACKEND_INTEGER_ERROR_TYPE,
    })),
  };
}

/**
 * Query parameters `GET /tweets` declares and coerces to `int`, in the order
 * `app/api/routes/tweets.py` line 12 declares them. Anything else - `page`, which every caller sends - it
 * ignores.
 *
 * The order is load-bearing: it is the order the 422 `detail` records arrive in, regardless of the order the
 * query string presents the parameters in.
 */
export const BACKEND_TWEETS_INT_PARAMETERS: readonly string[] = Object.freeze(['skip', 'limit']);

/**
 * A value pydantic v1 coerces to `int`.
 *
 * pydantic v1 coerces a query value by calling `int(value)`, so the domain is CPython's base-10 literal
 * grammar rather than ASCII digits: an optional sign, one or more Unicode decimal digits - category `Nd`, so
 * Arabic-Indic `١٠`, full-width `１０` and Tibetan `༡༠` all count, and scripts may be mixed - and single `_`
 * separators strictly between digits. `_10`, `10_`, `1__0` and `+_10` are refused, as is a digit-like
 * character outside `Nd` such as the superscript `⁰`.
 *
 * Surrounding whitespace is stripped before the test, as `int()` does. The two runtimes' whitespace sets are
 * not identical - CPython also strips `\x1c`-`\x1f` and `\x85`, and JavaScript also strips `\uFEFF` - but
 * none of those characters survives URL encoding into a query value, so the difference is unreachable from
 * any request this module can receive.
 *
 * @see backend/tests/integration/test_http_tweets.py -
 *   `test_get_tweets_coerces_an_unconventional_integer_limit` and
 *   `test_get_tweets_refuses_an_integer_lookalike`, which fix this domain against the real endpoint.
 */
const INTEGER_VALUE = /^[+-]?\p{Nd}+(?:_\p{Nd}+)*$/u;

/**
 * Whether the backend coerces `value` to `int` without raising. `undefined` stands for an absent parameter,
 * which takes the route's default and always coerces.
 */
function coercesToInteger(value: string | undefined): boolean {
  return value === undefined || INTEGER_VALUE.test(value.trim());
}

/**
 * The declared `int` parameters of `GET /tweets` that the request's query string does not coerce, in
 * declaration order - the list {@link backendIntegerCoercionErrorBody} turns into a 422 body, and empty when
 * the request passes validation.
 *
 * @param query - Query parameters as sent, values unparsed.
 */
function failingIntegerParameters(query: Readonly<Record<string, string>>): readonly string[] {
  return BACKEND_TWEETS_INT_PARAMETERS.filter((parameter) => !coercesToInteger(query[parameter]));
}

/* ------------------------------------------------------------------------------------------------------ *
 * Route contracts: what each caller emits, what the backend does with it, and what each layer answers.
 * ------------------------------------------------------------------------------------------------------ */

/** Query and body rules a request must satisfy to be the request the documented callers emit. */
interface RequestExpectation {
  /** Query keys the callers emit. A request carrying any other key, or missing one of these, is screened out. */
  readonly queryKeys: readonly string[];
  /** Named path parameters the pattern captures, each of which must be a usable non-placeholder value. */
  readonly pathParams: readonly string[];
  /** `'none'` when the callers send no body; otherwise the exact JSON keys they send. */
  readonly body: 'none' | { readonly jsonKeys: readonly string[] };
  /** Additional per-route value rules, returning one message per violation. */
  readonly validateQuery?: (query: Readonly<Record<string, string>>) => string[];
}

/**
 * One route this module handles, recording the production callers, the request they emit, the backend
 * contract, the outcome the backend produces today, and what each of the two layers answers.
 *
 * The `expectation` member is the same data the screening in {@link screenRequest} enforces, so this table
 * is what the handlers run on rather than a description kept alongside them.
 */
export interface RouteContract {
  /** Stable identifier, used in the request log and in violation messages. */
  readonly id: string;
  readonly method: 'GET' | 'POST';
  /**
   * The route path alone, exactly as the backend declares it, with msw's `:name` syntax for a path
   * parameter - `/tweets/:tweetId` for the backend's `/tweets/{tweet_id}`.
   *
   * Never registered as written: {@link originScopedPatterns} prefixes it with an allowed origin and the base
   * path prefix of the layer being registered. It carries **no** wildcard segment, so a request under any
   * other prefix matches no handler at all.
   */
  readonly path: string;
  /** Production functions that issue this request. */
  readonly callers: readonly string[];
  /** The request those callers emit, as it reaches msw. */
  readonly emittedRequest: string;
  /** The backend route and its declared parameters, or the absence of one. */
  readonly backendContract: string;
  /**
   * Status and body the assembled application returns for the request the callers emit **today**, under the
   * unset base URL - so for a path carrying the {@link UNSET_BASE_PATH_PREFIX} segment, which no router
   * declares.
   */
  readonly unsetBaseOutcome: string;
  /**
   * Status and body the same call gets once `REACT_APP_API_BASE_URL` is {@link CONFIGURED_BASE_URL}, so the
   * request reaches the backend's own path, with `app.db.firestore.get_db` left alone.
   */
  readonly configuredBaseOutcome: string;
  /**
   * How {@link configuredBaseOutcome} changes when a test has installed a SQLAlchemy-shaped stand-in through
   * `app.dependency_overrides[get_db]`, or `null` when the override changes nothing.
   */
  readonly dependencyOverriddenOutcome: string | null;
  /** What {@link frontendIsolationHandlers} answers, which is test-only. */
  readonly isolationResponse: string;
  /** Every way the emitted request or the isolation response differs from the backend contract. */
  readonly mismatches: readonly string[];
  readonly expectation: RequestExpectation;
}

/** Status returned to a request that does not match its route's {@link RequestExpectation}. */
export const CONTRACT_VIOLATION_STATUS = 599;

/** Body returned with {@link CONTRACT_VIOLATION_STATUS}. */
export interface ContractViolationBody {
  readonly detail: string;
  readonly handler: string;
  readonly url: string;
  readonly violations: readonly string[];
}

/** `detail` of every {@link ContractViolationBody}. */
export const CONTRACT_VIOLATION_DETAIL = 'msw handler request-contract violation';

/** Query keys `services/api.ts` `fetchTweets` puts in the URL, and the only ones its callers can influence. */
const TWEETS_QUERY_KEYS = ['page', 'limit'] as const;

const TWEETS_CONTRACT: RouteContract = {
  id: 'GET /tweets',
  method: 'GET',
  path: '/tweets',
  callers: [
    'services/api.ts fetchTweets(page, limit)',
    'services/twitterService.ts getLatestTweets(count)',
    'components/Dashboard RealTimeFeed (getLatestTweets with no argument)',
  ],
  emittedRequest:
    'GET undefined/tweets?page=<page>&limit=<limit>; limit is the literal string "undefined" when ' +
    'getLatestTweets supplies only its first argument, and page is too when it supplies none',
  backendContract: 'GET /tweets, query skip:int=0 and limit:int=100, returns List[Tweet]',
  unsetBaseOutcome:
    '404 {"detail":"Not Found"}: the emitted path is /undefined/tweets, which no router declares, so ' +
    'starlette answers before the query is coerced and before Depends(get_db) resolves',
  configuredBaseOutcome:
    '422 naming every declared int parameter the query does not coerce, in declaration order (skip before ' +
    'limit); otherwise 500 with the plain-text body "Internal Server Error", because the handler calls ' +
    'db.query(Tweet) on the Firestore Client that app.db.firestore.get_db yields, which has no query attribute',
  dependencyOverriddenOutcome:
    'the same 422 for the same values - validation precedes the endpoint either way - and 200 with the tweet ' +
    'list in place of the 500',
  isolationResponse: '200 with three schema-valid tweets, timestamps serialised to ISO-8601 strings',
  mismatches: [
    'the emitted path carries the /undefined prefix, so the request is unrouted and answered 404 rather than reaching this route at all',
    'page is not a declared backend parameter and is ignored; skip, which the backend paginates on, is never sent',
    'limit=undefined is refused with 422 once the base is configured, whichever object Depends(get_db) yields; the isolation layer answers 200',
    'the routed request answers 500 until a test replaces the database dependency; the isolation layer answers 200',
  ],
  expectation: {
    queryKeys: TWEETS_QUERY_KEYS,
    pathParams: [],
    body: 'none',
    // Only the declared keys are inspected here; an undeclared key is already reported by screenRequest.
    validateQuery: (query) =>
      TWEETS_QUERY_KEYS.filter(
        (key) => key in query && query[key] !== 'undefined' && !INTEGER_VALUE.test(query[key].trim()),
      ).map((key) => `query "${key}" is "${query[key]}"; callers emit an integer or the string "undefined"`),
  },
};

const TWEET_BY_ID_CONTRACT: RouteContract = {
  id: 'GET /tweets/:tweetId',
  method: 'GET',
  path: '/tweets/:tweetId',
  callers: [
    'services/api.ts fetchTweetById(tweetId)',
    'services/twitterService.ts getTweetDetails(tweetId)',
  ],
  emittedRequest: 'GET undefined/tweets/<tweetId>, no query string, no body',
  backendContract: 'GET /tweets/{tweet_id}, returns Tweet, raises HTTPException(404) when absent',
  unsetBaseOutcome:
    '404 {"detail":"Not Found"}, application/json: the emitted path is /undefined/tweets/<tweetId>, which no ' +
    'router declares. This 404 is the router refusing the path, not the handler reporting a missing tweet',
  configuredBaseOutcome:
    '500 with the plain-text body "Internal Server Error": db.query on the Firestore Client that ' +
    'app.db.firestore.get_db yields does not exist',
  dependencyOverriddenOutcome:
    '500 with the same plain-text body, for a second reason: the handler reads Tweet.id, which the pydantic ' +
    'model does not declare, so it raises before the 404 branch can be reached',
  isolationResponse: '200 with one schema-valid tweet whose tweet_id echoes the path parameter',
  mismatches: [
    'the emitted path carries the /undefined prefix, so the request is answered 404 by the router and never reaches this route',
    'once routed the backend answers 500 for every id; the isolation layer answers 200',
    'the handler-level 404 branch is unreachable, so no handler models it; the 404 under the unset base is a routing failure and must not be read as that branch',
  ],
  expectation: {
    queryKeys: [],
    pathParams: ['tweetId'],
    body: 'none',
  },
};

const TWEET_RESPONSES_CONTRACT: RouteContract = {
  id: 'POST /tweets/:tweetId/responses',
  method: 'POST',
  path: '/tweets/:tweetId/responses',
  callers: [],
  emittedRequest: 'POST undefined/tweets/<tweetId>/responses, no query string, no body',
  backendContract: 'POST /tweets/{tweet_id}/responses, no request body, returns Dict under the key "response"',
  unsetBaseOutcome: '404 {"detail":"Not Found"}, application/json, for the same routing reason',
  configuredBaseOutcome:
    '500 with the plain-text body "Internal Server Error", from the same absent db.query',
  dependencyOverriddenOutcome:
    '500 with the same plain-text body, from the same Tweet.id access',
  isolationResponse: '200 with {"response": DEFAULT_TWEET_RESPONSE}',
  mismatches: [
    'no module under src/ calls this route; it is registered because the backend implements it',
    'once routed the backend answers 500; the isolation layer answers 200',
  ],
  expectation: {
    queryKeys: [],
    pathParams: ['tweetId'],
    body: 'none',
  },
};

const GENERATE_RESPONSE_CONTRACT: RouteContract = {
  id: 'POST /generate-response',
  method: 'POST',
  path: '/generate-response',
  callers: [
    'services/api.ts generateResponse(tweetId)',
    'services/llmService.ts generateTweetResponse(tweetId)',
  ],
  emittedRequest: 'POST undefined/generate-response, application/json body {"tweetId": "<tweetId>"}',
  backendContract: 'none - no router declares this path',
  unsetBaseOutcome: '404 {"detail":"Not Found"}, application/json',
  configuredBaseOutcome:
    '404 {"detail":"Not Found"}: the only route on this path is the one that does not exist, so configuring ' +
    'the base changes nothing',
  dependencyOverriddenOutcome: null,
  isolationResponse: '200 with {"generatedResponse": DEFAULT_GENERATED_RESPONSE}',
  mismatches: [
    'the path does not exist on the backend under any base; the nearest implemented route is POST /tweets/{tweet_id}/responses',
    'that route takes the id from the path rather than a body, and returns it under "response" rather than "generatedResponse"',
  ],
  expectation: {
    queryKeys: [],
    pathParams: [],
    body: { jsonKeys: ['tweetId'] },
  },
};

/**
 * Every route this module handles, in the order the handler arrays register them. Each entry documents the
 * caller-to-backend mapping and carries the expectation its handlers screen against.
 */
export const ROUTE_CONTRACTS: readonly RouteContract[] = Object.freeze([
  TWEETS_CONTRACT,
  TWEET_BY_ID_CONTRACT,
  TWEET_RESPONSES_CONTRACT,
  GENERATE_RESPONSE_CONTRACT,
]);

/* ------------------------------------------------------------------------------------------------------ *
 * Origins a handler answers. The callers' base URL is the literal string `undefined`, so every request a
 * caller emits is same-origin with the jsdom document.
 * ------------------------------------------------------------------------------------------------------ */

/**
 * The explicitly handled loopback origins: the only origins any handler in this module is registered for, as
 * `URL.origin` reports them. `http://localhost` is jsdom's default document origin, and `http://127.0.0.1` is
 * handled too so a suite that overrides `testEnvironmentOptions.url` to the numeric form - a jsdom document
 * has one origin, whichever of the two it is - is served by the same handlers.
 *
 * Loopback only, and frozen: the constant carries no mutator, so no test can widen it for a later one.
 *
 * `http://localhost` is jsdom's default document origin; `http://127.0.0.1` is included so a suite that
 * overrides `testEnvironmentOptions.url` to the numeric form is served by the same handlers.
 *
 * A suite that explicitly drives some other origin registers a handler for that exact URL with
 * `server.use(...)`; without one the request matches nothing, reaches `onUnhandledRequest` and becomes a
 * ledger entry that {@link assertNoIsolationViolations} raises on.
 *
 * @see docs/testing/DECISION-LOG.md - rows D103, D136 and D343.
 */
export const ALLOWED_REQUEST_ORIGINS: readonly string[] = Object.freeze([
  'http://localhost',
  'http://127.0.0.1',
]);

/**
 * The origins the handlers answer.
 *
 * @returns {@link ALLOWED_REQUEST_ORIGINS}, which is already frozen.
 */
export function allowedRequestOrigins(): readonly string[] {
  return ALLOWED_REQUEST_ORIGINS;
}

/**
 * The absolute msw patterns one route path is registered under for one base: the origin, then the base path
 * prefix, then the route path - fully spelled out, with no wildcard segment anywhere.
 *
 * `fetchTweets` emits `undefined/tweets?...` while the base URL is unset, which jsdom resolves to
 * `http://localhost/undefined/tweets`; that is matched by naming the `/undefined` prefix rather than by
 * absorbing it. Nothing else matches: a request under a prefix no layer names - a mis-set base URL, or the
 * backend's own path while the client is still unconfigured - reaches `onUnhandledRequest` and becomes a
 * ledger entry.
 *
 * @param path - The `path` member of a {@link ROUTE_CONTRACTS} entry, for example `/tweets/:tweetId`.
 * @param basePathPrefix - {@link UNSET_BASE_PATH_PREFIX} or {@link CONFIGURED_BASE_PATH_PREFIX}.
 * @returns One pattern per entry in {@link ALLOWED_REQUEST_ORIGINS}, in that order.
 */
function originScopedPatterns(path: string, basePathPrefix: string): readonly string[] {
  return ALLOWED_REQUEST_ORIGINS.map((origin) => `${origin}${basePathPrefix}${path}`);
}

/* ------------------------------------------------------------------------------------------------------ *
 * Request log.
 * ------------------------------------------------------------------------------------------------------ */

/** One intercepted request, as a suite reads it back to assert the exact query, path and body it emitted. */
export interface RecordedRequest {
  /** {@link RouteContract.id} of the route that answered. */
  readonly handler: string;
  readonly method: string;
  /** Absolute request URL, for example `http://localhost/undefined/tweets?page=2&limit=10`. */
  readonly url: string;
  readonly origin: string;
  /**
   * The absolute prefix the caller's base URL occupied, for example `http://localhost/undefined` while the
   * base is unset and `http://localhost` once it is configured.
   */
  readonly base: string;
  readonly pathname: string;
  /** Query string including its leading `?`, or `''` when there is none. */
  readonly search: string;
  /** Query parameters as sent, values unparsed, so `limit` reads back as the string `undefined`. */
  readonly query: Readonly<Record<string, string>>;
  /** Named path parameters the pattern captured. */
  readonly pathParams: Readonly<Record<string, string>>;
  readonly contentType: string | null;
  /** Parsed JSON body, the empty string for a bodyless request, `undefined` for a GET. */
  readonly body: unknown;
  /** Status the handler answered with. */
  readonly status: number;
  /** Screening messages; empty when the request matched its contract. */
  readonly violations: readonly string[];
  /** {@link currentTestId} at the moment the request was answered. */
  readonly testId: string;
}

const requestLog: RecordedRequest[] = [];

/**
 * Every request the handlers have answered since the last {@link resetRecordedRequests}, oldest first.
 *
 * @returns A frozen snapshot; mutating it does not affect the log.
 */
export function recordedRequests(): readonly RecordedRequest[] {
  return Object.freeze([...requestLog]);
}

/**
 * The most recent entry of {@link recordedRequests}, or `undefined` when nothing has been intercepted.
 */
export function lastRecordedRequest(): RecordedRequest | undefined {
  return requestLog[requestLog.length - 1];
}

/** Empties the request log. Called from `setup-jest.ts` after every test; safe to call again. */
export function resetRecordedRequests(): void {
  requestLog.length = 0;
}

/* ------------------------------------------------------------------------------------------------------ *
 * Test correlation. Every recorded request and every violation log line carries the id of the test that
 * emitted it, in the one canonical form `frontend/jest.config.js` also emits into the JUnit report at
 * `frontend/reports/jest-junit.xml` - so a `<testcase>` and the requests it made match by string equality.
 * ------------------------------------------------------------------------------------------------------ */

/** Value {@link currentTestId} reports when no test is running, or when Jest exposes no state. */
export const UNATTRIBUTED_TEST_ID = 'no-test';

/** Joins the two halves of a {@link currentTestId}; the same separator `jest.config.js` documents. */
export const TEST_ID_SEPARATOR = ' > ';

/** Reported as the name half for a request emitted while a test module is still being evaluated. */
export const MODULE_SCOPE_TEST_NAME = '(module scope)';

/** Directory every test file in this suite sits under, and the point the file half is cut from. */
const ROOT_RELATIVE_MARKER = '/src/';

/** The Jest globals this module reads, declared so it also loads outside a test run. */
interface JestExpectState {
  getState?: () => { currentTestName?: string; testPath?: string } | undefined;
}

/**
 * Identifier of the test currently executing, as `<test file>` + {@link TEST_ID_SEPARATOR} +
 * `<full test name>` - for example
 * `src/services/api.test.ts > fetchTweets propagates the rejection instance unchanged`.
 *
 * The file half is `<rootDir>`-relative with forward slashes, which is `jest-junit`'s `{filepath}`
 * normalised the way `frontend/jest.config.js` normalises it for `<testcase classname>`. The name half is
 * Jest's `currentTestName` - every enclosing `describe` title and the leaf title, joined by a single space -
 * which is what that config emits as `<testcase name>`. So `classname` + `' > '` + `name` from the report is
 * this string, and two tests sharing a leaf title under different `describe` blocks are distinguished by
 * both.
 *
 * A request emitted outside a test reports {@link MODULE_SCOPE_TEST_NAME} as its name half while a module is
 * being evaluated, and {@link UNATTRIBUTED_TEST_ID} when Jest exposes no state at all - which is what makes
 * a leaked request visible as such.
 *
 * @see frontend/jest.config.js - the `jest-junit` template functions that emit the same two halves.
 */
export function currentTestId(): string {
  const jestExpect = (globalThis as { expect?: JestExpectState }).expect;
  const state = typeof jestExpect?.getState === 'function' ? jestExpect.getState() : undefined;
  if (state === undefined) {
    return UNATTRIBUTED_TEST_ID;
  }

  const name = state.currentTestName ?? '';
  const path = (state.testPath ?? '').replace(/\\/g, '/');
  const marker = path.lastIndexOf(ROOT_RELATIVE_MARKER);
  const file = marker === -1 ? path : path.slice(marker + 1);
  if (name === '' && file === '') {
    return UNATTRIBUTED_TEST_ID;
  }
  return file === '' ? name : `${file}${TEST_ID_SEPARATOR}${name || MODULE_SCOPE_TEST_NAME}`;
}

/* ------------------------------------------------------------------------------------------------------ *
 * Isolation-violation ledger. A rejection status can be caught by the code under test; a throw at teardown
 * cannot.
 * ------------------------------------------------------------------------------------------------------ */

/** Why a request breached the isolation boundary. */
export type IsolationViolationKind =
  /** Request to an origin no handler is registered for. */
  | 'origin'
  /** Request no handler matched at all, reported through msw's `onUnhandledRequest`. */
  | 'unhandled-request'
  /** Request the isolation layer screened out against its {@link RouteContract}. */
  | 'contract';

/** One breach, as {@link assertNoIsolationViolations} reports it. */
export interface IsolationViolation {
  readonly kind: IsolationViolationKind;
  /** {@link RouteContract.id}, or `'(no handler)'` for an unhandled request. */
  readonly handler: string;
  readonly method: string;
  readonly url: string;
  readonly violations: readonly string[];
}

const isolationViolations: IsolationViolation[] = [];

/**
 * Every isolation breach recorded since the last {@link resetIsolationViolations}, oldest first.
 *
 * @returns A frozen snapshot; mutating it does not affect the ledger.
 */
export function recordedIsolationViolations(): readonly IsolationViolation[] {
  return Object.freeze([...isolationViolations]);
}

/** Empties the ledger. `src/test-utils/setup-jest.ts` calls this after every test. */
export function resetIsolationViolations(): void {
  isolationViolations.length = 0;
}

/**
 * Takes the ledger's contents and empties it, so the breaches it held do not fail the current test.
 *
 * For the one case the ledger is not meant to catch: a test that *provokes* a screening and
 * asserts on it, rather than one that leaked a request without noticing. Call this after those assertions,
 * and assert on the returned entries if the ledger itself is the subject.
 *
 * Every other test leaves the ledger alone, so {@link assertNoIsolationViolations} stays fail-closed by
 * default: a breach nobody acknowledged still fails the test that caused it.
 *
 * @returns The entries the ledger held, oldest first.
 */
export function acknowledgeIsolationViolations(): readonly IsolationViolation[] {
  const acknowledged = Object.freeze([...isolationViolations]);
  isolationViolations.length = 0;
  return acknowledged;
}

function recordIsolationViolation(violation: IsolationViolation): void {
  isolationViolations.push(Object.freeze(violation));
}

/**
 * Records a request msw matched no handler for.
 *
 * Called from the `onUnhandledRequest` callback in `src/test-utils/setup-jest.ts` before it invokes
 * `print.error()`. msw's own error is raised inside the request lifecycle and can be caught by whatever
 * issued the request - `getLatestTweets`, `generateTweetResponse` and both list components all swallow what
 * they are handed - so the ledger entry is what survives to fail the test.
 *
 * @param method - HTTP method as msw reports it.
 * @param url - Absolute request URL.
 */
export function recordUnhandledRequest(method: string, url: string): void {
  recordIsolationViolation({
    kind: 'unhandled-request',
    handler: '(no handler)',
    method,
    url,
    violations: Object.freeze([
      `no handler is registered for ${method} ${url}; the isolation layer answers only ` +
        `${allowedRequestOrigins().join(' and ')}. Install a handler for this exact URL with ` +
        'server.use(...) if the request is intended.',
    ]),
  });
}

/**
 * Throws when any isolation breach was recorded, listing every one.
 *
 * `src/test-utils/reset-shared-state.ts` calls this from `runSharedAfterEach`, which `src/test-utils/setup-jest.ts`
 * registers as the suite's global `afterEach`. That is what makes a breach fail the test that caused it even
 * when the code under test caught the response. Without it a service that turns a rejection into `[]` - or a
 * component that logs and continues - reports success for a request that never should have been made.
 *
 * @throws Error naming each breach, its kind and its URL.
 */
export function assertNoIsolationViolations(): void {
  if (isolationViolations.length === 0) {
    return;
  }

  const detail = isolationViolations
    .map(
      (violation) =>
        `  [${violation.kind}] ${violation.method} ${violation.url} (${violation.handler})\n` +
        violation.violations.map((message) => `    - ${message}`).join('\n'),
    )
    .join('\n');

  throw new Error(
    `${isolationViolations.length} request(s) breached test isolation:\n${detail}\n` +
      'No request may leave the suite. Point the request at the jsdom origin, or register a handler for it.',
  );
}

/**
 * Restores every piece of module state this file holds - the request log and the isolation ledger - to the
 * state a freshly imported module has. Called from `resetSharedTestState()` in `./reset-shared-state`, which
 * is the single owner of this cleanup and which `./setup-jest` registers as the global `afterEach`; this file
 * registers no hook of its own. There is no origin state to reset: {@link ALLOWED_REQUEST_ORIGINS} is a
 * frozen constant.
 *
 * `runSharedAfterEach` asserts on the ledger *before* reaching this, so a breach still fails the test that
 * caused it, and resetting the ledger here keeps one test's breach from being attributed to a later one.
 *
 * A new piece of module state added to this file belongs here, so that one call site keeps discarding all of
 * it.
 */
export function resetHandlerState(): void {
  resetRecordedRequests();
  resetIsolationViolations();
}

/* ------------------------------------------------------------------------------------------------------ *
 * Screening.
 * ------------------------------------------------------------------------------------------------------ */

/** The parts of an msw request this module reads, named so a resolver passes them explicitly. */
interface RequestFacts {
  readonly method: string;
  readonly url: URL;
  /** `req.params`, the named path parameters the pattern captured. */
  readonly params: Readonly<Record<string, unknown>>;
  readonly contentType: string | null;
  readonly body: unknown;
  /**
   * The base path prefix the handler answering this request was registered under -
   * {@link UNSET_BASE_PATH_PREFIX} or {@link CONFIGURED_BASE_PATH_PREFIX}. Recorded as
   * {@link RecordedRequest.base} together with the origin.
   */
  readonly basePathPrefix: string;
}

/** A screened request: its normalised facts and every way it departs from its contract. */
interface ScreenedRequest {
  readonly contract: RouteContract;
  readonly facts: RequestFacts;
  readonly base: string;
  readonly query: Record<string, string>;
  readonly pathParams: Record<string, string>;
  /** `false` when the request came from an origin outside {@link allowedRequestOrigins}. */
  readonly originAllowed: boolean;
  readonly violations: readonly string[];
}

/** Path-parameter values that mean a caller interpolated a missing variable. */
const PLACEHOLDER_PATH_VALUES = ['', 'undefined', 'null', 'NaN'];

function stringifyParam(value: unknown): string {
  return Array.isArray(value) ? value.join(',') : String(value ?? '');
}

/**
 * The absolute prefix the caller's base URL occupied: the request origin followed by the base path prefix the
 * answering handler was registered under.
 *
 * Read from the registration: a handler is registered per base, so it already knows which one it is -
 * `http://localhost/undefined` for the unset base URL, `http://localhost` for {@link CONFIGURED_BASE_URL}.
 *
 * @param origin - `URL.origin` of the request.
 * @param basePathPrefix - The prefix the answering pattern named.
 */
function baseFromRegistration(origin: string, basePathPrefix: string): string {
  return `${origin}${basePathPrefix}`;
}

/** Named path parameters, with any positional capture msw may add removed. */
function namedPathParams(params: Readonly<Record<string, unknown>>): Record<string, string> {
  const named: Record<string, string> = {};
  for (const [key, value] of Object.entries(params)) {
    if (!/^\d+$/.test(key)) {
      named[key] = stringifyParam(value);
    }
  }
  return named;
}

function bodyViolations(contract: RouteContract, facts: RequestFacts): string[] {
  const violations: string[] = [];
  const expectation = contract.expectation.body;

  if (expectation === 'none') {
    if (facts.body !== undefined && facts.body !== null && facts.body !== '') {
      violations.push(`body is ${JSON.stringify(facts.body)}; callers send none`);
    }
    return violations;
  }

  if (typeof facts.body !== 'object' || facts.body === null || Array.isArray(facts.body)) {
    violations.push(
      `body is ${JSON.stringify(facts.body)}; callers send a JSON object with keys ${expectation.jsonKeys.join(', ')}`,
    );
    return violations;
  }

  const sent = Object.keys(facts.body as Record<string, unknown>).sort();
  const expected = [...expectation.jsonKeys].sort();
  if (sent.join(',') !== expected.join(',')) {
    violations.push(`body keys are [${sent.join(', ')}]; callers send exactly [${expected.join(', ')}]`);
  }

  for (const key of expectation.jsonKeys) {
    const value = (facts.body as Record<string, unknown>)[key];
    if (typeof value !== 'string' || value.length === 0) {
      violations.push(`body "${key}" is ${JSON.stringify(value)}; callers send a non-empty string`);
    }
  }

  return violations;
}

/**
 * Compares a request against its route contract without answering it.
 *
 * Checks the query keys against {@link RequestExpectation.queryKeys} in both directions, each named path
 * parameter against {@link PLACEHOLDER_PATH_VALUES}, and the body against
 * {@link RequestExpectation.body}, then applies the route's own {@link RequestExpectation.validateQuery}.
 *
 * The origin is checked too, and reported through {@link ScreenedRequest.originAllowed}. Because every
 * pattern is absolute, a request from another origin matches no handler and never reaches here; the check
 * remains as the second line of defence, and as what puts a ledger entry in place if a handler is ever
 * registered for a pattern this module did not scope.
 */
function screenRequest(contract: RouteContract, facts: RequestFacts): ScreenedRequest {
  const violations: string[] = [];
  const query: Record<string, string> = {};
  for (const [key, value] of facts.url.searchParams.entries()) {
    query[key] = value;
  }
  const pathParams = namedPathParams(facts.params);

  const originAllowed = allowedRequestOrigins().includes(facts.url.origin);
  if (!originAllowed) {
    violations.push(
      `origin "${facts.url.origin}" is not an allowed test origin (${allowedRequestOrigins().join(', ')})`,
    );
  }

  for (const key of contract.expectation.queryKeys) {
    if (!(key in query)) {
      violations.push(`query "${key}" is absent; callers always send it`);
    }
  }
  for (const key of Object.keys(query)) {
    if (!contract.expectation.queryKeys.includes(key)) {
      violations.push(`query "${key}" is not sent by any caller of this route`);
    }
  }

  for (const key of contract.expectation.pathParams) {
    const value = pathParams[key];
    if (value === undefined || PLACEHOLDER_PATH_VALUES.includes(value)) {
      violations.push(`path parameter "${key}" is ${JSON.stringify(value)}; callers send a real identifier`);
    }
  }

  violations.push(...bodyViolations(contract, facts));

  if (contract.expectation.validateQuery !== undefined) {
    violations.push(...contract.expectation.validateQuery(query));
  }

  return {
    contract,
    facts,
    // Every pattern is absolute and names its base prefix, so the prefix comes from the registration.
    base: baseFromRegistration(facts.url.origin, facts.basePathPrefix),
    query,
    pathParams,
    originAllowed,
    violations,
  };
}

/**
 * Appends a screened request to the log under the status it was answered with, and records an origin breach
 * in the ledger.
 *
 * Every handler in both layers calls this exactly once per request, which makes it the single place the
 * origin check can be turned into a failure the code under test cannot swallow.
 */
function record(screened: ScreenedRequest, status: number): void {
  if (!screened.originAllowed) {
    recordIsolationViolation({
      kind: 'origin',
      handler: screened.contract.id,
      method: screened.facts.method,
      url: screened.facts.url.href,
      violations: Object.freeze([...screened.violations]),
    });
  }

  requestLog.push(
    Object.freeze({
      handler: screened.contract.id,
      method: screened.facts.method,
      url: screened.facts.url.href,
      origin: screened.facts.url.origin,
      base: screened.base,
      pathname: screened.facts.url.pathname,
      search: screened.facts.url.search,
      query: Object.freeze({ ...screened.query }),
      pathParams: Object.freeze({ ...screened.pathParams }),
      contentType: screened.facts.contentType,
      body: screened.facts.body,
      status,
      violations: Object.freeze([...screened.violations]),
      testId: currentTestId(),
    }),
  );
}

/**
 * Records a screened-out request, writes its violations to `console.error` so they surface even when the
 * calling service swallows the rejection, and returns the body to answer it with.
 *
 * Layer 1 only. A request that fails its contract here is never intentional - a suite wanting to assert what
 * the backend does with a non-conforming request installs {@link unsetBaseBackendHandlers} or
 * {@link configuredBaseBackendHandlers} instead, and that layer records the deviation without adding a ledger
 * entry. So this also appends to the ledger, which turns the 599 from a status the caller may catch into a
 * failure of the test that emitted the request.
 */
function rejectScreenedRequest(screened: ScreenedRequest): ContractViolationBody {
  record(screened, CONTRACT_VIOLATION_STATUS);

  if (screened.originAllowed) {
    // An origin breach is already in the ledger, recorded by `record` above.
    recordIsolationViolation({
      kind: 'contract',
      handler: screened.contract.id,
      method: screened.facts.method,
      url: screened.facts.url.href,
      violations: Object.freeze([...screened.violations]),
    });
  }

  const body: ContractViolationBody = Object.freeze({
    detail: CONTRACT_VIOLATION_DETAIL,
    handler: screened.contract.id,
    url: screened.facts.url.href,
    violations: Object.freeze([...screened.violations]),
  });

  // eslint-disable-next-line no-console
  console.error(
    `${CONTRACT_VIOLATION_DETAIL} [${screened.contract.id}] ${screened.facts.method} ${screened.facts.url.href}\n` +
      `  test: ${currentTestId()}\n` +
      screened.violations.map((violation) => `  - ${violation}`).join('\n'),
  );

  return body;
}

/* ------------------------------------------------------------------------------------------------------ *
 * Layer 1 - frontend isolation. Test-only nominal responses; see the table in the module header for what
 * each of these routes really answers.
 * ------------------------------------------------------------------------------------------------------ */

/**
 * Nominal-success handlers: one per route in {@link ROUTE_CONTRACTS}, in that order, and one per entry in
 * {@link ALLOWED_REQUEST_ORIGINS} within each route - so eight handlers, indices `[0..1]` for the tweet
 * collection, `[2..3]` for the tweet detail, `[4..5]` for the tweet responses and `[6..7]` for
 * `generate-response`.
 *
 * All eight are registered under {@link UNSET_BASE_PATH_PREFIX}, which is the prefix every request carries
 * while `REACT_APP_API_BASE_URL` is unset - the state `src/test-utils/setup-jest.ts` guarantees. A suite that
 * configures the base URL therefore matches none of these and installs its own handlers, so a fixture cannot
 * follow a client onto a path it does not describe.
 *
 * These responses are fixtures, not backend behaviour: the assembled application answers **404** for every one
 * of these paths. A suite asserting an integration outcome installs {@link unsetBaseBackendHandlers} or
 * {@link configuredBaseBackendHandlers} instead.
 */
export const frontendIsolationHandlers: RestHandler[] = [
  ...originScopedPatterns(TWEETS_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
    rest.get(pattern, (req, res, ctx) => {
      const screened = screenRequest(TWEETS_CONTRACT, {
        method: req.method,
        url: req.url,
        params: req.params,
        contentType: req.headers.get('content-type'),
        body: undefined,
        basePathPrefix: UNSET_BASE_PATH_PREFIX,
      });

      if (screened.violations.length > 0) {
        return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
      }

      record(screened, 200);
      return res(ctx.status(200), ctx.json(makeDefaultTweets()));
    }),
  ),

  ...originScopedPatterns(TWEET_BY_ID_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
    rest.get<never, { tweetId: string }>(pattern, (req, res, ctx) => {
      const screened = screenRequest(TWEET_BY_ID_CONTRACT, {
        method: req.method,
        url: req.url,
        params: req.params,
        contentType: req.headers.get('content-type'),
        body: undefined,
        basePathPrefix: UNSET_BASE_PATH_PREFIX,
      });

      if (screened.violations.length > 0) {
        return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
      }

      record(screened, 200);
      return res(ctx.status(200), ctx.json(makeTweet({ tweet_id: req.params.tweetId })));
    }),
  ),

  ...originScopedPatterns(TWEET_RESPONSES_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
    rest.post<string, { tweetId: string }>(pattern, (req, res, ctx) => {
      const screened = screenRequest(TWEET_RESPONSES_CONTRACT, {
        method: req.method,
        url: req.url,
        params: req.params,
        contentType: req.headers.get('content-type'),
        body: req.body,
        basePathPrefix: UNSET_BASE_PATH_PREFIX,
      });

      if (screened.violations.length > 0) {
        return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
      }

      record(screened, 200);
      return res(ctx.status(200), ctx.json({ response: DEFAULT_TWEET_RESPONSE }));
    }),
  ),

  ...originScopedPatterns(GENERATE_RESPONSE_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
    rest.post<{ tweetId: string }>(pattern, (req, res, ctx) => {
      const screened = screenRequest(GENERATE_RESPONSE_CONTRACT, {
        method: req.method,
        url: req.url,
        params: req.params,
        contentType: req.headers.get('content-type'),
        body: req.body,
        basePathPrefix: UNSET_BASE_PATH_PREFIX,
      });

      if (screened.violations.length > 0) {
        return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
      }

      record(screened, 200);
      return res(ctx.status(200), ctx.json({ generatedResponse: DEFAULT_GENERATED_RESPONSE }));
    }),
  ),
];

/**
 * The array `msw-server.ts` spreads into `setupServer`. Same array as
 * {@link frontendIsolationHandlers}; the name is the one `frontend/TESTING.md` documents.
 */
export const handlers: RestHandler[] = frontendIsolationHandlers;

/* ------------------------------------------------------------------------------------------------------ *
 * Layer 2 - what the assembled application returns, one factory per base URL. Each reproduces the status,
 * body and content type the backend suites named below assert, and registers one handler per route per entry
 * in {@link ALLOWED_REQUEST_ORIGINS}, so a call site spreads the result:
 * `server.use(...unsetBaseBackendHandlers())`.
 *
 * Exactly one of the two is installed per suite: a request carries one base URL, so a suite installs the
 * set matching the base its subject was loaded under. {@link unsetBaseBackendHandlers} is the base every suite
 * runs under by default; {@link configuredBaseBackendHandlers} requires the subject to have been re-imported
 * with `REACT_APP_API_BASE_URL` set, which {@link importWithConfiguredBase} does.
 *
 * Unlike layer 1, a contract deviation here is not a ledger entry: reproducing what the backend does with a
 * request no caller should emit is the whole point of this layer, so the deviation is recorded in the
 * request log and the backend's own answer is returned.
 * ------------------------------------------------------------------------------------------------------ */

/**
 * Screens a request, records it under {@link BACKEND_NOT_FOUND_STATUS} and answers with the router's own 404 -
 * `{"detail":"Not Found"}` as JSON, which is what starlette returns for a path it does not route.
 */
function answerRouterNotFound(
  contract: RouteContract,
  facts: RequestFacts,
  res: ResponseComposition,
  ctx: RestContext,
) {
  record(screenRequest(contract, facts), BACKEND_NOT_FOUND_STATUS);
  return res(ctx.status(BACKEND_NOT_FOUND_STATUS), ctx.json(BACKEND_NOT_FOUND_BODY));
}

/**
 * Records a screened request under {@link BACKEND_SERVER_ERROR_STATUS} and answers with the response starlette
 * produces when an endpoint raises: the plain-text body `Internal Server Error`, not JSON.
 */
function answerServerError(screened: ScreenedRequest, res: ResponseComposition, ctx: RestContext) {
  record(screened, BACKEND_SERVER_ERROR_STATUS);
  return res(
    ctx.status(BACKEND_SERVER_ERROR_STATUS),
    ctx.set('Content-Type', BACKEND_TEXT_CONTENT_TYPE),
    ctx.body(BACKEND_SERVER_ERROR_BODY),
  );
}

/**
 * Every route as the assembled application answers it for the request the application **emits today**: `404`
 * with the JSON body `{"detail":"Not Found"}`, for all four, because `services/api.ts` prefixes every path
 * with the literal `undefined` segment and no router declares anything under it.
 *
 * There is one handler per route and no catch-all, so a request whose path is not one of the four matches
 * nothing and is ledgered, and the request log attributes each request to its route contract.
 *
 * Starlette answers this before the query string is coerced and before `Depends(get_db)` resolves, so the
 * status does not depend on the query values a caller sent or on whether a test overrode the database
 * dependency, and this factory therefore takes no options.
 *
 * @returns One handler per route in {@link ROUTE_CONTRACTS}, per entry in {@link ALLOWED_REQUEST_ORIGINS}.
 * @see backend/tests/integration/test_route_surface.py -
 *   `test_client_unset_base_path_returns_404`, which asserts the same four paths server-side.
 */
export function unsetBaseBackendHandlers(): RestHandler[] {
  return [
    ...originScopedPatterns(TWEETS_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
      rest.get(pattern, (req, res, ctx) =>
        answerRouterNotFound(
          TWEETS_CONTRACT,
          {
            method: req.method,
            url: req.url,
            params: req.params,
            contentType: req.headers.get('content-type'),
            body: undefined,
            basePathPrefix: UNSET_BASE_PATH_PREFIX,
          },
          res,
          ctx,
        ),
      ),
    ),

    ...originScopedPatterns(TWEET_BY_ID_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
      rest.get<never, { tweetId: string }>(pattern, (req, res, ctx) =>
        answerRouterNotFound(
          TWEET_BY_ID_CONTRACT,
          {
            method: req.method,
            url: req.url,
            params: req.params,
            contentType: req.headers.get('content-type'),
            body: undefined,
            basePathPrefix: UNSET_BASE_PATH_PREFIX,
          },
          res,
          ctx,
        ),
      ),
    ),

    ...originScopedPatterns(TWEET_RESPONSES_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
      rest.post<string, { tweetId: string }>(pattern, (req, res, ctx) =>
        answerRouterNotFound(
          TWEET_RESPONSES_CONTRACT,
          {
            method: req.method,
            url: req.url,
            params: req.params,
            contentType: req.headers.get('content-type'),
            body: req.body,
            basePathPrefix: UNSET_BASE_PATH_PREFIX,
          },
          res,
          ctx,
        ),
      ),
    ),

    ...originScopedPatterns(GENERATE_RESPONSE_CONTRACT.path, UNSET_BASE_PATH_PREFIX).map((pattern) =>
      rest.post<{ tweetId: string }>(pattern, (req, res, ctx) =>
        answerRouterNotFound(
          GENERATE_RESPONSE_CONTRACT,
          {
            method: req.method,
            url: req.url,
            params: req.params,
            contentType: req.headers.get('content-type'),
            body: req.body,
            basePathPrefix: UNSET_BASE_PATH_PREFIX,
          },
          res,
          ctx,
        ),
      ),
    ),
  ];
}

/** How {@link configuredBaseBackendHandlers} resolves `Depends(get_db)`. */
export interface ConfiguredBaseBackendOptions {
  /**
   * `true` to answer as the application does once a test has installed a SQLAlchemy-shaped stand-in through
   * `app.dependency_overrides[app.db.firestore.get_db]`, which is the only way `GET /tweets` reaches `200`.
   *
   * Defaults to `false`: the dependency yields the Firestore `Client` it yields in the assembled application,
   * which has no `query` attribute, so every endpoint that opens a query raises.
   *
   * @see backend/tests/integration/test_http_tweets.py -
   *   `test_a_firestore_client_declares_no_query_attribute` asserts the missing attribute against the real
   *   class, and `test_get_tweets_resolves_the_declared_dependency` shows the unoverridden request builds that
   *   client rather than a stand-in.
   */
  readonly dependencyOverridden?: boolean;
}

/**
 * Every route as the assembled application answers it once `REACT_APP_API_BASE_URL` is
 * {@link CONFIGURED_BASE_URL}, so the request reaches the backend's own path.
 *
 * The three stages a request passes through are reproduced in the order fastapi applies them; the stage that
 * answers decides the status:
 *
 * 1. **Routing.** The path is one the backend declares, so routing succeeds - that is the difference from
 *    {@link unsetBaseBackendHandlers} - except for `POST /generate-response`, which no router declares under
 *    any base and which is therefore still `404`.
 * 2. **Query coercion.** `GET /tweets` declares `skip: int = 0` and `limit: int = 100`. Every declared
 *    parameter the query does not coerce is reported, in the order line 12 declares them, as `422` with one
 *    `detail` record each. This happens **before** the endpoint body runs and before the injected database is
 *    touched, so it is independent of `dependencyOverridden`. `page`, which every caller sends and the backend
 *    does not declare, is ignored at this stage exactly as fastapi ignores it.
 * 3. **Endpoint execution.** Only now does the injected object matter: unoverridden it has no `query`, so the
 *    endpoint raises and starlette answers `500` with the plain-text body `Internal Server Error`; overridden,
 *    `GET /tweets` answers `200` with the list, while both tweet-detail routes still answer `500` because they
 *    read `Tweet.id`, which the pydantic model does not declare.
 *
 * Each of those three answers is fixed by a backend case asserting the same disposition, so no value here is a
 * frontend literal:
 *
 * | This factory answers | Backend case that fixes it, in `backend/tests/integration/` |
 * | --- | --- |
 * | `GET /tweets` `500` + plain text, dependency not overridden | `test_http_tweets.py::test_get_tweets_returns_500_without_an_override` |
 * | `GET /tweets` `422`, either disposition | `test_http_tweets.py::test_get_tweets_rejects_a_malformed_value_before_the_dependency_fails` |
 * | `GET /tweets` `200` + list, dependency overridden | `test_http_tweets.py::test_get_tweets_returns_serialized_tweet` |
 * | `GET /tweets/{id}` and `POST /tweets/{id}/responses` `500` | `test_http_tweets.py::test_get_tweet_by_id_returns_500_without_an_override` and `test_generate_response_returns_500_without_an_override` |
 * | `POST /generate-response` `404` | `test_route_surface.py` - the path no router declares |
 *
 * @param options - See {@link ConfiguredBaseBackendOptions}.
 * @returns One handler per route in {@link ROUTE_CONTRACTS}, per entry in {@link ALLOWED_REQUEST_ORIGINS}.
 * @see backend/tests/integration/test_http_tweets.py - the server-side assertions of every status and body
 *   this factory returns.
 */
export function configuredBaseBackendHandlers(
  options: ConfiguredBaseBackendOptions = {},
): RestHandler[] {
  const dependencyOverridden = options.dependencyOverridden === true;

  return [
    ...originScopedPatterns(TWEETS_CONTRACT.path, CONFIGURED_BASE_PATH_PREFIX).map((pattern) =>
      rest.get(pattern, (req, res, ctx) => {
        const screened = screenRequest(TWEETS_CONTRACT, {
          method: req.method,
          url: req.url,
          params: req.params,
          contentType: req.headers.get('content-type'),
          body: undefined,
          basePathPrefix: CONFIGURED_BASE_PATH_PREFIX,
        });

        /* Stage 2: every parameter that fails coercion, in declaration order. */
        const failing = failingIntegerParameters(screened.query);
        if (failing.length > 0) {
          record(screened, BACKEND_UNPROCESSABLE_STATUS);
          return res(
            ctx.status(BACKEND_UNPROCESSABLE_STATUS),
            ctx.json(backendIntegerCoercionErrorBody(failing)),
          );
        }

        /* Stage 3. */
        if (!dependencyOverridden) {
          return answerServerError(screened, res, ctx);
        }

        record(screened, 200);
        return res(ctx.status(200), ctx.json(makeDefaultTweets()));
      }),
    ),

    ...originScopedPatterns(TWEET_BY_ID_CONTRACT.path, CONFIGURED_BASE_PATH_PREFIX).map((pattern) =>
      rest.get<never, { tweetId: string }>(pattern, (req, res, ctx) =>
        answerServerError(
          screenRequest(TWEET_BY_ID_CONTRACT, {
            method: req.method,
            url: req.url,
            params: req.params,
            contentType: req.headers.get('content-type'),
            body: undefined,
            basePathPrefix: CONFIGURED_BASE_PATH_PREFIX,
          }),
          res,
          ctx,
        ),
      ),
    ),

    ...originScopedPatterns(TWEET_RESPONSES_CONTRACT.path, CONFIGURED_BASE_PATH_PREFIX).map((pattern) =>
      rest.post<string, { tweetId: string }>(pattern, (req, res, ctx) =>
        answerServerError(
          screenRequest(TWEET_RESPONSES_CONTRACT, {
            method: req.method,
            url: req.url,
            params: req.params,
            contentType: req.headers.get('content-type'),
            body: req.body,
            basePathPrefix: CONFIGURED_BASE_PATH_PREFIX,
          }),
          res,
          ctx,
        ),
      ),
    ),

    ...originScopedPatterns(GENERATE_RESPONSE_CONTRACT.path, CONFIGURED_BASE_PATH_PREFIX).map((pattern) =>
      rest.post<{ tweetId: string }>(pattern, (req, res, ctx) =>
        answerRouterNotFound(
          GENERATE_RESPONSE_CONTRACT,
          {
            method: req.method,
            url: req.url,
            params: req.params,
            contentType: req.headers.get('content-type'),
            body: req.body,
            basePathPrefix: CONFIGURED_BASE_PATH_PREFIX,
          },
          res,
          ctx,
        ),
      ),
    ),
  ];
}
