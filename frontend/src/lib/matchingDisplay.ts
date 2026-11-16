import { categoryById } from '../data/categories.ts';
import type { MatchRow, MatchSection } from '../types/models.ts';
import type { Filter } from '../types/workspace.ts';

export function rowMatchesFilter(row: MatchRow, filter: Filter, query: string): boolean {
  if (filter !== 'ALL' && row.status !== filter) return false;
  const search = query.trim().toLocaleLowerCase('id-ID');
  return (
    !search || `${row.field} ${row.expected} ${row.observed}`.toLocaleLowerCase('id-ID').includes(search)
  );
}

export function matchingSectionTitle(section: MatchSection): string {
  if (
    section.category === 'personel' &&
    (section.name.startsWith('Dokumen Personel · ') || section.name.startsWith('Dokumen Personel — '))
  ) {
    return section.name;
  }
  if (section.category === 'personel') {
    const label = section.rows.find((r) => r.detail?.source_label)?.detail?.source_label;
    if (label) return label;
  }
  // Backend supplies a controlled subtype label, never the uploaded filename.
  if (
    section.category === 'personel' &&
    /^Dokumen Personel - (SIB|Surat Perintah|Sertifikat Kompetensi PPR|Sertifikat Pelatihan|Surat Izin Kerja|Surat Keterangan Kerja|Surat Penunjukan Tugas|Evaluasi Dosis|Evaluasi Dosis \/ Zero Check)$/.test(
      section.name,
    )
  ) {
    return section.name;
  }
  return categoryById(section.category)?.name ?? 'Dokumen';
}

export function stripUploadTimestamp(filename?: string): string {
  if (!filename) return '';
  return filename.replace(/^\d{8,14}[-_]\s*/, '').trim();
}

export function findDuplicatePersonnelTabIds(
  groups: { id: string; docType: string; owners: string[] }[],
): Set<string> {
  const buckets = new Map<string, string[]>();
  for (const group of groups) {
    const ownerKey = group.owners
      .map((o) => o.trim().toLocaleLowerCase('id-ID'))
      .filter(Boolean)
      .sort()
      .join('|');
    const key = `${group.docType.trim().toLocaleLowerCase('id-ID')}::${ownerKey}`;
    buckets.set(key, [...(buckets.get(key) ?? []), group.id]);
  }
  const duplicates = new Set<string>();
  for (const ids of buckets.values()) {
    if (ids.length > 1) {
      for (const id of ids) duplicates.add(id);
    }
  }
  return duplicates;
}

export function extractUsagePeriods(row: MatchRow): { page?: number; value: string }[] {
  if (row.field !== 'Periode Pemakaian') return [];
  const observed = row.observed?.trim() ?? '';
  if (!observed || observed === '—' || observed.startsWith('Belum')) return [];

  const fromEvidence: { page?: number; value: string }[] = [];
  const seen = new Set<string>();
  for (const ev of row.detail?.evidence ?? []) {
    const val = ev.value?.trim();
    if (!val) continue;
    const dedupeKey = `${ev.page ?? ''}::${val.toLocaleLowerCase('id-ID')}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    fromEvidence.push({ page: ev.page, value: val });
  }
  if (fromEvidence.length > 0) return fromEvidence;

  const parts = observed
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean);
  const pages = [...new Set(row.detail?.pages ?? (row.page != null ? [row.page] : []))];
  return parts.map((value, idx) => ({
    page: pages.length === parts.length ? pages[idx] : pages.length === 1 ? pages[0] : undefined,
    value,
  }));
}
