import { useId, useState } from 'react';

import { COPY } from '../../copy';
import { formatIncomeInput } from '../../lib/format';
import { validateIncome } from '../../lib/validation';

interface IncomeFieldProps {
  /** Raw digits only, e.g. "75000" — the parent owns the canonical value. */
  value: string;
  onChange: (rawDigits: string) => void;
  disabled?: boolean;
}

/**
 * Monthly income input. Displays with live Indian digit grouping
 * (₹75,000 -> ₹7,50,000 as more digits are typed) while the value passed to
 * the parent stays a plain digit string, so onChange never has to be parsed
 * back out of a formatted display string.
 */
export function IncomeField({ value, onChange, disabled }: IncomeFieldProps) {
  const inputId = useId();
  const hintId = useId();
  const [touched, setTouched] = useState(false);

  const validity = validateIncome(value);
  const showError = touched && validity !== 'empty' && validity !== 'valid';

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const digitsOnly = event.target.value.replace(/[^\d]/g, '');
    // Mark touched on first keystroke so the user sees validation feedback
    // as they type, not only after they tab out of the field.
    if (!touched) setTouched(true);
    onChange(digitsOnly);
  }

  const displayValue = value === '' ? '' : formatIncomeInput(value);

  const hint = (): string => {
    switch (validity) {
      case 'too_low':
        return COPY.income.hintTooLow;
      case 'too_high':
        return COPY.income.hintTooHigh;
      default:
        return COPY.income.hintDefault;
    }
  };

  return (
    <div className="field">
      <label htmlFor={inputId} className="field-label">
        {COPY.income.label}
      </label>
      <div className="field-input-wrap">
        <span className="field-prefix" aria-hidden="true">
          ₹
        </span>
        <input
          id={inputId}
          className="field-input field-input--mono field-input--prefixed"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          placeholder={COPY.income.placeholder}
          value={displayValue}
          onChange={handleChange}
          onBlur={() => setTouched(true)}
          disabled={disabled}
          aria-invalid={showError}
          aria-describedby={hintId}
        />
        {showError && (
          <span className="field-icon field-icon--invalid" aria-hidden="true">
            ✗
          </span>
        )}
      </div>
      <p id={hintId} className="field-hint" role={showError ? 'alert' : undefined}>
        {hint()}
      </p>
    </div>
  );
}
