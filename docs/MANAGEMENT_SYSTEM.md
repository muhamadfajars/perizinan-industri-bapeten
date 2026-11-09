# Evaluasi Sistem Manajemen

Handler `app.management.service` membaca dokumen sendiri menggunakan teks PDF dan OCR
bila diperlukan. Identitas terstruktur diutamakan; fallback Qwen lokal hanya untuk
halaman kandidat yang memiliki petunjuk identitas/alamat. Nilai Qwen harus didukung
kutipan pada halaman yang sama. Acuan formulir tidak dimasukkan sebagai hasil ekstraksi.

Tabel membandingkan Nama Instansi (Instansi formulir), Alamat (Alamat Proyek formulir),
dan Nomor Dokumen (baris Dokumen Sistem Manajemen dalam persyaratan formulir).
Nomor Program Proteksi tidak digunakan untuk Sistem Manajemen. Tidak ada acuan berarti
INFO; acuan tersedia tetapi nilai dokumen tidak terbaca berarti REVIEW tanpa skor.
Nomor dokumen berbeda berarti MISMATCH; beberapa nomor berbeda berarti REVIEW.

Informasi pendukung tidak masuk perhitungan kecocokan:
- Lembar Pengesahan: kandidat halaman diprioritaskan berdasarkan judul/konteks pengesahan.
  Tombol sumber membuka gambar halaman di dialog; tanda tangan tetap diperiksa evaluator.
- Budaya Keselamatan dan Keamanan: memiliki satu status gabungan: Ditemukan jika kedua unsur memiliki uraian,
  Belum lengkap jika hanya satu unsur, dan Belum ditemukan jika keduanya belum terbaca.
  Bagian khusus budaya diprioritaskan tanpa mengunci nomor subbab. Daftar isi, judul saja,
  atau penyebutan singkat tanpa uraian tidak cukup. Status ini bukan penilaian penerapan.
  Bukti halaman tersedia melalui pratinjau PDF.

Pada sampel Tuku Emas, nomor dokumen cocok, pengesahan berada di halaman 2, dan uraian
budaya pada halaman 5–7. Alamat belum ditemukan sehingga REVIEW, bukan disalin dari formulir.
Pada sampel CV Mulia, identitas/alamat dan nomor cocok, pengesahan di halaman 2, uraian
budaya pada halaman 7–9. Nomor halaman berasal dari dokumen, bukan konstanta per batch.

Pengujian `backend/tests/test_management.py` memeriksa pemisahan acuan nomor,
alamat tidak terbaca, konflik/mismatch nomor, status INFO, serta bukti budaya dan daftar isi.
