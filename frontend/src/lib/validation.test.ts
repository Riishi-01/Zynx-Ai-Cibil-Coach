import { describe, expect, it } from 'vitest';

import {
  MAX_MONTHLY_INCOME_INR,
  isIncomeValid,
  isPanValid,
  normalizePan,
  parseIncomeInput,
  validateIncome,
  validatePan,
} from './validation';

describe('validatePan', () => {
  it('treats an empty string as empty, not invalid', () => {
    expect(validatePan('')).toBe('empty');
    expect(validatePan('   ')).toBe('empty');
  });

  it('accepts the canonical valid format', () => {
    expect(validatePan('ABCPS1234A')).toBe('valid');
  });

  it('is case-insensitive on input but matches the uppercased form', () => {
    expect(validatePan('abcps1234a')).toBe('valid');
  });

  it('treats a valid-so-far prefix as incomplete, not invalid', () => {
    expect(validatePan('ABC')).toBe('incomplete');
    expect(validatePan('ABCPS')).toBe('incomplete');
    expect(validatePan('ABCPS123')).toBe('incomplete');
  });

  it('rejects a prefix that already violates the pattern', () => {
    // digit where a letter is required
    expect(validatePan('ABC1')).toBe('invalid');
    // letter where a digit is required
    expect(validatePan('ABCPSX')).toBe('invalid');
  });

  it('rejects strings at full length that do not match', () => {
    expect(validatePan('ABCPS12345')).toBe('invalid'); // 5 digits, no trailing letter
    expect(validatePan('1BCPS1234A')).toBe('invalid'); // leading digit
  });

  it('rejects strings longer than 10 characters', () => {
    expect(validatePan('ABCPS1234AX')).toBe('invalid');
  });

  for (const pan of ['BCDRM2345B', 'CDEPI3456C', 'KLMPO1234K', 'NOPPR4567N']) {
    it(`accepts real seed PAN ${pan}`, () => {
      expect(validatePan(pan)).toBe('valid');
    });
  }
});

describe('isPanValid', () => {
  it('agrees with validatePan for complete strings', () => {
    expect(isPanValid('ABCPS1234A')).toBe(true);
    expect(isPanValid('ABCPS1234')).toBe(false);
    expect(isPanValid('not a pan')).toBe(false);
  });
});

describe('normalizePan', () => {
  it('uppercases and trims, matching the backend normalisation', () => {
    expect(normalizePan('  abcps1234a  ')).toBe('ABCPS1234A');
  });
});

describe('parseIncomeInput', () => {
  it('parses a plain integer string', () => {
    expect(parseIncomeInput('75000')).toBe(75000);
  });

  it('strips the rupee sign and grouping commas', () => {
    expect(parseIncomeInput('₹75,000')).toBe(75000);
    expect(parseIncomeInput('7,50,000')).toBe(750000);
  });

  it('returns null for an empty string', () => {
    expect(parseIncomeInput('')).toBeNull();
  });

  it('returns null for non-numeric input', () => {
    expect(parseIncomeInput('abc')).toBeNull();
    expect(parseIncomeInput('75000.50')).toBeNull();
    expect(parseIncomeInput('-5000')).toBeNull();
  });
});

describe('validateIncome', () => {
  it('flags empty input distinctly from an invalid one', () => {
    expect(validateIncome('')).toBe('empty');
  });

  it('accepts a normal income', () => {
    expect(validateIncome('75000')).toBe('valid');
    expect(validateIncome('₹75,000')).toBe('valid');
  });

  it('rejects zero and negative amounts', () => {
    expect(validateIncome('0')).toBe('too_low');
  });

  it('rejects non-numeric input', () => {
    expect(validateIncome('not a number')).toBe('not_a_number');
  });

  it('rejects absurdly large input', () => {
    expect(validateIncome(String(MAX_MONTHLY_INCOME_INR + 1))).toBe('too_high');
  });

  it('accepts the ceiling value itself', () => {
    expect(validateIncome(String(MAX_MONTHLY_INCOME_INR))).toBe('valid');
  });
});

describe('isIncomeValid', () => {
  it('is true only for the valid case', () => {
    expect(isIncomeValid('75000')).toBe(true);
    expect(isIncomeValid('0')).toBe(false);
    expect(isIncomeValid('')).toBe(false);
  });
});
