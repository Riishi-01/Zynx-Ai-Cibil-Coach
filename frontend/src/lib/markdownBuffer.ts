/**
 * Pre-process in-flight Markdown so react-markdown never sees a half-open
 * code fence or backtick span. The final Markdown (after stream end) is
 * rendered untouched — this only applies during streaming.
 *
 * See SPEC.md §4.5.
 */

export function bufferStreamingMarkdown(s: string): string {
  let out = s;

  // 1. Close any unterminated ``` code block.
  const fences = (out.match(/```/g) || []).length;
  if (fences % 2 === 1) out += '\n```';

  // 2. Close any unterminated inline ` code span.
  const backticks = (out.match(/(?<!`)`(?!`)/g) || []).length;
  if (backticks % 2 === 1) out += '`';

  return out;
}
