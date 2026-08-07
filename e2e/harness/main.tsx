/**
 * Entry module of the Playwright end-to-end harness, loaded by
 * `e2e/harness/index.html` as `/main.tsx`.
 *
 * Mounts the four routed component modules of `frontend/src/components` into the
 * `#root` element, under a Redux store built from the two `frontend/src/store`
 * slice reducers and a `BrowserRouter`. `e2e/vite.harness.config.ts` supplies
 * module resolution, and the default API responses, for every specifier below.
 *
 * Two of the four routes render a shell only, and a spec that supplies data able to
 * fill them in unmounts the route instead. Both are marked at their `<Route>` entry.
 *
 * Adding a route takes one `<Route>` entry in the block at the bottom of this
 * file; `e2e/README.md` covers the harness end to end.
 *
 * @see docs/testing/DECISION-LOG.md - section 4, the route-table and store decisions.
 */

import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
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
      <Routes>
        {/* Feed shell. Renders its heading and nothing else: every member of a
            non-empty tweet collection is rendered by the undefined `TweetCard`, an
            invalid element type that unmounts the route. The harness answers the
            collection request with `[]`. */}
        <Route path="/" element={<RealTimeFeed />} />
        <Route path="/tweets" element={<TweetList filters={EMPTY_FILTERS} />} />
        {/* Chart shell. Renders its heading and canvas: `harness/stubs/analyticsService.ts`
            always rejects, which holds the component on its caught-failure path and
            keeps it from constructing an unregistered `Chart`. */}
        <Route path="/analytics" element={<TrendCharts dateRange={ANALYTICS_DATE_RANGE} />} />
        <Route path="/configuration" element={<TwitterAPISettings />} />
      </Routes>
    </BrowserRouter>
  </Provider>,
);
