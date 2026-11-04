import { useEffect, useState, type FormEvent } from 'react';
import { Eye, EyeOff, Lock } from 'lucide-react';
import { useSettings, useUi } from '../state/store';
import { PROVIDERS } from '../lib/providers';
import type { Provider } from '../types';
import { Dialog } from './ui';

export function SettingsDialog() {
  const open = useUi((s) => s.settingsOpen);
  const setUi = useUi((s) => s.set);
  const saved = useSettings();
  const [provider, setProvider] = useState<Provider>(saved.provider);
  const [model, setModel] = useState(saved.model);
  const [apiKey, setApiKey] = useState(saved.apiKey);
  const [reveal, setReveal] = useState(false);

  // Recharge le brouillon à chaque ouverture.
  useEffect(() => {
    if (open) {
      setProvider(saved.provider);
      setModel(saved.model);
      setApiKey(saved.apiKey);
      setReveal(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const info = PROVIDERS[provider];
  const valid = model.trim().length > 0 && apiKey.trim().length > 0;

  const changeProvider = (p: Provider) => {
    const wasSuggestion = Object.values(PROVIDERS).some((x) => x.models.includes(model));
    setProvider(p);
    if (!model.trim() || wasSuggestion) setModel(PROVIDERS[p].models[0]);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    saved.save({ provider, model: model.trim(), apiKey: apiKey.trim() });
    setUi({ settingsOpen: false });
  };

  return (
    <Dialog open={open} onClose={() => setUi({ settingsOpen: false })} title="Réglages LLM">
      <form className="dialog__body" onSubmit={submit}>
        <label className="field">
          <span>Fournisseur</span>
          <select value={provider} onChange={(e) => changeProvider(e.target.value as Provider)}>
            {Object.entries(PROVIDERS).map(([id, p]) => (
              <option key={id} value={id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Modèle</span>
          <input list="model-suggestions" value={model} onChange={(e) => setModel(e.target.value)} spellCheck={false} autoComplete="off" />
          <datalist id="model-suggestions">
            {info.models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <small>Choisissez dans la liste ou saisissez un identifiant de modèle.</small>
        </label>

        <label className="field">
          <span>Clé API</span>
          <div className="field__secret">
            <input
              type={reveal ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={info.keyPlaceholder}
              spellCheck={false}
              autoComplete="off"
            />
            <button type="button" className="icon-btn" aria-label={reveal ? 'Masquer la clé' : 'Afficher la clé'} onClick={() => setReveal((r) => !r)}>
              {reveal ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>
        </label>

        <div className="reassure">
          <Lock size={16} aria-hidden="true" />
          <p>
            <strong>Votre clé API n'est jamais enregistrée sur nos serveurs.</strong> Elle reste dans la mémoire de votre navigateur et n'est transmise que le temps de chaque requête. Elle disparaît dès que vous fermez cette page. Seuls le fournisseur et le modèle sont mémorisés sur cet appareil.
          </p>
        </div>

        <div className="dialog__actions">
          {saved.apiKey && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => {
                saved.clearKey();
                setApiKey('');
              }}
            >
              Effacer la clé
            </button>
          )}
          <button className="btn btn--primary" type="submit" disabled={!valid}>
            Enregistrer
          </button>
        </div>
      </form>
    </Dialog>
  );
}
