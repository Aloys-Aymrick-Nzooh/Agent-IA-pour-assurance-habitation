import { useEffect, useState } from 'react';
import { BadgeCheck, ChevronLeft, ChevronRight, CircleAlert, X } from 'lucide-react';
import { getBackendPage } from '../api/client';
import { useUi } from '../state/store';
import type { Conversation } from '../types';
import { chipLabel } from '../lib/utils';
import { MarkdownContent } from './MarkdownContent';

export function SourceDrawer({ conv }: { conv: Conversation }) {
  const source = useUi((s) => s.source);
  const setUi = useUi((s) => s.set);
  const [pageText, setPageText] = useState('');
  const [pageError, setPageError] = useState('');

  useEffect(() => {
    if (!source) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setUi({ source: null });
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [source, setUi]);

  const msg = source ? conv.messages.find((m) => m.id === source.messageId) : undefined;
  const citations = msg?.role === 'agent' ? (msg.answer?.citations ?? []) : [];
  const backendCitations = msg?.role === 'agent' ? (msg.backendAnswer?.citations ?? []) : [];
  const dedupedCitations = [...citations, ...backendCitations].filter((citation, index, list) => {
    const key = `${citation.documentId ?? 'unknown'}:${citation.documentType ?? 'unknown'}:${citation.page}`;
    return list.findIndex((item) => `${item.documentId ?? 'unknown'}:${item.documentType ?? 'unknown'}:${item.page}` === key) === index;
  });
  const allCitations = dedupedCitations;
  const idx = source ? allCitations.findIndex((c) => c.id === source.citationId) : -1;
  const c = idx >= 0 ? allCitations[idx] : undefined;

  useEffect(() => {
    if (!source || !conv.backendId || !c?.documentId) {
      setPageText('');
      setPageError('');
      return;
    }

    let active = true;
    setPageText('');
    setPageError('');
    void getBackendPage(conv.backendId, c.documentId, c.page)
      .then((page) => active && setPageText(page.text))
      .catch((error: unknown) => active && setPageError(error instanceof Error ? error.message : 'Impossible de charger cette page.'));
    return () => {
      active = false;
    };
  }, [conv.backendId, c?.documentId, c?.page, source]);

  if (!source || idx < 0 || !c) return null;
  const go = (d: number) => setUi({ source: { messageId: source.messageId, citationId: allCitations[idx + d].id } });

  return (
    <aside className="drawer" aria-label="Détail de la source">
      <header className="drawer__head">
        <div>
          <h2>{chipLabel(c)}</h2>
          <p>
            Source {idx + 1} sur {allCitations.length}
          </p>
        </div>
        <div className="drawer__nav">
          <button className="icon-btn" aria-label="Source précédente" disabled={idx === 0} onClick={() => go(-1)}>
            <ChevronLeft size={18} />
          </button>
          <button className="icon-btn" aria-label="Source suivante" disabled={idx === allCitations.length - 1} onClick={() => go(1)}>
            <ChevronRight size={18} />
          </button>
          <button className="icon-btn" aria-label="Fermer la source" onClick={() => setUi({ source: null })}>
            <X size={18} />
          </button>
        </div>
      </header>

      <div className="drawer__body">
        <p className="drawer__origin" data-origin={c.source}>
          {c.documentName ? `${c.documentType} · ${c.documentName}` : c.source === 'catalog' ? 'Conditions générales' : 'Document importé'}
        </p>
        <p className="drawer__crumb">{c.breadcrumb}</p>

        <div className="excerpt">
          {pageError ? <p className="excerpt__error">{pageError}</p> : <MarkdownContent text={pageText || c.excerpt || 'Chargement de la page source…'} className="excerpt__markdown" />}
        </div>

        <p className="drawer__verify" data-ok={c.verified}>
          {c.verified ? (
            <>
              <BadgeCheck size={16} /> Référence renvoyée par le backend, page {c.page}.
            </>
          ) : (
            <>
              <CircleAlert size={16} /> Cet extrait n'a pas pu être vérifié dans le document.
            </>
          )}
        </p>

      </div>
    </aside>
  );
}
