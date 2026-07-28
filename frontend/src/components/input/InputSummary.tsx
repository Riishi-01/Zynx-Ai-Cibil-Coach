import { motion } from 'framer-motion';

import { formatInr } from '../../lib/format';

interface InputSummaryProps {
  pan: string;
  incomeInr: number;
  onEdit: () => void;
  reducedMotion: boolean;
}

/**
 * The top-left chip the input form morphs into once submitted
 * (SPEC.md motion #1, "the headline motion"). Shares `layoutId="input-form"`
 * with InputForm's wrapping element so Framer Motion animates between the two
 * as one continuous shape rather than a cross-fade.
 *
 * Clickable to reopen the form for editing — this is the only way back to
 * IDLE once submitted.
 */
export function InputSummary({ pan, incomeInr, onEdit, reducedMotion }: InputSummaryProps) {
  return (
    <motion.button
      type="button"
      layoutId="input-form"
      layout
      className="input-summary"
      onClick={onEdit}
      transition={
        reducedMotion
          ? { duration: 0 }
          : {
              duration: 0.5, // --duration-headline
              ease: [0.34, 1.56, 0.64, 1], // --ease-overshoot
            }
      }
      aria-label={`Editing details for PAN ${pan}, income ${formatInr(incomeInr)}. Click to edit.`}
    >
      <span className="input-summary-chip">
        <span className="input-summary-label">PAN</span>
        <span className="input-summary-value">{pan}</span>
      </span>
      <span className="input-summary-divider" aria-hidden="true" />
      <span className="input-summary-chip">
        <span className="input-summary-value">{formatInr(incomeInr)}</span>
        <span className="input-summary-label">/ mo</span>
      </span>
    </motion.button>
  );
}
