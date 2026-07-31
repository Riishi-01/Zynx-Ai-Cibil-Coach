import { useCallback, useRef, useState } from 'react';

import type { CanvasResponse, ChatCitation, PartialCoachPlan, PlanMetadata } from '../types';

export interface StreamState {
  /** Accumulated markdown text (for /api/chat token events). */
  text: string;
  /** The progressively-complete coaching plan (for /api/analyze plan_delta events). */
  plan: PartialCoachPlan | null;
  /** Canvas data delivered as the first SSE event from /api/analyze. */
  canvas: CanvasResponse | null;
  /** Token-usage metadata delivered after the plan stream completes. */
  metadata: PlanMetadata | null;
  streaming: boolean;
  error: string | null;
  done: boolean;
}

type SseHandler = {
  onCanvas?: (data: CanvasResponse) => void;
  onPlanDelta?: (data: PartialCoachPlan) => void;
  onMetadata?: (data: PlanMetadata) => void;
  onToken?: (content: string) => void;
  onCitations?: (citations: ChatCitation[]) => void;
  onGuardrail?: (info: { verdict: string; reason: string }) => void;
  onReplace?: (content: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

/**
 * Low-level SSE stream consumer. Knows about fetch, ReadableStream, and
 * AbortController. Knows nothing about Markdown, KaTeX, or React rendering.
 *
 * Parses `event: <name>\ndata: <json>\n\n` frames as emitted by app/web.py.
 */
export function useStream() {
  const [state, setState] = useState<StreamState>({
    text: '',
    plan: null,
    canvas: null,
    metadata: null,
    streaming: false,
    error: null,
    done: false,
  });

  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async (url: string, body: unknown, handlers?: SseHandler) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setState({
      text: '',
      plan: null,
      canvas: null,
      metadata: null,
      streaming: true,
      error: null,
      done: false,
    });

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });

      if (!res.ok || !res.body) {
        const errBody = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errBody.detail ?? `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done: readerDone } = await reader.read();
        if (readerDone) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse complete SSE frames (terminated by \n\n).
        const frames = buffer.split('\n\n');
        buffer = frames.pop() ?? ''; // last element is incomplete

        for (const frame of frames) {
          if (!frame.trim()) continue;
          const lines = frame.split('\n');
          let event = '';
          let data = '';

          for (const line of lines) {
            if (line.startsWith('event: ')) event = line.slice(7);
            else if (line.startsWith('data: ')) data = line.slice(6);
          }

          if (!event || !data) continue;

          try {
            const parsed = JSON.parse(data);

            switch (event) {
              case 'canvas':
                setState((s) => ({ ...s, canvas: parsed }));
                handlers?.onCanvas?.(parsed);
                break;
              case 'plan_delta':
                setState((s) => ({ ...s, plan: parsed }));
                handlers?.onPlanDelta?.(parsed);
                break;
              case 'metadata':
                setState((s) => ({ ...s, metadata: parsed }));
                handlers?.onMetadata?.(parsed);
                break;
              case 'token':
                setState((s) => ({ ...s, text: s.text + (parsed.content ?? '') }));
                handlers?.onToken?.(parsed.content ?? '');
                break;
              case 'citations': {
                const list = Array.isArray(parsed.citations) ? parsed.citations : [];
                handlers?.onCitations?.(list);
                break;
              }
              case 'guardrail': {
                const verdict = typeof parsed.verdict === 'string' ? parsed.verdict : 'unknown';
                const reason = typeof parsed.reason === 'string' ? parsed.reason : 'unknown';
                handlers?.onGuardrail?.({ verdict, reason });
                break;
              }
              case 'replace': {
                const replacement =
                  typeof parsed.content === 'string'
                    ? parsed.content
                    : (parsed.content?.content ?? '');
                handlers?.onReplace?.(replacement);
                break;
              }
              case 'done':
                setState((s) => ({ ...s, streaming: false, done: true }));
                handlers?.onDone?.();
                break;
              case 'error':
                setState((s) => ({
                  ...s,
                  streaming: false,
                  error: parsed.message ?? 'Stream error',
                }));
                handlers?.onError?.(parsed.message ?? 'Stream error');
                break;
            }
          } catch {
            // Malformed JSON in a frame; skip it.
          }
        }
      }

      // Stream ended without a 'done' event (connection closed by server).
      setState((s) => (s.streaming ? { ...s, streaming: false, done: true } : s));
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        setState((s) => ({ ...s, streaming: false }));
      } else {
        setState((s) => ({
          ...s,
          streaming: false,
          error: (err as Error).message ?? 'Connection failed',
        }));
      }
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    setState({
      text: '',
      plan: null,
      canvas: null,
      metadata: null,
      streaming: false,
      error: null,
      done: false,
    });
  }, []);

  return { ...state, send, stop, reset };
}
