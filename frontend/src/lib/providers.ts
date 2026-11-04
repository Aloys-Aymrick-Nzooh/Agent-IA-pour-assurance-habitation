import type { Provider } from '../types';

export interface ProviderInfo {
  label: string;
  models: string[]; // suggestions : le champ modèle reste libre
  keyPlaceholder: string;
}

export const PROVIDERS: Record<Provider, ProviderInfo> = {
  anthropic: {
    label: 'Anthropic',
    models: ['claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5'],
    keyPlaceholder: 'sk-ant-…',
  },
  openai: { label: 'OpenAI', models: ['gpt-4.1', 'gpt-4o-mini'], keyPlaceholder: 'sk-…' },
  google: {
    label: 'Google Gemini',
    models: ['gemini-2.5-pro', 'gemini-2.5-flash'],
    keyPlaceholder: 'AIza…',
  },
};
