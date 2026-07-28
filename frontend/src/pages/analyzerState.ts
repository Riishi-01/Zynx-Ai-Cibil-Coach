/**
 * The states the analyzer page moves through. See SPEC.md's master
 * prompt: IDLE -> SUBMITTING -> STREAMING -> CHATTING, with CANVAS_COLLAPSED
 * tracked as an independent flag.
 *
 * STREAMING replaces the old synchronous ANALYZED step: the canvas pane now
 * reveals the moment the first SSE frame arrives from /api/analyze (the
 * `event: canvas` frame sent before any LLM tokens). The chat-stream timing
 * is driven by the LLM, not by the user, so the user no longer waits for a
 * deterministic /api/canvas call before seeing charts.
 *
 * `START_CHAT` is still reachable from STREAMING — the dispatcher in
 * Analyzer.tsx sends it once `plan_delta` arrives, mirroring the old flow.
 */
export type AnalyzerStage = 'IDLE' | 'SUBMITTING' | 'STREAMING' | 'CHATTING';

export interface SubmittedValues {
  pan: string;
  incomeInr: number;
  /**
   * Turnstile token from the invisible widget, when configured. Null/undefined
   * when the gate is disabled (Phase 1 deploy before VITE_TURNSTILE_SITE_KEY
   * is set). The backend short-circuits the gate to True when no secret is
   * configured, so omitting this is always safe.
   */
  turnstileToken?: string | null;
}

export interface AnalyzerState {
  stage: AnalyzerStage;
  values: SubmittedValues | null;
  /** Independent of `stage`: the canvas can collapse in STREAMING or CHATTING. */
  canvasCollapsed: boolean;
  error: string | null;
}

export const INITIAL_STATE: AnalyzerState = {
  stage: 'IDLE',
  values: null,
  canvasCollapsed: false,
  error: null,
};

export type AnalyzerAction =
  | { type: 'SUBMIT'; values: SubmittedValues }
  | { type: 'STREAM_STARTED' }
  | { type: 'SUBMIT_FAILED'; error: string }
  | { type: 'START_CHAT' }
  | { type: 'EDIT' } // chip clicked: back to IDLE with the form reopened
  | { type: 'TOGGLE_CANVAS' };

export function analyzerReducer(state: AnalyzerState, action: AnalyzerAction): AnalyzerState {
  switch (action.type) {
    case 'SUBMIT':
      return { ...state, stage: 'SUBMITTING', values: action.values, error: null };

    case 'STREAM_STARTED':
      // First SSE frame received — the canvas is now hydratable. Only
      // meaningful while still submitting; idempotent if the LLM is fast
      // and the user has already moved on (no-op outside SUBMITTING).
      if (state.stage !== 'SUBMITTING') return state;
      return { ...state, stage: 'STREAMING' };

    case 'SUBMIT_FAILED':
      return { ...state, stage: 'IDLE', error: action.error };

    case 'START_CHAT':
      if (state.stage !== 'STREAMING') return state;
      return { ...state, stage: 'CHATTING' };

    case 'EDIT':
      return { ...INITIAL_STATE };

    case 'TOGGLE_CANVAS':
      return { ...state, canvasCollapsed: !state.canvasCollapsed };

    default:
      return state;
  }
}
