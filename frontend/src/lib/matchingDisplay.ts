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
