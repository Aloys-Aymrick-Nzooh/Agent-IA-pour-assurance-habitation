import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { AgentMessage, Conversation, IndexedDocument, Message, Provider, UploadState } from '../types';
import { uid } from '../lib/utils';
import { PROVIDERS } from '../lib/providers';

export const DEFAULT_TITLE = 'Nouvelle conversation';

const newConversation = (): Conversation => ({
  id: uid(),
  title: DEFAULT_TITLE,
  createdAt: Date.now(),
  updatedAt: Date.now(),
  messages: [],
  upload: { status: 'none' },
  documents: [],
});

/* ---------- Conversations (sessionStorage : effacées à la fermeture de l'onglet) ---------- */

interface ChatState {
  conversations: Conversation[];
  activeId: string;
  create: () => string;
  select: (id: string) => void;
  remove: (id: string) => void;
  patch: (id: string, fn: (c: Conversation) => Conversation) => void;
  setTitle: (id: string, title: string) => void;
  addMessage: (id: string, m: Message) => void;
  patchAgent: (id: string, msgId: string, fn: (m: AgentMessage) => AgentMessage) => void;
  setUpload: (id: string, upload: UploadState) => void;
  setBackendId: (id: string, backendId: string) => void;
  setDocuments: (id: string, documents: IndexedDocument[]) => void;
  setMessages: (id: string, messages: Message[]) => void;
}

const first = newConversation();

export const useChats = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [first],
      activeId: first.id,
      create: () => {
        // Réutilise une conversation vide plutôt que d'en empiler.
        const empty = get().conversations.find((c) => c.messages.length === 0 && c.upload.status === 'none');
        if (empty) {
          set({ activeId: empty.id });
          return empty.id;
        }
        const c = newConversation();
        set((s) => ({ conversations: [c, ...s.conversations], activeId: c.id }));
        return c.id;
      },
      select: (id) => set({ activeId: id }),
      remove: (id) =>
        set((s) => {
          const rest = s.conversations.filter((c) => c.id !== id);
          if (rest.length === 0) {
            const c = newConversation();
            return { conversations: [c], activeId: c.id };
          }
          const sorted = [...rest].sort((a, b) => b.updatedAt - a.updatedAt);
          return { conversations: rest, activeId: s.activeId === id ? sorted[0].id : s.activeId };
        }),
      patch: (id, fn) =>
        set((s) => ({
          conversations: s.conversations.map((c) => (c.id === id ? { ...fn(c), updatedAt: Date.now() } : c)),
        })),
      setTitle: (id, title) => get().patch(id, (c) => ({ ...c, title })),
      addMessage: (id, m) => get().patch(id, (c) => ({ ...c, messages: [...c.messages, m] })),
      patchAgent: (id, msgId, fn) =>
        get().patch(id, (c) => ({
          ...c,
          messages: c.messages.map((m) => (m.id === msgId && m.role === 'agent' ? fn(m) : m)),
        })),
      setUpload: (id, upload) => get().patch(id, (c) => ({ ...c, upload })),
        setBackendId: (id, backendId) => get().patch(id, (c) => ({ ...c, backendId })),
        setDocuments: (id, documents) => get().patch(id, (c) => ({ ...c, documents })),
        setMessages: (id, messages) => get().patch(id, (c) => ({ ...c, messages })),
    }),
    {
      name: 'conversations',
      storage: createJSONStorage(() => sessionStorage),
      // Après un rechargement, les flux en cours sont perdus : on les marque comme interrompus.
      onRehydrateStorage: () => (state) => {
        state?.conversations.forEach((c) => {
          if (c.upload.status === 'uploading' || c.upload.status === 'indexing') {
            c.upload = { status: 'error', fileName: c.upload.fileName, message: "L'indexation a été interrompue. Importez de nouveau votre document." };
          }
          c.messages.forEach((m) => {
            if (m.role === 'agent' && m.status === 'running') {
              m.status = 'error';
              m.error = 'La réponse a été interrompue. Posez de nouveau votre question.';
              m.steps.forEach((s) => s.status === 'running' && (s.status = 'error'));
            }
          });
        });
      },
    },
  ),
);

/* ---------- Réglages LLM : provider/modèle en local, clé API UNIQUEMENT en mémoire ---------- */

interface SettingsState {
  provider: Provider;
  model: string;
  apiKey: string; // jamais persisté (voir partialize)
  save: (s: { provider: Provider; model: string; apiKey: string }) => void;
  clearKey: () => void;
}

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      provider: 'anthropic',
      model: PROVIDERS.anthropic.models[0],
      apiKey: '',
      save: (s) => set(s),
      clearKey: () => set({ apiKey: '' }),
    }),
    {
      name: 'llm-settings',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ provider: s.provider, model: s.model }),
      merge: (persisted, current) => {
        const saved = persisted as Partial<Pick<SettingsState, 'provider' | 'model'>>;
        const provider = saved.provider === 'openai' || saved.provider === 'google'
          ? saved.provider
          : 'anthropic';
        return {
          ...current,
          provider,
          model: saved.model || PROVIDERS[provider].models[0],
        };
      },
    },
  ),
);

/* ---------- État purement visuel ---------- */

interface UiState {
  settingsOpen: boolean;
  uploadOpen: boolean;
  sidebarOpen: boolean;
  source: { messageId: string; citationId: string } | null;
  set: (p: Partial<Omit<UiState, 'set'>>) => void;
}

export const useUi = create<UiState>()((set) => ({
  settingsOpen: false,
  uploadOpen: false,
  sidebarOpen: false,
  source: null,
  set: (p) => set(p),
}));

export const useActive = () =>
  useChats((s) => s.conversations.find((c) => c.id === s.activeId) ?? s.conversations[0]);

export const isBusyUpload = (c: Conversation) => c.upload.status === 'uploading' || c.upload.status === 'indexing';
export const isRunning = (c: Conversation) => c.messages.some((m) => m.role === 'agent' && m.status === 'running');
