import { useEffect, useRef, useState } from 'react';

/**
 * Buffers the streamed text and only commits it to React state every `delay`ms.
 * On unmount or stream-end, flushes immediately. This prevents re-parsing
 * ~1KB of Markdown on every token (SPEC.md §4.4).
 */
export function useDebouncedStream(text: string, streaming: boolean, delay = 80): string {
  const [debounced, setDebounced] = useState(text);
  const bufRef = useRef(text);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    bufRef.current = text;
    if (!streaming) {
      setDebounced(text); // final flush
      return;
    }
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setDebounced(bufRef.current), delay);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [text, streaming, delay]);

  return debounced;
}
