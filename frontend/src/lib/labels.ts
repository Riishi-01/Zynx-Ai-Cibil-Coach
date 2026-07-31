/**
 * Human-readable display names for the 32 chat-KB labels.
 *
 * Source of truth lives in the Python ``app.chat_kb_data`` artifact. This
 * hand-maintained mirror exists because shipping the full sources map to
 * the bundle just to render citation pills is unnecessary weight.
 */
export const LABEL_NAMES: Record<string, { name: string }> = {
  maxed_out: { name: 'Maxed Out' },
  all_cards_maxed: { name: 'All Cards Maxed' },
  maxed_out_account: { name: 'Maxed-Out Card' },
  very_high_utilization: { name: 'Very High Utilization' },
  high_utilization: { name: 'High Utilization' },
  low_utilization: { name: 'Low Utilization' },
  utilization_concentration: { name: 'Utilization Concentration' },
  major_delinquency: { name: 'Major Delinquency' },
  serious_delinquency: { name: 'Serious Delinquency' },
  recent_late_payment: { name: 'Recent Late Payment' },
  perfect_payment: { name: 'Perfect Payment' },
  zero_utilization_paradox: { name: 'Zero Utilization Paradox' },
  recent_inquiries: { name: 'Recent Inquiries' },
  credit_seeking_pattern: { name: 'Credit Seeking Pattern' },
  excessive_new_credit: { name: 'Excessive New Credit' },
  disputable_collection: { name: 'Disputable Collection' },
  collection_past_sol: { name: 'Collection Past SOL' },
  paid_collection_still_reporting: { name: 'Paid Collection Still Reporting' },
  thin_file: { name: 'Thin File' },
  extreme_thin_file: { name: 'Extreme Thin File' },
  no_revolving_credit: { name: 'No Revolving Credit' },
  unused_revolving_cards: { name: 'Unused Revolving Cards' },
  single_card_dependency: { name: 'Single Card Dependency' },
  oldest_card_at_risk: { name: 'Oldest Card At Risk' },
  single_card_limit_share: { name: 'Single Card Limit Share' },
  score_falling: { name: 'Score Falling' },
  score_rising: { name: 'Score Rising' },
  score_volatile: { name: 'Score Volatile' },
  high_dti: { name: 'High DTI' },
  severe_dti: { name: 'Severe DTI' },
  data_staleness: { name: 'Data Staleness' },
  credit_score_context: { name: 'Credit Score Context' },
};

export function labelDisplayName(labelId: string): string {
  return LABEL_NAMES[labelId]?.name ?? labelId;
}
