import { useEffect, useRef } from 'react';
import { isBusyUpload } from '../state/store';
import { ask } from '../state/controller';
import type { Conversation } from '../types';
import { AgentResponse } from './AgentResponse';
import { ContractCard } from './ContractCard';

const STARTERS = [
  "On m'a volé mon vélo dans le local commun de l'immeuble, qui n'était pas fermé à clé. Suis-je couvert ?",
  "J'ai laissé une bougie sur la table de mon jardin pendant mes vacances. Avec la chaleur, elle a fondu et abîmé la table. Est-ce couvert ?",
];

export function MessageList({ conv }: { conv: Conversation }) {
  const end = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const frozen = isBusyUpload(conv);

  useEffect(() => {
    stick.current = true;
  }, [conv.id]);

  useEffect(() => {
    if (stick.current) end.current?.scrollIntoView({ block: 'end' });
  }, [conv.messages, conv.id]);

  return (
    <div
      className="thread"
      data-frozen={frozen}
      aria-busy={frozen}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      }}
    >
      <div className="thread__inner">
        {(conv.documents?.length ?? 0) > 0 && <ContractCard documents={conv.documents ?? []} />}

        {conv.messages.length === 0 && (
          <div className="empty">
            <h2>Votre sinistre est-il couvert ?</h2>
            <p>Décrivez ce qui s'est passé. Je m'appuie sur les clauses de votre contrat, je les cite, et je vous dis quand je ne peux pas conclure.</p>
            <div className="starters">
              {STARTERS.map((s) => (
                <button key={s} className="starter" disabled={frozen} onClick={() => ask(conv.id, s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {conv.messages.map((m) =>
          m.role === 'user' ? (
            <div key={m.id} className="bubble-row">
              <p className="bubble">{m.text}</p>
            </div>
          ) : (
            <AgentResponse key={m.id} msg={m} />
          ),
        )}
        <div ref={end} />
      </div>
    </div>
  );
}
