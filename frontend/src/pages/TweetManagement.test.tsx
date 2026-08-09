/**
 * Suite over `frontend/src/pages/TweetManagement.tsx` - the one module in `src/pages` that mounts.
 *
 * Two properties of the page's own imports are what make it mountable, and both are load-bearing for the
 * cases below:
 *
 * 1. Line 4 imports `useAppSelector` from `@/store`, and no line calls it. Because the binding is never used
 *    as a value, the emit this suite runs against drops the `@/store` require outright: the compiled page
 *    requires `react/jsx-runtime`, `react`, `@/components/TweetManagement` and `@/services/twitterService`
 *    and nothing else, so `src/store/index.ts` is never evaluated here and neither is the invalid-reducer
 *    store its line 15 builds. Were the require retained, the binding would still be inert: that module
 *    exports `setupStore` and `store` at runtime and nothing else, its two remaining exports being
 *    TypeScript types. `pages/Dashboard.tsx`, `pages/Analytics.tsx` and `pages/Configuration.tsx` each call
 *    the store hook they import, which both keeps their require and throws on the `undefined` it resolves.
 * 2. Line 2 named-imports `TweetList`, `TweetCard` and `ResponseGenerator` from
 *    `@/components/TweetManagement`, whose sole export is `TweetList` at its line 17. `TweetCard` and
 *    `ResponseGenerator` are therefore `undefined`. React receives neither: `selectedTweet` starts `null`
 *    (line 11) and the only block that instantiates them is guarded on it (lines 44-49).
 *
 * Nothing in the page's subtree is substituted, so the real `TweetList` mounts and its own mount effect
 * reaches `getTweets`, which `src/services/twitterService.ts` does not export. The resulting `TypeError` is
 * caught and logged by the component, and that log is part of what this page does on mount; it is pinned
 * exactly below.
 *
 * The cases that assert that log identify it by its own first argument, the marker constant declared below,
 * and read the error it carries as that call's second argument.
 *
 * @see frontend/src/components/TweetManagement.test.tsx - the suite over the child component itself.
 * @see frontend/src/store/index.test.ts - the suite over the invalid-reducer store this page never loads.
 */

import { waitFor } from '@testing-library/react';

import TweetManagement from './TweetManagement';
import { renderWithProviders } from '../test-utils/render';

/** Text of the page's line-35 `<h1>`. */
const PAGE_HEADING = 'Tweet Management';

/** Heading level of that element: it is an `<h1>`, and the page renders no other heading. */
const PAGE_HEADING_LEVEL = 1;

/** First argument of the child component's line-35 `console.error`, a literal in its source. */
const FETCH_ERROR_MARKER = 'Error fetching tweets:';

/**
 * What the `TypeError` the child records as that call's second argument must say.
 *
 * Two semantic fragments rather than the whole message. The full text - which reads
 * `(0 , twitterService_1.getTweets) is not a function` under the current toolchain - is built from
 * things that are not this page's contract: `twitterService_1` is the local alias ts-jest's CommonJS
 * emit happens to give the `@/services/twitterService` namespace, `(0 , …)` with its single leading
 * space is how V8 currently renders an indirect callee, and both would change with a module target, a
 * transformer or a V8 version without anything about the product changing. What *is* the contract is
 * that the missing export is named and that calling it failed, so that is what these match.
 */
const MISSING_GET_TWEETS_FRAGMENTS = [/getTweets/, /is not a function/] as const;

/** Number of times the child's mount effect runs: its `filters` dependency is the page's stable initialiser. */
const EXPECTED_MOUNT_FETCHES = 1;

describe('pages/TweetManagement', () => {
  let errorSpy: jest.SpyInstance;

  beforeEach(() => {
    /* Records the child's fetch-failure log, which the cases below assert, and keeps it out of the output. */
    errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  /** Every recorded `console.error` call whose first argument is the child's fetch-failure marker. */
  function fetchFailureCalls(): unknown[][] {
    return errorSpy.mock.calls.filter(([marker]) => marker === FETCH_ERROR_MARKER);
  }

  /**
   * Renders the page and returns once its mount fetch has settled, so every case starts from the same
   * committed DOM.
   */
  async function mountPage() {
    const rendered = renderWithProviders(<TweetManagement />);

    await waitFor(() => expect(fetchFailureCalls()).toHaveLength(EXPECTED_MOUNT_FETCHES));

    return rendered;
  }

  it('renders its heading and content wrapper inside the tweet-management container', async () => {
    const { container, getByRole } = await mountPage();

    const heading = getByRole('heading', { level: PAGE_HEADING_LEVEL, name: PAGE_HEADING });

    expect(heading).toBeInTheDocument();
    expect(heading.tagName).toBe('H1');
    expect(heading.textContent).toBe(PAGE_HEADING);

    /* Lines 34-36: the heading and the content wrapper are both children of the outer container. */
    const root = container.querySelector('div.tweet-management');

    expect(root).not.toBeNull();
    expect(root).toContainElement(heading);

    const content = root?.querySelector('div.tweet-management__content');

    expect(content).not.toBeNull();
    expect(content).toBeInTheDocument();
  });

  it('mounts the real TweetList, which renders an empty tweet-list container', async () => {
    const { container } = await mountPage();

    /*
     * The child's line-58 element. Its line-59 map produces nothing because `getTweets` threw before any
     * tweet was appended, and its line-62 indicator is gone because `finally` cleared `loading` in the same
     * turn the throw was caught - so the container is committed and empty.
     */
    const list = container.querySelector<HTMLElement>('div.tweet-list');

    expect(list).not.toBeNull();
    expect(list).toBeInTheDocument();
    expect(list).toBeEmptyDOMElement();
    expect(list?.textContent).toBe('');

    /* Line 37: the child is rendered inside the content wrapper, not beside it. */
    expect(container.querySelector('div.tweet-management__content')).toContainElement(list);
  });

  it('records the missing getTweets export once, as a two-argument TypeError log', async () => {
    await mountPage();

    expect(errorSpy).toHaveBeenCalledWith(FETCH_ERROR_MARKER, expect.any(TypeError));

    /*
     * One record, not two: the child's effect depends on `[filters, page]`, the page supplies the same
     * `{}` from its line-12 initialiser on every render, and neither value changes while this page is
     * mounted.
     */
    const failures = fetchFailureCalls();

    expect(failures).toHaveLength(EXPECTED_MOUNT_FETCHES);

    /* Two arguments, a marker and an error - the shape a spy records for `console.error(a, b)`. */
    const [failure] = failures;

    expect(failure).toHaveLength(2);

    const [marker, recorded] = failure;

    expect(marker).toBe(FETCH_ERROR_MARKER);
    expect(recorded).toBeInstanceOf(TypeError);

    /* The missing export is named, and calling it is what failed. */
    const message = (recorded as TypeError).message;

    MISSING_GET_TWEETS_FRAGMENTS.forEach((fragment) => expect(message).toMatch(fragment));
    expect(String(recorded)).toMatch(/^TypeError: /);
  });

  it('omits the selected-tweet block, leaving the undefined TweetCard unreached', async () => {
    const { container } = await mountPage();

    /* Lines 44-49 are guarded on `selectedTweet`, which is still its line-11 `null`. */
    expect(container.querySelector('.tweet-management__selected-tweet')).toBeNull();

    /*
     * The same absence stated positively: the content wrapper holds the child component and nothing else,
     * so no element built from the `undefined` `TweetCard` or `ResponseGenerator` bindings was committed.
     */
    const content = container.querySelector('div.tweet-management__content');

    expect(content?.children).toHaveLength(1);
    expect(content?.firstElementChild).toBe(container.querySelector('div.tweet-list'));
  });
});
