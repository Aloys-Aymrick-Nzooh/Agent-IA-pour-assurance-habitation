export type Provider = 'anthropic' | 'openai' | 'google';
export type DocumentType = 'CG' | 'CP' | 'AVENANT' | 'ANNEXE';

export type Verdict = 'COUVERT' | 'NON_COUVERT_PROBABLE' | 'INDETERMINE' | 'INFO_MANQUANTE';
export type Confidence = 'haute' | 'moyenne' | 'basse';

/** Une clause du contrat citée par l'agent. L'extrait a été vérifié mot pour mot par le backend. */
export interface Citation {
  id: string; // marqueur local utilisé dans le texte : [[c1]]
  clauseId: string;
  article: string;
  page: number;
  breadcrumb: string;
  excerpt: string;
  source: 'catalog' | 'user_upload';
  verified: boolean;
  documentId?: string;
  documentName?: string;
  documentType?: DocumentType;
  chunkId?: string;
}

export interface BackendAnswer {
  text: string;
  citations: Citation[];
  limitations: string[];
}

export interface IndexedDocument {
  documentId: string;
  filename: string;
  documentType: DocumentType;
  pageCount: number;
  processingStatus: string;
}

export interface ConditionCheck {
  text: string;
  status: 'remplie' | 'non_remplie' | 'inconnue';
  citationIds: string[];
}

export interface AgentAnswer {
  verdict: Verdict;
  confidence: Confidence;
  summary: string; // peut contenir des marqueurs [[c1]]
  conditions: ConditionCheck[];
  missingFacts: string[];
  ambiguities: string[];
  limits?: string;
  citations: Citation[];
}

export interface Step {
  id: string;
  label: string;
  detail?: string;
  status: 'running' | 'done' | 'error';
  startedAt: number;
  endedAt?: number;
}

export interface UserMessage {
  id: string;
  role: 'user';
  text: string;
  createdAt: number;
}

export interface AgentMessage {
  id: string;
  role: 'agent';
  status: 'running' | 'done' | 'error';
  steps: Step[];
  startedAt: number;
  endedAt?: number;
  question?: string; // l'agent demande une précision
  answer?: AgentAnswer;
  backendAnswer?: BackendAnswer;
  error?: string;
}

export type Message = UserMessage | AgentMessage;

export interface ContractInfo {
  insurer: string;
  product: string;
  version: string;
  options: { label: string; state: 'souscrite' | 'non_souscrite' | 'non_trouvee' }[];
  lowQuality: boolean;
}

export type UploadState =
  | { status: 'none' }
  | { status: 'uploading' | 'indexing'; fileName: string; stage: string; percent: number }
  | { status: 'indexed'; fileName: string; document: IndexedDocument }
  | { status: 'ready'; fileName: string; contract: ContractInfo }
  | { status: 'error'; fileName?: string; message: string };

export interface Conversation {
  id: string;
  backendId?: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
  upload: UploadState;
  documents?: IndexedDocument[];
}

/** Événements SSE d'un run de l'agent (relayés par Redis côté backend). */
export type RunEvent =
  | { type: 'step'; id: string; label: string; detail?: string; status: 'running' | 'done' | 'error' }
  | { type: 'title'; title: string }
  | { type: 'question'; text: string }
  | { type: 'answer'; answer: AgentAnswer }
  | { type: 'error'; message: string }
  | { type: 'done' };

/** Événements SSE de l'indexation d'un document uploadé. */
export type UploadEvent =
  | { type: 'progress'; stage: string; percent: number }
  | { type: 'ready'; contract: ContractInfo }
  | { type: 'error'; message: string };
