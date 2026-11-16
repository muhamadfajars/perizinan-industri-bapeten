import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildSectionTopicTabs,
  isAdditionalLocation,
  isManagementInformation,
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

test('buildSectionTopicTabs organizes protection and management views for split navigation', () => {
  const protComparison = [
    row('Nama Instansi', 'Data acuan'),
    { ...row('Nomor Dokumen', 'Data acuan'), status: 'REVIEW' as const },
  ];
  const protInfo = [
    {
      ...row('Dasar hukum: UU No. 10', 'Dasar hukum', { required: true, pages: [2] }),
      status: 'INFO' as const,
    },
    {
      ...row('Dasar hukum: PP No. 45', 'Dasar hukum', { required: true, pages: [] }),
      status: 'INFO' as const,
    },
    { ...row('Daerah Pengendalian', 'Isi program', { pages: [5] }), status: 'INFO' as const },
    { ...row('Pembatas Dosis', 'Isi program', { pages: [7] }), status: 'INFO' as const },
    { ...row('Lembar Pengesahan', 'Pengesahan', { pages: [1] }), status: 'INFO' as const },
  ];
  const protTabs = buildSectionTopicTabs('proteksi', protComparison, protInfo);
  assert.deepEqual(
    protTabs.map((t) => [t.key, t.label, t.status, t.subtitle]),
    [
      ['perbandingan', 'Perbandingan Field', 'REVIEW', '1/2 sesuai formulir'],
      ['dasar-hukum', 'Dasar Hukum', 'REVIEW', '1/2 dasar hukum wajib'],
      ['zonasi', 'Zonasi Kerja', 'INFO', 'Ditemukan'],
      ['pembatas-dosis', 'Pembatas Dosis', 'INFO', 'Ditemukan'],
      ['pengesahan', 'Lembar Pengesahan', 'INFO', 'Halaman ditemukan'],
    ],
  );

  const mgmtComparison: MatchRow[] = [
    {
      id: 'm1',
      field: 'Nama Instansi',
      expected: 'PT X',
      observed: 'PT X',
      score: 100,
      status: 'MATCH',
      detail: { type: 'management', group: 'Data acuan' },
    },
  ];
  const mgmtInfo: MatchRow[] = [
    {
      id: 'm2',
      field: 'Budaya Keselamatan dan Keamanan',
      expected: '—',
      observed: 'Ditemukan',
      score: null,
      status: 'INFO',
      detail: {
        type: 'management',
        group: 'Budaya',
        pages: [4],
        topics: [
          { label: 'Budaya Keselamatan', found: true },
          { label: 'Budaya Keamanan', found: false },
        ],
      },
    },
    {
      id: 'm3',
      field: 'Lembar Pengesahan',
      expected: '—',
      observed: 'Halaman ditemukan',
      score: null,
      status: 'INFO',
      detail: { type: 'management', group: 'Pengesahan', pages: [1] },
    },
  ];
  assert.equal(isManagementInformation(mgmtInfo[0]), true);
  assert.equal(isManagementInformation(mgmtComparison[0]), false);
  const mgmtTabs = buildSectionTopicTabs('manajemen', mgmtComparison, mgmtInfo);
  assert.deepEqual(
    mgmtTabs.map((t) => [t.key, t.label, t.status, t.subtitle]),
    [
      ['perbandingan', 'Perbandingan Field', 'MATCH', '1/1 sesuai formulir'],
      ['budaya', 'Budaya Keselamatan', 'REVIEW', '1/2 pokok bahasan'],
      ['pengesahan', 'Lembar Pengesahan', 'INFO', 'Halaman ditemukan'],
    ],
  );
});
