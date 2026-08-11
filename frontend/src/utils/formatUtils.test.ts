import { formatNumber, truncateText } from './formatUtils';

type FormatNumberCase = [input: number, expected: string, covers: string];

type TruncateTextCase = [text: string, maxLength: number, expected: string, covers: string];

/* The regex also groups fractional digits, so 1234.5678 currently formats as 1,234.5,678. */
const FORMAT_NUMBER_CASES: FormatNumberCase[] = [
  [1234567, '1,234,567', 'thousands grouping'],
  [-1234, '-1,234', 'leading minus sign preserved'],
  [1234.5678, '1,234.5,678', 'fractional part grouped as well'],
  [999, '999', 'one below the grouping threshold'],
  [1000, '1,000', 'at the grouping threshold'],
];

const TRUNCATE_TEXT_UNCHANGED_CASES: TruncateTextCase[] = [
  ['abc', 6, 'abc', 'well under maxLength'],
  ['abcde', 6, 'abcde', 'one character below the boundary'],
  ['abcdef', 6, 'abcdef', 'exactly maxLength'],
];

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
