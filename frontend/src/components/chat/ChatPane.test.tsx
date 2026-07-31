import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CanvasResponse } from '../../types';
import { COPY } from '../../copy';
import { ChatPane } from './ChatPane';

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
        utilization: 0.70,
        is_maxed: false,
        is_unused: false,
        paydown_to_target_paise: 240000,
      },
      {
        account_id: 'acc_001_2',
        display_name: 'SBI SimplyCLICK',
        balance_paise: 90000,
        credit_limit_paise: 200000,
        utilization: 0.45,
        is_maxed: false,
        is_unused: false,
        paydown_to_target_paise: 30000,
      },
    ],
    top_card_account_id: 'acc_001_1',
    callout:
      'Highest card: HDFC Millennia at 70%. Pay ₹2,40,000 to bring it to 30%.',
  },
  payment_heatmap: {
    cells: Array.from({ length: 24 }, (_, i) => ({
      period: `2024-${String((i % 12) + 1).padStart(2, '0')}`,
      label: `Month ${i + 1}`,
      status: 0 as const,
      has_data: true,
    })),
    months_on_time: 24,
    months_total: 24,
    pct_on_time: 1.0,
    worst_status: 0,
    most_recent_late_period: null,
    summary: '24/24 months on time — perfect history.',
  },
  labels: {
    pan_masked: 'ABCPS****A',
    customer_id: 'cust_001',
    score: 715,
    score_band: 'Good',
    as_of_date: '2026-07-25',
    total_labels: 32,
    n_fired: 5,
    labels: [],
    fired_by_severity: { critical: [], warning: [], ok: [], excellent: [], info: [] },
  },
};

function flush() {
  return act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

function makeFetch(routes: Record<string, () => string>) {
  return vi.fn().mockImplementation((url: string) => {
    const factory = routes[url];
    if (!factory) {
      return Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not found' }),
      });
    }
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(factory()));
        controller.close();
      },
    });
    return Promise.resolve({
      ok: true,
      status: 200,
      body: stream,
      headers: new Headers({ 'content-type': 'text/event-stream' }),
    });
  });
}

const ANALYZE_SSE = () =>
  [
    `event: canvas\ndata: ${JSON.stringify(MOCK_CANVAS)}\n\n`,
    `event: plan_delta\ndata: ${JSON.stringify({ current_situation: 'Mocked plan.' })}\n\n`,
    `event: metadata\ndata: ${JSON.stringify({ model: 'gpt-4o-mini', prompt_tokens: 1, completion_tokens: 2 })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ].join('');

const CHAT_OK_SSE = (text: string) =>
  [
    `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
    `event: citations\ndata: ${JSON.stringify({ citations: [{ label_id: 'maxed_out' }] })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ].join('');

const CHAT_GUARDRAIL_SSE = () =>
  [
    `event: guardrail\ndata: ${JSON.stringify({ verdict: 'out_of_scope', reason: 'in' })}\n\n`,
    `event: token\ndata: ${JSON.stringify({ content: COPY.chat.outOfScope })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ].join('');

const CHAT_REPLACE_SSE = () =>
  [
    `event: token\ndata: ${JSON.stringify({ content: 'I can help. ' })}\n\n`,
    `event: guardrail\ndata: ${JSON.stringify({ verdict: 'out_of_scope', reason: 'post_check' })}\n\n`,
    `event: replace\ndata: ${JSON.stringify({ content: COPY.chat.outOfScope })}\n\n`,
    `event: done\ndata: {"ok":true}\n\n`,
  ].join('');

const CHAT_ERROR_SSE = () =>
  [
    `event: error\ndata: ${JSON.stringify({ message: 'embedding failed' })}\n\n`,
  ].join('');

describe('ChatPane follow-up flow', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the composer with the placeholder', async () => {
    vi.stubGlobal('fetch', makeFetch({ '/api/analyze': ANALYZE_SSE }));
    render(<ChatPane pan="ABCPS1234A" incomeInr={75000} />);
    await flush();
    expect(
      screen.getByPlaceholderText(COPY.chat.composerPlaceholder),
    ).toBeInTheDocument();
  });

  it('sends a follow-up and renders the streamed assistant reply with citation pills', async () => {
    const fetched: { url: string; body?: string }[] = [];
    const fetchImpl = vi.fn().mockImplementation((url: string, init?: { body?: string }) => {
      fetched.push({ url, body: init?.body });
      const sse =
        url === '/api/analyze'
          ? ANALYZE_SSE()
          : url === '/api/chat'
            ? CHAT_OK_SSE('Pay down the card [maxed_out].')
            : '';
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(<ChatPane pan="ABCPS1234A" incomeInr={75000} />);
    await flush();

    const textarea = screen.getByPlaceholderText(
      COPY.chat.composerPlaceholder,
    );
    fireEvent.change(textarea, {
      target: { value: 'what should I pay off first?' },
    });
    await user.click(screen.getByRole('button', { name: COPY.chat.sendAria }));

    await waitFor(() => {
      const allBubbles = document.querySelectorAll('.chat-message--assistant');
      const matched = Array.from(allBubbles).find((node) =>
        (node.textContent ?? '').includes('Pay down the card'),
      );
      expect(matched).toBeDefined();
    });
    expect(screen.getByText('Maxed Out')).toBeInTheDocument();

    const chatCall = fetched.find((entry) => entry.url === '/api/chat');
    expect(chatCall).toBeDefined();
    const body = JSON.parse(chatCall!.body!);
    expect(body.message).toBe('what should I pay off first?');
    // The user turn is appended to the message list right before the chat
    // request is fired, so it shows up in the history attached to the
    // chat request. For the very first follow-up the history contains the
    // user turn that initiated it.
    expect(Array.isArray(body.history)).toBe(true);
    expect(body.history).toEqual([
      { role: 'user', content: 'what should I pay off first?' },
    ]);
  });

  it('renders the guardrail redirect copy when /api/chat emits a guardrail event', async () => {
    const fetchImpl = vi.fn().mockImplementation((url: string) => {
      const sse =
        url === '/api/analyze'
          ? ANALYZE_SSE()
          : url === '/api/chat'
            ? CHAT_GUARDRAIL_SSE()
            : '';
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(<ChatPane pan="ABCPS1234A" incomeInr={75000} />);
    await flush();

    fireEvent.change(
      screen.getByPlaceholderText(COPY.chat.composerPlaceholder),
      { target: { value: 'should I invest in stocks?' } },
    );
    await user.click(screen.getByRole('button', { name: COPY.chat.sendAria }));

    await waitFor(() => {
      expect(screen.getByText(COPY.chat.outOfScope)).toBeInTheDocument();
    });
  });

  it('replaces a partial reply when the post-check fires', async () => {
    const fetchImpl = vi.fn().mockImplementation((url: string) => {
      const sse =
        url === '/api/analyze'
          ? ANALYZE_SSE()
          : url === '/api/chat'
            ? CHAT_REPLACE_SSE()
            : '';
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(<ChatPane pan="ABCPS1234A" incomeInr={75000} />);
    await flush();

    fireEvent.change(
      screen.getByPlaceholderText(COPY.chat.composerPlaceholder),
      { target: { value: 'help me' } },
    );
    await user.click(screen.getByRole('button', { name: COPY.chat.sendAria }));

    await waitFor(() => {
      expect(screen.getByText(COPY.chat.outOfScope)).toBeInTheDocument();
    });
  });

  it('renders an error bubble when the chat stream errors', async () => {
    const fetchImpl = vi.fn().mockImplementation((url: string) => {
      const sse =
        url === '/api/analyze'
          ? ANALYZE_SSE()
          : url === '/api/chat'
            ? CHAT_ERROR_SSE()
            : '';
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse));
          controller.close();
        },
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        body: stream,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
      });
    });
    vi.stubGlobal('fetch', fetchImpl);

    const user = userEvent.setup();
    render(<ChatPane pan="ABCPS1234A" incomeInr={75000} />);
    await flush();

    fireEvent.change(
      screen.getByPlaceholderText(COPY.chat.composerPlaceholder),
      { target: { value: 'help me' } },
    );
    await user.click(screen.getByRole('button', { name: COPY.chat.sendAria }));

    await waitFor(() => {
      expect(screen.getByText('embedding failed')).toBeInTheDocument();
    });
  });
});
