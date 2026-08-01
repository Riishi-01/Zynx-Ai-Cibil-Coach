import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import {
  fmtDuration,
  fmtInt,
  fmtRelative,
  formatIncomeInput,
  formatIndianDigits,
  formatInr,
  formatInrFromPaise,
  formatPct,
} from './format';

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

describe('fmtInt', () => {
  it('uses Indian thousands grouping', () => {
    expect(fmtInt(1234567)).toBe('12,34,567');
  });

  it('returns the input untouched below 1000', () => {
    expect(fmtInt(999)).toBe('999');
  });
});

describe('fmtDuration', () => {
  it('formats ms with one decimal place', () => {
    expect(fmtDuration(17_600)).toBe('17.6s');
  });

  it('returns 0.0s for zero ms', () => {
    expect(fmtDuration(0)).toBe('0.0s');
  });
});

describe('fmtRelative', () => {
  const now = new Date('2026-08-01T12:00:00.000Z');

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for under 45 seconds', () => {
    const ts = new Date(now.getTime() - 20_000).toISOString();
    expect(fmtRelative(ts)).toBe('just now');
  });

  it('formats minutes', () => {
    const ts = new Date(now.getTime() - 5 * 60_000).toISOString();
    expect(fmtRelative(ts)).toBe('5m ago');
  });

  it('formats hours', () => {
    const ts = new Date(now.getTime() - 3 * 60 * 60_000).toISOString();
    expect(fmtRelative(ts)).toBe('3h ago');
  });

  it('formats days', () => {
    const ts = new Date(now.getTime() - 2 * 24 * 60 * 60_000).toISOString();
    expect(fmtRelative(ts)).toBe('2d ago');
  });

  it('falls back to a date string for older entries', () => {
    const ts = new Date(now.getTime() - 30 * 24 * 60 * 60_000).toISOString();
    // jsdom's Intl.DateTimeFormat ignores the locale and emits e.g. "2 Jul".
    expect(fmtRelative(ts)).toMatch(/[A-Za-z0-9 ]+/);
    expect(fmtRelative(ts)).not.toMatch(/ago$/);
  });

  it('returns an empty string for invalid input', () => {
    expect(fmtRelative('')).toBe('');
    expect(fmtRelative('not a date')).toBe('');
  });
});
