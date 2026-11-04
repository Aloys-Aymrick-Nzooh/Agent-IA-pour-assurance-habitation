/** Typed client for the synchronous FastAPI conversation and document endpoints. */
import { useSettings } from '../state/store';
import type { Provider } from '../types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export interface LlmChoice {
  provider: Provider;
  model: string;
}

export interface BackendDocument {
  document_id: string;
  filename: string;
  document_type: 'CG' | 'CP' | 'AVENANT' | 'ANNEXE';
  page_count: number;
  processing_status: string;
}

export interface BackendCitation {
  document_id: string;
  document_name: string;
  document_type: 'CG' | 'CP' | 'AVENANT' | 'ANNEXE';
  page_number: number;
  chunk_id: string;
  excerpt?: string;
}

export interface BackendHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  citations?: BackendCitation[];
  limitations?: string[];
}

export interface BackendChatResponse {
  conversation_id: string;
  status: 'completed' | 'waiting_for_clarification';
  answer: string;
  clarification_question?: string;
  citations: BackendCitation[];
  limitations: string[];
}

export type BackendProgressEvent =
  | { type: 'step'; id: string; label: string; status: 'running' | 'done' | 'error'; detail?: string }
  | ({ type: 'answer' } & BackendChatResponse)
  | { type: 'error'; message: string }
  | { type: 'done' };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload.detail === 'string' ? payload.detail : '';
    throw new Error(detail || `Erreur serveur (${response.status})`);
  }
  return payload as T;
}

export async function createBackendConversation(): Promise<{ conversation_id: string }> {
  return request('/conversations', { method: 'POST' });
}

export async function getBackendDocuments(conversationId: string): Promise<BackendDocument[]> {
  return request(`/conversations/${encodeURIComponent(conversationId)}/documents`);
}

export async function getBackendMessages(
  conversationId: string,
): Promise<{ conversation_id: string; messages: BackendHistoryMessage[] }> {
  return request(`/conversations/${encodeURIComponent(conversationId)}/messages`);
}

export async function uploadBackendDocument(
  conversationId: string,
  file: File,
  documentType: 'CG' | 'CP' | 'AVENANT' | 'ANNEXE',
): Promise<BackendDocument & { conversation_id: string }> {
  const body = new FormData();
  body.append('file', file);
  body.append('document_type', documentType);
  return request(`/conversations/${encodeURIComponent(conversationId)}/documents`, {
    method: 'POST',
    body,
  });
}

export async function streamBackendMessage(
  conversationId: string,
  content: string,
  llm: LlmChoice,
  apiKey: string,
  onEvent: (event: BackendProgressEvent) => void,
): Promise<BackendChatResponse> {
  const response = await fetch(`${API_BASE}/conversations/${encodeURIComponent(conversationId)}/messages/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-LLM-Provider': llm.provider === 'google' ? 'gemini' : llm.provider,
      'X-LLM-Model': llm.model,
      'X-LLM-Api-Key': apiKey,
    },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload && typeof payload.detail === 'string' ? payload.detail : `Erreur serveur (${response.status})`);
  }
  if (!response.body) throw new Error('Le serveur n’a pas ouvert le flux de progression.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: BackendChatResponse | undefined;

  const dispatch = (frame: string) => {
    let eventType = 'message';
    const data: string[] = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) eventType = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join('\n')) as Record<string, unknown>;
    if (eventType === 'answer') result = payload as unknown as BackendChatResponse;
    if (eventType === 'error') {
      const message = typeof payload.message === 'string' ? payload.message : 'Le traitement a échoué.';
      if (/expired|invalid .*key|authentication|unauthorized/i.test(message)) {
        useSettings.getState().clearKey();
      }
      onEvent({ type: 'error', message });
      throw new Error(message);
    }
    onEvent({ ...payload, type: eventType } as BackendProgressEvent);
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
    }
    if (done) break;
  }

  if (buffer.trim()) dispatch(buffer);
  if (!result) throw new Error('Le flux s’est terminé sans réponse finale.');
  return result;
}

export async function getBackendPage(
  conversationId: string,
  documentId: string,
  pageNumber: number,
): Promise<{ document_id: string; page_number: number; text: string }> {
  return request(
    `/conversations/${encodeURIComponent(conversationId)}/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}`,
  );
}

export async function deleteBackendConversation(conversationId: string): Promise<void> {
  await request(`/conversations/${encodeURIComponent(conversationId)}`, { method: 'DELETE' });
}

