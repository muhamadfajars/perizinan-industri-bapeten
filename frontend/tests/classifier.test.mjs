import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Run the browser filename classifier without loading browser-only API initialization.
const source = readFileSync(new URL('../src/lib/classifier.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } });
const sharedRules = JSON.parse(readFileSync(new URL('../../backend/app/classification_rules.json', import.meta.url), 'utf8'));
let apiCalls = 0;
const sandbox = { exports: {}, require: name => {
  if (name === '../../../backend/app/classification_rules.json') return { default: sharedRules };
  if (name === '../api') return { classifyFile: async () => {
    apiCalls++;
    return { category: 'unknown', layer: 0, confidence: 0, reason: 'Nama dan isi berbeda' };
  } };
  throw new Error(`Unexpected import: ${name}`);
} };
vm.runInNewContext(compiled.outputText, sandbox);
const classify = sandbox.exports.classifyByFilename;

test('recognized filenames still require content verification', async () => {
  const before = apiCalls;
  const result = await sandbox.exports.classifyFile({ name: 'Program Proteksi.pdf' });
  assert.equal(apiCalls, before + 1);
  assert.equal(result.category, 'unknown');
});

test('shared rules match the filename regression baseline', () => {
  const baseline = JSON.parse(readFileSync(new URL('../../backend/tests/fixtures/classification_filename_baseline.json', import.meta.url), 'utf8'));
  for (const { name, browser } of baseline) {
    assert.deepEqual(JSON.parse(JSON.stringify(classify(name))), browser, name);
  }
});

test('dose reports remain personnel documents while removed categories stay unclassified', () => {
  for (const name of ['20260714134027-Laporan Dosis Awal RS Hermina Kepanjen Periode Oktober - Desember 2026.pdf',
    'Laporan_Dosis_OSL.pdf', 'Hasil Pembacaan Dosis TLD.pdf', 'Dosis Awal.pdf', 'Evaluasi Dosis OSL.pdf']) {
    assert.equal(classify(name)?.category, 'personel', name);
    assert.equal(classify(name)?.subtype, 'Evaluasi Dosis / Zero Check', name);
  }
  for (const name of [
    'Daftar Pemakai TLD.pdf',
    'Daftar Pengguna Lencana OSL.pdf',
    'Petugas TLD.pdf',
    'Kepesertaan Pemantauan OSL.pdf',
    'DOKUMEN TEKNIS RSH KEPANJEN.pdf',
    'Lencana OSL.pdf',
    'TLD.pdf',
    'dosimeter.pdf',
    'NUKLINDOLAB.pdf',
  ]) {
    assert.equal(classify(name), null, name);
  }
  assert.equal(classify('Sertifikat Kalibrasi Alat.pdf')?.category, 'kalibrasi');
  assert.equal(classify('Certificate of Manufacture and Calibration XRF.pdf')?.category, 'kalibrasi');
  assert.equal(classify('Sertifikat Uji Mutu.pdf')?.category, 'mutu');
  for (const name of ['LHU DOSIS MARET-MEI 2026.pdf', 'LHU TLD.pdf', 'Pemantauan Dosis Perorangan.pdf']) {
    assert.equal(classify(name)?.category, 'personel', name);
    assert.equal(classify(name)?.subtype, 'Evaluasi Dosis / Zero Check', name);
  }
  assert.equal(classify('LHU Uji Kesesuaian.pdf'), null);
  assert.equal(classify('250169011_KTUN_Sertifikat_UK jiwa aceh.pdf'), null);
});

test('tube label aliases resolve in the browser', () => {
  for (const name of ['20260917112321-sn tube Fix 2.jpg', 'SN_TABUNG_03.png', 'sn-generator.jpeg', 'sn unit Fix 2.jpg']) {
    assert.equal(classify(name)?.category, 'label', name);
  }
});

test('PPR appointment titles take precedence over generic protection terms', () => {
  for (const name of ['20260918090751-Surat Penunjukan PPR FIX 2.jpg', 'Surat_Penunjukan_Sebagai_PPR.pdf',
    'Surat Penunjukan Petugas Proteksi Radiasi.jpg', 'Surat Penunjukan sebagai Petugas Proteksi Radiasi.pdf']) {
    assert.equal(classify(name)?.category, 'personel', name);
    assert.equal(classify(name)?.subtype, 'Surat Penunjukan Tugas', name);
  }
  assert.equal(classify('PROGRAM PROTEKSI RADIASI FIX SIP.pdf')?.category, 'proteksi');
});

test('unrelated names still need a category', () => {
  for (const name of ['sn tubing.jpg', 'Surat Penunjukan Vendor.pdf', 'scan001.jpg']) {
    assert.equal(classify(name), null, name);
  }
});

test('worker appointment variants are recognized and removed categories stay unclassified', () => {
  for (const name of ['20260818155148-SK PENETAPAN PEKERJA RADIASI DAN PENUNJUKAN PPR.pdf',
    'SK_PENETAPAN_PEKERJA_RADIASI.pdf', 'Penunjukan Petugas Proteksi Radiasi.pdf']) {
    assert.equal(classify(name)?.category, 'personel', name);
    assert.equal(classify(name)?.subtype, 'Surat Penunjukan Tugas', name);
  }
  for (const name of ['DOKUMEN_PERAWATAN_MOBILE.pdf', 'perawatan fasilitas.pdf', 'SIP dokter.pdf']) {
    assert.equal(classify(name), null, name);
  }
});

test('conflicting categories or personnel subtypes require manual selection', () => {
  for (const name of ['PROGRAM PROTEKSI DAN SPESIFIKASI ALAT.pdf',
    'Sertifikat Pelatihan dan Surat Keterangan Kerja.pdf']) {
    assert.equal(classify(name)?.category, 'unknown', name);
    assert.equal(classify(name)?.confidence, 0, name);
  }
  assert.equal(classify('HASIL UJI ZERO CHECK TLD.pdf')?.category, 'personel');
});
