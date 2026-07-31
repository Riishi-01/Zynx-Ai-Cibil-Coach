import type { ChatCitation } from '../../types';
import { labelDisplayName } from '../../lib/labels';

interface ChatCitationsProps {
  citations: ChatCitation[];
}

/**
 * Renders one pill per citation beneath an assistant reply.
 *
 * Hover-only in v1 — clicking a pill does nothing because the public KB
 * URL structure isn't in scope. The title and label are still useful as
 * affordances that the answer is sourced.
 */
export function ChatCitations({ citations }: ChatCitationsProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="chat-citations" aria-label="Sources cited in this reply">
      {citations.map((cite, index) => {
        if (cite.label_id) {
          return (
            <span
              key={`label-${cite.label_id}-${index}`}
              className="chat-citation-pill"
              title={`Label: ${cite.label_id}`}
            >
              {labelDisplayName(cite.label_id)}
            </span>
          );
        }
        if (cite.source_title) {
          return (
            <span
              key={`source-${cite.source_title}-${index}`}
              className="chat-citation-pill"
              title={cite.source_title}
            >
              {cite.source_title}
            </span>
          );
        }
        return null;
      })}
    </div>
  );
}
