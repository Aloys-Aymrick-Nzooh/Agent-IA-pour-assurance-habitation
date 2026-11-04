export const uid = () =>
  globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

export function formatDuration(ms: number): string {
  const s = ms / 1000;
  return s < 10 ? `${s.toFixed(1).replace('.', ',')} s` : `${Math.round(s)} s`;
}

export function formatBytes(n: number): string {
  return n < 1024 * 1024
    ? `${Math.max(1, Math.round(n / 1024))} Ko`
    : `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} Mo`;
}

export const chipLabel = (c: { source: 'catalog' | 'user_upload'; article: string; page: number; documentType?: string }) =>
  c.documentType ? `${c.documentType} · p. ${c.page}` : c.source === 'user_upload' ? `Document importé · p. ${c.page}` : `Art. ${c.article} · p. ${c.page}`;
