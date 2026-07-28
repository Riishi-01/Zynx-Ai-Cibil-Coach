import { Component, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';

import { bufferStreamingMarkdown } from '../../lib/markdownBuffer';
import { normalizeLatex } from '../../lib/latex';

interface MarkdownRendererProps {
  text: string;
  streaming?: boolean;
}

/**
 * Renders Markdown + GFM + LaTeX (SPEC.md §4.6).
 * During streaming, auto-closes unterminated fences and normalizes LaTeX
 * delimiters so the parser never breaks on a half-open token.
 */
export function MarkdownRenderer({ text, streaming = false }: MarkdownRendererProps) {
  const safe = streaming ? bufferStreamingMarkdown(text) : text;
  const normalized = normalizeLatex(safe);

  return (
    <LaTeXErrorBoundary>
      <div className="markdown-body">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeHighlight, rehypeKatex]}
        >
          {normalized}
        </ReactMarkdown>
      </div>
    </LaTeXErrorBoundary>
  );
}

/**
 * Catches KaTeX render errors (e.g. unbalanced $) and falls back to showing
 * the raw text rather than crashing the whole message bubble (SPEC.md §4.6).
 */
class LaTeXErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return <div className="markdown-body">{this.props.children}</div>;
    }
    return this.props.children;
  }
}
