import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { PartialCoachPlan } from '../../types';
import { PlanView } from './ChatPane';
import anjaliPlan from './__fixtures__/anjali-100k-plan.json';

/**
 * Renders a real Maya (gpt-4o-mini) coaching plan for Anjali through the same
 * `PlanView` the chat pane uses, and verifies the DOM is well-formed and
 * surfaces the expected rupee amounts and action titles.
 *
 * If this test breaks, the LLM output has drifted in a way that the frontend
 * cannot render — the most common causes are:
 *   - JSON-shape drift (an unexpected field, missing required field)
 *   - Markdown that crashes the renderer (e.g. an unbalanced LaTeX delimiter
 *     that the `LaTeXErrorBoundary` falls back from)
 *   - Lost rupee symbols / misformatted Indian-digit grouping
 */
describe('PlanView (real Maya output for Anjali at ₹1,00,000/month)', () => {
  it('renders the situation paragraph with the customer first name', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);
    const section = screen.getByText(/Anjali/i);
    expect(section).toBeInTheDocument();
    expect(section.textContent).toMatch(/CIBIL/);
  });

  it('renders all three top actions with their titles', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    expect(screen.getByRole('heading', { level: 3, name: /Pay Down High Utilization Card/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: /Dispute the Collection/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: /Place a Credit Freeze/i })).toBeInTheDocument();
  });

  it('preserves the canonical rupee amounts (₹2,400 paydown, ₹890 collection)', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    // The model is supposed to cite the precomputed slot value of ₹2,400.
    expect(screen.getAllByText(/₹2,400/).length).toBeGreaterThan(0);
    // The Airtel Postpaid collection balance, also a slot value.
    expect(screen.getByText(/₹890/)).toBeInTheDocument();
  });

  it('renders step lists as <ul> with one <li> per step', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    const firstActionSteps = screen
      .getByRole('heading', { level: 3, name: /Pay Down High Utilization Card/i })
      .closest('.plan-action')!
      .querySelector('.plan-action-steps')!;
    const items = firstActionSteps.querySelectorAll('li');
    expect(items.length).toBe(3);
  });

  it('renders each step text without HTML escaping issues', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    expect(screen.getByText(/Make a payment of ₹2,400 to your HDFC Millennia card\./)).toBeInTheDocument();
  });

  it('renders the what_to_avoid list with all three items', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    expect(screen.getAllByText(/Do not apply for any new credit/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Avoid making late payments/i)).toBeInTheDocument();
    expect(screen.getByText(/Do not ignore the collection/i)).toBeInTheDocument();
  });

  it('does not render a follow-up paragraph (UI no longer surfaces user input)', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    // Even if a future LLM emits the field, PlanView ignores it.
    expect(screen.queryByText(/What specific goals do you have for your credit score/i)).not.toBeInTheDocument();
    expect(document.querySelector('.plan-followup')).toBeNull();
  });

  it('renders the timeline pills under each action', () => {
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    expect(screen.getAllByText(/1-2 billing cycles/).length).toBeGreaterThan(0);
    expect(screen.getByText(/30 days after filing the dispute/)).toBeInTheDocument();
    expect(screen.getByText(/After 6-12 months/)).toBeInTheDocument();
  });

  it('does not crash on LaTeX or unbalanced delimiters', () => {
    // The LLM output above contains no LaTeX, but MarkdownRenderer wraps its
    // children in a LaTeXErrorBoundary that catches KaTeX throws. This test
    // is a sanity check that the boundary doesn't strip legitimate content.
    render(<PlanView plan={anjaliPlan as PartialCoachPlan} />);

    // If the error boundary ate the content, none of the action titles would
    // be in the document. We assert on a title that would only appear if the
    // full tree rendered correctly.
    expect(screen.getByRole('heading', { level: 3, name: /Dispute the Collection/i })).toBeInTheDocument();
  });
});
