/**
 * localStorage-backed conversation store for the dock history panel.
 *
 * Each conversation freezes the analyzer canvas, plan, and the chat turns
 * that follow. Reopening a conversation is a pure read — no LLM call.
 *
 * The store caps itself at {@link MAX_CONVERSATIONS} entries; when that
 * ceiling is hit, the oldest (smallest `updatedAt`) entry is dropped on
 * each subsequent write. Reads tolerate malformed payloads.
 *
 * Persistence key versioning lives in the constant below — bump the
 * suffix if the {@link Conversation} shape breaks compat.
 */

import type {
  CanvasResponse,
  ChatCitation,
  PartialCoachPlan,
  PlanMetadata,
} from '../types';

const STORAGE_KEY = 'cibil-coach.conversations.v1';
export const MAX_CONVERSATIONS = 50;

export interface ConversationTurn {
  role: 'user' | 'assistant';
  content: string;
  metadata?: PlanMetadata;
  elapsedMs?: number;
  citations?: ChatCitation[];
}

export interface Conversation {
  id: string;
  panMasked: string;
  firstName: string | null;
  incomeInr: number;
  /** Frozen analyzer payload — charts render from this directly on reopen. */
  canvas: CanvasResponse | null;
  /** The structured CoachPlan emitted by /api/analyze. */
  initialPlan: PartialCoachPlan | null;
  /** Metadata for the initial analyzer call. */
  initialMetadata: PlanMetadata | null;
  elapsedMs: number;
  /** Chat turns appended after the initial plan. Empty until the user types. */
  turns: ConversationTurn[];
  /** ISO timestamp. */
  createdAt: string;
  /** ISO timestamp. Updated whenever turns are appended or the chat is cleared. */
  updatedAt: string;
}

function emptyConversation(): Conversation {
  const now = new Date().toISOString();
  return {
    id: '',
    panMasked: '',
    firstName: null,
    incomeInr: 0,
    canvas: null,
    initialPlan: null,
    initialMetadata: null,
    elapsedMs: 0,
    turns: [],
    createdAt: now,
    updatedAt: now,
  };
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function asArray<T>(value: unknown, guard: (item: unknown) => item is T): T[] {
  return Array.isArray(value) ? value.filter(guard) : [];
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function sanitizeCitation(input: unknown): ChatCitation | null {
  if (!isObject(input)) return null;
  const labelId = typeof input.label_id === 'string' ? input.label_id : undefined;
  const sourceTitle =
    typeof input.source_title === 'string' ? input.source_title : undefined;
  if (!labelId && !sourceTitle) return null;
  return { label_id: labelId, source_title: sourceTitle };
}

function sanitizeTurn(input: unknown): ConversationTurn | null {
  if (!isObject(input)) return null;
  const role = asString(input.role);
  if (role !== 'user' && role !== 'assistant') return null;
  if (typeof input.content !== 'string') return null;
  const content = input.content;
  return {
    role,
    content,
    metadata: isObject(input.metadata)
      ? {
          model: asString(input.metadata.model),
          prompt_tokens: asNumber(input.metadata.prompt_tokens),
          completion_tokens: asNumber(input.metadata.completion_tokens),
        }
      : undefined,
    elapsedMs:
      typeof input.elapsedMs === 'number' && Number.isFinite(input.elapsedMs)
        ? input.elapsedMs
        : undefined,
    citations: asArray(input.citations, isObject)
      .map(sanitizeCitation)
      .filter((cite): cite is ChatCitation => cite !== null),
  };
}

function sanitizeConversation(input: unknown): Conversation | null {
  if (!isObject(input)) return null;
  const id = asString(input.id);
  if (!id) return null;
  const base = emptyConversation();
  return {
    ...base,
    id,
    panMasked: asString(input.panMasked),
    firstName: typeof input.firstName === 'string' ? input.firstName : null,
    incomeInr: asNumber(input.incomeInr),
    canvas: isObject(input.canvas)
      ? (input.canvas as unknown as CanvasResponse)
      : null,
    initialPlan: isObject(input.initialPlan)
      ? (input.initialPlan as unknown as PartialCoachPlan)
      : null,
    initialMetadata: isObject(input.initialMetadata)
      ? (input.initialMetadata as unknown as PlanMetadata)
      : null,
    elapsedMs: asNumber(input.elapsedMs),
    turns: asArray(input.turns, isObject)
      .map(sanitizeTurn)
      .filter((turn): turn is ConversationTurn => turn !== null),
    createdAt: asString(input.createdAt, base.createdAt),
    updatedAt: asString(input.updatedAt, base.updatedAt),
  };
}

function readAll(): Conversation[] {
  if (typeof window === 'undefined') return [];
  const store = window.localStorage;
  if (!store || typeof store.getItem !== 'function') return [];
  let raw: string | null = null;
  try {
    raw = store.getItem(STORAGE_KEY);
  } catch {
    return [];
  }
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  return parsed
    .map(sanitizeConversation)
    .filter((conv): conv is Conversation => conv !== null);
}

function writeAll(conversations: Conversation[]): void {
  if (typeof window === 'undefined') return;
  const store = window.localStorage;
  if (!store || typeof store.setItem !== 'function') return;
  const trimmed = conversations.slice(0, MAX_CONVERSATIONS);
  try {
    store.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // QuotaExceededError or storage unavailable: drop the write rather than crash.
  }
}

function evictOldest(conversations: Conversation[]): Conversation[] {
  if (conversations.length <= MAX_CONVERSATIONS) return conversations;
  const sorted = [...conversations].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
  return sorted.slice(0, MAX_CONVERSATIONS);
}

/** List conversations, newest updatedAt first. */
export function listConversations(): Conversation[] {
  const all = readAll();
  return [...all].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

/** Look up a conversation by id. */
export function getConversation(id: string): Conversation | null {
  if (!id) return null;
  return readAll().find((conv) => conv.id === id) ?? null;
}

/** Persist or replace a conversation. Caps to MAX_CONVERSATIONS oldest-first. */
export function saveConversation(conv: Conversation): void {
  if (!conv.id) return;
  const nowIso = new Date().toISOString();
  const existing = readAll().find((entry) => entry.id === conv.id);
  // The dock reads `updatedAt` to order the panel. New conversations
  // get `now`; existing records preserve their `updatedAt` so an
  // overwrite (e.g. caller re-saves with new content without new turns)
  // doesn't bubble the row to the top of the list.
  const stamped: Conversation = {
    ...conv,
    createdAt: conv.createdAt || existing?.createdAt || nowIso,
    updatedAt:
      conv.updatedAt ||
      existing?.updatedAt ||
      nowIso,
  };
  const filtered = readAll().filter((entry) => entry.id !== stamped.id);
  filtered.push(stamped);
  writeAll(evictOldest(filtered));
}

/** Append a turn to a stored conversation; returns the updated copy. */
export function appendTurn(
  id: string,
  turn: ConversationTurn,
): Conversation | null {
  const conversations = readAll();
  const index = conversations.findIndex((conv) => conv.id === id);
  if (index === -1) return null;
  const existing = conversations[index];
  const updated: Conversation = {
    ...existing,
    turns: [...existing.turns, turn],
    updatedAt: new Date().toISOString(),
  };
  const filtered = conversations.filter((conv) => conv.id !== id);
  filtered.push(updated);
  writeAll(evictOldest(filtered));
  return updated;
}

/** Drop the chat turns only — canvas/plan/metadata survive. */
export function clearTurns(id: string): Conversation | null {
  const conversations = readAll();
  const index = conversations.findIndex((conv) => conv.id === id);
  if (index === -1) return null;
  const existing = conversations[index];
  const updated: Conversation = {
    ...existing,
    turns: [],
    updatedAt: new Date().toISOString(),
  };
  const filtered = conversations.filter((conv) => conv.id !== id);
  filtered.push(updated);
  writeAll(evictOldest(filtered));
  return updated;
}

/** Remove a single conversation from storage. */
export function deleteConversation(id: string): void {
  if (!id) return;
  writeAll(readAll().filter((conv) => conv.id !== id));
}

/** Wipe every stored conversation. */
export function clearAllConversations(): void {
  writeAll([]);
}

/** Test seam — restore the storage key to a clean slate. */
export function _resetConversationStore(): void {
  if (typeof window === 'undefined') return;
  const store = window.localStorage;
  if (!store || typeof store.removeItem !== 'function') return;
  try {
    store.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable; nothing to clear.
  }
}

export const __test_helpers = {
  emptyConversation,
  sanitizeConversation,
  sanitizeTurn,
};

export { STORAGE_KEY };
