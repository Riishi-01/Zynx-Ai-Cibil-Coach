import { describe, expect, it } from 'vitest';

import { INITIAL_STATE, analyzerReducer } from './analyzerState';

const VALUES = { pan: 'ABCPS1234A', incomeInr: 75000 };

describe('analyzerReducer', () => {
  it('starts IDLE with no values', () => {
    expect(INITIAL_STATE.stage).toBe('IDLE');
    expect(INITIAL_STATE.values).toBeNull();
  });

  it('SUBMIT moves IDLE -> SUBMITTING and stores the values', () => {
    const next = analyzerReducer(INITIAL_STATE, { type: 'SUBMIT', values: VALUES });
    expect(next.stage).toBe('SUBMITTING');
    expect(next.values).toEqual(VALUES);
    expect(next.error).toBeNull();
  });

  it('ANALYZED moves SUBMITTING -> ANALYZED', () => {
    const submitting = analyzerReducer(INITIAL_STATE, { type: 'SUBMIT', values: VALUES });
    const analyzed = analyzerReducer(submitting, { type: 'ANALYZED' });
    expect(analyzed.stage).toBe('ANALYZED');
    expect(analyzed.values).toEqual(VALUES); // values survive the transition
  });

  it('ANALYZED is a no-op outside SUBMITTING', () => {
    const stillIdle = analyzerReducer(INITIAL_STATE, { type: 'ANALYZED' });
    expect(stillIdle.stage).toBe('IDLE');
  });

  it('SUBMIT_FAILED returns to IDLE and records the error', () => {
    const submitting = analyzerReducer(INITIAL_STATE, { type: 'SUBMIT', values: VALUES });
    const failed = analyzerReducer(submitting, { type: 'SUBMIT_FAILED', error: 'network error' });
    expect(failed.stage).toBe('IDLE');
    expect(failed.error).toBe('network error');
  });

  it('START_CHAT moves ANALYZED -> CHATTING', () => {
    let state = analyzerReducer(INITIAL_STATE, { type: 'SUBMIT', values: VALUES });
    state = analyzerReducer(state, { type: 'ANALYZED' });
    state = analyzerReducer(state, { type: 'START_CHAT' });
    expect(state.stage).toBe('CHATTING');
  });

  it('START_CHAT is a no-op outside ANALYZED', () => {
    const stillIdle = analyzerReducer(INITIAL_STATE, { type: 'START_CHAT' });
    expect(stillIdle.stage).toBe('IDLE');
  });

  it('EDIT resets fully back to IDLE from any stage', () => {
    let state = analyzerReducer(INITIAL_STATE, { type: 'SUBMIT', values: VALUES });
    state = analyzerReducer(state, { type: 'ANALYZED' });
    state = analyzerReducer(state, { type: 'START_CHAT' });
    state = analyzerReducer(state, { type: 'TOGGLE_CANVAS' }); // dirty canvasCollapsed too

    const reset = analyzerReducer(state, { type: 'EDIT' });
    expect(reset).toEqual(INITIAL_STATE);
  });

  it('TOGGLE_CANVAS flips independently of stage', () => {
    let state = analyzerReducer(INITIAL_STATE, { type: 'SUBMIT', values: VALUES });
    state = analyzerReducer(state, { type: 'ANALYZED' });

    const collapsed = analyzerReducer(state, { type: 'TOGGLE_CANVAS' });
    expect(collapsed.canvasCollapsed).toBe(true);
    expect(collapsed.stage).toBe('ANALYZED'); // stage unaffected

    const expanded = analyzerReducer(collapsed, { type: 'TOGGLE_CANVAS' });
    expect(expanded.canvasCollapsed).toBe(false);
  });

  it('TOGGLE_CANVAS survives into CHATTING', () => {
    let state = analyzerReducer(INITIAL_STATE, { type: 'SUBMIT', values: VALUES });
    state = analyzerReducer(state, { type: 'ANALYZED' });
    state = analyzerReducer(state, { type: 'TOGGLE_CANVAS' });
    state = analyzerReducer(state, { type: 'START_CHAT' });

    expect(state.stage).toBe('CHATTING');
    expect(state.canvasCollapsed).toBe(true);
  });

  it('follows the full documented sequence IDLE -> SUBMITTING -> ANALYZED -> CHATTING', () => {
    const stages: string[] = [INITIAL_STATE.stage];
    let state = INITIAL_STATE;

    state = analyzerReducer(state, { type: 'SUBMIT', values: VALUES });
    stages.push(state.stage);
    state = analyzerReducer(state, { type: 'ANALYZED' });
    stages.push(state.stage);
    state = analyzerReducer(state, { type: 'START_CHAT' });
    stages.push(state.stage);

    expect(stages).toEqual(['IDLE', 'SUBMITTING', 'ANALYZED', 'CHATTING']);
  });
});
