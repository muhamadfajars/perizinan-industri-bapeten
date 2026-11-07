# Catatan perapihan — 6 November 2026

## Pemulihan

- Commit awal sebelum perubahan: `726592d`.
- Cadangan lengkap: `/home/fajar/bapeten-industri-backup-qUU8Ts/project-before-cleanup.tar.gz`.
- Cadangan tidak memasukkan lingkungan virtual, node_modules, atau runtime_data.
  Data operasional di luar folder proyek tidak dipindahkan atau dihapus.
- Perubahan setelah commit awal tetap tersedia sebagai perubahan lokal untuk ditinjau.

## Struktur dan penamaan

- `app/main.py` menjadi perakitan aplikasi/middleware. Endpoint berada di `app/api/`,
  konfigurasi di `app/config.py`, dan model HTTP di `app/schemas.py`.
- Pekerjaan latar berada di `app/services/jobs.py`.
- `engine_adapter.py` dipecah ke `app/analysis/`: pipeline, reference, rows,
  programs, equipment, personnel, labels, evidence, constants, dan registry.
- Modul berakhiran versi diganti menurut tanggung jawab. Pasangan lama yang
  saling bergantung dipertahankan sebagai modul berbeda, bukan ditimpa.
- `label_parallel_v057` menjadi `label_ocr_worker`; `label_parallel_v058`
  menjadi `label_ocr_scheduler`.
- `program_robust_v43`, `program_robust_v44`, dan `program_robust_v46`
  menjadi `program_evidence`, `program_identity`, dan `program_matching`.
- `personnel_evidence_v40` dan `personnel_evidence_v42` menjadi
  `personnel_evidence` dan `personnel_comparison`.
- Modul address, identity, unit_model, facility, serial, reference_evidence,
  evidence_cohesion, field_evidence, label_gs1, label_panel, dan
  supplementary_matching tidak lagi menggunakan akhiran versi pada nama file.
- `parity_personnel`/`parity_label` menjadi `personnel_results`/`label_results`.
- Matcher label dipisah menjadi normalisasi, kandidat, field, halaman,
  identitas, dan tahapan pencocokan dokumen. Definisi fungsi berulang diganti
  menjadi tahapan eksplisit dengan urutan yang sama.
- Matcher personel dipisah menjadi normalisasi, identitas, masa berlaku,
  izin personel, penugasan, dan koordinasi validasi dokumen.
- Frontend dipisah menjadi pages, components, hooks, lib, types, dan styles.
  `App.tsx` menjadi penggabungan tata letak; penerimaan berkas ada di
  `useUploadIntake`, sedangkan sesi analisis ada di `useEvaluationWorkspace`.
- Warna manual terakhir dipertahankan. Variabel tema berada di `styles/theme.css`.
  Urutan CSS tetap dipertahankan melalui `styles/index.css`.
- Nomor versi API dan format data/cache sengaja tetap dipertahankan.

## Penghapusan dan pemindahan

Modul berikut dihapus setelah penelusuran referensi menunjukkan tidak dipakai
jalur aplikasi aktif:

- `extraction/admin_table.py`.
- Jalur label lama: `extraction/label_pipeline.py`, `extraction/label_parser.py`,
  `matching/equipment_validator.py`, dan `matching/label_matcher.py`.
- Enam skrip contoh di `engine/tests/legacy/` yang bergantung pada berkas contoh
  lokal dan sebagian pada jalur label lama.
- Dua belas modul pengujian antarmuka lama yang membaca `engine/app/app.py`
  (file aplikasi tersebut tidak tersedia). Assertion domain yang masih berguna
  dari pengujian campuran dipertahankan; assertion antarmuka usang dihapus.
- Nama komponen/CSS, komentar, serta dokumentasi yang mengacu pada framework
  antarmuka lama dibersihkan. Fungsi evaluasi yang masih dipakai API dipertahankan.

`compare_ocr_methods.py` dipindahkan ke `backend/scripts/` dan menerima gambar
melalui argumen CLI. File yang dihapus dapat dipulihkan dari commit awal/cadangan.
Cache bytecode yang sumbernya sudah dipindah/dihapus dibersihkan; cache baru
dapat dibuat kembali oleh Python.

## Perbaikan pendukung

- Konfigurasi dimuat sebelum storage pada startup FastAPI langsung.
- Fingerprint cache analisis mencakup seluruh modul aplikasi setelah pemisahan,
  sehingga perubahan handler/bukti ikut membatalkan cache ekstraksi lama.
- Import `os` dan `shutil` yang hilang pada pembaca checkbox diperbaiki.
- Pemeriksaan statis frontend diperbarui mengikuti struktur halaman baru.
- Pengujian integrasi analisis kini memastikan hasil tidak berisi error ekstraksi
  dan memiliki baris pencocokan, bukan sekadar pekerjaan berstatus selesai.
- Runner backend mengisolasi data, token, konfigurasi CORS, dan proses pengujian.
- Ruff dan Prettier disediakan untuk menjaga format yang konsisten.

## Hasil pemeriksaan

- Backend API/klasifikasi: 20 pengujian, 18 lulus dan 2 dilewati karena dokumen
  contoh lokal tidak tersedia.
- Frontend: 19 pengujian lulus; pemeriksaan statis, TypeScript, dan build lulus.
- Pemeriksaan nama Python yang tidak terdefinisi/definisi ulang lulus.
- Browser: navigasi lima halaman, unggah dua PDF sintetis, analisis, refresh
  hasil, dan navigasi ponsel lulus. Warna/padding/display utama dibandingkan
  dengan build cadangan dan cocok (normalisasi penulisan stop gradasi CSS).
- Layanan Industri telah dimulai ulang setelah dipastikan tidak ada analisis
  aktif; frontend dan health endpoint pada port 8010 berhasil diakses.
- Runner lengkap backend: 19 dari 25 kelompok pengujian lulus. Enam kelompok
  mempunyai delapan kegagalan/error yang juga terjadi pada commit awal.
  Kegagalan tersebut tidak dihapus atau disembunyikan.

### Regresi bawaan yang masih memerlukan keputusan domain

| Kelompok | Ketidaksesuaian yang sudah ada sebelum perapihan |
|---|---|
| `test_label_conflicting_fields` | Pengujian meminta bukti model dari perangkat berbeda; aturan penolakan identitas mengosongkannya. |
| `test_label_fields` | Pengujian meminta dua varian ROI, implementasi menghasilkan empat. |
| `test_label_original_gating` | Dua pengujian meniru jalur OCR lama; stub tidak menyediakan `ensure_bgr`, sedangkan jalur aktif memakai worker OCR. |
| `test_program_documents` | Pengujian mengharapkan `INDIKASI`, implementasi mengembalikan `MATCH` untuk keberadaan pengesahan. |
| `test_program_matching` | Teks referensi pengesahan masih diterima sebagai kandidat. |
| `test_program_robustness` | Dua ekspektasi status nomor seri berbeda dari hasil implementasi. |

Perbandingan baseline dilakukan dengan menjalankan kembali berkas pengujian
asli pada sumber dari commit awal menggunakan interpreter yang sama.
Pemeriksaan ini belum mencakup validasi OCR seluruh dokumen operasional ataupun
perubahan persyaratan domain industri.
