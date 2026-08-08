/**
 * Colocated unit suite for `frontend/src/utils/dateUtils.ts`.
 *
 * The subject holds two exports and this file has one `describe` for each. `formatDate` is a
 * pass-through onto `dayjs(date).format(format)`; the assertions below check that the wrapper
 * delegates faithfully across a date-only pattern, a date-and-time pattern and the numeric half of
 * its `string | number` parameter. Dayjs's own token grammar is not exercised beyond that.
 *
 * `getTimeAgo` is a six-arm `if / else if` chain over `now.diff(inputDate, 'second')`. Its
 * sixteen cases sit in the two tables further down: eleven at and around each threshold, covering
 * every arm and both sides of all five plural ternaries, and five at the top edge of each arm.
 *
 * Two pins make the file deterministic, and both are installed from hooks:
 *
 * 1. The system clock is frozen at `FIXED_NOW` for the duration of every test. `dateUtils.ts`
 *    line 8 reads the current time through `dayjs()`.
 * 2. `process.env.TZ` is `'UTC'`; `dayjs(...).format(...)` renders local date parts. The effective
 *    pin is set in `frontend/jest.config.js`, before the workers are spawned. A test file's own
 *    `process.env` is a sandboxed copy whose writes leave V8's cached zone untouched, so the
 *    `beforeAll` hook below scopes and restores the variable for this file without itself
 *    changing the zone.
 *
 * Every input is derived from `FIXED_NOW`; every expectation is a literal string. Neither the
 * relative-time arithmetic nor the plural suffix is recomputed here.
 *
 * @see frontend/jest.config.js - the runner-level TZ pin these `formatDate` assertions rely on.
 * @see frontend/TESTING.md - this folder's arrangement and the fake-clock pitfall.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why the clock and the
 *   timezone are pinned the way they are, and for the options not taken.
 * @see docs/testing/TRACEABILITY-MATRIX.md - one row per `getTimeAgo` arm; each test title below
 *   names the arm, the source lines and the plural side it covers.
 */

import { formatDate, getTimeAgo } from './dateUtils';

/** The instant the clock is frozen at for every test in this file: `2024-06-15T12:00:00.000Z`. */
const FIXED_NOW = Date.UTC(2024, 5, 15, 12, 0, 0);

/**
 * ISO-8601 UTC timestamp exactly `seconds` before `FIXED_NOW`, so `getTimeAgo` measures a
 * difference of exactly `seconds`.
 *
 * `new Date(...)` with an explicit argument is unaffected by the fake clock, and `toISOString()`
 * renders UTC regardless of `process.env.TZ`.
 */
const isoSecondsAgo = (seconds: number): string =>
  new Date(FIXED_NOW - seconds * 1000).toISOString();

/** One `getTimeAgo` case: the measured difference, the literal oracle, and the arm it covers. */
interface TimeAgoCase {
  diff: number;
  expected: string;
  arm: string;
}

/**
 * At and around each threshold. Covers all six arms and both sides of all five plural ternaries.
 *
 * The threshold values are exclusive upper bounds, so a difference of exactly 60 fails
 * `diffInSeconds < 60` and lands in the minutes arm as the singular `'1 minute ago'`; 3600, 86400,
 * 2592000 and 31536000 behave the same way one arm further down each time.
 */
const THRESHOLD_CASES: TimeAgoCase[] = [
  { diff: 30, expected: '30 seconds ago', arm: 'seconds L12-13, no plural ternary' },
  { diff: 60, expected: '1 minute ago', arm: 'minutes L14-16 singular at the 60s threshold' },
  { diff: 120, expected: '2 minutes ago', arm: 'minutes L14-16 plural' },
  { diff: 3600, expected: '1 hour ago', arm: 'hours L17-19 singular at the 3600s threshold' },
  { diff: 7200, expected: '2 hours ago', arm: 'hours L17-19 plural' },
  { diff: 86400, expected: '1 day ago', arm: 'days L20-22 singular at the 86400s threshold' },
  { diff: 172800, expected: '2 days ago', arm: 'days L20-22 plural' },
  { diff: 2592000, expected: '1 month ago', arm: 'months L23-25 singular at the 2592000s threshold' },
  { diff: 5184000, expected: '2 months ago', arm: 'months L23-25 plural' },
  { diff: 31536000, expected: '1 year ago', arm: 'years else L26-28 singular at the 31536000s threshold' },
  { diff: 63072000, expected: '2 years ago', arm: 'years else L26-28 plural' },
];

/**
 * The largest difference each arm still claims - one second below its threshold - so every
 * `Math.floor` is exercised at the point it is about to roll over into the next unit.
 */
const UPPER_EDGE_CASES: TimeAgoCase[] = [
  { diff: 59, expected: '59 seconds ago', arm: 'seconds L12-13 upper edge' },
  { diff: 3599, expected: '59 minutes ago', arm: 'minutes L14-16 upper edge' },
  { diff: 86399, expected: '23 hours ago', arm: 'hours L17-19 upper edge' },
  { diff: 2591999, expected: '29 days ago', arm: 'days L20-22 upper edge' },
  { diff: 31535999, expected: '12 months ago', arm: 'months L23-25 upper edge' },
];

/**
 * Captured so `afterAll` can put the variable back exactly as it was found, including the case
 * where it was never set.
 */
let originalTZ: string | undefined;

beforeAll(() => {
  originalTZ = process.env.TZ;
  process.env.TZ = 'UTC';
});

afterAll(() => {
  if (originalTZ === undefined) {
    delete process.env.TZ;
  } else {
    process.env.TZ = originalTZ;
  }
});

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(FIXED_NOW);
});

afterEach(() => {
  jest.useRealTimers();
});

describe('formatDate', () => {
  it('renders a UTC instant through the YYYY-MM-DD tokens', () => {
    expect(formatDate('2024-01-15T00:00:00Z', 'YYYY-MM-DD')).toBe('2024-01-15');
  });

  it('renders date and time together through the DD/MM/YYYY HH:mm tokens', () => {
    expect(formatDate('2024-01-15T13:45:30Z', 'DD/MM/YYYY HH:mm')).toBe('15/01/2024 13:45');
  });

  it('accepts an epoch-millisecond number for its string | number parameter', () => {
    expect(formatDate(Date.UTC(2024, 0, 15), 'YYYY-MM-DD')).toBe('2024-01-15');
  });
});

describe('getTimeAgo', () => {
  it.each(THRESHOLD_CASES)('$arm: diff $diff s -> "$expected"', ({ diff, expected }) => {
    expect(getTimeAgo(isoSecondsAgo(diff))).toBe(expected);
  });

  it.each(UPPER_EDGE_CASES)('$arm: diff $diff s -> "$expected"', ({ diff, expected }) => {
    expect(getTimeAgo(isoSecondsAgo(diff))).toBe(expected);
  });
});
