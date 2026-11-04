import { useMemo, useState } from 'react';
import { Paperclip, Plus, Settings2, Trash2 } from 'lucide-react';
import { isBusyUpload, isRunning, useChats, useSettings, useUi } from '../state/store';
import { removeConversation } from '../state/controller';
import type { Conversation } from '../types';
import { Spinner } from './ui';

function Item({ conv, active }: { conv: Conversation; active: boolean }) {
  const select = useChats((s) => s.select);
  const setUi = useUi((s) => s.set);
  const [confirming, setConfirming] = useState(false);
  const busy = isRunning(conv) || isBusyUpload(conv);
  const lastUser = [...conv.messages].reverse().find((m) => m.role === 'user');

  return (
    <li className="conv" data-active={active}>
      {confirming ? (
        <div className="conv__confirm" role="alertdialog" aria-label="Confirmer la suppression">
          <span>Supprimer cette conversation ?</span>
          <div>
            <button className="btn btn--ghost btn--sm" onClick={() => setConfirming(false)}>
              Annuler
            </button>
            <button className="btn btn--danger btn--sm" autoFocus onClick={() => removeConversation(conv.id)}>
              Supprimer
            </button>
          </div>
        </div>
      ) : (
        <>
          <button
            className="conv__main"
            aria-current={active ? 'page' : undefined}
            onClick={() => {
              select(conv.id);
              setUi({ sidebarOpen: false, source: null });
            }}
          >
            <span className="conv__line">
              <span key={conv.title} className="conv__title fade-in">
                {conv.title}
              </span>
              {busy && <Spinner size={14} />}
              {!busy && (conv.documents?.length ?? 0) > 0 && <Paperclip size={13} aria-label="Documents importés" className="conv__clip" />}
            </span>
            <span className="conv__preview">{lastUser?.role === 'user' ? lastUser.text : 'Aucun message'}</span>
          </button>
          <button className="conv__del icon-btn" aria-label={`Supprimer « ${conv.title} »`} onClick={() => setConfirming(true)}>
            <Trash2 size={15} />
          </button>
        </>
      )}
    </li>
  );
}

export function Sidebar() {
  const conversations = useChats((s) => s.conversations);
  const activeId = useChats((s) => s.activeId);
  const create = useChats((s) => s.create);
  const { sidebarOpen, set: setUi } = useUi();
  const hasKey = useSettings((s) => s.apiKey.length > 0);
  const sorted = useMemo(() => [...conversations].sort((a, b) => b.updatedAt - a.updatedAt), [conversations]);

  return (
    <aside className="side" data-open={sidebarOpen}>
      <div className="side__top">
        <span className="side__brand">Couverture habitation</span>
        <button
          className="icon-btn"
          aria-label="Nouvelle conversation"
          title="Nouvelle conversation"
          onClick={() => {
            create();
            setUi({ sidebarOpen: false, source: null });
          }}
        >
          <Plus size={18} />
        </button>
      </div>

      <nav className="side__nav" aria-label="Conversations">
        <ul>
          {sorted.map((c) => (
            <Item key={c.id} conv={c} active={c.id === activeId} />
          ))}
        </ul>
      </nav>

      <div className="side__bottom">
        <button className="side__settings" onClick={() => setUi({ settingsOpen: true })}>
          <Settings2 size={17} />
          <span>Réglages LLM</span>
          <span className="status" data-on={hasKey}>
            {hasKey ? 'Prêt' : 'À configurer'}
          </span>
        </button>
      </div>
    </aside>
  );
}
