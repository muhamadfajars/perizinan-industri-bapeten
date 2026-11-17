import type { CategoryId, MatchRow, MatchSection } from '../types/models';

export function isPersonnelInformation(row: MatchRow): boolean {
  return (
    row.field !== 'Nama' &&
    (['Masa Berlaku', 'Pengesahan', 'Jenis Dokumen'].includes(row.field) ||
      !row.expected?.trim() ||
      ['—', '-'].includes(row.expected.trim()) ||
      row.status === 'INFO')
  );
}

const MATCHING_CATEGORY_ORDER: readonly CategoryId[] = [
  'proteksi',
  'manajemen',
  'personel',
  'tld',
  'teknis',
  'spesifikasi',
  'label',
  'impor',
  'kesesuaian',
  'fungsi',
  'mutu',
  'paparan',
  'kebocoran',
];
const categoryRank = new Map(MATCHING_CATEGORY_ORDER.map((category, index) => [category, index]));

export function sortMatchingSections(sections: readonly MatchSection[]): MatchSection[] {
  // Keep the server result intact, including row order and sections within each category.
  return [...sections].sort(
    (a, b) =>
      (categoryRank.get(a.category) ?? MATCHING_CATEGORY_ORDER.length) -
      (categoryRank.get(b.category) ?? MATCHING_CATEGORY_ORDER.length),
  );
}

export function matchingTotals(sections: MatchSection[]) {
  const allRows = sections.flatMap((x) =>
    x.rows.filter((r) => x.category !== 'personel' || r.field !== 'Jenis Dokumen'),
  );
  const rows = sections.flatMap((x) =>
    x.rows.filter((r) => x.category !== 'personel' || !isPersonnelInformation(r)),
  );
  const match = rows.filter((x) => x.status === 'MATCH').length;
  const review = rows.filter((x) => x.status === 'REVIEW').length;
  const mismatch = rows.filter((x) => x.status === 'MISMATCH').length;
  const missing = rows.filter((x) => x.status === 'MISSING').length;
  const info = allRows.length - rows.filter((x) => x.status !== 'INFO').length;
  const compared = rows.filter((x) => x.status !== 'INFO').length;
  return {
    match,
    review,
    mismatch,
    missing,
    info,
    compared,
    total: allRows.length,
    percentage: compared ? Math.round((match / compared) * 1000) / 10 : 0,
  };
}

export function isSectionExpanded(
  openMap: Record<string, boolean>,
  sectionId: string,
  index: number,
): boolean {
  return openMap[sectionId] ?? index === 0;
}

export function nextToggleAllSections(
  sections: readonly Pick<MatchSection, 'id'>[],
  openMap: Record<string, boolean>,
): Record<string, boolean> {
  const allOpen = sections.length > 0 && sections.every((s, i) => isSectionExpanded(openMap, s.id, i));
  const target = !allOpen;
  return Object.fromEntries(sections.map((s) => [s.id, target]));
}
