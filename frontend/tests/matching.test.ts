import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isPersonnelInformation,
  isSectionExpanded,
  matchingTotals,
  nextToggleAllSections,
  sortMatchingSections,
} from '../src/lib/matching.ts';
import {
  extractUsagePeriods,
  findDuplicatePersonnelTabIds,
  matchingSectionTitle,
  stripUploadTimestamp,
} from '../src/lib/matchingDisplay.ts';
import type { CategoryId, MatchRow, MatchSection } from '../src/types/models.ts';

const order: CategoryId[] = [
  'proteksi',
  'manajemen',
  'personel',
  'spesifikasi',
  'label',
  'impor',
  'fungsi',
  'mutu',
  'kalibrasi',
  'paparan',
  'kebocoran',
];
const section = (category: CategoryId, id = category): MatchSection => ({
  id,
  category,
  name: category,
  rows: [
    { id: `${id}-row`, field: 'Nama fasilitas', expected: 'A', observed: 'B', score: 0, status: 'MISMATCH' },
  ],
});

test('personnel expiry reviews do not reduce identity matching percentage', () => {
  const data = section('personel');
  data.rows = [
    { id: 'name', field: 'Nama', expected: 'Budi', observed: 'Budi', score: 100, status: 'MATCH' },
    {
      id: 'expiry',
      field: 'Masa Berlaku',
      expected: '',
      observed: '01/01/2020',
      score: null,
      status: 'REVIEW',
    },
    {
      id: 'role',
      field: 'Profesi / Keahlian',
      expected: '',
      observed: 'Operator',
      score: null,
      status: 'INFO',
    },
    { id: 'type', field: 'Jenis Dokumen', expected: '', observed: 'SIB', score: null, status: 'INFO' },
  ];
  const totals = matchingTotals([data]);
  assert.equal(totals.percentage, 100);
  assert.equal(totals.compared, 1);
  assert.equal(totals.info, 2);
  assert.equal(totals.total, 3);
  data.rows[0].status = 'REVIEW';
  assert.equal(matchingTotals([data]).review, 1);
  assert.equal(matchingTotals([data]).percentage, 0);
});

test('display-only legal and approval evidence does not affect matching percentage', () => {
  const data = section('proteksi');
  data.rows[0].status = 'MATCH';
  data.rows.push({
    id: 'law',
    field: 'UU No. 10 Tahun 1997',
    expected: '—',
    observed: 'Ditemukan',
    score: null,
    status: 'INFO',
  });
  const totals = matchingTotals([data]);
  assert.equal(totals.percentage, 100);
  assert.equal(totals.compared, 1);
  assert.equal(totals.info, 1);
  assert.equal(totals.total, 2);
  data.rows.shift();
  assert.equal(matchingTotals([data]).compared, 0);
});

test('matching follows the agreed category order regardless of upload order without altering results', () => {
  const input = order.toReversed().map((category: CategoryId) => section(category));
  const original = structuredClone(input);
  const sorted = sortMatchingSections(input);
  assert.deepEqual(
    sorted.map((item) => item.category),
    order,
  );
  assert.deepEqual(input, original);
  assert.deepEqual(matchingTotals(sorted), matchingTotals(input));
  for (const item of sorted)
    assert.equal(
      item,
      input.find((source: MatchSection) => source.id === item.id),
    );
  assert.deepEqual(sortMatchingSections([]), []);
});

test('multiple sections stay together and filtering preserves category order', () => {
  const personnelA = section('personel');
  const personnelB = { ...section('personel'), id: 'personel-b' };
  const sorted = sortMatchingSections([section('kalibrasi'), personnelA, section('proteksi'), personnelB]);
  assert.deepEqual(
    sorted.map((item) => item.id),
    ['proteksi', 'personel', 'personel-b', 'kalibrasi'],
  );
  assert.deepEqual(
    sorted.filter((item) => item.category !== 'personel').map((item) => item.category),
    ['proteksi', 'kalibrasi'],
  );
});

test('toggle all sections expands remaining collapsed panels then collapses all when every panel is open', () => {
  const sections = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  assert.equal(isSectionExpanded({}, 'a', 0), true);
  assert.equal(isSectionExpanded({}, 'b', 1), false);

  const opened = nextToggleAllSections(sections, {});
  assert.deepEqual(opened, { a: true, b: true, c: true });
  assert.equal(isSectionExpanded(opened, 'b', 1), true);

  const closed = nextToggleAllSections(sections, opened);
  assert.deepEqual(closed, { a: false, b: false, c: false });
  assert.equal(isSectionExpanded(closed, 'a', 0), false);

  const manualAfterCollapse = { ...closed, b: !isSectionExpanded(closed, 'b', 1) };
  assert.equal(isSectionExpanded(manualAfterCollapse, 'a', 0), false);
  assert.equal(isSectionExpanded(manualAfterCollapse, 'b', 1), true);
  assert.equal(isSectionExpanded(manualAfterCollapse, 'c', 2), false);

  const manualAfterExpandAll = { ...opened, c: !isSectionExpanded(opened, 'c', 2) };
  assert.equal(isSectionExpanded(manualAfterExpandAll, 'a', 0), true);
  assert.equal(isSectionExpanded(manualAfterExpandAll, 'c', 2), false);
});

test('isPersonnelInformation separates comparison fields from supporting information correctly', () => {
  const nameRow: MatchRow = {
    id: '1',
    field: 'Nama',
    expected: 'JUVIANDY',
    observed: 'Juviandy',
    score: 100,
    status: 'MATCH',
  };
  const roleRow: MatchRow = {
    id: '2',
    field: 'Profesi / Keahlian',
    expected: 'PPR',
    observed: 'Petugas Proteksi Radiasi',
    score: 90,
    status: 'MATCH',
  };
  const expiryRow: MatchRow = {
    id: '3',
    field: 'Masa Berlaku',
    expected: '—',
    observed: '13/08/2031',
    score: null,
    status: 'INFO',
  };
  const approvalRow: MatchRow = {
    id: '4',
    field: 'Pengesahan',
    expected: '—',
    observed: 'Ditemukan',
    score: null,
    status: 'INFO',
  };

  assert.equal(isPersonnelInformation(nameRow), false);
  assert.equal(isPersonnelInformation(roleRow), false);
  assert.equal(isPersonnelInformation(expiryRow), true);
  assert.equal(isPersonnelInformation(approvalRow), true);
});

test('matchingSectionTitle returns proper personnel title with and without person name', () => {
  const unifiedSection: MatchSection = {
    id: 'sec-0',
    category: 'personel',
    name: 'Dokumen Personel · 3 Dokumen',
    rows: [],
  };
  const namedSection: MatchSection = {
    id: 'sec-1',
    category: 'personel',
    name: 'Dokumen Personel — JUVIANDY',
    rows: [],
  };
  const groupedSubtypeSection: MatchSection = {
    id: 'sec-2',
    category: 'personel',
    name: 'Dokumen Personel',
    rows: [
      {
        id: 'r1',
        field: 'Nama',
        expected: 'A',
        observed: 'A',
        score: 100,
        status: 'MATCH',
        detail: {
          type: 'personnel',
          source_label: 'Surat Izin Bekerja (SIB)',
        },
      },
    ],
  };

  assert.equal(matchingSectionTitle(unifiedSection), 'Dokumen Personel · 3 Dokumen');
  assert.equal(matchingSectionTitle(namedSection), 'Dokumen Personel — JUVIANDY');
  assert.equal(matchingSectionTitle(groupedSubtypeSection), 'Surat Izin Bekerja (SIB)');
});

test('stripUploadTimestamp and findDuplicatePersonnelTabIds identify colliding tabs only', () => {
  assert.equal(
    stripUploadTimestamp('20261019082501-Mulia Perbaikan Garansi (Rama).pdf'),
    'Mulia Perbaikan Garansi (Rama).pdf',
  );
  const duplicates = findDuplicatePersonnelTabIds([
    { id: 'd1', docType: 'Sertifikat Pelatihan', owners: ['Shafira'] },
    { id: 'd2', docType: 'Surat Penugasan / Keterangan Kerja', owners: ['Shafira'] },
    { id: 'd3', docType: 'Surat Penugasan / Keterangan Kerja', owners: ['Shafira'] },
    { id: 'd4', docType: 'Surat Penugasan / Keterangan Kerja', owners: ['Juviandy'] },
  ]);
  assert.deepEqual([...duplicates], ['d2', 'd3']);
});

test('extractUsagePeriods prefers structured page evidence and falls back cleanly', () => {
  const withEvidence: MatchRow = {
    id: 'p1',
    field: 'Periode Pemakaian',
    expected: '—',
    observed: 'September - November 2026; Desember 2026 - Februari 2027',
    score: null,
    status: 'INFO',
    detail: {
      type: 'personnel',
      pages: [1, 2],
      evidence: [
        { page: 1, quote: 'Periode pemakaian September - November 2026', value: 'September - November 2026' },
        {
          page: 2,
          quote: 'Periode pemakaian Desember 2026 - Februari 2027',
          value: 'Desember 2026 - Februari 2027',
        },
      ],
    },
  };
  assert.deepEqual(extractUsagePeriods(withEvidence), [
    { page: 1, value: 'September - November 2026' },
    { page: 2, value: 'Desember 2026 - Februari 2027' },
  ]);

  const fallbackRow: MatchRow = {
    id: 'p2',
    field: 'Periode Pemakaian',
    expected: '—',
    observed: 'Mei - Juli 2026; Agustus - Oktober 2026',
    score: null,
    status: 'INFO',
    detail: {
      type: 'personnel',
      pages: [1, 2],
    },
  };
  assert.deepEqual(extractUsagePeriods(fallbackRow), [
    { page: 1, value: 'Mei - Juli 2026' },
    { page: 2, value: 'Agustus - Oktober 2026' },
  ]);
});
