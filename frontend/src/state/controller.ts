/**
 * Orchestration hors React : envoi d'un message, suivi des flux SSE, upload et indexation.
 * Les composants appellent ces fonctions et se contentent de lire le store.
 */
import {
  createBackendConversation,
  deleteBackendConversation,
  getBackendDocuments,
  getBackendMessages,
  streamBackendMessage,
  uploadBackendDocument,
} from '../api/client';
import type { BackendCitation, BackendHistoryMessage, BackendProgressEvent } from '../api/client';
import type { DocumentType, IndexedDocument, Message, Step } from '../types';
import { uid } from '../lib/utils';
import { useChats, useUi } from './store';
import { useSettings } from './store';

const pendingConversations = new Map<string, Promise<string>>();

function fromBackendDocument(document: {
  document_id: string;
  filename: string;
  document_type: DocumentType;
  page_count: number;
  processing_status: string;
}): IndexedDocument {
  return {
    documentId: document.document_id,
    filename: document.filename,
    documentType: document.document_type,
    pageCount: document.page_count,
    processingStatus: document.processing_status,
  };
}

function fromBackendCitation(citation: BackendCitation, index: number) {
  return {
    id: `c${index + 1}`,
    clauseId: citation.chunk_id,
    article: citation.document_type,
    page: citation.page_number,
    breadcrumb: `${citation.document_name} · ${citation.document_type}`,
    excerpt: citation.excerpt ?? '',
    source: 'user_upload' as const,
    verified: true,
    documentId: citation.document_id,
    documentName: citation.document_name,
    documentType: citation.document_type,
    chunkId: citation.chunk_id,
  };
}

function fromBackendHistory(messages: BackendHistoryMessage[]): Message[] {
  return messages.map((message, index) => {
    const createdAt = Date.parse(message.created_at) || Date.now();
    if (message.role === 'user') {
      return { id: `backend-user-${index}`, role: 'user', text: message.content, createdAt };
    }
    return {
      id: `backend-agent-${index}`,
      role: 'agent',
      status: 'done',
      steps: [],
      startedAt: createdAt,
      endedAt: createdAt,
      backendAnswer: {
        text: message.content,
        citations: (message.citations ?? []).map(fromBackendCitation),
        limitations: message.limitations ?? [],
      },
    };
  });
}

async function ensureBackendConversation(localId: string): Promise<string> {
  const conversation = useChats.getState().conversations.find((item) => item.id === localId);
  if (!conversation) throw new Error('Conversation introuvable.');
  if (conversation.backendId) return conversation.backendId;

  let pending = pendingConversations.get(localId);
  if (!pending) {
    pending = createBackendConversation().then(({ conversation_id }) => {
      useChats.getState().setBackendId(localId, conversation_id);
      return conversation_id;
    });
    pendingConversations.set(localId, pending);
  }

  try {
    return await pending;
  } finally {
    pendingConversations.delete(localId);
  }
}

export async function restoreBackendData() {
  const conversations = useChats.getState().conversations.filter((item) => item.backendId);
  await Promise.all(
    conversations.map(async (conversation) => {
      try {
        const [documents, history] = await Promise.all([
          getBackendDocuments(conversation.backendId!),
          getBackendMessages(conversation.backendId!),
        ]);
        useChats.getState().setDocuments(conversation.id, documents.map(fromBackendDocument));
        useChats.getState().setMessages(conversation.id, fromBackendHistory(history.messages));
      } catch (error) {
        console.error('Unable to restore backend conversation', error);
      }
    }),
  );
}

const closeRunning = (steps: Step[], as: 'done' | 'error'): Step[] =>
  steps.map((s) => (s.status === 'running' ? { ...s, status: as, endedAt: Date.now() } : s));

function applyProgressEvent(convId: string, agentId: string, event: BackendProgressEvent) {
  const { patchAgent } = useChats.getState();
  const now = Date.now();

  if (event.type === 'step') {
    patchAgent(convId, agentId, (message) => {
      if (event.status === 'running') {
        return {
          ...message,
          steps: [...message.steps, {
            id: event.id,
            label: event.label,
            detail: event.detail,
            status: 'running' as const,
            startedAt: now,
          }],
        };
      }
      // done / error : fermer la dernière ligne encore "running" avec cet id
      const steps = [...message.steps];
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].id === event.id && steps[i].status === 'running') {
          steps[i] = {
            ...steps[i],
            status: event.status,
            detail: event.detail ?? steps[i].detail,
            endedAt: now,
          };
          break;
        }
      }
      return { ...message, steps };
    });
} else if (event.type === 'answer') {
    patchAgent(convId, agentId, (message) => ({
      ...message,
      backendAnswer: {
        text: event.answer,
        citations: event.citations.map(fromBackendCitation),
        limitations: event.limitations,
      },
    }));
  } else if (event.type === 'done') {
    patchAgent(convId, agentId, (message) => ({
      ...message,
      status: 'done',
      endedAt: now,
      steps: closeRunning(message.steps, 'done'),
    }));
  }
}

/* ---------- Chat ---------- */

export async function sendMessage(convId: string, text: string) {
  const { addMessage, patchAgent } = useChats.getState();
  const { provider, model, apiKey } = useSettings.getState();
  const agentId = uid();
  const now = Date.now();

  addMessage(convId, { id: uid(), role: 'user', text, createdAt: now });
  addMessage(convId, { id: agentId, role: 'agent', status: 'running', steps: [], startedAt: now });

  const fail = (message: string) =>
    patchAgent(convId, agentId, (m) => ({ 
      ...m, 
      status: 'error', 
      error: message, 
      endedAt: Date.now(),
      steps: closeRunning(m.steps, 'error'),
     }));

  try {
    const backendId = await ensureBackendConversation(convId);
    const response = await streamBackendMessage(
      backendId,
      text,
      { provider, model },
      apiKey,
      (event) => applyProgressEvent(convId, agentId, event),
    );
    const citations = response.citations.map(fromBackendCitation);
    patchAgent(convId, agentId, (message) => ({
      ...message,
      status: 'done',
      endedAt: Date.now(),
      steps: closeRunning(message.steps, 'done'),
      backendAnswer: {
        text: response.answer,
        citations,
        limitations: response.limitations,
      },
    }));
    const conversation = useChats.getState().conversations.find((item) => item.id === convId);
    if (conversation?.title === 'Nouvelle conversation') {
      useChats.getState().setTitle(convId, text.length > 42 ? `${text.slice(0, 39)}…` : text);
    }
  } catch (e) {
    fail(e instanceof Error ? e.message : "Impossible de joindre le serveur.");
  }
}

/* ---------- Upload des documents contractuels ---------- */

export const MAX_UPLOAD_BYTES = 30 * 1024 * 1024;

export interface UploadJob {
  id: string;
  file: File;
  documentType: DocumentType;
}

export type UploadJobUpdate =
  | { status: 'uploading' }
  | { status: 'done' }
  | { status: 'error'; message: string };

export function validateFile(file: File): string | null {
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
  if (!isPdf) return 'Le document doit être un PDF.';
  if (file.size > MAX_UPLOAD_BYTES) return 'Le fichier dépasse 30 Mo.';
  if (file.size === 0) return 'Le fichier est vide.';
  return null;
}

export async function startUploadBatch(
  convId: string,
  jobs: UploadJob[],
  onUpdate: (id: string, update: UploadJobUpdate) => void,
) {
  const { setUpload } = useChats.getState();
  const successful: IndexedDocument[] = [];

  for (const [index, job] of jobs.entries()) {
    const invalid = validateFile(job.file);
    if (invalid) {
      onUpdate(job.id, { status: 'error', message: invalid });
      continue;
    }

    onUpdate(job.id, { status: 'uploading' });
    setUpload(convId, {
      status: 'uploading',
      fileName: job.file.name,
      stage: `Indexation du document ${index + 1} sur ${jobs.length}`,
      percent: 0,
    });

    try {
      const backendId = await ensureBackendConversation(convId);
      const uploaded = await uploadBackendDocument(backendId, job.file, job.documentType);
      successful.push(fromBackendDocument(uploaded));
      onUpdate(job.id, { status: 'done' });
    } catch (error) {
      onUpdate(job.id, {
        status: 'error',
        message: error instanceof Error ? error.message : "L'indexation a échoué.",
      });
    }
  }

  if (successful.length > 0) {
    try {
      const backendId = await ensureBackendConversation(convId);
      const documents = await getBackendDocuments(backendId);
      useChats.getState().setDocuments(convId, documents.map(fromBackendDocument));
      const lastDocument = successful[successful.length - 1];
      setUpload(convId, {
        status: 'indexed',
        fileName: lastDocument.filename,
        document: lastDocument,
      });
    } catch (error) {
      setUpload(convId, {
        status: 'error',
        message: error instanceof Error ? error.message : 'Impossible de charger la liste des documents.',
      });
    }
  } else {
    setUpload(convId, {
      status: 'error',
      message: 'Aucun document du lot n’a pu être indexé.',
    });
  }
}

/* ---------- Suppression ---------- */

export async function removeConversation(convId: string) {
  const conversation = useChats.getState().conversations.find((item) => item.id === convId);
  if (conversation?.backendId) {
    try {
      await deleteBackendConversation(conversation.backendId);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'La suppression a échoué.');
      return;
    }
  }
  const ui = useUi.getState();
  if (ui.source) ui.set({ source: null });
  useChats.getState().remove(convId);
}

/** Point d'entrée des composants : exige une clé API, sinon ouvre les réglages. */
export function ask(convId: string, text: string): boolean {
  if (!useSettings.getState().apiKey) {
    useUi.getState().set({ settingsOpen: true });
    return false;
  }
  void sendMessage(convId, text);
  return true;
}
