import { useReducedMotion as useFramerReducedMotion } from 'framer-motion';

/**
 * Whether the user has requested reduced motion.
 *
 * Thin wrapper over framer-motion's own hook (which already tracks
 * `prefers-reduced-motion` via a matchMedia listener) so every component in
 * this app imports it from `hooks/` per the project's file layout, and so a
 * future swap of animation library only touches this one file.
 */
export function useReducedMotion(): boolean {
  return useFramerReducedMotion() ?? false;
}
