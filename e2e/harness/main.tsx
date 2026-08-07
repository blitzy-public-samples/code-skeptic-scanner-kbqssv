/**
 * Entry point for the Playwright end-to-end harness.
 *
 * Declares its own route table over the real component modules in
 * `frontend/src/components`, mirroring the four routes that
 * `frontend/src/app.tsx` declares at lines 20-23.
 *
 * `frontend/src/app.tsx` is deliberately not mounted: it imports `store` from
 * `@/store`, whose reducer is invalid, imports a `setupInterceptors` symbol that
 * `frontend/src/services/api.ts` never exports, and default-imports
 * `TweetManagement`, which has only a named export. The store below is built from
 * the slices' own default reducers instead.
 *
 * Resolution of the extension-less component files and of the specifiers that
 * have no implementation is handled by `e2e/vite.harness.config.ts`.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';

import RealTimeFeed from '@/components/Dashboard';
import { TweetList } from '@/components/TweetManagement';
import TrendCharts from '@/components/Analytics';
import TwitterAPISettings from '@/components/Configuration';

import tweetReducer from '@/store/tweetSlice';
import configReducer from '@/store/configSlice';

/** Valid store over the two slices' default reducers. */
const store = configureStore({
  reducer: {
    tweets: tweetReducer,
    config: configReducer,
  },
});

/**
 * `frontend/src/components/Analytics` requires a `dateRange` prop and reads both
 * members. Fixed values keep the rendered output identical on every run.
 */
const DATE_RANGE = { startDate: '2024-01-01', endDate: '2024-01-31' };

/** `frontend/src/components/TweetManagement` requires a `filters` prop. */
const FILTERS = {};

function Harness(): JSX.Element {
  return (
    <Provider store={store}>
      <BrowserRouter>
        <nav data-testid="harness-nav">
          <Link to="/">Dashboard</Link>
          <Link to="/tweets">Tweets</Link>
          <Link to="/analytics">Analytics</Link>
          <Link to="/configuration">Configuration</Link>
        </nav>
        <main data-testid="harness-outlet">
          <Routes>
            <Route path="/" element={<RealTimeFeed />} />
            <Route path="/tweets" element={<TweetList filters={FILTERS} />} />
            <Route path="/analytics" element={<TrendCharts dateRange={DATE_RANGE} />} />
            <Route path="/configuration" element={<TwitterAPISettings />} />
          </Routes>
        </main>
      </BrowserRouter>
    </Provider>
  );
}

const container = document.getElementById('root');
if (container === null) {
  throw new Error('harness/index.html must provide an element with id "root"');
}

ReactDOM.createRoot(container).render(<Harness />);
