import type { MatchRow } from '../types/models';

export function fieldExplanation(row: MatchRow): string {
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
