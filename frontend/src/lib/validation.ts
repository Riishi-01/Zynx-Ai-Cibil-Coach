/**
 * Validation for the two IDLE-state inputs: PAN and monthly income.
 *
 * The PAN regex mirrors app/config.py's PAN_FORMAT_REGEX exactly
 * (^[A-Z]{5}\d{4}[A-Z]$) so a PAN that validates client-side is guaranteed to
 * pass app/pan_validator.py server-side too.
 */

export const PAN_REGEX = /^[A-Z]{5}\d{4}[A-Z]$/;

export type PanValidity = 'empty' | 'incomplete' | 'valid' | 'invalid';

/**
 * Classify a PAN as the user types.
 *
 * 'incomplete' (rather than 'invalid') while the string is a valid PREFIX of
 * the pattern but not yet 10 characters — this is what lets the field stay
 * neutral instead of flashing an error on every keystroke. A prefix is valid
 * only if each character typed so far fits the position it occupies in
 * AAAAA9999A (5 letters, then 4 digits, then 1 letter) — "ABC1" is invalid,
 * not incomplete, because position 4 must be a letter, not a digit.
 */
export function validatePan(rawValue: string): PanValidity {
  const value = rawValue.trim().toUpperCase();

  if (value.length === 0) return 'empty';
  if (value.length > 10) return 'invalid';
  if (PAN_REGEX.test(value)) return 'valid';

  for (let i = 0; i < value.length; i++) {
    const char = value[i];
    const expectsLetter = i < 5 || i === 9;
    const isLetter = /^[A-Z]$/.test(char);
    const isDigit = /^\d$/.test(char);

    if (expectsLetter ? !isLetter : !isDigit) return 'invalid';
  }

  return value.length === 10 ? 'invalid' : 'incomplete';
}

export function isPanValid(rawValue: string): boolean {
  return PAN_REGEX.test(rawValue.trim().toUpperCase());
}

/** Uppercase and strip whitespace — the exact normalisation the backend applies. */
export function normalizePan(rawValue: string): string {
  return rawValue.trim().toUpperCase();
}

// -------------------------------------------------------------- income ----

export const MIN_MONTHLY_INCOME_INR = 1;
// A generous ceiling to catch fat-fingered extra zeros without being a real
// business constraint — the backend does not enforce an upper bound.
export const MAX_MONTHLY_INCOME_INR = 100_00_00_000; // ₹100 crore

export type IncomeValidity = 'empty' | 'valid' | 'too_low' | 'too_high' | 'not_a_number';

/** Strip grouping commas and the ₹ sign, leaving a plain integer string. */
export function parseIncomeInput(rawValue: string): number | null {
  const digitsOnly = rawValue.replace(/[₹,\s]/g, '');
  if (digitsOnly === '') return null;
  if (!/^\d+$/.test(digitsOnly)) return null;
  return Number(digitsOnly);
}

export function validateIncome(rawValue: string): IncomeValidity {
  if (rawValue.trim() === '') return 'empty';

  const parsed = parseIncomeInput(rawValue);
  if (parsed === null) return 'not_a_number';
  if (parsed < MIN_MONTHLY_INCOME_INR) return 'too_low';
  if (parsed > MAX_MONTHLY_INCOME_INR) return 'too_high';
  return 'valid';
}

export function isIncomeValid(rawValue: string): boolean {
  return validateIncome(rawValue) === 'valid';
}
