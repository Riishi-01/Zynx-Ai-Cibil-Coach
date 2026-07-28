/**
 * Turnstile integration — env-gated.
 *
 * Phase 1 (first Vercel deploy): VITE_TURNSTILE_SITE_KEY is unset, so
 * getTurnstileToken() resolves to null and the backend's verify_turnstile()
 * short-circuits to True. No widget renders.
 *
 * Phase 2 (after Cloudflare registration): set VITE_TURNSTILE_SITE_KEY +
 * TURNSTILE_SECRET_KEY in Vercel env, redeploy, and the widget mounts and
 * returns tokens. The mount/render is driven from InputForm.tsx via
 * <Turnstile /> — this module just exposes the token getter.
 */

export function getTurnstileSiteKey(): string | null {
  const key = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;
  return key && key.length > 0 ? key : null;
}

export function turnstileEnabled(): boolean {
  return getTurnstileSiteKey() !== null;
}