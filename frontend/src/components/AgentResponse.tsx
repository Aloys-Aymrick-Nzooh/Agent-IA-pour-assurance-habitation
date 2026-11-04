import { Fragment, useEffect, useState } from 'react';
import { BadgeCheck, Check, ChevronDown, CircleAlert, CircleHelp, Info, BookOpen, ShieldCheck, ShieldX, X } from 'lucide-react';
import type { AgentAnswer, AgentMessage, BackendAnswer, Citation, Step, Verdict } from '../types';
import { chipLabel, formatDuration } from '../lib/utils';
import { useUi } from '../state/store';
import { Spinner } from './ui';
import { MarkdownContent } from './MarkdownContent';

/* ---------- Barre d'étapes (haut de la réponse) ---------- */

function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function StepIcon({ status }: { status: Step['status'] }) {
  if (status === 'running') return <Spinner size={14} />;
  if (status === 'error') return <X size={14} />;
  return <Check size={14} />;
}

function StepsBar({ msg }: { msg: AgentMessage }) {
  const running = msg.status === 'running';
  const now = useNow(running);
  const [manual, setManual] = useState<boolean | null>(null);
  const open = manual ?? running; // ouvert pendant l'exécution, replié ensuite
  const current = [...msg.steps].reverse().find((s) => s.status === 'running') ?? msg.steps[msg.steps.length - 1];
  const elapsed = formatDuration((msg.endedAt ?? now) - msg.startedAt);

  const label = running
    ? (current?.label ?? 'Analyse en cours')
    : msg.status === 'error'
      ? 'Analyse interrompue'
      : msg.question
        ? "J'ai besoin d'une précision"
        : 'Analyse terminée';

  return (
    <div className="steps" data-status={msg.status}>
      <button className="steps__head" aria-expanded={open} onClick={() => setManual(!open)}>
        <span className="steps__state" aria-hidden="true">
          {running ? <Spinner size={15} /> : msg.status === 'error' ? <CircleAlert size={15} /> : <Check size={15} />}
        </span>
        <span className="steps__label" aria-live="polite">
          {label}
        </span>
        <span className="steps__meta">
          {msg.steps.length > 0 && `${msg.steps.length} étape${msg.steps.length > 1 ? 's' : ''} · `}
          {elapsed}
        </span>
        <ChevronDown size={16} className="steps__chev" aria-hidden="true" />
      </button>
      {open && msg.steps.length > 0 && (
        <ol className="steps__list">
          {msg.steps.map((s) => (
            <li key={s.id} data-status={s.status}>
              <span className="steps__dot">
                <StepIcon status={s.status} />
              </span>
              <span className="steps__text">
                <span>{s.label}</span>
                {s.detail && <small>{s.detail}</small>}
              </span>
              {s.endedAt && <span className="steps__time">{formatDuration(s.endedAt - s.startedAt)}</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/* ---------- Corps de la réponse ---------- */

const VERDICTS: Record<Verdict, { label: string; tone: string; Icon: typeof Info }> = {
  COUVERT: { label: 'Couvert', tone: 'green', Icon: ShieldCheck },
  NON_COUVERT_PROBABLE: { label: 'Probablement non couvert', tone: 'coral', Icon: ShieldX },
  INDETERMINE: { label: 'Je ne peux pas conclure', tone: 'slate', Icon: CircleHelp },
  INFO_MANQUANTE: { label: 'Il me manque une information', tone: 'amber', Icon: Info },
};

function RichText({ text, citations, onCite }: { text: string; citations: Citation[]; onCite: (id: string) => void }) {
  return (
    <>
      {text.split(/(\[\[c\d+\]\])/g).map((part, i) => {
        const m = part.match(/^\[\[(c\d+)\]\]$/);
        if (!m) return <Fragment key={i}>{part}</Fragment>;
        const idx = citations.findIndex((c) => c.id === m[1]);
        if (idx < 0) return null;
        return (
          <button key={i} className="cite" onClick={() => onCite(m[1])} aria-label={`Source ${idx + 1}, ${chipLabel(citations[idx])}`}>
            {idx + 1}
          </button>
        );
      })}
    </>
  );
}

const CONDITION_ICON = { remplie: Check, non_remplie: X, inconnue: CircleHelp } as const;
const CONDITION_LABEL = { remplie: 'Remplie', non_remplie: 'Non remplie', inconnue: 'Inconnue' } as const;

function AnswerBody({ answer, onCite }: { answer: AgentAnswer; onCite: (id: string) => void }) {
  const v = VERDICTS[answer.verdict];
  const level = { basse: 1, moyenne: 2, haute: 3 }[answer.confidence];
  const idxOf = (id: string) => answer.citations.findIndex((c) => c.id === id);

  return (
    <div className="answer">
      <div className="answer__top">
        <span className="verdict" data-tone={v.tone}>
          <v.Icon size={16} aria-hidden="true" /> {v.label}
        </span>
        <span className="confidence" title={`Confiance ${answer.confidence}`}>
          <span className="confidence__bars" data-level={level} aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          Confiance {answer.confidence}
        </span>
      </div>

      {answer.summary.split(/\n{2,}/).map((p, i) => (
        <p key={i} className="answer__text">
          <RichText text={p} citations={answer.citations} onCite={onCite} />
        </p>
      ))}

      {answer.conditions.length > 0 && (
        <section>
          <h3>Conditions de la garantie</h3>
          <ul className="conditions">
            {answer.conditions.map((c, i) => {
              const Icon = CONDITION_ICON[c.status];
              return (
                <li key={i} data-status={c.status}>
                  <span className="conditions__icon">
                    <Icon size={13} aria-hidden="true" />
                    <span className="visually-hidden">{CONDITION_LABEL[c.status]} : </span>
                  </span>
                  <span>
                    {c.text}
                    {c.citationIds.map((id) => {
                      const i = idxOf(id);
                      return i < 0 ? null : (
                        <button key={id} className="cite" onClick={() => onCite(id)} aria-label={`Source ${i + 1}`}>
                          {i + 1}
                        </button>
                      );
                    })}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {answer.missingFacts.length > 0 && (
        <section>
          <h3>Ce qui me manque</h3>
          <ul className="plain">
            {answer.missingFacts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      {answer.ambiguities.length > 0 && (
        <section>
          <h3>Points ambigus dans le contrat</h3>
          <ul className="plain">
            {answer.ambiguities.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      {answer.limits && (
        <p className="answer__limits">
          <Info size={14} aria-hidden="true" /> {answer.limits}
        </p>
      )}
    </div>
  );
}

function BackendAnswerBody({ answer, onCite }: { answer: BackendAnswer; onCite: (id: string) => void }) {
  return (
    <div className="answer">
      <MarkdownContent text={answer.text} className="answer__markdown" citations={answer.citations} onCite={onCite} />
      {answer.limitations.length > 0 && (
        <section>
          <h3>Limites de la réponse</h3>
          <ul className="plain">
            {answer.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}

/* ---------- Barre de sources (bas de la réponse) ---------- */

function SourcesBar({ msg, answer, onCite, emptyText }: { msg: AgentMessage; answer: { citations: Citation[] }; onCite: (id: string) => void; emptyText?: string }) {
  const selected = useUi((s) => (s.source?.messageId === msg.id ? s.source.citationId : null));
  return (
    <footer className="sources">
      <span className="sources__title">
        <BookOpen size={15} aria-hidden="true" /> Sources
        <span className="sources__count">{answer.citations.length}</span>
      </span>
      {answer.citations.length === 0 ? (
        <span className="sources__none">{emptyText ?? 'Aucune clause citable : je ne conclus pas au-delà de ce qui est écrit.'}</span>
      ) : (
        <div className="sources__chips">
          {answer.citations.map((c, i) => (
            <button key={c.id} className="chip" data-active={selected === c.id} data-origin={c.source} onClick={() => onCite(c.id)}>
              <span className="chip__n">{i + 1}</span>
              {chipLabel(c)}
              {c.verified ? (
                <BadgeCheck size={14} className="chip__ok" aria-label="Extrait vérifié mot pour mot" />
              ) : (
                <CircleAlert size={14} className="chip__warn" aria-label="Extrait non vérifié" />
              )}
            </button>
          ))}
        </div>
      )}
    </footer>
  );
}

/* ---------- Réponse complète : étapes / contenu / sources ---------- */

export function AgentResponse({ msg }: { msg: AgentMessage }) {
  const setUi = useUi((s) => s.set);
  const open = (citationId: string) => setUi({ source: { messageId: msg.id, citationId } });

  return (
    <article className="agent" aria-busy={msg.status === 'running'}>
      <StepsBar msg={msg} />
      <div className="agent__body">
        {msg.backendAnswer ? (
          <BackendAnswerBody answer={msg.backendAnswer} onCite={open} />
        ) : msg.answer ? (
          <AnswerBody answer={msg.answer} onCite={open} />
        ) : msg.question ? (
          <p className="answer__text">{msg.question}</p>
        ) : msg.error ? (
          <p className="agent__error" role="alert">
            <CircleAlert size={16} /> {msg.error}
          </p>
        ) : (
          <div className="skeleton" aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
        )}
      </div>
      {msg.backendAnswer && <SourcesBar msg={msg} answer={msg.backendAnswer} onCite={open} emptyText="Aucune citation documentaire n'a été renvoyée pour cette réponse." />}
      {msg.answer && <SourcesBar msg={msg} answer={msg.answer} onCite={open} />}
    </article>
  );
}
