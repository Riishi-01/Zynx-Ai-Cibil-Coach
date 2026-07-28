/**
 * Browser-side Supabase client (anon key only).
 *
 * Initialised lazily so importing this module doesn't break the build when
 * the env vars are absent (local dev without .env, or before the Phase 1
 * deploy wires them up). When the URL or anon key is missing the getter
 * returns null and callers must no-op.
 *
 * Reads VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY, which Vite exposes at
 * build time. The service_role key MUST NEVER appear in this bundle — it
 * bypasses RLS.
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js';

let cached: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient | null {
  if (cached) return cached;

  const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

  if (!url || !anonKey) {
    return null; // env not configured — caller treats this as "no client available"
  }

  cached = createClient(url, anonKey, {
    auth: { persistSession: false }, // portfolio demo — no auth flow
  });
  return cached;
}