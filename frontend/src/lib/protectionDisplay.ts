import type { MatchRow } from '../types/models';

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
