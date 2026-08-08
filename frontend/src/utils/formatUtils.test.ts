/**
 * The colocated unit suite for `./formatUtils`.
 *
 * `frontend/src/utils/formatUtils.ts` exports two pure string formatters, imports nothing, and reads
 * no clock, no network and no DOM. This suite imports those two functions and nothing else: it
 * installs no timer, no spy and no mock, it holds no mutable module-level state, and every expected
 * value below is a hardcoded literal rather than a value recomputed from the production expression.
 *
 * Construct-to-row map. The three groups between them execute both branches of the module:
 *
 * | Construct               | Branch                                                 | Rows |
 * |-------------------------|--------------------------------------------------------|------|
 * | `formatNumber` (L6-8)   | none - one unconditional `String.prototype.replace`    | 5    |
 * | `truncateText` (L17-19) | `text.length <= maxLength`, input returned unchanged   | 3    |
 * | `truncateText` (L20)    | `text.length > maxLength`, sliced then suffixed        | 2    |
 *
 * @see frontend/src/utils/formatUtils.ts - the module under test.
 * @see frontend/TESTING.md - this folder's arrangement and the commands that run this suite.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for every "why" behind this suite,
 *   including the disposition of `formatNumber`'s fractional output.
 */

import { formatNumber, truncateText } from './formatUtils';

/** One `formatNumber` row: the argument, the exact string returned, and the aspect it covers. */
type FormatNumberCase = [input: number, expected: string, covers: string];

/** One `truncateText` row: both arguments, the exact string returned, and the aspect it covers. */
type TruncateTextCase = [text: string, maxLength: number, expected: string, covers: string];

/*
 * The oracle for the two rows below whose output is not self-evident.
 *
 * `formatNumber` feeds `num.toString()` through a single global replace whose pattern is
 * `\B(?=(\d{3})+(?!\d))`. That pattern also matches inside the fractional part of `1234.5678`, so the
 * value returned is '1,234.5,678': a comma lands before `234` because the lookahead sees three digits
 * followed by `.`, which satisfies `(?!\d)`, and a second comma lands before `678` because the
 * lookahead sees three digits followed by end-of-input. The positions either side of `.` are word
 * boundaries, where `\B` cannot match, so no comma appears next to the decimal point itself. The same
 * word-boundary rule leaves the leading `-` of `-1234` intact.
 */
const FORMAT_NUMBER_CASES: FormatNumberCase[] = [
  [1234567, '1,234,567', 'thousands grouping'],
  [-1234, '-1,234', 'leading minus sign preserved'],
  [1234.5678, '1,234.5,678', 'fractional part grouped as well'],
  [999, '999', 'one below the grouping threshold'],
  [1000, '1,000', 'at the grouping threshold'],
];

/** Rows taken by L17-19: `text.length <= maxLength` holds, so `text` is returned untouched. */
const TRUNCATE_TEXT_UNCHANGED_CASES: TruncateTextCase[] = [
  ['abc', 6, 'abc', 'well under maxLength'],
  ['abcde', 6, 'abcde', 'one character below the boundary'],
  ['abcdef', 6, 'abcdef', 'exactly maxLength'],
];

/** Rows that fall through to L20: `slice(0, maxLength - 3)` keeps 3 characters, then the ellipsis. */
const TRUNCATE_TEXT_TRUNCATED_CASES: TruncateTextCase[] = [
  ['abcdefg', 6, 'abc...', 'one character above the boundary'],
  ['abcdefgh', 6, 'abc...', 'two characters above the boundary'],
];

describe('formatNumber', () => {
  it.each(FORMAT_NUMBER_CASES)(
    'formatNumber(%p) returns %p [%s]',
    (input, expected) => {
      expect(formatNumber(input)).toBe(expected);
    },
  );
});

describe('truncateText', () => {
  describe('text.length <= maxLength: the input is returned unchanged (L17-19)', () => {
    it.each(TRUNCATE_TEXT_UNCHANGED_CASES)(
      'truncateText(%p, %p) returns %p [L17-19 early return, %s]',
      (text, maxLength, expected) => {
        expect(truncateText(text, maxLength)).toBe(expected);
      },
    );
  });

  describe('text.length > maxLength: the input is sliced and suffixed with an ellipsis (L20)', () => {
    it.each(TRUNCATE_TEXT_TRUNCATED_CASES)(
      'truncateText(%p, %p) returns %p [L20 truncation, %s]',
      (text, maxLength, expected) => {
        expect(truncateText(text, maxLength)).toBe(expected);
      },
    );
  });
});
