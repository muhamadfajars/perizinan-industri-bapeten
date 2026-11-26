import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  applyClassification,
  classificationBlocker,
  analysisBlocker,
  toggleCategorySelection,
} from '../src/lib/uploadState.ts';
import type { UploadItem } from '../src/types/models.ts';

const pending: UploadItem = { id: 'scan', name: 'scan.pdf', size: 100,
  category: 'unknown', isClassifying: true, addedAt: '' };

test('pending and unrecognized documents block analysis until a category is chosen', () => {
  assert.match(classificationBlocker([pending])!, /Sedang mengenali/);
  const unknown = applyClassification(pending, { category: 'unknown', layer: 0, confidence: 0, reason: 'Tidak dikenali' });
  assert.equal(unknown.category, 'unknown');
  assert.equal(unknown.isClassifying, false);
  assert.match(classificationBlocker([unknown])!, /Perlu Pilih Kategori/);
  assert.equal(classificationBlocker([{ ...unknown, category: 'kalibrasi' }]), null);
});

test('recognized content carries its category and personnel subtype', () => {
  const known = applyClassification(pending, { category: 'personel', subtype: 'Surat Penugasan / Keterangan Kerja', layer: 2, confidence: .9, reason: 'Isi dokumen' });
  assert.equal(known.category, 'personel');
  assert.equal(known.subtype, 'Surat Penugasan / Keterangan Kerja');
  assert.equal(classificationBlocker([known]), null);
  assert.match(classificationBlocker([known, pending])!, /Sedang mengenali/);
});

test('late recognition success or failure cannot overwrite a manual choice', () => {
  const manual: UploadItem = { ...pending, category: 'paparan', isClassifying: false };
  for (const category of ['kalibrasi', 'unknown'] as const) {
    assert.equal(applyClassification(manual, { category, layer: 0, confidence: 0, reason: 'Late response' }), manual);
  }
});

test('analysis requires exactly one reference form and at least one classified supporting document', () => {
  const form: UploadItem = { ...pending, id: 'form', category: 'formulir', isClassifying: false };
  const support: UploadItem = { ...pending, category: 'kalibrasi', isClassifying: false };
  assert.match(analysisBlocker([])!, /Unggah/);
  assert.match(analysisBlocker([support])!, /Tambahkan 1 Formulir/);
  assert.match(analysisBlocker([form])!, /dokumen pendukung/);
  assert.match(analysisBlocker([form, { ...form, id: 'form2' }, support])!, /tepat 1/);
  assert.equal(analysisBlocker([form, support]), null);
  assert.match(analysisBlocker([form, support, pending])!, /Sedang mengenali/);
  assert.match(analysisBlocker([form, support, { ...pending, isClassifying: false }])!, /Perlu Pilih Kategori/);
});

 test('obsolete personnel results require reclassification instead of creating duplicate options', () => {
  const result = applyClassification(pending, { category: 'personel', subtype: 'Sertifikat Kompetensi', layer: 2, confidence: .9, reason: 'Old server' });
  assert.equal(result.category, 'unknown');
  assert.equal(result.subtype, undefined);
  assert.match(classificationBlocker([{ ...pending, isClassifying: false, category: 'personel', subtype: 'Sertifikat Kompetensi' }])!, /Perlu Pilih Kategori/);
});

test('applyClassification and blockers handle multiple categories per file safely', () => {
  const form: UploadItem = { ...pending, id: 'form', category: 'formulir', isClassifying: false };
  const combined = applyClassification(pending, {
    category: 'fungsi',
    extraCategories: [
      { category: 'paparan' },
      { category: 'fungsi' },
      { category: 'formulir' },
      { category: 'paparan' },
    ],
    layer: 2,
    confidence: 0.9,
    reason: 'Laporan gabungan',
  });
  assert.equal(combined.category, 'fungsi');
  assert.deepEqual(combined.extraCategories, [{ category: 'paparan' }]);
  assert.equal(analysisBlocker([form, combined]), null);

  assert.match(
    classificationBlocker([
      {
        ...combined,
        extraCategories: [{ category: 'personel', subtype: 'Sertifikat Kompetensi' }],
      },
    ])!,
    /Perlu Pilih Kategori/,
  );
  assert.match(
    analysisBlocker([
      { ...form, extraCategories: [{ category: 'paparan' }] },
      combined,
    ])!,
    /Formulir Permohonan tidak dapat digabung/,
  );
});

test('toggleCategorySelection supports Opsi A multi-select checkbox rules cleanly', () => {
  // Adding a second category to a single category puts it in extraCategories.
  const added = toggleCategorySelection('fungsi', undefined, [], 'paparan');
  assert.deepEqual(added, {
    category: 'fungsi',
    subtype: undefined,
    extraCategories: [{ category: 'paparan' }],
  });

  // Adding a distinct personnel subtype to an existing personnel subtype.
  const bundledPersonnel = toggleCategorySelection(
    'personel',
    'Surat Izin Bekerja (SIB)',
    [],
    'personel',
    'Sertifikat Kompetensi PPR',
  );
  assert.deepEqual(bundledPersonnel, {
    category: 'personel',
    subtype: 'Surat Izin Bekerja (SIB)',
    extraCategories: [{ category: 'personel', subtype: 'Sertifikat Kompetensi PPR' }],
  });

  // Removing primary category promotes the remaining extra category cleanly.
  const removedPrimary = toggleCategorySelection(
    bundledPersonnel.category,
    bundledPersonnel.subtype,
    bundledPersonnel.extraCategories,
    'personel',
    'Surat Izin Bekerja (SIB)',
  );
  assert.deepEqual(removedPrimary, {
    category: 'personel',
    subtype: 'Sertifikat Kompetensi PPR',
    extraCategories: [],
  });

  // Cannot uncheck the last remaining category.
  const keptLast = toggleCategorySelection('kalibrasi', undefined, [], 'kalibrasi');
  assert.deepEqual(keptLast, { category: 'kalibrasi', subtype: undefined, extraCategories: [] });

  // Selecting formulir clears extras; selecting supporting replaces formulir.
  const asForm = toggleCategorySelection('fungsi', undefined, [{ category: 'paparan' }], 'formulir');
  assert.deepEqual(asForm, { category: 'formulir', subtype: undefined, extraCategories: [] });

  const fromForm = toggleCategorySelection('formulir', undefined, [], 'mutu');
  assert.deepEqual(fromForm, { category: 'mutu', subtype: undefined, extraCategories: [] });
});
