/**
 * msw request handlers for the frontend Jest suite, in two separately named layers. This module registers
 * handlers only - it constructs no server and makes no lifecycle call. See `frontend/TESTING.md` for how a
 * suite consumes it, `docs/testing/DECISION-LOG.md` for why it is shaped this way, and
 * `docs/testing/TRACEABILITY-MATRIX.md` for the per-route caller-to-backend mapping.
 *
 * ## Layer 1 - {@link frontendIsolationHandlers}, exported also as {@link handlers}
 *
 * TEST-ONLY nominal-success responses. They exist so a component or service suite can run without a
 * socket; they are **not** a model of the backend and a suite that only exercises them has covered no
 * integration. The status each of these four routes really answers with today, measured against the
 * assembled FastAPI app:
 *
 * | Route                              | Isolation layer | Real current outcome                                    |
 * |------------------------------------|-----------------|---------------------------------------------------------|
 * | `GET /tweets`                      | 200 + 3 tweets  | 200, but `page` is ignored; 422 when `limit` is not an int |
 * | `GET /tweets/{tweet_id}`           | 200 + 1 tweet   | 500 `Internal Server Error` (raises at `Tweet.id`)      |
 * | `POST /tweets/{tweet_id}/responses`| 200 + `response`| 500 `Internal Server Error` (raises at `Tweet.id`)      |
 * | `POST /generate-response`          | 200 + `generatedResponse` | 404 `{"detail":"Not Found"}` - no such route   |
 *
 * ## Layer 2 - {@link currentBackendBehaviorHandlers} and the `currentBehavior*Handler` factories
 *
 * The right-hand column above, reproduced byte for byte. A suite installs one through `server.use(...)` to
 * assert what the backend does today. These are never part of the default array.
 *
 * ## Request screening and the request log
 *
 * Every handler in both layers screens the request against the contract in {@link ROUTE_CONTRACTS} and
 * records it in the log that {@link recordedRequests} returns, so a suite asserts the exact query, path and
 * body it emitted rather than inferring correctness from a 200.
 *
 * The two layers act on a failed screening differently. In layer 1 a request that deviates from the
 * contract - an unknown or absent query key, a placeholder path parameter, an unexpected body, or an origin
 * outside {@link allowedRequestOrigins} - is answered with {@link CONTRACT_VIOLATION_STATUS} and a body
 * listing the violations, and never with a success status. In layer 2 the violations are recorded and the
 * response is whatever the backend returns for that request, including for a request no caller should
 * emit.
 *
 * ## API version
 *
 * msw 1.x: handlers are built with `rest`, resolvers have the form
 * `(req, res, ctx) => res(ctx.status(...), ctx.json(...))`.
 */

import { rest } from 'msw';
import type { RestHandler } from 'msw';

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
 * A function rather than an array: the tweets are rebuilt on every call, so each request is handed its own
 * objects and a suite that mutates a response changes nothing for the next one.
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

/** One entry of a FastAPI 422 `detail` array. */
export interface BackendValidationError {
  readonly loc: readonly [string, string];
  readonly msg: string;
  readonly type: string;
}

/**
 * The 422 body FastAPI returns when an `int` query parameter cannot be coerced, with `loc` naming the
 * parameter that failed.
 *
 * @param parameter - Name of the failing query parameter, `skip` or `limit` on `GET /tweets`.
 */
export function backendIntegerCoercionErrorBody(parameter: string): {
  readonly detail: readonly BackendValidationError[];
} {
  return {
    detail: [
      {
        loc: ['query', parameter],
        msg: 'value is not a valid integer',
        type: 'type_error.integer',
      },
    ],
  };
}

/** Query parameters `GET /tweets` declares and coerces to `int`. Anything else it ignores. */
const BACKEND_TWEETS_INT_PARAMETERS = ['skip', 'limit'] as const;

/** A value pydantic v1 coerces to `int`: optional sign, digits, surrounding whitespace tolerated. */
const INTEGER_VALUE = /^[+-]?\d+$/;

/**
 * Whether the backend coerces `value` to `int` without raising. `undefined` stands for an absent parameter,
 * which takes the route's default and always coerces.
 */
function coercesToInteger(value: string | undefined): boolean {
  return value === undefined || INTEGER_VALUE.test(value.trim());
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
  /** msw path pattern. Host-agnostic: the callers' base URL is the literal string `undefined`. */
  readonly pattern: string;
  /** Production functions that issue this request. */
  readonly callers: readonly string[];
  /** The request those callers emit, as it reaches msw. */
  readonly emittedRequest: string;
  /** The backend route and its declared parameters, or the absence of one. */
  readonly backendContract: string;
  /** Status and body the assembled application returns today. */
  readonly currentBackendOutcome: string;
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
  id: 'GET */tweets',
  method: 'GET',
  pattern: '*/tweets',
  callers: [
    'services/api.ts fetchTweets(page, limit)',
    'services/twitterService.ts getLatestTweets(count)',
    'components/Dashboard RealTimeFeed (getLatestTweets with no argument)',
  ],
  emittedRequest:
    'GET undefined/tweets?page=<page>&limit=<limit>; limit is the literal string "undefined" when ' +
    'getLatestTweets supplies only its first argument, and page is too when it supplies none',
  backendContract: 'GET /tweets, query skip:int=0 and limit:int=100, returns List[Tweet]',
  currentBackendOutcome:
    '200 with the tweet list when skip and limit coerce to int; 422 ' +
    '{"detail":[{"loc":["query","<param>"],"msg":"value is not a valid integer","type":"type_error.integer"}]} ' +
    'when either does not',
  isolationResponse: '200 with three schema-valid tweets, timestamps serialised to ISO-8601 strings',
  mismatches: [
    'page is not a declared backend parameter and is ignored; skip, which the backend paginates on, is never sent',
    'limit=undefined and page=undefined are answered 422 by the backend and 200 by the isolation layer',
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
  id: 'GET */tweets/:tweetId',
  method: 'GET',
  pattern: '*/tweets/:tweetId',
  callers: [
    'services/api.ts fetchTweetById(tweetId)',
    'services/twitterService.ts getTweetDetails(tweetId)',
  ],
  emittedRequest: 'GET undefined/tweets/<tweetId>, no query string, no body',
  backendContract: 'GET /tweets/{tweet_id}, returns Tweet, raises HTTPException(404) when absent',
  currentBackendOutcome:
    '500 with the plain-text body "Internal Server Error": the handler reads Tweet.id, which the pydantic ' +
    'model does not declare, so it raises before the 404 branch can be reached',
  isolationResponse: '200 with one schema-valid tweet whose tweet_id echoes the path parameter',
  mismatches: [
    'the backend answers 500 for every id; the isolation layer answers 200',
    'the declared 404 branch is unreachable, so no handler models it',
  ],
  expectation: {
    queryKeys: [],
    pathParams: ['tweetId'],
    body: 'none',
  },
};

const TWEET_RESPONSES_CONTRACT: RouteContract = {
  id: 'POST */tweets/:tweetId/responses',
  method: 'POST',
  pattern: '*/tweets/:tweetId/responses',
  callers: [],
  emittedRequest: 'POST undefined/tweets/<tweetId>/responses, no query string, no body',
  backendContract: 'POST /tweets/{tweet_id}/responses, no request body, returns Dict under the key "response"',
  currentBackendOutcome:
    '500 with the plain-text body "Internal Server Error", from the same Tweet.id access',
  isolationResponse: '200 with {"response": DEFAULT_TWEET_RESPONSE}',
  mismatches: [
    'no module under src/ calls this route; it is registered because the backend implements it',
    'the backend answers 500; the isolation layer answers 200',
  ],
  expectation: {
    queryKeys: [],
    pathParams: ['tweetId'],
    body: 'none',
  },
};

const GENERATE_RESPONSE_CONTRACT: RouteContract = {
  id: 'POST */generate-response',
  method: 'POST',
  pattern: '*/generate-response',
  callers: [
    'services/api.ts generateResponse(tweetId)',
    'services/llmService.ts generateTweetResponse(tweetId)',
  ],
  emittedRequest: 'POST undefined/generate-response, application/json body {"tweetId": "<tweetId>"}',
  backendContract: 'none - no router declares this path',
  currentBackendOutcome: '404 {"detail":"Not Found"}',
  isolationResponse: '200 with {"generatedResponse": DEFAULT_GENERATED_RESPONSE}',
  mismatches: [
    'the path does not exist on the backend; the nearest implemented route is POST /tweets/{tweet_id}/responses',
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
 * Origins a handler will answer. jsdom serves the suite from http://localhost, and the callers' base URL is
 * the literal string `undefined`, so every intercepted request is same-origin with the document.
 * ------------------------------------------------------------------------------------------------------ */

const DEFAULT_REQUEST_ORIGINS: readonly string[] = Object.freeze(['http://localhost', 'http://127.0.0.1']);

const requestOrigins = new Set<string>(DEFAULT_REQUEST_ORIGINS);

/**
 * The origins the handlers currently answer. A request from any other origin is screened out, so a base URL
 * pointing somewhere real surfaces as a failing test rather than as a mocked success.
 */
export function allowedRequestOrigins(): readonly string[] {
  return Object.freeze([...requestOrigins]);
}

/**
 * Adds an origin to {@link allowedRequestOrigins} for a suite that sets `REACT_APP_API_BASE_URL` to an
 * absolute URL on purpose.
 *
 * @param origin - Origin as `URL.origin` reports it, for example `https://api.example.test`.
 */
export function allowRequestOrigin(origin: string): void {
  requestOrigins.add(origin);
}

/** Restores {@link allowedRequestOrigins} to the two jsdom origins. */
export function resetAllowedRequestOrigins(): void {
  requestOrigins.clear();
  for (const origin of DEFAULT_REQUEST_ORIGINS) {
    requestOrigins.add(origin);
  }
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
  /** What the pattern's leading `*` matched, for example `http://localhost/undefined`. */
  readonly base: string;
  readonly pathname: string;
  /** Query string including its leading `?`, or `''` when there is none. */
  readonly search: string;
  /** Query parameters as sent, values unparsed, so `limit` reads back as the string `undefined`. */
  readonly query: Readonly<Record<string, string>>;
  /** Named path parameters the pattern captured, without the wildcard capture. */
  readonly pathParams: Readonly<Record<string, string>>;
  readonly contentType: string | null;
  /** Parsed JSON body, the empty string for a bodyless request, `undefined` for a GET. */
  readonly body: unknown;
  /** Status the handler answered with. */
  readonly status: number;
  /** Screening messages; empty when the request matched its contract. */
  readonly violations: readonly string[];
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

/** Empties the request log. Registered with `afterEach` automatically; safe to call again. */
export function resetRecordedRequests(): void {
  requestLog.length = 0;
}

/**
 * Registers {@link resetRecordedRequests} with Jest's `afterEach` so the log cannot carry entries from one
 * test into the next. Outside a test run `afterEach` is undefined and nothing is registered.
 */
function registerRequestLogReset(): void {
  const hook = (globalThis as { afterEach?: (teardown: () => void) => void }).afterEach;
  if (typeof hook === 'function') {
    hook(resetRecordedRequests);
  }
}

registerRequestLogReset();

/* ------------------------------------------------------------------------------------------------------ *
 * Screening.
 * ------------------------------------------------------------------------------------------------------ */

/** The parts of an msw request this module reads, named so a resolver passes them explicitly. */
interface RequestFacts {
  readonly method: string;
  readonly url: URL;
  /** `req.params`, which on a `*`-prefixed pattern also carries the wildcard capture under the key `0`. */
  readonly params: Readonly<Record<string, unknown>>;
  readonly contentType: string | null;
  readonly body: unknown;
}

/** A screened request: its normalised facts and every way it departs from its contract. */
interface ScreenedRequest {
  readonly contract: RouteContract;
  readonly facts: RequestFacts;
  readonly base: string;
  readonly query: Record<string, string>;
  readonly pathParams: Record<string, string>;
  readonly violations: readonly string[];
}

/** Path-parameter values that mean a caller interpolated a missing variable. */
const PLACEHOLDER_PATH_VALUES = ['', 'undefined', 'null', 'NaN'];

function stringifyParam(value: unknown): string {
  return Array.isArray(value) ? value.join(',') : String(value ?? '');
}

/** Named path parameters, with msw's numeric wildcard captures removed. */
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
 * Checks the origin against {@link allowedRequestOrigins}, the query keys against
 * {@link RequestExpectation.queryKeys} in both directions, each named path parameter against
 * {@link PLACEHOLDER_PATH_VALUES}, and the body against {@link RequestExpectation.body}, then applies the
 * route's own {@link RequestExpectation.validateQuery}.
 */
function screenRequest(contract: RouteContract, facts: RequestFacts): ScreenedRequest {
  const violations: string[] = [];
  const query: Record<string, string> = {};
  for (const [key, value] of facts.url.searchParams.entries()) {
    query[key] = value;
  }
  const pathParams = namedPathParams(facts.params);

  if (!requestOrigins.has(facts.url.origin)) {
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
    base: stringifyParam(facts.params['0']),
    query,
    pathParams,
    violations,
  };
}

/** Appends a screened request to the log under the status it was answered with. */
function record(screened: ScreenedRequest, status: number): void {
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
    }),
  );
}

/**
 * Records a screened-out request, writes its violations to `console.error` so they surface even when the
 * calling service swallows the rejection, and returns the body to answer it with.
 */
function rejectScreenedRequest(screened: ScreenedRequest): ContractViolationBody {
  record(screened, CONTRACT_VIOLATION_STATUS);

  const body: ContractViolationBody = Object.freeze({
    detail: CONTRACT_VIOLATION_DETAIL,
    handler: screened.contract.id,
    url: screened.facts.url.href,
    violations: Object.freeze([...screened.violations]),
  });

  // eslint-disable-next-line no-console
  console.error(
    `${CONTRACT_VIOLATION_DETAIL} [${screened.contract.id}] ${screened.facts.method} ${screened.facts.url.href}\n` +
      screened.violations.map((violation) => `  - ${violation}`).join('\n'),
  );

  return body;
}

/* ------------------------------------------------------------------------------------------------------ *
 * Layer 1 - frontend isolation. Test-only nominal responses; see the table in the module header for what
 * each of these routes really answers.
 * ------------------------------------------------------------------------------------------------------ */

/**
 * Nominal-success handlers, one per route in {@link ROUTE_CONTRACTS}, in that order. Adding a route is one
 * more `RouteContract` and one more `rest.<method>(...)` entry: no entry reads or branches through another.
 *
 * These responses are fixtures, not backend behaviour. A suite asserting an integration outcome installs
 * the matching entry from {@link currentBackendBehaviorHandlers} instead.
 */
export const frontendIsolationHandlers: RestHandler[] = [
  rest.get(TWEETS_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(TWEETS_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: undefined,
    });

    if (screened.violations.length > 0) {
      return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
    }

    record(screened, 200);
    return res(ctx.status(200), ctx.json(makeDefaultTweets()));
  }),

  rest.get<never, { tweetId: string }>(TWEET_BY_ID_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(TWEET_BY_ID_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: undefined,
    });

    if (screened.violations.length > 0) {
      return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
    }

    record(screened, 200);
    return res(ctx.status(200), ctx.json(makeTweet({ tweet_id: req.params.tweetId })));
  }),

  rest.post<string, { tweetId: string }>(TWEET_RESPONSES_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(TWEET_RESPONSES_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: req.body,
    });

    if (screened.violations.length > 0) {
      return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
    }

    record(screened, 200);
    return res(ctx.status(200), ctx.json({ response: DEFAULT_TWEET_RESPONSE }));
  }),

  rest.post<{ tweetId: string }>(GENERATE_RESPONSE_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(GENERATE_RESPONSE_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: req.body,
    });

    if (screened.violations.length > 0) {
      return res(ctx.status(CONTRACT_VIOLATION_STATUS), ctx.json(rejectScreenedRequest(screened)));
    }

    record(screened, 200);
    return res(ctx.status(200), ctx.json({ generatedResponse: DEFAULT_GENERATED_RESPONSE }));
  }),
];

/**
 * The array `msw-server.ts` spreads into `setupServer`. Same array as
 * {@link frontendIsolationHandlers}; the name is the one `frontend/TESTING.md` documents.
 */
export const handlers: RestHandler[] = frontendIsolationHandlers;

/* ------------------------------------------------------------------------------------------------------ *
 * Layer 2 - current backend behaviour. Each factory reproduces the status, body and content type the
 * assembled application returns today, as measured against that application.
 * ------------------------------------------------------------------------------------------------------ */

/**
 * `GET /tweets` as the backend answers it: 200 with the tweet list, or 422 when `skip` or `limit` does not
 * coerce to `int`, naming the first failing parameter. `page` is not a declared parameter, so it is read
 * back into the request log and otherwise ignored, exactly as FastAPI ignores it.
 */
export function currentBehaviorTweetsHandler(): RestHandler {
  return rest.get(TWEETS_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(TWEETS_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: undefined,
    });

    const failing = BACKEND_TWEETS_INT_PARAMETERS.find(
      (parameter) => !coercesToInteger(screened.query[parameter]),
    );

    if (failing !== undefined) {
      record(screened, BACKEND_UNPROCESSABLE_STATUS);
      return res(
        ctx.status(BACKEND_UNPROCESSABLE_STATUS),
        ctx.json(backendIntegerCoercionErrorBody(failing)),
      );
    }

    record(screened, 200);
    return res(ctx.status(200), ctx.json(makeDefaultTweets()));
  });
}

/**
 * `GET /tweets/{tweet_id}` as the backend answers it: 500 with the plain-text body `Internal Server Error`
 * for every id, because the handler reads `Tweet.id` before it can reach its 404 branch.
 */
export function currentBehaviorTweetByIdHandler(): RestHandler {
  return rest.get<never, { tweetId: string }>(TWEET_BY_ID_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(TWEET_BY_ID_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: undefined,
    });

    record(screened, BACKEND_SERVER_ERROR_STATUS);
    return res(
      ctx.status(BACKEND_SERVER_ERROR_STATUS),
      ctx.set('Content-Type', BACKEND_TEXT_CONTENT_TYPE),
      ctx.body(BACKEND_SERVER_ERROR_BODY),
    );
  });
}

/**
 * `POST /tweets/{tweet_id}/responses` as the backend answers it: 500 with the plain-text body
 * `Internal Server Error`, from the same `Tweet.id` access.
 */
export function currentBehaviorTweetResponsesHandler(): RestHandler {
  return rest.post<string, { tweetId: string }>(TWEET_RESPONSES_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(TWEET_RESPONSES_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: req.body,
    });

    record(screened, BACKEND_SERVER_ERROR_STATUS);
    return res(
      ctx.status(BACKEND_SERVER_ERROR_STATUS),
      ctx.set('Content-Type', BACKEND_TEXT_CONTENT_TYPE),
      ctx.body(BACKEND_SERVER_ERROR_BODY),
    );
  });
}

/**
 * `POST /generate-response` as the backend answers it: 404 `{"detail":"Not Found"}`, because no router
 * declares that path.
 */
export function currentBehaviorGenerateResponseHandler(): RestHandler {
  return rest.post<{ tweetId: string }>(GENERATE_RESPONSE_CONTRACT.pattern, (req, res, ctx) => {
    const screened = screenRequest(GENERATE_RESPONSE_CONTRACT, {
      method: req.method,
      url: req.url,
      params: req.params,
      contentType: req.headers.get('content-type'),
      body: req.body,
    });

    record(screened, BACKEND_NOT_FOUND_STATUS);
    return res(ctx.status(BACKEND_NOT_FOUND_STATUS), ctx.json(BACKEND_NOT_FOUND_BODY));
  });
}

/**
 * Every current-behaviour handler, in {@link ROUTE_CONTRACTS} order, for a suite that installs the whole
 * set through `server.use(...)`. Built fresh on each call so no handler instance is shared between tests.
 *
 * @returns The four handlers that reproduce today's 200-or-422, 500, 500 and 404.
 */
export function currentBackendBehaviorHandlers(): RestHandler[] {
  return [
    currentBehaviorTweetsHandler(),
    currentBehaviorTweetByIdHandler(),
    currentBehaviorTweetResponsesHandler(),
    currentBehaviorGenerateResponseHandler(),
  ];
}
