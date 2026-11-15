import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isAdditionalLocation,
  isSupportingInformation,
  personnelGroups,
} from '../src/lib/protectionDisplay.ts';
import { administrationDocuments } from '../src/lib/presentation.ts';
import type { MatchRow } from '../src/types/models.ts';

const row = (field: string, group: string, extra = {}): MatchRow => ({
  id: field,
  field,
  expected: 'A',
  observed: 'A',
  score: 100,
  status: 'MATCH',
  detail: { type: 'protection', group, ...extra },
});

test('person groups pair name and role and preserve identity when filtering', () => {
  const name = row('Petugas A: Nama', 'Petugas', { person_id: '2', person_name: 'A', field_label: 'Nama' });
  const role = row('Petugas A: Profesi / Keahlian', 'Petugas', {
    person_id: '2',
    person_name: 'A',
    field_label: 'Profesi / Keahlian',
  });
  assert.equal(personnelGroups([name, role]).length, 1);
  assert.equal(personnelGroups([name, role])[0].rows.length, 2);
  assert.equal(personnelGroups([role])[0].id, '2');
  assert.equal(personnelGroups([row('Petugas B: Nama', 'Petugas')])[0].name, 'B');
});

test('supporting information contains only laws, program content and approval', () => {
  for (const group of ['Dasar hukum', 'Isi program', 'Pengesahan'])
    assert.equal(isSupportingInformation(row('Info', group)), true);
  for (const group of ['Petugas', 'Pesawat Sinar-X', 'Data acuan', 'Catatan pembacaan'])
    assert.equal(isSupportingInformation(row('Info', group)), false);
  const extra = row('Petugas tambahan / lokasi lain', 'Petugas');
  assert.equal(isAdditionalLocation(extra), true);
  assert.deepEqual(personnelGroups([extra]), []);
});

test('administrationDocuments resolves explicit entries and falls back to protection/management', () => {
  assert.deepEqual(
    administrationDocuments({
      facility: 'PT Contoh',
      address: 'Jl. Contoh',
      administrationDocuments: [
        { document: 'Dokumen Program Proteksi', number: 'PPR-01', date: '19/07/2026' },
        { document: 'Dokumen Sistem Manajemen', number: 'SM-02', date: '20/07/2026' },
      ],
      personnel: [],
      equipment: [],
    }),
    [
      { document: 'Dokumen Program Proteksi', number: 'PPR-01', date: '19/07/2026' },
      { document: 'Dokumen Sistem Manajemen', number: 'SM-02', date: '20/07/2026' },
    ],
  );
  assert.deepEqual(
    administrationDocuments({
      facility: 'PT Contoh',
      address: 'Jl. Contoh',
      protectionDocument: { number: 'PPR-01', date: '19/07/2026' },
      managementDocument: { number: 'SM-02', date: '20/07/2026' },
      personnel: [],
      equipment: [],
    }),
    [
      {
        document: 'Dokumen Program Proteksi dan Keselamatan Radiasi',
        number: 'PPR-01',
        date: '19/07/2026',
      },
      { document: 'Dokumen Sistem Manajemen', number: 'SM-02', date: '20/07/2026' },
    ],
  );
});
