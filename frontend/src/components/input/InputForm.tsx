import { motion } from 'framer-motion';
import { useState } from 'react';

import { isIncomeValid, isPanValid, normalizePan, parseIncomeInput } from '../../lib/validation';
import { COPY } from '../../copy';
import { Dropdown } from './Dropdown';
import { IncomeField } from './IncomeField';

export interface InputFormValues {
  pan: string;
  incomeInr: number;
}

interface InputFormProps {
  onSubmit: (values: InputFormValues) => void;
  submitting?: boolean;
  reducedMotion?: boolean;
}

/**
 * The IDLE-state form: PAN + income + submit. Purely a controlled input
 * surface — validation lives in lib/validation.ts. The state machine that
 * reacts to submission (IDLE -> SUBMITTING -> ...) lives in
 * pages/Analyzer.tsx. The button stays disabled until both fields are
 * independently valid, so there is no "submit and then see three errors"
 * round trip.
 *
 * Shares `layoutId="input-form"` with InputSummary so Framer Motion morphs
 * this element into the top-left chip on submit (SPEC.md motion #1) instead
 * of unmounting one and mounting the other.
 */
export function InputForm({ onSubmit, submitting = false, reducedMotion = false }: InputFormProps) {
  const [pan, setPan] = useState('');
  const [incomeDigits, setIncomeDigits] = useState('');

  const panValid = isPanValid(pan);
  const incomeValid = isIncomeValid(incomeDigits);
  const canSubmit = panValid && incomeValid && !submitting;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;

    const incomeInr = parseIncomeInput(incomeDigits);
    if (incomeInr === null) return;

    onSubmit({ pan: normalizePan(pan), incomeInr });
  }

  return (
    <motion.form
      layoutId="input-form"
      layout
      className="input-form"
      onSubmit={handleSubmit}
      noValidate
      transition={
        reducedMotion
          ? { duration: 0 }
          : { duration: 0.5, ease: [0.34, 1.56, 0.64, 1] } // --duration-headline / --ease-overshoot
      }
    >
      <div className="input-form-fields">
        <Dropdown value={pan} onChange={setPan} disabled={submitting} />
        <IncomeField value={incomeDigits} onChange={setIncomeDigits} disabled={submitting} />
      </div>

      <button
        type="submit"
        className="button button--primary"
        disabled={!canSubmit}
        aria-busy={submitting}
      >
        {submitting && <span className="button-spinner" aria-hidden="true" />}
        {submitting ? COPY.form.submitting : COPY.form.submit}
      </button>
    </motion.form>
  );
}
