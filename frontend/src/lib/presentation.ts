export const ID = () => `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

export const MAX_FILE = 40 * 1024 * 1024;

export const SUPPORTED_EXTENSIONS = new Set([
  'pdf',
  'jpg',
  'jpeg',
  'png',
  'bmp',
  'webp',
  'tif',
  'tiff',
  'docx',
]);

export const sizeLabel = (bytes: number) =>
  bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;

export const dateLabel = (iso: string) =>
  new Date(iso).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });

export const analysisDateLabel = (timestamp: number) => {
  const date = new Date(timestamp * 1000);
  return `${date.toLocaleDateString('id-ID')}, ${date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })}`;
};
