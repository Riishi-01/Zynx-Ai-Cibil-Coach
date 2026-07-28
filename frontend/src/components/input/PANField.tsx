import { useId, useState } from 'react';

import { normalizePan, validatePan } from '../../lib/validation';

interface PANFieldProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/**
 * PAN input: auto-uppercases as the user types, live-validates against the
 * same regex the backend enforces, and shows an inline ✓/✗ once the string is
 * either complete or has already violated the pattern. While the input is a
 * valid PREFIX (e.g. "ABC"), no icon shows — an error mid-word would be noise.
 */
export function PANField({ value, onChange, disabled }: PANFieldProps) {
  const inputId = useId();
  const hintId = useId();
  const [touched, setTouched] = useState(false);

  const validity = validatePan(value);
  const showValid = validity === 'valid';
  const showInvalid = touched && validity === 'invalid';

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    // Auto-uppercase, and cap at 10 characters — PAN is a fixed-width format.
    const next = event.target.value.toUpperCase().slice(0, 10);
    onChange(next);
  }

  return (
    <div className="field">
      <label htmlFor={inputId} className="field-label">
        PAN
      </label>
      <div className="field-input-wrap">
        <input
          id={inputId}
          className="field-input field-input--mono"
          type="text"
          inputMode="text"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="ABCPS1234A"
          value={normalizePan(value)}
          onChange={handleChange}
          onBlur={() => setTouched(true)}
          disabled={disabled}
          maxLength={10}
          aria-invalid={showInvalid}
          aria-describedby={hintId}
        />
        {showValid && (
          <span className="field-icon field-icon--valid" aria-hidden="true">
            ✓
          </span>
        )}
        {showInvalid && (
          <span className="field-icon field-icon--invalid" aria-hidden="true">
            ✗
          </span>
        )}
      </div>
      <p id={hintId} className="field-hint" role={showInvalid ? 'alert' : undefined}>
        {showInvalid
          ? 'Enter a valid 10-character PAN, e.g. ABCPS1234A'
          : '10-character PAN, e.g. ABCPS1234A'}
      </p>
    </div>
  );
}
