/**
 * Entry module of the Playwright end-to-end harness, loaded by
 * `e2e/harness/index.html` as `/main.tsx`.
 *
 * Mounts the four routed component modules of `frontend/src/components` into the
 * `#root` element, under a Redux store built from the two `frontend/src/store`
 * slice reducers and a `BrowserRouter`. `e2e/vite.harness.config.ts` supplies
 * module resolution for every specifier below.
 *
 * Adding a route takes one `<Route>` entry in the block at the bottom of this
 * file; `e2e/README.md` covers the harness end to end.
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

/** Shape of the `dateRange` prop that `@/components/Analytics` requires. */
interface DateRange {
  startDate: string;
  endDate: string;
}

// stable props identities
const EMPTY_FILTERS = {};
const ANALYTICS_DATE_RANGE: DateRange = {
  startDate: '2024-01-01',
  endDate: '2024-01-31',
};

// store
const store = configureStore({
  reducer: {
    tweets: tweetReducer,
    config: configReducer,
  },
});

// root element
const rootElement = document.getElementById('root');
if (rootElement === null) {
  throw new Error('e2e/harness/index.html must provide an element with id "root"');
}

// mount
createRoot(rootElement).render(
  <Provider store={store}>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RealTimeFeed />} />
        <Route path="/tweets" element={<TweetList filters={EMPTY_FILTERS} />} />
        <Route path="/analytics" element={<TrendCharts dateRange={ANALYTICS_DATE_RANGE} />} />
        <Route path="/configuration" element={<TwitterAPISettings />} />
      </Routes>
    </BrowserRouter>
  </Provider>,
);
