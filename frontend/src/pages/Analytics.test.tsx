/**
 * The suite for `frontend/src/pages/Analytics.tsx`, whose single export is the default `Analytics`
 * page component.
 *
 * Every test below is written out in full, collected, and skipped individually. The subject cannot be
 * mounted by any test in this repository, for three reasons that hold independently of one another.
 *
 * 1. **`useAppSelector` is not a function.** The subject imports it at L4 from `@/store` and calls
 *    it at L13. `frontend/src/store/index.ts` has two runtime exports, `setupStore` (L5) and
 *    `store` (L15); its remaining two, L17-18, are TypeScript types and are erased by the
 *    transform. No module in this repository exports `useAppSelector` or `useAppDispatch` -
 *    `frontend/src/store/index.test.ts` asserts their absence from that module's export set. Under
 *    the CommonJS emit the named import binds `undefined`, so L13 calls `undefined`.
 *
 * 2. **There is no `user` slice.** L13 selects `state.user` and L18 and L27 read `user.id`. No
 *    slice named `user` exists anywhere under `frontend/src`, and the store
 *    `frontend/src/test-utils/render.tsx` builds is keyed by `tweets` and `config` only, as is the
 *    one `frontend/src/store/index.ts` configures. Separately, the repository's user shape -
 *    `frontend/src/schema/userSchema.ts` - declares `user_id` and no `id`.
 *
 * 3. **`@/components/Analytics` exports one symbol, and it is a default.** That module - an
 *    extension-less file - ends at L73 with `export default TrendCharts`. The subject's L2
 *    `import { TrendCharts, AIToolComparison, UserEngagement }` therefore binds all three to
 *    `undefined`, and L39-41 render them. That failure is asynchronous: L29-31 returns
 *    `Loading...` until `analyticsData` is set. The one component that does exist takes a
 *    `dateRange` prop, where L39 passes `data`.
 *
 * The group below is an ordinary `describe`, so this module is collected and every specifier in it
 * resolves on each run. Each test is marked `it.skip` and carries {@link BLOCKER} - which names the
 * first of the three - in its own title, so the reason travels with the identity a result reader
 * sees. `frontend/jest.config.js` gives `jest-junit` a `titleTemplate` that prefixes each test's
 * name with its ancestor titles, so both strings reach every `<testcase>` this file contributes to
 * `frontend/reports/jest-junit.xml`. No blanket `describe.skip` is used.
 *
 * ## The module graph still loads
 *
 * None of the three is an import-time failure: an absent named export binds `undefined` rather than
 * throwing. Importing the subject does load `@/components/Analytics`, `@/store` and
 * `@/services/analyticsService`, and `frontend/src/store/index.ts` L15 calls `setupStore()` while
 * doing so, which logs Redux's invalid-reducer notice. Nothing there prevents collection, so this
 * file is reported as skipped rather than as a suite that failed to load.
 *
 * `@/services/analyticsService` is the one specifier here with no implementation under
 * `frontend/src/services`; `frontend/jest.config.js` maps it to
 * `frontend/src/test-utils/stubs/analyticsService.ts`, whose `getAnalyticsData` takes the three
 * arguments L18 passes and resolves with the three members L39-41 read. The `jest.mock` below
 * replaces that stub with an automock, and `beforeEach` installs this suite's own resolution.
 *
 * This file defines no store hook, adds no `user` slice, seeds no `user` state, mocks neither
 * `@/store` nor `@/components/Analytics`, and installs no canvas or resize-observer shim. It
 * asserts no thrown error in place of the skip.
 *
 * @see frontend/src/pages/Analytics.tsx - the module under test.
 * @see frontend/src/store/index.ts - the two runtime exports named in item 1.
 * @see frontend/src/store/index.test.ts - the existing oracle for the two absent hook exports.
 * @see frontend/src/components/Analytics - the default-only module named in item 3.
 * @see frontend/src/test-utils/stubs/analyticsService.ts - the mapped stub and its contract.
 * @see frontend/src/test-utils/render.tsx - `renderWithProviders`, the shared mount harness.
 * @see frontend/TESTING.md - the stub substitutions and the shared harness.
 * @see docs/testing/TRACEABILITY-MATRIX.md - row G2, the disposition this suite implements: a test
 *   per page, three of them skipped with a reason naming the missing hook.
 * @see docs/testing/DECISION-LOG.md - row D148 for the boundary these comments observe, and row D35
 *   for the coverage gate, which does not include `src/pages`.
 */

import { screen, waitFor } from '@testing-library/react';

import { getAnalyticsData } from '@/services/analyticsService';
import { renderWithProviders } from '@/test-utils/render';

import Analytics from './Analytics';

/*
 * Hoisted above the imports by the transform. Replaces the stub the mapper resolves
 * `@/services/analyticsService` to; `beforeEach` installs this suite's default resolution.
 */
jest.mock('@/services/analyticsService');

const getAnalyticsDataMock = jest.mocked(getAnalyticsData);

/** Title of the group below, which is an ordinary `describe` so this module stays collected. */
const SUITE_TITLE = 'pages/Analytics (src/pages/Analytics.tsx)';

/**
 * Blocker carried by every skipped test identity below.
 *
 * Jest's skip takes no reason argument, so the title is where one goes. It is appended to each
 * individual test rather than declared once on the group: a blanket `describe.skip` leaves each
 * `<testcase>` in `frontend/reports/jest-junit.xml` marked skipped with no reason of its own, and a
 * reader of one result then has nothing to go on. `frontend/jest.config.js` gives `jest-junit` a
 * `titleTemplate` that prefixes each name with its ancestor titles, so both {@link SUITE_TITLE} and
 * this string reach every `<testcase>` this file contributes.
 *
 * It names the first of the three reasons in the module docstring - the one that raises first - and
 * the module whose export set does not contain it.
 */
const BLOCKER =
  'BLOCKED: src/store/index.ts exports no useAppSelector, so src/pages/Analytics.tsx line 13 ' +
  'raises TypeError: useAppSelector is not a function';

/** Accessible name of the subject's L35 heading. */
const ANALYTICS_HEADING = 'Analytics Dashboard';

/** The whole of the subject's pre-data output, L29-31. */
const LOADING_TEXT = 'Loading...';

/** First of the two arguments the subject's `catch` block passes to `console.error` at L21. */
const FETCH_FAILURE_PREFIX = 'Error fetching analytics data:';

/** Message of the rejection the error case below installs. */
const FETCH_REJECTION_MESSAGE = 'analytics fetch failed';

/**
 * Fragment React logs when a state update lands outside `act`. The `afterEach` below asserts that
 * nothing the `console.error` spy recorded contains it.
 */
const ACT_WARNING_FRAGMENT = 'not wrapped in act';

/**
 * Third argument the subject passes to `getAnalyticsData` at L18: the `id` of the object its L13
 * selector returned.
 *
 * The subject reads `user.id`, while `frontend/src/schema/userSchema.ts` declares `user_id`. Both
 * the slice that would hold this value and the `id` member itself are absent, so this is the value
 * a `user` slice would have to carry for the assertion below to hold.
 */
const EXPECTED_USER_ID = 'user-1';

/**
 * The resolution `getAnalyticsData` is given by default: non-falsy, so the subject's L29 guard
 * falls through, and carrying exactly the three members L39-41 read. Its shape mirrors the
 * `AnalyticsSummary` the mapped stub resolves with, which the automock above removes.
 *
 * Fixed literals throughout - nothing here is derived from the clock or from a random source.
 */
const ANALYTICS_SUMMARY = {
  trends: {
    labels: ['2024-01-01', '2024-01-02', '2024-01-03'],
    values: [4, 9, 6],
  },
  aiToolComparison: [
    { tool: 'GitHub Copilot', mentions: 9, averageDoubtRating: 0.8 },
    { tool: 'ChatGPT', mentions: 6, averageDoubtRating: 0.6 },
  ],
  userEngagement: {
    totalLikes: 120,
    totalRetweets: 45,
    totalReplies: 18,
  },
};

/** A member of the resolved summary that the subject forwards to one of its three children. */
type ForwardedMember = 'trends' | 'aiToolComparison' | 'userEngagement';

/** The three forwarded members, in the order L39-41 read them. */
const FORWARDED_MEMBERS: ForwardedMember[] = ['trends', 'aiToolComparison', 'userEngagement'];

/**
 * A resolution equal in value to {@link ANALYTICS_SUMMARY} whose three forwarded members are
 * accessors, paired with the log of the reads they record.
 *
 * The subject reads each member as it builds the child element it forwards that member to, so the
 * log is what the subject asked the resolved object for and in which order. It is the observable
 * this file has for forwarding: the three children are the `undefined` bindings of item 3 in the
 * module docstring, and neither they nor the subject are replaced here.
 *
 * @returns The resolution to install, and the array each read appends to.
 */
function summaryWithReadLog(): {
  summary: typeof ANALYTICS_SUMMARY;
  reads: ForwardedMember[];
} {
  const reads: ForwardedMember[] = [];

  const summary = {
    get trends() {
      reads.push('trends');
      return ANALYTICS_SUMMARY.trends;
    },
    get aiToolComparison() {
      reads.push('aiToolComparison');
      return ANALYTICS_SUMMARY.aiToolComparison;
    },
    get userEngagement() {
      reads.push('userEngagement');
      return ANALYTICS_SUMMARY.userEngagement;
    },
  };

  return { summary, reads };
}

let consoleError: jest.SpyInstance;

/** Every `console.error` argument recorded so far, flattened to one string per call. */
function consoleErrorText(): string {
  return consoleError.mock.calls.map((args: unknown[]) => args.map(String).join(' ')).join('\n');
}

/**
 * Renders the subject and waits for the render that follows the fetch it starts on mount.
 *
 * The subject fetches from an effect and stores the result in state, so its loaded markup - L34-42 -
 * only exists on the render that the resolution triggers. Awaiting the heading is what settles that
 * chain inside `act`.
 *
 * @returns Testing Library's result for the mounted subject.
 */
async function renderLoaded() {
  const result = renderWithProviders(<Analytics />);

  await screen.findByRole('heading', { level: 1, name: ANALYTICS_HEADING });

  return result;
}

describe(SUITE_TITLE, () => {
  beforeEach(() => {
    getAnalyticsDataMock.mockReset();
    getAnalyticsDataMock.mockResolvedValue(ANALYTICS_SUMMARY);

    // Scoped to this suite and restored below. `frontend/src/test-utils/setup-jest.ts` leaves
    // `console` untouched, so this is the only spy on it while these tests run.
    consoleError = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    try {
      expect(consoleErrorText()).not.toContain(ACT_WARNING_FRAGMENT);
    } finally {
      consoleError.mockRestore();
    }
  });

  it.skip(`renders "Loading..." and nothing else until the mount fetch settles - ${BLOCKER}`, async () => {
    const { container } = renderWithProviders(<Analytics />);

    // Asserted before the fetch is given a turn: `analyticsData` is still the `null` L11 starts it
    // at, so L29-31 is the whole output and none of L34-42 exists yet.
    expect(screen.getByText(LOADING_TEXT)).toBeInTheDocument();
    expect(container.querySelector('div.analytics-page')).toBeNull();

    // Settles the pending fetch inside `act`, so the state update it schedules is applied here
    // rather than after this test has finished.
    await screen.findByRole('heading', { level: 1, name: ANALYTICS_HEADING });
  });

  it.skip(`renders the analytics-page shell with its heading and its empty date-range picker - ${BLOCKER}`, async () => {
    const { container } = await renderLoaded();

    const page = container.querySelector('div.analytics-page');
    expect(page).not.toBeNull();

    // The heading is inside the page container rather than merely somewhere in the document.
    expect(page).toContainElement(screen.getByRole('heading', { level: 1, name: ANALYTICS_HEADING }));

    // L36-38 is a container holding a comment: no element children and no text.
    const picker = container.querySelector('div.date-range-picker');
    expect(picker).not.toBeNull();
    expect(picker).toBeEmptyDOMElement();

    // The pre-data branch is gone once `analyticsData` is set.
    expect(screen.queryByText(LOADING_TEXT)).toBeNull();

    // The subject reports nothing on the path where the fetch resolves.
    expect(consoleError).not.toHaveBeenCalled();
  });

  it.skip(`calls getAnalyticsData once with the two dateRange dates and the selected user id - ${BLOCKER}`, async () => {
    await renderLoaded();

    expect(getAnalyticsDataMock).toHaveBeenCalledTimes(1);

    const call = getAnalyticsDataMock.mock.calls[0];

    // Three arguments and no fourth: L18 passes the two range ends and the id, nothing more.
    expect(call).toHaveLength(3);

    // L12 builds both ends of the range with `new Date()`, so each arrives as a `Date` instance.
    expect(call[0]).toBeInstanceOf(Date);
    expect(call[1]).toBeInstanceOf(Date);

    expect(call[2]).toBe(EXPECTED_USER_ID);
  });

  it.skip(`forwards trends, aiToolComparison and userEngagement to its three child components - ${BLOCKER}`, async () => {
    const { summary, reads } = summaryWithReadLog();
    getAnalyticsDataMock.mockResolvedValue(summary);

    await renderLoaded();

    // One render of the loaded tree, so one read of each member, in the order L39-41 create the
    // elements they are forwarded to. A member wired to the wrong child is a difference here.
    expect(reads).toEqual(FORWARDED_MEMBERS);
  });

  it.skip(`fetches once on mount and does not refetch when re-rendered - ${BLOCKER}`, async () => {
    const { rerender } = await renderLoaded();

    expect(getAnalyticsDataMock).toHaveBeenCalledTimes(1);

    // Both members of the L27 dependency array keep their identity across a re-render: `dateRange`
    // is state whose L12 initial value is built once and whose setter has no call site, and
    // `user.id` is read from the store rather than rebuilt per render.
    rerender(<Analytics />);

    await waitFor(() => {
      expect(getAnalyticsDataMock).toHaveBeenCalledTimes(1);
    });
  });

  it.skip(`swallows a getAnalyticsData rejection, logs it, and stays on "Loading..." - ${BLOCKER}`, async () => {
    const rejection = new Error(FETCH_REJECTION_MESSAGE);
    getAnalyticsDataMock.mockRejectedValue(rejection);

    const { container } = renderWithProviders(<Analytics />);

    await waitFor(() => {
      expect(consoleError).toHaveBeenCalledTimes(1);
    });

    // L21 passes a prefix string and the error object itself - two arguments, not one interpolated
    // message - so the error reaches the record unflattened.
    expect(consoleError).toHaveBeenCalledWith(FETCH_FAILURE_PREFIX, rejection);
    expect(consoleError.mock.calls[0]).toHaveLength(2);

    // The rejection did not propagate out of the effect, and `setAnalyticsData` never ran, so the
    // L29-31 branch still holds the render.
    expect(screen.getByText(LOADING_TEXT)).toBeInTheDocument();
    expect(container.querySelector('div.analytics-page')).toBeNull();
  });
});
