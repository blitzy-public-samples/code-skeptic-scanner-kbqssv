/**
 * Entry module of the Playwright end-to-end harness, loaded by
 * `e2e/harness/index.html` as `/main.tsx`.
 *
 * Mounts the four routed component modules of `frontend/src/components` into the
 * `#root` element, inside the document's single `<main>` landmark, under a Redux store
 * built from the two `frontend/src/store` slice reducers and a `BrowserRouter`.
 * `e2e/vite.harness.config.ts` supplies module resolution for every specifier below.
 *
 * Two of the four routes render a shell only, and a spec that supplies data able to fill them
 * in brings the whole page down instead of filling them: nothing here is an error boundary, so
 * a throw out of either component unmounts the entire root this file creates - the `<Provider>`,
 * the `<BrowserRouter>`, the `<main>` landmark and the `<Routes>` with it - leaving `#root`
 * empty and no route reachable until a reload. Both are marked at their `<Route>` entry.
 *
 * This file contains no error boundary, so that teardown is a property the specs observe rather
 * than one the harness contains.
 *
 * @see docs/testing/DECISION-LOG.md - row D396.
 * @see docs/testing/TRACEABILITY-MATRIX.md - rows G3, G4 and G14, the assertions that stand in
 *   for these two ceilings.
 *
 * Adding a route takes one `<Route>` entry in the block at the bottom of this
 * file; a path no entry matches renders {@link UnroutedPath}, which names it.
 * `e2e/README.md` covers the harness end to end.
 *
 * @see docs/testing/DECISION-LOG.md - section 4, the route-table and store decisions,
 *   and row D132 for the landmark.
 */

import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { BrowserRouter, Route, Routes, useLocation } from 'react-router-dom';
import { configureStore } from '@reduxjs/toolkit';

import tweetReducer from '@/store/tweetSlice';
import configReducer from '@/store/configSlice';

import RealTimeFeed from '@/components/Dashboard';
import { TweetList } from '@/components/TweetManagement';
import TrendCharts from '@/components/Analytics';
import TwitterAPISettings from '@/components/Configuration';

interface DateRange {
  startDate: string;
  endDate: string;
}

// Declared at module scope so each prop keeps one identity for the lifetime of
// the page: a fresh object per render would re-fire the effects that depend on it.
const EMPTY_FILTERS = {};
const ANALYTICS_DATE_RANGE: DateRange = {
  startDate: '2024-01-01',
  endDate: '2024-01-31',
};

/**
 * Names the condition on the element below and in its `data-harness-error` attribute, the
 * same way `harnessApiFailClosed` in `../vite.harness.config.ts` names
 * `harness-api-not-intercepted` in the body it answers an un-intercepted API request with.
 */
const UNROUTED_ERROR = 'harness-route-not-defined';

/**
 * Rendered for a path the route table below defines no element for.
 *
 * Without it such a path produced a document whose `<main>` was empty, which is also what
 * `/tweets` produces - that route's component renders an empty container - so a mistyped
 * path and a working route were indistinguishable on screen, and the only trace of the
 * difference was a development-mode router warning in the console.
 *
 * This element is reachable only when no route above it matches, so it adds nothing to any
 * of the four routed workspaces: what a spec sees at `/`, `/tweets`, `/analytics` and
 * `/configuration` is unchanged.
 *
 * @see docs/testing/DECISION-LOG.md - row D377.
 */
function UnroutedPath() {
  const { pathname } = useLocation();

  return (
    <div className="harness-unrouted" data-harness-error={UNROUTED_ERROR} role="status">
      <p>
        {UNROUTED_ERROR}: the harness route table defines no element for <code>{pathname}</code>.
      </p>
      <p>
        It defines <code>/</code>, <code>/tweets</code>, <code>/analytics</code> and{' '}
        <code>/configuration</code>. Add a <code>&lt;Route&gt;</code> to{' '}
        <code>e2e/harness/main.tsx</code> to serve this path.
      </p>
    </div>
  );
}

const store = configureStore({
  reducer: {
    tweets: tweetReducer,
    config: configReducer,
  },
});

const rootElement = document.getElementById('root');
if (rootElement === null) {
  throw new Error('e2e/harness/index.html must provide an element with id "root"');
}

createRoot(rootElement).render(
  <Provider store={store}>
    <BrowserRouter>
      {/* The one landmark of the document, so every routed component is inside named
          page structure rather than a bare `div`. It carries no styling and no
          chrome, so nothing here alters what a spec sees of the component itself.
          `Routes` renders one match, so the diagnostic entry at the bottom of the table
          never renders alongside a routed component. */}
      <main>
        <Routes>
          {/* Feed shell. Renders its heading and nothing else: every member of a
              non-empty tweet collection is rendered by the undefined `TweetCard`, an
              invalid element type whose throw unmounts this whole root - and React's
              unmount runs the component's own cleanup, so the 30 s poll is cleared and
              never reinstalled. A spec fulfils the collection request with `[]`. */}
          <Route path="/" element={<RealTimeFeed />} />
          <Route path="/tweets" element={<TweetList filters={EMPTY_FILTERS} />} />
          {/* Chart shell. Renders its heading and canvas whenever
              `harness/stubs/analyticsService.ts` rejects, which is every response that does
              not set its forwarding header, and which holds the component on its
              caught-failure path. The one spec that sets that header asserts the opposite:
              the component reaches an unregistered `Chart` and this whole root comes down. */}
          <Route path="/analytics" element={<TrendCharts dateRange={ANALYTICS_DATE_RANGE} />} />
          <Route path="/configuration" element={<TwitterAPISettings />} />
          {/* Last, and matched only when none of the four above is: names the path the
              table defines nothing for, rather than rendering an empty document. */}
          <Route path="*" element={<UnroutedPath />} />
        </Routes>
      </main>
    </BrowserRouter>
  </Provider>,
);
