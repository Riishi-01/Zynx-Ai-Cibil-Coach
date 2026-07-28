import { useEffect, useRef, useState } from 'react';

/**
 * Buffers the streamed text and only commits it to React state every `delay`ms.
 * On stream-end, flushes immediately. On unmount, the buffered value is
 * committed as the final state so a mid-debounce unmount does not lose
 * already-streamed tokens (SPEC.md §4.4).
 */
export function useDebouncedStream(text: string, streaming: boolean, delay = 80): string {
  const [debounced, setDebounced] = useState(text);
  const bufRef = useRef(text);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    bufRef.current = text;
    if (!streaming) {
      // Final flush on stream end.
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setDebounced(text);
      return;
    }
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebounced(bufRef.current);
      timerRef.current = null;
    }, delay);
    return () => {
      // Unmount: commit the latest buffered text rather than dropping it.
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (bufRef.current !== debounced) {
        setDebounced(bufRef.current);
      }
    };
    // debounced is intentionally omitted from deps — we only want the latest
    // value of `debounced` to detect a divergence on unmount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, streaming, delay]);

  return debounced;
}
