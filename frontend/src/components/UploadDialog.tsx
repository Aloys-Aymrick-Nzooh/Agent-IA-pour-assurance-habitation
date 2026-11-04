import { useRef, useState } from 'react';
import { Check, CircleAlert, FileText, LoaderCircle, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { useActive, useUi } from '../state/store';
import { MAX_UPLOAD_BYTES, startUploadBatch, type UploadJob } from '../state/controller';
import { formatBytes } from '../lib/utils';
import type { DocumentType } from '../types';
import { uid } from '../lib/utils';
import { ContractCard } from './ContractCard';
import { Dialog } from './ui';

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: 'CG', label: 'Conditions générales' },
  { value: 'CP', label: 'Conditions particulières' },
  { value: 'AVENANT', label: 'Avenant' },
  { value: 'ANNEXE', label: 'Annexe' },
];

type QueuedDocument = UploadJob & {
  status: 'queued' | 'uploading' | 'done' | 'error';
  message?: string;
};

function inferDocumentType(fileName: string, fallback: DocumentType): DocumentType {
  const normalized = fileName
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();

  if (normalized.includes('conditions generales') || /\bcg\b/.test(normalized)) return 'CG';
  if (normalized.includes('conditions particulieres') || /\bcp\b/.test(normalized)) return 'CP';
  if (normalized.includes('avenant')) return 'AVENANT';
  if (normalized.includes('annexe')) return 'ANNEXE';
  return fallback;
}

export function UploadDialog() {
  const open = useUi((s) => s.uploadOpen);
  const setUi = useUi((s) => s.set);
  const conv = useActive();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [drag, setDrag] = useState(false);
  const [documentType, setDocumentType] = useState<DocumentType>('CP');
  const [documents, setDocuments] = useState<QueuedDocument[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const up = conv.upload;
  const busy = submitting || up.status === 'uploading' || up.status === 'indexing';
  const hasPendingDocuments = documents.some((document) => document.status === 'queued' || document.status === 'error');

  const openFilePicker = () => {
    if (busy) return;
    inputRef.current?.click();
  };

  const addFiles = (files: FileList | File[]) => {
    const next = Array.from(files).map((file) => ({
      id: uid(),
      file,
      documentType: inferDocumentType(file.name, documentType),
      status: 'queued' as const,
    }));

    if (!next.length) return;

    setDocuments((current) => [...current, ...next]);
  };

  const submitBatch = async () => {
    const pending = documents.filter((document) => document.status === 'queued' || document.status === 'error');
    if (!pending.length || busy) return;
    setSubmitting(true);
    await startUploadBatch(conv.id, pending, (id, update) => {
      setDocuments((current) => current.map((document) =>
        document.id === id
          ? { ...document, status: update.status, message: update.status === 'error' ? update.message : undefined }
          : document,
      ));
    });
    setSubmitting(false);
  };

  return (
    <Dialog open={open} onClose={() => !busy && setUi({ uploadOpen: false })} title="Importer des documents">
      <input
        ref={inputRef}
        id="conversation-document-input"
        type="file"
        accept="application/pdf,.pdf"
        multiple
        className="visually-hidden"
        tabIndex={-1}
        onChange={(e) => {
          if (e.target.files) addFiles(e.target.files);
          e.target.value = '';
        }}
      />

      <div className="dialog__body">
        <p className="muted">Ajoutez plusieurs PDF et choisissez leur type individuellement. Ils seront indexés séquentiellement dans cette conversation.</p>
        <label className="field">
          <span>Type attribué aux prochains fichiers</span>
          <select value={documentType} onChange={(event) => setDocumentType(event.target.value as DocumentType)} disabled={busy}>
            {DOCUMENT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
          </select>
        </label>
        <p className="upload__instruction">
          Après la sélection, vérifiez le type de chaque PDF dans la file puis lancez l'import et l'indexation.
        </p>
        <div
          className="dropzone"
          data-drag={drag}
          aria-disabled={busy}
          onClick={() => openFilePicker()}
          onDragOver={(event) => {
            event.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDrag(false);
            addFiles(event.dataTransfer.files);
          }}
        >
          <Upload size={22} />
          <span className="dropzone__main">Déposez plusieurs PDF ou parcourez vos fichiers</span>
          <span className="dropzone__sub">PDF · {formatBytes(MAX_UPLOAD_BYTES)} maximum par fichier</span>
        </div>

        {documents.length > 0 && (
          <section className="upload-queue" aria-label="Documents à indexer">
            <h3>{documents.length} document{documents.length > 1 ? 's' : ''} dans le lot</h3>
            <ul>
              {documents.map((document) => (
                <li key={document.id} className="upload-queue__item">
                  <FileText size={16} aria-hidden="true" />
                  <span className="upload-queue__name" title={document.file.name}>{document.file.name}</span>
                  <select
                    aria-label={`Type de ${document.file.name}`}
                    value={document.documentType}
                    disabled={busy || document.status === 'done'}
                    onChange={(event) => setDocuments((current) => current.map((item) => item.id === document.id ? { ...item, documentType: event.target.value as DocumentType } : item))}
                  >
                    {DOCUMENT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                  </select>
                  <span className="upload-queue__status" data-status={document.status}>
                    {document.status === 'uploading' ? <LoaderCircle size={15} className="spin" /> : document.status === 'done' ? <Check size={15} /> : document.status === 'error' ? <CircleAlert size={15} /> : null}
                  </span>
                  {!busy && document.status !== 'done' && (
                    <button className="icon-btn" aria-label={`Retirer ${document.file.name}`} onClick={() => setDocuments((current) => current.filter((item) => item.id !== document.id))}>
                      <Trash2 size={15} />
                    </button>
                  )}
                  {document.message && <small className="upload-queue__error">{document.message}</small>}
                </li>
              ))}
            </ul>
            {(up.status === 'uploading' || up.status === 'indexing') && (
              <p className="upload__stage" role="status"><LoaderCircle size={15} className="spin" /> {up.stage}: {up.fileName}</p>
            )}
          </section>
        )}

        <div className="dialog__actions upload__actions">
          <button
            type="button"
            className="btn btn--outline"
            aria-disabled={busy}
            disabled={busy}
            onClick={() => openFilePicker()}
          >
            <Upload size={15} /> Ajouter des fichiers
          </button>
          <button className="btn btn--primary" disabled={busy || !hasPendingDocuments} onClick={() => void submitBatch()}>
            {busy ? 'Indexation en cours…' : hasPendingDocuments ? 'Importer et indexer le lot' : documents.length ? 'Lot indexé' : 'Sélectionnez des PDF'}
          </button>
        </div>

        {(conv.documents?.length ?? 0) > 0 && <ContractCard documents={conv.documents ?? []} />}
        {up.status === 'error' && documents.length === 0 && <p className="form-error" role="alert"><CircleAlert size={15} /> {up.message}</p>}
        <p className="privacy">
          <ShieldCheck size={15} /> Les PDF sont conservés dans le dossier de la conversation et supprimés avec celle-ci.
        </p>
      </div>
    </Dialog>
  );
}
