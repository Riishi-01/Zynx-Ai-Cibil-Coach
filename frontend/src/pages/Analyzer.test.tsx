import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CanvasResponse } from '../types';
import { Analyzer } from './Analyzer';
import { COPY } from '../copy';

const MOCK_CANVAS: CanvasResponse = {
  pan_masked: 'ABCPS****A',
  customer_id: 'cust_001',
  as_of_date: '2026-07-25',
  score_hero: {
    score: 715,
    band: 'Good',
    score_min: 300,
    score_max: 900,
    previous_score_1mo: 730,
    previous_score_3mo: 740,
    score_change_1mo: -15,
    score_change_3mo: -25,
    score_trend: 'falling',
    band_progress: 0.3,
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
    trend: 'falling',
    change_3mo: -25,
    annotation: 'Score dropped 25 points in 3 months',
  },
  utilization: {
    overall_utilization: 0.572,
    total_balance_paise: 515000,
    total_credit_limit_paise: 900000,
    target_utilization: 0.30,
    paydown_to_target_paise: 245000,
    cards: [
      {
        account_id: 'acc_001_1',
        display_name: 'HDFC Millennia',
        balance_paise: 420000,
        credit_limit_paise: 600000,
        utilization: 0.7,
        is_maxed: false,
        is_unused: false,
        paydown_to_target_paise: 240000,
      },
    ],
    top_card_account_id: 'acc_001_1',
    callout: 'Highest card: HDFC Millennia at 70%.',
  },
  payment_heatmap: {
    cells: [],
    months_on_time: 24,
    months_total: 24,
    pct_on_time: 1.0,
    worst_status: 0,
    most_recent_late_period: null,
    summary: '24/24 on time',
  },
  labels: {
    pan_masked: 'ABCPS****A',
    customer_id: 'cust_001',
    score: 715,
    score_band: 'Good',
    as_of_date: '2026-07-25',
    total_labels: 32,
    n_fired: 0,
    labels: [],
    fired_by_severity: { critical: [], warning: [], ok: [], excellent: [], info: [] },
  },
  first_name: 'Anjali',
};

const PLAN_PAYLOADS = {
  current_situation: 'Mocked plan.',
  top_actions: [
    {
      title: 'Pay Down High Utilization Card',
      why: 'Your utilization is high.',
      steps: ['Pay ₹2,400 today.'],
      when_youll_see_results: '1-2 billing cycles',
    },
  ],
  what_to_avoid: ['Do not apply for new credit.'],
};

const ANALYZE_SSE = () => {
  const frames = [
    `event: canvas\ndata: ${JSON.stringify(MOCK_CANVAS)}\n\n`,
    `event: plan_delta\ndata: ${JSON.stringify(PLAN_PAYLOADS)}\n\n`,
    `event: metadata\ndata: ${JSON.stringify({
      model: 'gpt-4o-mini-2024-07-18',
      prompt_tokens: 1234,
      completion_tokens: 567,
    })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ];
  return frames.join('');
};

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
}

describe('Analyzer shell', () => {
  beforeEach(() => {
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.clear();
      } catch {
        // ignore (jsdom returns a stub without real methods)
      }
    }
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('starts on the centered IDLE form', () => {
    render(<Analyzer />);
    expect(
      screen.getByRole('button', { name: /get credit analyzed/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: /main navigation/i })).toBeInTheDocument();
  });

  it('streams canvas + plan + metadata into a session view', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ANALYZE_SSE()));
        controller.close();
      },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url !== '/api/analyze') {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: () => Promise.resolve({ detail: 'Not found' }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          body: stream,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
        });
      }),
    );

    const user = userEvent.setup();
    render(<Analyzer />);

    await user.click(screen.getByLabelText(/pan/i));
    await user.click(screen.getByRole('option', { name: /ABCPS1234A/i }));
    await user.type(screen.getByLabelText(/monthly income/i), '75000');
    await user.click(screen.getByRole('button', { name: /get credit analyzed/i }));

    await waitFor(() => {
      expect(screen.getByText(/Pay Down High Utilization Card/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText('gpt-4o-mini-2024-07-18'),
    ).toBeInTheDocument();
  });

  it('shows the dock history badge after an analysis completes', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(ANALYZE_SSE()));
        controller.close();
      },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url !== '/api/analyze') {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: () => Promise.resolve({ detail: 'Not found' }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          body: stream,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
        });
      }),
    );

    const user = userEvent.setup();
    render(<Analyzer />);
    await user.click(screen.getByLabelText(/pan/i));
    await user.click(screen.getByRole('option', { name: /ABCPS1234A/i }));
    await user.type(screen.getByLabelText(/monthly income/i), '75000');
    await user.click(screen.getByRole('button', { name: /get credit analyzed/i }));

    await waitFor(() => {
      expect(screen.getByText(/Pay Down High Utilization Card/i)).toBeInTheDocument();
    });

    // History panel only renders on hover; the badge counts the new record.
    const nav = screen.getByRole('navigation', { name: /main navigation/i });
    const historyWrapper = nav.querySelector('.dock-history-wrapper');
    if (!historyWrapper) throw new Error('history wrapper not found');
    fireEvent.mouseEnter(historyWrapper);
    expect(
      screen.getByLabelText(/History \(1 conversation\)/i),
    ).toBeInTheDocument();
  });

  it('clears the chat turns via the docked Chat confirm dialog', async () => {
    // Render an existing conversation that already has chat turns, then
    // activate it through the dock so the Clear action is reachable.
    localStorage.setItem(
      'cibil-coach.conversations.v1',
      JSON.stringify([
        {
          id: 'existing',
          panMasked: 'ABCPS****A',
          firstName: 'Anjali',
          incomeInr: 75000,
          canvas: MOCK_CANVAS,
          initialPlan: PLAN_PAYLOADS,
          initialMetadata: {
            model: 'gpt-4o-mini-2024-07-18',
            prompt_tokens: 100,
            completion_tokens: 50,
          },
          elapsedMs: 1000,
          turns: [
            { role: 'user', content: 'First question' },
            { role: 'assistant', content: 'First answer' },
          ],
          createdAt: '2026-07-25T00:00:00.000Z',
          updatedAt: '2026-07-25T00:00:00.000Z',
        },
      ]),
    );

    const user = userEvent.setup();
    render(<Analyzer />);

    // While idle, the chat pane's Clear conversation button is hidden.
    expect(
      screen.queryByRole('button', { name: COPY.message.clearChat }),
    ).not.toBeInTheDocument();

    // Activate the session by hovering History + clicking the row. The
    // seeded conversation already has 2 chat turns, so the Clear
    // conversation button is reachable right away.
    const nav = screen.getByRole('navigation', { name: /main navigation/i });
    const historyWrapper = nav.querySelector('.dock-history-wrapper');
    if (!historyWrapper) throw new Error('history wrapper not found');
    fireEvent.mouseEnter(historyWrapper);
    const historyItem = await screen.findByRole('button', {
      name: /ABCPS\*\*\*\*A/,
    });
    await user.click(historyItem);

    const clearButton = await screen.findByRole('button', {
      name: COPY.message.clearChat,
    });
    expect(clearButton).toBeInTheDocument();
    fireEvent.click(clearButton);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: COPY.message.clearChatConfirmConfirm }));

    await flush();
    const after = JSON.parse(
      localStorage.getItem('cibil-coach.conversations.v1') || '[]',
    ) as Array<{ turns: unknown[] }>;
    expect(after[0].turns).toEqual([]);
  });
});
