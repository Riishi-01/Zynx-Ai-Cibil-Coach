/**
 * Types mirroring the backend's Pydantic models.
 *
 * Source of truth: app/api_schemas.py (LabelsResponse, CanvasResponse and
 * their children) and app/prompt_builder.py (CoachPlan, CoachAction).
 *
 * Field names and optionality are kept identical to the Python side. Where
 * Python has `Optional[X] = None`, TypeScript has `X | null`, since Pydantic
 * serialises None to JSON null rather than omitting the key.
 */

// ---------------------------------------------------------------- enums ----

export type ScoreBand = 'Poor' | 'Fair' | 'Good' | 'Very Good' | 'Excellent';

export type LabelCategory =
  | 'utilization'
  | 'payment'
  | 'inquiries'
  | 'collections'
  | 'credit_age'
  | 'mix'
  | 'score_trend'
  | 'dti'
  | 'data_quality';

export type LabelSeverity = 'critical' | 'warning' | 'ok' | 'excellent' | 'info';

export type ScoreTrendDirection = 'falling' | 'rising' | 'stable';

// --------------------------------------------------------------- labels ----

export interface SourceView {
  title: string;
  url: string;
}

export interface LabelInstance {
  account_id: string | null;
  account_name: string | null;
  message: string;
  mitigation_steps: string[];
}

export interface LabelView {
  label_id: string;
  display_name: string;
  category: LabelCategory;
  severity: LabelSeverity;
  priority_rank: number;

  fired: boolean;

  condition_human: string;
  what_it_means_cibil: string;
  why_it_matters: string;

  instances: LabelInstance[];

  /** Precomputed fact values, already resolved — keys vary per label. */
  facts_to_cite: Record<string, unknown>;

  cibil_reason_codes: string[];
  sources: SourceView[];
}

export interface LabelsResponse {
  pan_masked: string;
  customer_id: string;
  score: number;
  score_band: ScoreBand;
  as_of_date: string; // "YYYY-MM-DD"

  total_labels: number;
  n_fired: number;

  labels: LabelView[];

  /** Fired label ids bucketed by severity, each bucket priority-ordered. */
  fired_by_severity: Record<LabelSeverity, string[]>;
}

// --------------------------------------------------------------- canvas ----

export interface BandRange {
  name: string;
  min_score: number;
  max_score: number;
}

export interface ScoreHero {
  score: number;
  band: ScoreBand;
  score_min: number;
  score_max: number;

  previous_score_1mo: number | null;
  previous_score_3mo: number | null;
  score_change_1mo: number;
  score_change_3mo: number;
  score_trend: ScoreTrendDirection;

  /** 0-1: how far through its own band the score sits. */
  band_progress: number;
  bands: BandRange[];
}

export interface ScoreTrendPoint {
  label: string;
  score: number | null;
}

export interface ScoreTrend {
  points: ScoreTrendPoint[];
  trend: ScoreTrendDirection;
  change_3mo: number;
  annotation: string | null;
}

export interface CardUtilization {
  account_id: string;
  display_name: string;
  balance_paise: number;
  credit_limit_paise: number;
  utilization: number;
  is_maxed: boolean;
  is_unused: boolean;
  paydown_to_target_paise: number;
}

export interface UtilizationView {
  overall_utilization: number;
  total_balance_paise: number;
  total_credit_limit_paise: number;
  target_utilization: number;
  paydown_to_target_paise: number;

  cards: CardUtilization[];
  top_card_account_id: string | null;
  callout: string | null;
}

export interface HeatmapCell {
  period: string; // "YYYY-MM"
  label: string; // "June 2026"
  /** 0 on time, 1/2/3 late tiers (30/60/90+ days). */
  status: 0 | 1 | 2 | 3;
  has_data: boolean;
}

export interface PaymentHeatmap {
  cells: HeatmapCell[]; // always exactly 24
  months_on_time: number;
  months_total: number;
  pct_on_time: number;
  worst_status: number;
  most_recent_late_period: string | null;
  summary: string;
}

export interface CanvasResponse {
  pan_masked: string;
  customer_id: string;
  as_of_date: string;

  score_hero: ScoreHero;
  score_trend: ScoreTrend;
  utilization: UtilizationView;
  payment_heatmap: PaymentHeatmap;
  labels: LabelsResponse;
}

// -------------------------------------------------- streaming coach plan ----

export interface CoachAction {
  title: string;
  why: string;
  steps: string[];
  when_youll_see_results: string;
}

export interface CoachPlan {
  current_situation: string;
  top_actions: CoachAction[];
  what_to_avoid: string[];
  follow_up_question: string;
}

/**
 * A CoachPlan as it exists mid-stream: every field may be absent or partial
 * until the corresponding JSON has arrived. Components consuming this must
 * treat every field as optional, not just top_actions[].
 */
export type PartialCoachPlan = Partial<{
  current_situation: string;
  top_actions: Partial<CoachAction>[];
  what_to_avoid: string[];
  follow_up_question: string;
}>;

export interface Citation {
  claim: string;
  sources: string[];
  fact_ids: string[];
}

/**
 * A citation extracted from a follow-up chat reply. Distinct from the
 * analyze-flow Citation — chat citations surface inline `[label_id]` /
 * `[Source: title]` markers rather than numeric fact traces.
 */
export interface ChatCitation {
  label_id?: string;
  source_title?: string;
}

export interface ChatHistoryTurn {
  role: 'user' | 'assistant';
  content: string;
}

// ------------------------------------------------------- SSE envelopes ----
// Mirrors the `event: <name>\ndata: <json>` frames emitted by
// app/web.py's _sse() helper for POST /api/analyze and /api/chat.

export interface PlanMetadata {
  /** Model id returned by LangChain's response_metadata.model_name. */
  model: string;
  /** Input (prompt) tokens captured from usage_metadata.input_tokens. */
  prompt_tokens: number;
  /** Output (completion) tokens captured from usage_metadata.output_tokens. */
  completion_tokens: number;
}

export type AnalyzeSseEvent =
  | { event: 'canvas'; data: CanvasResponse }
  | { event: 'plan_delta'; data: PartialCoachPlan }
  | { event: 'metadata'; data: PlanMetadata }
  | { event: 'citations'; data: { citations: Citation[] } }
  | { event: 'done'; data: { ok: true } }
  | { event: 'error'; data: { message: string } };

export type ChatSseEvent =
  | { event: 'token'; data: { content: string } }
  | { event: 'guardrail'; data: { verdict: string; reason: string } }
  | { event: 'replace'; data: { content: string } }
  | { event: 'citations'; data: { citations: ChatCitation[] } }
  | { event: 'done'; data: { ok: true } }
  | { event: 'error'; data: { message: string } };
