/**
 * The five states the analyzer page moves through. See SPEC.md's master
 * prompt: IDLE -> SUBMITTING -> ANALYZED -> CHATTING -> CANVAS_COLLAPSED.
 *
 * CHATTING and CANVAS_COLLAPSED are independent of each other in practice
 * (the user can toggle the canvas while chatting), but SPEC.md presents them
 * as a linear progression, so `stage` models exactly that while
 * `canvasCollapsed` is tracked as its own flag or ivar in AnalyzerState —
 * see the state shape below for how the two combine.
 */
export type AnalyzerStage = 'IDLE' | 'SUBMITTING' | 'ANALYZED' | 'CHATTING';

export interface SubmittedValues {
  pan: string;
  incomeInr: number;
}

export interface AnalyzerState {
  stage: AnalyzerStage;
  values: SubmittedValues | null;
  /** Independent of `stage`: the canvas can collapse in ANALYZED or CHATTING. */
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
  | { type: 'ANALYZED' }
  | { type: 'SUBMIT_FAILED'; error: string }
  | { type: 'START_CHAT' }
  | { type: 'EDIT' } // chip clicked: back to IDLE with the form reopened
  | { type: 'TOGGLE_CANVAS' };

export function analyzerReducer(state: AnalyzerState, action: AnalyzerAction): AnalyzerState {
  switch (action.type) {
    case 'SUBMIT':
      return { ...state, stage: 'SUBMITTING', values: action.values, error: null };

    case 'ANALYZED':
      // Only meaningful mid-submission; a stray ANALYZED after EDIT is a no-op.
      if (state.stage !== 'SUBMITTING') return state;
      return { ...state, stage: 'ANALYZED' };

    case 'SUBMIT_FAILED':
      return { ...state, stage: 'IDLE', error: action.error };

    case 'START_CHAT':
      if (state.stage !== 'ANALYZED') return state;
      return { ...state, stage: 'CHATTING' };

    case 'EDIT':
      return { ...INITIAL_STATE };

    case 'TOGGLE_CANVAS':
      return { ...state, canvasCollapsed: !state.canvasCollapsed };

    default:
      return state;
  }
}
