/**
 * Tests for the localStorage-backed conversation store.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { Conversation } from './conversationStore';
import {
  __test_helpers,
  MAX_CONVERSATIONS,
  STORAGE_KEY,
  _resetConversationStore,
  appendTurn,
  clearAllConversations,
  clearTurns,
  deleteConversation,
  getConversation,
  listConversations,
  saveConversation,
} from './conversationStore';

function clearStorage() {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.clear();
  } catch {
    // jsdom occasionally returns a window with no usable localStorage; the
    // tests below only need _resetConversationStore to wipe state.
  }
}

beforeEach(() => {
  _resetConversationStore();
  clearStorage();
});

afterEach(() => {
  _resetConversationStore();
  clearStorage();
});

function makeConversation(id: string, ageMs = 0): Conversation {
  const now = new Date(Date.now() - ageMs).toISOString();
  return {
    id,
    panMasked: 'ABCPS****A',
    firstName: 'Anjali',
    incomeInr: 75000,
    canvas: null,
    initialPlan: null,
    initialMetadata: null,
    elapsedMs: 0,
    turns: [],
    createdAt: now,
    updatedAt: now,
  };
}

function makeTurn(
  role: 'user' | 'assistant' = 'user',
  text = 'hello',
): Conversation['turns'][number] {
  return {
    role,
    content: text,
  };
}

describe('conversationStore', () => {
  it('round-trips a saved conversation', () => {
    const conv = makeConversation('c1');
    saveConversation(conv);
    expect(getConversation('c1')).toMatchObject({
      id: 'c1',
      panMasked: 'ABCPS****A',
      firstName: 'Anjali',
    });
  });

  it('lists newest updates first', () => {
    saveConversation(makeConversation('older', 60_000));
    saveConversation(makeConversation('newer'));
    const list = listConversations();
    expect(list.map((c) => c.id)).toEqual(['newer', 'older']);
  });

  it('appendTurn updates the timestamp and adds the turn', () => {
    saveConversation(makeConversation('c1'));
    const updated = appendTurn('c1', makeTurn('user', 'how can I pay down faster?'));
    expect(updated).not.toBeNull();
    expect(updated!.turns).toHaveLength(1);
    expect(updated!.turns[0].role).toBe('user');
  });

  it('appendTurn returns null for unknown id', () => {
    expect(appendTurn('missing', makeTurn())).toBeNull();
  });

  it('clearTurns keeps the initial fields and empties the turns', () => {
    saveConversation(makeConversation('c1'));
    appendTurn('c1', makeTurn());
    appendTurn('c1', makeTurn('assistant', 'reply'));
    const updated = clearTurns('c1');
    expect(updated).not.toBeNull();
    expect(updated!.turns).toEqual([]);
    expect(updated!.id).toBe('c1');
  });

  it('caps at MAX_CONVERSATIONS by evicting the oldest updatedAt', () => {
    const overflow = MAX_CONVERSATIONS + 5;
    for (let i = 0; i < overflow; i++) {
      saveConversation(makeConversation(`c${i}`, (overflow - i) * 1000));
    }
    const list = listConversations();
    expect(list).toHaveLength(MAX_CONVERSATIONS);
    // The newest save (c<overflow-1>) wins; c0 (oldest age) is dropped.
    expect(list[0].id).toBe(`c${overflow - 1}`);
    expect(list.find((c) => c.id === 'c0')).toBeUndefined();
  });

  it('deleteConversation removes one entry', () => {
    saveConversation(makeConversation('c1'));
    saveConversation(makeConversation('c2'));
    deleteConversation('c1');
    expect(getConversation('c1')).toBeNull();
    expect(getConversation('c2')).not.toBeNull();
  });

  it('clearAllConversations wipes the store', () => {
    saveConversation(makeConversation('c1'));
    saveConversation(makeConversation('c2'));
    clearAllConversations();
    expect(listConversations()).toEqual([]);
  });

  it('silently skips malformed conversations on read', () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify([{ id: 'c1' }, { broken: true }, 'nope', null]),
    );
    // The defensively-shaped c1 must survive; everything else is dropped.
    expect(listConversations().map((c) => c.id)).toEqual(['c1']);
  });

  it('survives corrupted JSON in localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'not-json');
    expect(listConversations()).toEqual([]);
  });

  it('survives a non-array payload', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ not: 'an array' }));
    expect(listConversations()).toEqual([]);
  });
});

describe('conversationStore sanitizers', () => {
  it('drops turns with an unknown role', () => {
    const result = __test_helpers.sanitizeTurn({
      role: 'system',
      content: 'nope',
    });
    expect(result).toBeNull();
  });

  it('drops turns whose content is not a string', () => {
    const result = __test_helpers.sanitizeTurn({
      role: 'user',
      content: 42,
    });
    expect(result).toBeNull();
  });

  it('keeps turns with valid metadata', () => {
    const result = __test_helpers.sanitizeTurn({
      role: 'assistant',
      content: 'ok',
      metadata: { model: 'gpt-4o-mini-2024-07-18', prompt_tokens: 12, completion_tokens: 34 },
      elapsedMs: 1500,
      citations: [{ label_id: 'maxed_out' }, { source_title: 'CIBIL Score Factors' }],
    });
    expect(result).toEqual({
      role: 'assistant',
      content: 'ok',
      metadata: { model: 'gpt-4o-mini-2024-07-18', prompt_tokens: 12, completion_tokens: 34 },
      elapsedMs: 1500,
      citations: [
        { label_id: 'maxed_out' },
        { source_title: 'CIBIL Score Factors' },
      ],
    });
  });

  it('drops turns whose citations are malformed', () => {
    const result = __test_helpers.sanitizeTurn({
      role: 'assistant',
      content: 'ok',
      citations: [null, { label_id: 12 }, 'c1'],
    });
    expect(result).toEqual({
      role: 'assistant',
      content: 'ok',
      citations: [],
    });
  });

  it('returns null for a non-object conversation', () => {
    expect(__test_helpers.sanitizeConversation(null)).toBeNull();
    expect(__test_helpers.sanitizeConversation('c1')).toBeNull();
  });
});
