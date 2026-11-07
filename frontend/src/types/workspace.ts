import type { MatchStatus } from './models';

export type PageId = 'ringkasan' | 'upload' | 'formulir' | 'matching' | 'dokumen';

export type Filter = 'ALL' | MatchStatus;

export type Toast = { tone: 'success' | 'warning' | 'info'; message: string } | null;
