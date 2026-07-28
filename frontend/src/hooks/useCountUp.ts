import { useEffect, useRef, useState } from 'react';

/**
 * Animated count-up from `from` to `to` over `duration` ms.
 * Uses requestAnimationFrame for 60fps smoothness (SPEC.md motion #3).
 * easeOutExpo gives the fast-start / slow-finish feel.
 */
export function useCountUp(to: number, duration = 1500, from = 0): number {
  const [value, setValue] = useState(from);
  const rafRef = useRef<number | undefined>(undefined);
  const startRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    startRef.current = undefined;
    const delta = to - from;

    function tick(timestamp: number) {
      if (startRef.current === undefined) startRef.current = timestamp;
      const elapsed = timestamp - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // easeOutExpo: 1 - 2^(-10*x)
      const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setValue(Math.round(from + delta * eased));

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [to, from, duration]);

  return value;
}
