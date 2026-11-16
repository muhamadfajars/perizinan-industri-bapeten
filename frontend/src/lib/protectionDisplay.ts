import type { MatchRow, MatchStatus } from '../types/models';

export function fieldExplanation(row: MatchRow): string {
  const rawNote = row.note ?? '';
  if (row.detail?.type === 'personnel' && row.status === 'REVIEW') {
    if (/nama penerima.*belum terbaca/i.test(rawNote)) {
      return 'Nama petugas pada dokumen belum terbaca dengan jelas. Periksa nama pada dokumen sumber dan bandingkan dengan formulir.';
    }
    if (/blok penugasan/i.test(rawNote)) {
      return 'Nama penerima tugas sudah terbaca. Periksa kembali kesesuaiannya dengan petugas pada formulir.';
    }
    if (/LLM|pemilik tunggal.*belum terverifikasi/i.test(rawNote)) {
      return 'Pemilik dokumen belum dapat dipastikan. Periksa nama penerima atau pemegang dokumen pada sumber, lalu bandingkan dengan formulir.';
    }
  }
  if (row.status === 'MATCH' && row.score === 100) return 'Nilai sesuai dengan formulir.';
  if (row.status === 'REVIEW' && row.detail?.field_label === 'Nama' && row.observed !== 'Belum terbaca') {
    return `Nama pada formulir “${row.expected}”, sedangkan dokumen tertulis “${row.observed}”.`;
  }
  const note = (row.note ?? '')
    .replaceAll('v43_address_components', 'Pemeriksaan komponen alamat')
    .replace(/\s*\(skor aturan [\d.,]+%\)/g, '');
  return (
    note
      .split(/(?<=[.!?])\s+(?=[A-Z])/)
      .slice(0, 2)
      .join(' ') || 'Periksa bukti pada halaman sumber.'
  );
}

export function orderProtectionRows(rows: MatchRow[]) {
  const priority: Record<string, number> = {
    'Nama Instansi': 0,
    Alamat: 1,
    'Alamat Proyek / Lokasi Pemanfaatan': 1,
    'Nomor Dokumen': 2,
    'Tanggal Dokumen': 3,
  };
  return [...rows].sort((a, b) => (priority[a.field] ?? 4) - (priority[b.field] ?? 4));
}

export function protectionFieldLabel(row: MatchRow) {
  if (row.detail?.type === 'protection' && row.detail.group === 'Pengesahan') return 'Pengesahan';
  return row.detail?.type === 'protection' && row.field === 'Alamat Proyek / Lokasi Pemanfaatan'
    ? 'Alamat'
    : row.field;
}

export function isSupportingInformation(row: MatchRow) {
  return (
    row.detail?.type === 'protection' &&
    ['Dasar hukum', 'Isi program', 'Pengesahan'].includes(row.detail.group ?? '')
  );
}

export function isAdditionalLocation(row: MatchRow) {
  return (
    row.detail?.type === 'protection' &&
    ['Petugas tambahan / lokasi lain', 'Pesawat tambahan / lokasi lain'].includes(row.field)
  );
}

export function personnelGroups(rows: MatchRow[]) {
  const groups = new Map<string, { id: string; name: string; rows: MatchRow[] }>();
  for (const row of rows) {
    if (row.detail?.type !== 'protection' || row.detail.group !== 'Petugas' || isAdditionalLocation(row))
      continue;
    const name =
      row.detail.person_name ?? row.field.match(/^Petugas (.*): (?:Nama|Profesi \/ Keahlian)$/)?.[1] ?? '';
    const id = row.detail.person_id ?? name;
    if (!groups.has(id)) groups.set(id, { id, name, rows: [] });
    groups.get(id)!.rows.push(row);
  }
  return [...groups.values()];
}

export function getVerificationHint(row: MatchRow): string {
  if (row.detail?.group === 'Dasar hukum') {
    const hasEvidence =
      (row.detail?.pages?.length ?? 0) > 0 ||
      (row.observed && !row.observed.toLowerCase().includes('belum ditemukan'));
    return hasEvidence
      ? 'Pastikan peraturan ini tercantum sebagai rujukan dalam dokumen.'
      : 'Peraturan belum terdeteksi otomatis; periksa bab dasar hukum.';
  }
  if (
    row.field.includes('Daerah Pengendalian') ||
    row.field.includes('Daerah Pengawasan') ||
    row.field.includes('Supervisi')
  ) {
    return 'Periksa uraian zonasi kerja radiasi dan lampiran denah ruangan pada gambar.';
  }
  if (row.field === 'Pembatas Dosis' || row.field.includes('Dosis')) {
    return 'Pastikan angka batas dosis tidak melebihi Nilai Batas Dosis (NBD) ketentuan BAPETEN.';
  }
  if (row.detail?.group === 'Pengesahan' || row.field.includes('Pengesahan')) {
    return 'Periksa keberadaan tanda tangan pimpinan atau penanggung jawab pada gambar.';
  }
  return row.note || 'Periksa kesesuaian dokumen sumber.';
}

/** Compact regulation names without changing the subject after “tentang”. */
export function regulationDisplayTitle(field: string): string {
  return field
    .replace(/^Dasar hukum:\s*/, '')
    .replace(/^Undang-Undang Nomor /, 'UU No. ')
    .replace(/^Peraturan Pemerintah Nomor /, 'PP No. ')
    .replace(/^Peraturan (?:Badan Pengawas Tenaga Nuklir|BAPETEN) Nomor /, 'Perba No. ');
}

export function isManagementInformation(row: MatchRow): boolean {
  return row.detail?.type === 'management' && ['Pengesahan', 'Budaya'].includes(row.detail.group ?? '');
}

export type ProtectionTabKey = 'dasar-hukum' | 'zonasi' | 'pembatas-dosis' | 'pengesahan';

export function getProtectionTabKey(row: MatchRow): ProtectionTabKey {
  if (row.detail?.group === 'Dasar hukum') return 'dasar-hukum';
  if (row.detail?.group === 'Pengesahan' || row.field.includes('Pengesahan')) return 'pengesahan';
  if (row.field === 'Pembatas Dosis' || row.field.includes('Dosis')) return 'pembatas-dosis';
  return 'zonasi';
}

export interface SectionTopicTab {
  key: string;
  label: string;
  headerTitle: string;
  subtitle: string;
  status: MatchStatus;
  rows: MatchRow[];
}

function summarizeComparisonStatus(rows: MatchRow[]): MatchStatus {
  if (rows.some((r) => r.status === 'MISMATCH')) return 'MISMATCH';
  if (rows.some((r) => r.status === 'REVIEW' || r.detail?.review_required)) return 'REVIEW';
  if (rows.some((r) => r.status === 'MATCH')) return 'MATCH';
  return 'INFO';
}

function isInfoRowFound(row: MatchRow): boolean {
  const topics = row.detail?.topics;
  if (topics?.length) return topics.every((t) => t.found);
  return (row.detail?.pages?.length ?? 0) > 0;
}

export function buildSectionTopicTabs(
  category: 'proteksi' | 'manajemen',
  comparisonRows: MatchRow[],
  infoRows: MatchRow[],
): SectionTopicTab[] {
  const tabs: SectionTopicTab[] = [];

  if (comparisonRows.length > 0) {
    const compared = comparisonRows.filter((r) => r.status !== 'INFO');
    const matched = compared.filter((r) => r.status === 'MATCH').length;
    tabs.push({
      key: 'perbandingan',
      label: 'Perbandingan Field',
      headerTitle: 'Perbandingan Field dengan Formulir',
      subtitle:
        compared.length > 0
          ? `${matched}/${compared.length} sesuai formulir`
          : `${comparisonRows.length} field`,
      status: summarizeComparisonStatus(comparisonRows),
      rows: comparisonRows,
    });
  }

  if (category === 'proteksi') {
    const defs: { key: ProtectionTabKey; label: string; headerTitle: string }[] = [
      { key: 'dasar-hukum', label: 'Dasar Hukum', headerTitle: 'Dasar Hukum' },
      { key: 'zonasi', label: 'Zonasi Kerja', headerTitle: 'Zonasi Kerja' },
      { key: 'pembatas-dosis', label: 'Pembatas Dosis', headerTitle: 'Pembatas Dosis' },
      { key: 'pengesahan', label: 'Lembar Pengesahan', headerTitle: 'Lembar Pengesahan' },
    ];
    for (const def of defs) {
      const groupRows = infoRows.filter((r) => getProtectionTabKey(r) === def.key);
      if (!groupRows.length) continue;

      if (def.key === 'dasar-hukum') {
        const required = groupRows.filter((r) => r.detail?.required);
        const target = required.length > 0 ? required : groupRows;
        const foundCount = target.filter((r) => (r.detail?.pages?.length ?? 0) > 0).length;
        const hasReview =
          foundCount < target.length ||
          groupRows.some((r) => r.detail?.review_required || r.status === 'REVIEW');
        tabs.push({
          key: def.key,
          label: def.label,
          headerTitle: def.headerTitle,
          subtitle: required.length
            ? `${foundCount}/${required.length} dasar hukum wajib`
            : `${foundCount}/${groupRows.length} ditemukan`,
          status: hasReview ? 'REVIEW' : 'INFO',
          rows: groupRows,
        });
        continue;
      }

      const foundCount = groupRows.filter(isInfoRowFound).length;
      const hasReview =
        foundCount < groupRows.length ||
        groupRows.some((r) => r.detail?.review_required || r.status === 'REVIEW');
      const subtitle =
        groupRows.length === 1
          ? def.key === 'pengesahan'
            ? foundCount === 1
              ? 'Halaman ditemukan'
              : 'Perlu diperiksa'
            : foundCount === 1
              ? 'Ditemukan'
              : 'Belum ditemukan'
          : `${foundCount}/${groupRows.length} ditemukan`;
      tabs.push({
        key: def.key,
        label: def.label,
        headerTitle: def.headerTitle,
        subtitle,
        status: hasReview ? 'REVIEW' : 'INFO',
        rows: groupRows,
      });
    }
    return tabs;
  }

  const mgmtDefs = [
    {
      key: 'budaya',
      group: 'Budaya',
      label: 'Budaya Keselamatan',
      headerTitle: 'Budaya Keselamatan dan Keamanan',
    },
    {
      key: 'pengesahan',
      group: 'Pengesahan',
      label: 'Lembar Pengesahan',
      headerTitle: 'Lembar Pengesahan',
    },
  ];
  for (const def of mgmtDefs) {
    const groupRows = infoRows.filter((r) => r.detail?.group === def.group);
    if (!groupRows.length) continue;
    const foundCount = groupRows.filter(isInfoRowFound).length;
    const hasReview =
      foundCount < groupRows.length ||
      groupRows.some((r) => r.detail?.review_required || r.status === 'REVIEW');
    const firstTopics = groupRows[0]?.detail?.topics;
    const subtitle =
      def.key === 'budaya' && firstTopics?.length
        ? `${firstTopics.filter((t) => t.found).length}/${firstTopics.length} pokok bahasan`
        : groupRows.length === 1
          ? foundCount === 1
            ? 'Halaman ditemukan'
            : 'Perlu diperiksa'
          : `${foundCount}/${groupRows.length} ditemukan`;
    tabs.push({
      key: def.key,
      label: def.label,
      headerTitle: def.headerTitle,
      subtitle,
      status: hasReview ? 'REVIEW' : 'INFO',
      rows: groupRows,
    });
  }

  return tabs;
}
