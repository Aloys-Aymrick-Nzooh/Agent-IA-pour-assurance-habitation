import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Citation } from '../types';
import { chipLabel } from '../lib/utils';

function citationLink(chunkId: string, citations: Citation[]): string {
  let index = citations.findIndex((citation) => citation.chunkId === chunkId);
  if (index < 0 && chunkId.includes(':')) {
    const pageKey = chunkId.split(':').slice(0, -1).join(':');
    index = citations.findIndex((citation) => citation.chunkId?.split(':').slice(0, -1).join(':') === pageKey);
  }
  if (index < 0) return '';
  return `[${index + 1}](#citation-${encodeURIComponent(citations[index].id)})`;
}

function prepareMarkdown(text: string, citations: Citation[]): string {
  return text
    .replace(/\[\[cite:([^\]]+)\]\]/gi, (_marker, chunkId: string) => citationLink(chunkId, citations))
    .replace(/\(([^)]*\bchunk_id\s*:\s*([^,\s)]+)[^)]*)\)/gi, (_reference, _details: string, chunkId: string) => citationLink(chunkId, citations));
}

export function MarkdownContent({
  text,
  className,
  citations = [],
  onCite,
}: {
  text: string;
  className?: string;
  citations?: Citation[];
  onCite?: (citationId: string) => void;
}) {
  const components: Components = {
    a: ({ href, children }) => {
      if (href?.startsWith('#citation-')) {
        let citationId: string;
        try {
          citationId = decodeURIComponent(href.slice('#citation-'.length));
        } catch {
          return null;
        }
        const index = citations.findIndex((citation) => citation.id === citationId);
        const citation = citations[index];
        if (!citation || !onCite) return null;
        return (
          <button
            type="button"
            className="cite"
            onClick={() => onCite(citation.id)}
            aria-label={`Ouvrir la source ${index + 1}, ${chipLabel(citation)}`}
            title={`Source ${index + 1} · ${chipLabel(citation)}`}
          >
            {index + 1}
          </button>
        );
      }
      return (
        <a href={href} target={href?.startsWith('http') ? '_blank' : undefined} rel={href?.startsWith('http') ? 'noreferrer' : undefined}>
          {children}
        </a>
      );
    },
    table: ({ children }) => (
      <div className="markdown-table-wrap">
        <table>{children}</table>
      </div>
    ),
  };

  return (
    <div className={className ? `markdown-body ${className}` : 'markdown-body'}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {prepareMarkdown(text, citations)}
      </ReactMarkdown>
    </div>
  );
}