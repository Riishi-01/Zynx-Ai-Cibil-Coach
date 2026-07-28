import { describe, expect, it } from 'vitest';

import { formatIncomeInput, formatIndianDigits, formatInr, formatInrFromPaise, formatPct } from './format';

/**
 * Golden pairs generated directly from app/template_renderer.py's
 * format_indian_digits (not hand-computed), so this test catches any drift
 * between the Python and TypeScript implementations rather than just
 * confirming the TS code agrees with itself.
 *
 * Regenerate with:
 *   PYTHONPATH=. .venv/bin/python -c "
 *   from app.template_renderer import format_indian_digits
 *   for v in [...]: print(f'{v},{format_indian_digits(v)}')"
 */
const GOLDEN_PAIRS: Array<[number, string]> = [
  [0, '0'],
  [5, '5'],
  [100, '100'],
  [999, '999'],
  [1000, '1,000'],
  [4200, '4,200'],
  [99999, '99,999'],
  [100000, '1,00,000'],
  [120000, '1,20,000'],
  [515000, '5,15,000'],
  [999999, '9,99,999'],
  [1000000, '10,00,000'],
  [10000000, '1,00,00,000'],
  [99999999, '9,99,99,999'],
  [100000000, '10,00,00,000'],
  [123456789, '12,34,56,789'],
  [-120000, '-1,20,000'],
  [-1000, '-1,000'],
  [-1, '-1'],
  [-999999999, '-99,99,99,999'],
];

describe('formatIndianDigits', () => {
  for (const [value, expected] of GOLDEN_PAIRS) {
    it(`formats ${value} as "${expected}" (matches the Python implementation)`, () => {
      expect(formatIndianDigits(value)).toBe(expected);
    });
  }

  it('is not western grouping', () => {
    // Western grouping would produce "120,000".
    expect(formatIndianDigits(120000)).not.toBe('120,000');
    expect(formatIndianDigits(120000)).toBe('1,20,000');
  });
});

describe('formatInr', () => {
  it('prepends the rupee sign', () => {
    expect(formatInr(120000)).toBe('₹1,20,000');
  });
});

describe('formatInrFromPaise', () => {
  it('converts paise to grouped rupees', () => {
    // Anjali's HDFC Millennia balance from the seed fixture: 420000 paise = ₹4,200.
    expect(formatInrFromPaise(420000)).toBe('4,200');
  });

  it('truncates rather than rounds, matching Python integer division', () => {
    expect(formatInrFromPaise(199)).toBe('1'); // 199 // 100 == 1
  });
});

describe('formatPct', () => {
  it('rounds a 0-1 ratio to a whole-number percentage', () => {
    expect(formatPct(0.572)).toBe('57');
    expect(formatPct(0.9625)).toBe('96');
    expect(formatPct(0)).toBe('0');
    expect(formatPct(1)).toBe('100');
  });
});

describe('formatIncomeInput', () => {
  it('groups digits as the user types', () => {
    expect(formatIncomeInput('75000')).toBe('75,000');
    expect(formatIncomeInput('750000')).toBe('7,50,000');
  });

  it('strips non-digit characters before grouping', () => {
    expect(formatIncomeInput('₹75,000')).toBe('75,000');
    expect(formatIncomeInput('75,000')).toBe('75,000');
  });

  it('returns an empty string for empty input rather than "0"', () => {
    expect(formatIncomeInput('')).toBe('');
  });

  it('handles a single digit', () => {
    expect(formatIncomeInput('5')).toBe('5');
  });
});
