import { formatDate, getTimeAgo } from './dateUtils';

const FIXED_NOW = Date.UTC(2024, 5, 15, 12, 0, 0);

const isoSecondsAgo = (seconds: number): string =>
  new Date(FIXED_NOW - seconds * 1000).toISOString();

interface TimeAgoCase {
  diff: number;
  expected: string;
  arm: string;
}

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

const UPPER_EDGE_CASES: TimeAgoCase[] = [
  { diff: 59, expected: '59 seconds ago', arm: 'seconds L12-13 upper edge' },
  { diff: 3599, expected: '59 minutes ago', arm: 'minutes L14-16 upper edge' },
  { diff: 86399, expected: '23 hours ago', arm: 'hours L17-19 upper edge' },
  { diff: 2591999, expected: '29 days ago', arm: 'days L20-22 upper edge' },
  { diff: 31535999, expected: '12 months ago', arm: 'months L23-25 upper edge' },
];

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
