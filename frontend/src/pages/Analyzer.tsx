import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';

import { CanvasPane } from '../components/canvas/CanvasPane';
import { CanvasToggle as CanvasToggleButton } from '../components/canvas/CanvasToggle';
import { ChatPane } from '../components/chat/ChatPane';
import { InputForm } from '../components/input/InputForm';
import { InputSummary } from '../components/input/InputSummary';
import { COPY } from '../copy';
import { useReducedMotion } from '../hooks/useReducedMotion';
import type { CanvasResponse } from '../types';
import type { AnalyzerAction, AnalyzerState } from './analyzerState';
import { analyzerReducer, INITIAL_STATE } from './analyzerState';

/**
 * Top-level state machine: IDLE -> SUBMITTING -> STREAMING -> CHATTING, with
 * an independent canvas-collapsed flag. Children stay dumb — everything
 * here is either reducer state or a callback into the reducer, per SPEC.md
 * §2's "why this shape" note.
 *
 * The canvas pane reveals the moment the first SSE frame arrives from
 * /api/analyze (the `event: canvas` frame). Charts paint as soon as the
 * payload hydrates; the chat plan streams in alongside.
 */
export function Analyzer() {
  const [state, dispatch] = useReducer(analyzerReducer, INITIAL_STATE);
  const [canvasData, setCanvasData] = useState<CanvasResponse | null>(null);
  const reducedMotion = useReducedMotion();

  // Stage-aware dispatch: holds the latest state in a ref so callbacks fired
  // long after mount (e.g. `onPlanDelta`) read the current stage instead of
  // the value captured at mount time.
  const stateRef = useRef<AnalyzerState>(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  const dispatchWithState = useCallback((action: AnalyzerAction) => {
    dispatch(action);
    // Optimistically reflect the post-dispatch stage for synchronous readers
    // (e.g. the `onPlanDelta` callback fired by ChatPane in the same tick).
    // The next render will overwrite via the effect above.
    if (action.type === 'STREAM_STARTED') stateRef.current = { ...stateRef.current, stage: 'STREAMING' };
    if (action.type === 'START_CHAT') stateRef.current = { ...stateRef.current, stage: 'CHATTING' };
    if (action.type === 'SUBMIT') stateRef.current = { ...stateRef.current, stage: 'SUBMITTING', values: action.values };
    if (action.type === 'SUBMIT_FAILED') stateRef.current = { ...stateRef.current, stage: 'IDLE', error: action.error };
    if (action.type === 'EDIT') stateRef.current = INITIAL_STATE;
  }, []);

  // The chat pane mounts as soon as the user submits so it can call
  // /api/analyze; the first SSE frame from that call (event: canvas) is
  // what flips the stage from SUBMITTING to STREAMING via STREAM_STARTED.
  const isIdle = state.stage === 'IDLE';

  return (
    <div className="analyzer">
      {isIdle ? (
        <div className="analyzer-idle">
          <h1 className="analyzer-brand">{COPY.analyzer.brand}</h1>
          <InputForm
            onSubmit={(values) => {
              dispatchWithState({ type: 'SUBMIT', values });
              // Canvas + chat hydration kicks off when ChatPane mounts and
              // dispatches STREAM_STARTED on its first SSE frame.
            }}
            submitting={state.stage === 'SUBMITTING'}
            reducedMotion={reducedMotion}
          />
          {state.error && (
            <div className="analyzer-error" role="alert">
              <p>{state.error}</p>
              <button
                type="button"
                className="analyzer-error-retry"
                onClick={() => dispatchWithState({ type: 'EDIT' })}
              >
                {COPY.error.retry}
              </button>
            </div>
          )}
        </div>
      ) : (
        <>
          <header className="analyzer-header">
            {state.values && (
              <InputSummary
                pan={state.values.pan}
                incomeInr={state.values.incomeInr}
                onEdit={() => dispatchWithState({ type: 'EDIT' })}
                reducedMotion={reducedMotion}
              />
            )}
            <CanvasToggleButton
              collapsed={state.canvasCollapsed}
              onToggle={() => dispatchWithState({ type: 'TOGGLE_CANVAS' })}
            />
          </header>

          {/* Pane reveal (SPEC.md motion #2): opacity 0->1, translateY 12->0,
              450ms --ease-standard. Chat leads at 0ms, canvas follows at
              140ms — the stagger that makes the reveal read as one sequence
              rather than two things popping in together. */}
          <div className={`analyzer-panes ${state.canvasCollapsed ? 'analyzer-panes--collapsed' : ''}`}>
            <motion.section
              className="analyzer-pane analyzer-pane--chat"
              initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reducedMotion ? 0.15 : 0.45, ease: [0.4, 0, 0.2, 1], delay: 0 }}
              aria-label={COPY.analyzer.chatSection}
            >
              {state.values && (
                <ChatPane
                  pan={state.values.pan}
                  incomeInr={state.values.incomeInr}
                  onCanvasReady={(data) => {
                    setCanvasData(data);
                    dispatchWithState({ type: 'STREAM_STARTED' });
                  }}
                  onPlanDelta={() => {
                    if (stateRef.current.stage === 'STREAMING') {
                      dispatchWithState({ type: 'START_CHAT' });
                    }
                  }}
                  onRetry={() => dispatchWithState({ type: 'EDIT' })}
                />
              )}
            </motion.section>

            <AnimatePresence>
              {!state.canvasCollapsed && (
                <motion.section
                  className="analyzer-pane analyzer-pane--canvas"
                  initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{
                    duration: reducedMotion ? 0.15 : 0.45,
                    ease: [0.4, 0, 0.2, 1],
                    delay: reducedMotion ? 0 : 0.14,
                  }}
                >
                  <CanvasPane data={canvasData} />
                </motion.section>
              )}
            </AnimatePresence>
          </div>
        </>
      )}
    </div>
  );
}
