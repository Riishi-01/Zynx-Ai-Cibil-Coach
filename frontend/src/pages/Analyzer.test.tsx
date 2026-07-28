import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CanvasResponse } from '../types';
import { Analyzer } from './Analyzer';

/** Minimal fixture that satisfies the CanvasResponse shape for chart rendering. */
const MOCK_CANVAS: CanvasResponse = {
  pan_masked: 'ABCPS****A',
  customer_id: 'cust_001',
  as_of_date: '2026-07-25',
  score_hero: {
    score: 715, band: 'Good', score_min: 300, score_max: 900,
    previous_score_1mo: 730, previous_score_3mo: 740,
    score_change_1mo: -15, score_change_3mo: -25,
    score_trend: 'falling', band_progress: 0.3,
    bands: [
      { name: 'Poor', min_score: 300, max_score: 579 },
      { name: 'Fair', min_score: 580, max_score: 699 },
      { name: 'Good', min_score: 700, max_score: 749 },
      { name: 'Very Good', min_score: 750, max_score: 799 },
      { name: 'Excellent', min_score: 800, max_score: 900 },
    ],
  },
  score_trend: {
    points: [
      { label: '3 months ago', score: 740 },
      { label: '1 month ago', score: 730 },
      { label: 'Now', score: 715 },
    ],
    trend: 'falling', change_3mo: -25,
    annotation: 'Score dropped 25 points in 3 months',
  },
  utilization: {
    overall_utilization: 0.572, total_balance_paise: 515000,
    total_credit_limit_paise: 900000, target_utilization: 0.30,
    paydown_to_target_paise: 245000,
    cards: [
      { account_id: 'acc_001_1', display_name: 'HDFC Millennia', balance_paise: 420000, credit_limit_paise: 600000, utilization: 0.70, is_maxed: false, is_unused: false, paydown_to_target_paise: 240000 },
      { account_id: 'acc_001_2', display_name: 'SBI SimplyCLICK', balance_paise: 90000, credit_limit_paise: 200000, utilization: 0.45, is_maxed: false, is_unused: false, paydown_to_target_paise: 30000 },
    ],
    top_card_account_id: 'acc_001_1',
    callout: 'Highest card: HDFC Millennia at 70%. Pay ₹2,40,000 to bring it to 30%.',
  },
  payment_heatmap: {
    cells: Array.from({ length: 24 }, (_, i) => ({
      period: `2024-${String((i % 12) + 1).padStart(2, '0')}`,
      label: `Month ${i + 1}`,
      status: 0 as const,
      has_data: true,
    })),
    months_on_time: 24, months_total: 24, pct_on_time: 1.0,
    worst_status: 0, most_recent_late_period: null,
    summary: '24/24 months on time — perfect history.',
  },
  labels: {
    pan_masked: 'ABCPS****A', customer_id: 'cust_001', score: 715,
    score_band: 'Good', as_of_date: '2026-07-25',
    total_labels: 32, n_fired: 5,
    labels: Array.from({ length: 32 }, (_, i) => ({
      label_id: `label_${i}`, display_name: `Label ${i}`,
      category: 'utilization' as const, severity: i < 5 ? 'critical' as const : 'ok' as const,
      priority_rank: i < 5 ? 1 : 5, fired: i < 5,
      condition_human: '', what_it_means_cibil: '', why_it_matters: '',
      instances: i < 5 ? [{ account_id: null, account_name: null, message: `Msg ${i}`, mitigation_steps: [] }] : [],
      facts_to_cite: {}, cibil_reason_codes: [], sources: [],
    })),
    fired_by_severity: { critical: ['label_0'], warning: [], ok: [], excellent: [], info: [] },
  },
};

/**
 * Advance React's reconciliation after the mocked fetch resolves.
 */
async function flushFetch() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });
}

describe('Analyzer integration', () => {
  beforeEach(() => {
    // Mock fetch to handle both /api/canvas (from fetchCanvas) and /api/analyze (from ChatPane).
    // The ChatPane's /api/analyze call needs a ReadableStream SSE response.
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/canvas') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(MOCK_CANVAS),
        });
      }
      if (url === '/api/analyze' || url === '/api/chat') {
        // Return an SSE stream with canvas + done events (no LLM call simulated).
        const sseBody = [
          `event: canvas\ndata: ${JSON.stringify(MOCK_CANVAS)}\n\n`,
          `event: done\ndata: {"ok":true}\n\n`,
        ].join('');
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(sseBody));
            controller.close();
          },
        });
        return Promise.resolve({
          ok: true,
          body: stream,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
        });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({ detail: 'Not found' }) });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('starts on the centered IDLE form', () => {
    render(<Analyzer />);
    expect(screen.getByRole('button', { name: /get credit analyzed/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/chat/i)).not.toBeInTheDocument();
  });

  it('submitting moves to ANALYZED and reveals the chat + canvas panes', async () => {
    const user = userEvent.setup();
    render(<Analyzer />);

    await user.type(screen.getByLabelText(/pan/i), 'ABCPS1234A');
    await user.type(screen.getByLabelText(/monthly income/i), '75000');
    await user.click(screen.getByRole('button', { name: /get credit analyzed/i }));

    await flushFetch();

    await waitFor(() => {
      // ChatPane renders inside the chat section
      expect(screen.getByLabelText(/chat message/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/credit profile canvas/i)).toBeInTheDocument();
    });

    // The chip now shows the submitted PAN, and the form itself is gone.
    expect(screen.getByText('ABCPS1234A')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /get credit analyzed/i })).not.toBeInTheDocument();

    // Charts are rendered with real data from the mock.
    expect(screen.getByText('Good')).toBeInTheDocument(); // band label in ScoreHero
    expect(screen.getByText('5')).toBeInTheDocument(); // n_fired in LabelsFired count
  });

  it('clicking the chip returns to IDLE with the form reopened', async () => {
    const user = userEvent.setup();
    render(<Analyzer />);

    await user.type(screen.getByLabelText(/pan/i), 'ABCPS1234A');
    await user.type(screen.getByLabelText(/monthly income/i), '75000');
    await user.click(screen.getByRole('button', { name: /get credit analyzed/i }));
    await flushFetch();

    const chip = await screen.findByRole('button', { name: /editing details/i });
    await user.click(chip);

    expect(screen.getByRole('button', { name: /get credit analyzed/i })).toBeInTheDocument();
    // Back to a clean form, not the previous values.
    expect(screen.getByLabelText(/pan/i)).toHaveValue('');
  });

  it('the canvas toggle flips aria-expanded and the button label without touching chat', async () => {
    const user = userEvent.setup();
    render(<Analyzer />);

    await user.type(screen.getByLabelText(/pan/i), 'ABCPS1234A');
    await user.type(screen.getByLabelText(/monthly income/i), '75000');
    await user.click(screen.getByRole('button', { name: /get credit analyzed/i }));
    await flushFetch();
    await screen.findByLabelText(/chat message/i);

    // The real toggle is inside CanvasPane, labelled "Hide canvas".
    const toggle = screen.getByRole('button', { name: /hide canvas/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await user.click(toggle);

    expect(screen.getByRole('button', { name: /show canvas/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.getByLabelText(/chat message/i)).toBeInTheDocument();
  });

  it('after analysis, the chat composer is available for follow-up questions', async () => {
    const user = userEvent.setup();
    render(<Analyzer />);

    await user.type(screen.getByLabelText(/pan/i), 'ABCPS1234A');
    await user.type(screen.getByLabelText(/monthly income/i), '75000');
    await user.click(screen.getByRole('button', { name: /get credit analyzed/i }));
    await flushFetch();

    // ChatComposer is rendered with the textarea for follow-up questions.
    expect(screen.getByLabelText(/chat message/i)).toBeInTheDocument();
  });
});
