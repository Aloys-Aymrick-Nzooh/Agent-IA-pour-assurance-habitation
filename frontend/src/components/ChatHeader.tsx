import { Check, Menu, Upload } from 'lucide-react';
import { useUi } from '../state/store';
import type { Conversation } from '../types';
import { Spinner } from './ui';

export function ChatHeader({ conv }: { conv: Conversation }) {
  const setUi = useUi((s) => s.set);
  const up = conv.upload;
  const busy = up.status === 'uploading' || up.status === 'indexing';
  const hasDocuments = (conv.documents?.length ?? 0) > 0;

  return (
    <header className="head">
      <button className="icon-btn head__menu" aria-label="Ouvrir les conversations" onClick={() => setUi({ sidebarOpen: true })}>
        <Menu size={20} />
      </button>
      <h1 key={conv.title} className="head__title fade-in" title={conv.title}>
        {conv.title}
      </h1>
      <button className="btn btn--outline head__upload" data-state={busy ? 'uploading' : hasDocuments ? 'ready' : up.status} onClick={() => setUi({ uploadOpen: true })}>
        {busy ? <Spinner /> : hasDocuments ? <Check size={16} /> : <Upload size={16} />}
        <span>
          {busy ? 'Indexation en cours' : hasDocuments ? `Documents (${conv.documents?.length})` : up.status === 'error' ? "Réessayer l'import" : 'Importer un document'}
        </span>
      </button>
    </header>
  );
}

export function NoticeBar({ conv }: { conv: Conversation }) {
  const setUi = useUi((s) => s.set);
  const missing = (conv.documents?.length ?? 0) === 0;
  if (!missing || conv.messages.length === 0) return null;
  return (
    <div className="notice" role="note">
      <span>Aucun document n'est encore indexé pour cette conversation.</span>
      <button className="link-btn" onClick={() => setUi({ uploadOpen: true })}>
        Importer
      </button>
    </div>
  );
}
