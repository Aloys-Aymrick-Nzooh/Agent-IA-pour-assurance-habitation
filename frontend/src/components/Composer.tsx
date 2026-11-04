import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowUp } from 'lucide-react';
import { isBusyUpload, isRunning, useSettings, useUi } from '../state/store';
import { ask } from '../state/controller';
import type { Conversation } from '../types';
import { Spinner } from './ui';

export function Composer({ conv }: { conv: Conversation }) {
  const [text, setText] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);
  const hasKey = useSettings((s) => s.apiKey.length > 0);
  const setUi = useUi((s) => s.set);
  const running = isRunning(conv);
  const frozen = isBusyUpload(conv);
  const up = conv.upload.status === 'uploading' || conv.upload.status === 'indexing' ? conv.upload : null;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  const submit = () => {
    const value = text.trim();
    if (!value || running || frozen) return;
    if (ask(conv.id, value)) setText('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <footer className="composer">
      {up && (
        <div className="frozen" role="status">
          <Spinner size={15} />
          <span>
            Conversation en pause pendant l'indexation de <strong>{up.fileName}</strong> · {up.stage}
          </span>
        </div>
      )}

      <div className="composer__box" data-disabled={frozen}>
        <textarea
          ref={ref}
          rows={1}
          value={text}
          disabled={frozen}
          placeholder={frozen ? 'Indexation en cours…' : 'Décrivez votre sinistre…'}
          aria-label="Votre message"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button className="send" aria-label={running ? 'Réponse en cours' : 'Envoyer'} disabled={!text.trim() || frozen || running} onClick={submit}>
          {running ? <Spinner size={15} /> : <ArrowUp size={18} />}
        </button>
      </div>

      <p className="composer__hint">
        {hasKey ? (
          'Aide à la lecture du contrat, pas un avis juridique : la décision revient à votre assureur.'
        ) : (
          <>
            Pour commencer, <button className="link-btn" onClick={() => setUi({ settingsOpen: true })}>ajoutez votre clé API dans les réglages LLM</button>.
          </>
        )}
      </p>
    </footer>
  );
}
