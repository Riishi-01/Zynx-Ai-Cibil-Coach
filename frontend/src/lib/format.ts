/**
 * Formatting helpers for the frontend.
 *
 * formatIndianDigits mirrors app/template_renderer.py::format_indian_digits
 * exactly (last 3 digits form one group, then pairs): 120000 -> "1,20,000".
 * This is a client-side reimplementation for live input formatting — it does
 * not call the backend, and must stay numerically identical to the Python
 * version since both are shown for the same figures.
 */

export function formatIndianDigits(value: number): string {
  const negative = value < 0;
  const digits = Math.trunc(Math.abs(value)).toString();

  let grouped: string;
  if (digits.length <= 3) {
    grouped = digits;
  } else {
    let head = digits.slice(0, -3);
    const tail = digits.slice(-3);
    const parts: string[] = [];
    while (head.length > 2) {
      parts.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) parts.unshift(head);
    grouped = [...parts, tail].join(',');
  }

  return (negative ? '-' : '') + grouped;
}

/** Rupees with the ₹ sign and Indian grouping: 120000 -> "₹1,20,000". */
export function formatInr(value: number): string {
  return `₹${formatIndianDigits(value)}`;
}

/** Paise to a grouped rupee string, no sign: 12000000 -> "1,20,000". */
export function formatInrFromPaise(paise: number): string {
  return formatIndianDigits(Math.trunc(paise / 100));
}

export function formatPct(ratio: number): string {
  return String(Math.round(ratio * 100));
}

/** Integer with en-IN thousands grouping (1,23,456 not 123,456). */
export function fmtInt(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value);
}

/** Milliseconds → "17.6s". Used by the metadata footer. */
export function fmtDuration(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

/** "just now" / "5m ago" / "3h ago" / "2d ago" — coarse, non-localized. */
export function fmtRelative(isoTimestamp: string, now: Date = new Date()): string {
  if (!isoTimestamp) return '';
  const then = new Date(isoTimestamp);
  if (Number.isNaN(then.getTime())) return '';
  const diffMs = now.getTime() - then.getTime();
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 45) return 'just now';
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return then.toLocaleDateString('en-IN', {
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Live-format a raw text input as Indian-grouped digits while the user types.
 * Strips everything but digits first, so pasted "₹1,20,000" or "1,20,000"
 * both normalise to the same grouped output rather than double-grouping.
 */
export function formatIncomeInput(rawValue: string): string {
  const digitsOnly = rawValue.replace(/[^\d]/g, '');
  if (digitsOnly === '') return '';
  return formatIndianDigits(Number(digitsOnly));
}
