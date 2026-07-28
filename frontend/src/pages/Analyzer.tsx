import { AnimatePresence, motion } from 'framer-motion';
import { useReducer, useState } from 'react';

import { CanvasPane } from '../components/canvas/CanvasPane';
import { CanvasToggle as CanvasToggleButton } from '../components/canvas/CanvasToggle';
import { ChatPane } from '../components/chat/ChatPane';
import { InputForm } from '../components/input/InputForm';
import { InputSummary } from '../components/input/InputSummary';
import { useReducedMotion } from '../hooks/useReducedMotion';
import type { CanvasResponse } from '../types';
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

  // The chat pane mounts as soon as the user submits so it can call
  // /api/analyze; the first SSE frame from that call (event: canvas) is
  // what flips the stage from SUBMITTING to STREAMING via STREAM_STARTED.
  const isIdle = state.stage === 'IDLE';

  return (
    <div className="analyzer">
      {isIdle ? (
        <div className="analyzer-idle">
          <h1 className="analyzer-brand">CIBIL Credit Coach</h1>
          <InputForm
            onSubmit={(values) => {
              dispatch({ type: 'SUBMIT', values });
              // Canvas + chat hydration kicks off when ChatPane mounts and
              // dispatches STREAM_STARTED on its first SSE frame.
            }}
            submitting={state.stage === 'SUBMITTING'}
            reducedMotion={reducedMotion}
          />
          {state.error && (
            <p className="analyzer-error" role="alert">
              {state.error}
            </p>
          )}
        </div>
      ) : (
        <>
          <header className="analyzer-header">
            {state.values && (
              <InputSummary
                pan={state.values.pan}
                incomeInr={state.values.incomeInr}
                onEdit={() => dispatch({ type: 'EDIT' })}
                reducedMotion={reducedMotion}
              />
            )}
            <CanvasToggleButton
              collapsed={state.canvasCollapsed}
              onToggle={() => dispatch({ type: 'TOGGLE_CANVAS' })}
            />
          </header>

          {/* Pane reveal (SPEC.md motion #2): opacity 0->1, translateY 12->0,
              450ms --ease-standard. Chat leads at 0ms, canvas follows at
              80ms — the stagger that makes the reveal read as one sequence
              rather than two things popping in together. */}
          <div className={`analyzer-panes ${state.canvasCollapsed ? 'analyzer-panes--collapsed' : ''}`}>
            <motion.section
              className="analyzer-pane analyzer-pane--chat"
              initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reducedMotion ? 0.15 : 0.45, ease: [0.4, 0, 0.2, 1], delay: 0 }}
              aria-label="Chat"
            >
              {state.values && (
                <ChatPane
                  pan={state.values.pan}
                  incomeInr={state.values.incomeInr}
                  onCanvasReady={(data) => {
                    setCanvasData(data);
                    dispatch({ type: 'STREAM_STARTED' });
                  }}
                  onPlanDelta={() => {
                    if (state.stage === 'STREAMING') dispatch({ type: 'START_CHAT' });
                  }}
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
                    delay: reducedMotion ? 0 : 0.08,
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
