/**
 * All user-visible strings in one place so PMs can edit copy without grep.
 * Keep keys stable — tests may reference them.
 */
export const COPY = {
  analyzer: {
    brand: 'CIBIL Credit Coach',
    chatSection: 'Chat',
    canvasSection: 'Credit profile canvas',
  },
  form: {
    submit: 'Get Credit Analyzed',
    submitting: 'Analysing…',
  },
  summary: {
    panLabel: 'PAN',
    incomeUnit: '/ mo',
    editAria: (pan: string, income: string) =>
      `Editing details for PAN ${pan}, income ${income}. Click to edit.`,
  },
  error: {
    retry: 'Try again',
  },
  chat: {
    /** Empty state shown when the stream completes with no plan, no text, no
     *  error and no follow-up turns. Reachable only on a degenerate
     *  response. Includes a retry path. */
    emptyNoResponse: 'No analysis received.',
    emptyNoResponseHint: 'You can retry — the canvas may still be useful.',
    crunching: 'Crunching the numbers…',
    outOfScope:
      "I'm your credit coach, so I can only help with credit report questions — score, utilization, payment history, collections, and similar. I can't advise on investments, career, housing, or tax planning. Want to ask something credit-related instead?",
    outOfScopeShort: "That's outside what I cover as a credit coach.",
  },
  composer: {
    placeholder: 'Ask about your credit report…',
    sendAria: 'Send message',
    stopAria: 'Stop generating',
    disabledHint: 'Complete the analysis first to start chatting.',
  },
  message: {
    metadataAria: 'Response metadata',
    clearChat: 'Clear conversation',
    clearChatConfirmTitle: 'Clear conversation?',
    clearChatConfirmBody:
      'This removes your follow-up questions and the AI replies. The original coaching plan stays.',
    clearChatConfirmCancel: 'Cancel',
    clearChatConfirmConfirm: 'Clear',
  },
  dock: {
    home: 'Home',
    homeAria: 'Home — return to the input form',
    history: 'History',
    historyAria: (count: number) =>
      `History (${count} conversation${count === 1 ? '' : 's'})`,
    historyEmpty: 'No analyses yet — your first run will appear here.',
    historyClearAll: 'Clear all',
    historyDelete: 'Delete conversation',
    chat: 'Chat',
    chatAria: 'Clear chat history',
    chatDisabledHint: 'Chat is empty',
  },
  analysisFooter: {
    /** Display name shown in the footer — matches the actual model used. */
    modelDisplay: 'gpt-4o-mini',
    separator: ' · ',
    /** OpenAI gpt-4o-mini standard text pricing (USD per 1M tokens). */
    cost: {
      inputPer1M: 0.15 as number,
      outputPer1M: 0.6 as number,
      currencySymbol: '$',
      /** Decimal places shown for the cost (e.g. 4 -> "$0.0005"). */
      decimals: 4 as number,
    },
  },
  dropdown: {
    placeholder: 'Search by PAN or first name',
    hintDefault: 'Pick a record from the list',
    hintSelected: (label: string) => `Selected: ${label}`,
    empty: 'No matches',
  },
  income: {
    label: 'Monthly income',
    hintDefault: 'Monthly income, e.g. ₹75,000',
    hintTooLow: 'Income must be greater than zero',
    hintTooHigh: 'That number looks too large — check for extra digits',
    placeholder: '75,000',
  },
} as const;
