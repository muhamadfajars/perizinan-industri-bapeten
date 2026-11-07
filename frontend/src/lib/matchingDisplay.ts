import { categoryById } from '../data/categories';
import type { MatchRow, MatchSection } from '../types/models';
import { Filter } from '../types/workspace';

export function rowMatchesFilter(row: MatchRow, filter: Filter, query: string): boolean {
  if (filter !== 'ALL' && row.status !== filter) return false;
  const search = query.trim().toLocaleLowerCase('id-ID');
  return (
    !search || `${row.field} ${row.expected} ${row.observed}`.toLocaleLowerCase('id-ID').includes(search)
  );
}

export function matchingSectionTitle(section: MatchSection): string {
  // Backend supplies a controlled subtype label, never the uploaded filename.
  if (
    section.category === 'personel' &&
    /^Dokumen Personel - (SIP|SIB|Surat Perintah|Sertifikat Kompetensi|Surat Izin Kerja|Surat Keterangan Kerja|Surat Penunjukan Tugas|Evaluasi Dosis|Evaluasi Dosis \/ Zero Check)$/.test(
      section.name,
    )
  ) {
    return section.name;
  }
  return categoryById(section.category)?.name ?? 'Dokumen';
}
