/**
 * Normalize LaTeX delimiters from `\(..\)` / `\[..\]` (ChatGPT convention)
 * to `$..$` / `$$..$$` (remark-math convention).
 *
 * See SPEC.md §4.6: remark-math supports both, but being explicit avoids
 * edge cases. The system prompt already requests `$..$` but models sometimes
 * slip, so this normalizer runs on every chunk before rendering.
 */

export function normalizeLatex(s: string): string {
  return s
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, t) => `$$${t}$$`)
    .replace(/\\\((.*?)\\\)/g, (_, t) => `$${t}$`);
}
