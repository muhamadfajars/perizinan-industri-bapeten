# Evaluasi Sistem Manajemen

Handler `app.management.service` membaca dokumen sendiri menggunakan teks PDF dan OCR
bila diperlukan. Identitas terstruktur diutamakan; fallback Qwen lokal dipakai untuk
field identitas yang belum terbaca dan uraian budaya yang belum ditemukan oleh aturan.
Pembacaan dibatasi tiga halaman kandidat per tugas. Nilai Qwen harus didukung
kutipan pada halaman yang sama. Acuan formulir tidak dimasukkan sebagai hasil ekstraksi.
Setiap kandidat dapat menyertakan halaman berikutnya jika total konteks tidak
melebihi 12.000 karakter. Bukti tetap menyebut halaman asal masing-masing kutipan.
Fallback identitas meminta hanya field yang belum terbaca, dengan batas keluaran
1.000 token. Halaman yang sudah tercakup konteks tidak dikirim ulang. Jika tidak
ada petunjuk identitas/alamat, satu konteks halaman awal tetap diperiksa. Pencarian
yang dibatasi atau gagal tetap menghasilkan catatan, bukan kesimpulan bahwa data tidak ada.
Pencarian identitas meliputi seluruh halaman, menggunakan hasil OCR bila tersedia,
dan mengenali instansi seperti RSUD, Klinik, Universitas, Balai, Koperasi dan Yayasan.

Tabel membandingkan Nama Instansi (Instansi formulir), Alamat (Alamat Proyek formulir),
dan Nomor Dokumen (baris Dokumen Sistem Manajemen dalam persyaratan formulir).
Nomor Program Proteksi tidak digunakan untuk Sistem Manajemen. Tidak ada acuan berarti
INFO; acuan tersedia tetapi nilai dokumen tidak terbaca berarti REVIEW tanpa skor.
Nomor dokumen berbeda berarti MISMATCH; beberapa nomor berbeda berarti REVIEW.
Cakupan tetap lima item yang disepakati: tiga field tersebut, pengesahan, serta
Budaya Keselamatan dan Keamanan. Tanggal dan kelengkapan bab lain belum menjadi
kriteria evaluasi; hasil ini bukan pemeriksaan seluruh kelengkapan Sistem Manajemen.

Informasi pendukung tidak masuk perhitungan kecocokan:
- Lembar Pengesahan: kandidat halaman diprioritaskan berdasarkan judul/konteks pengesahan.
  Status berbunyi “Halaman pengesahan ditemukan”, bukan verifikasi tanda tangan.
  Tombol sumber membuka gambar halaman di dialog; tanda tangan tetap diperiksa evaluator.
- Budaya Keselamatan dan Keamanan: memiliki satu status gabungan: Ditemukan jika kedua unsur memiliki uraian,
  Belum lengkap jika hanya satu unsur, dan Belum ditemukan jika keduanya belum terbaca.
  Bagian khusus budaya diprioritaskan tanpa mengunci nomor subbab. Daftar isi, judul saja,
  atau penyebutan singkat tanpa uraian tidak cukup. Status ini bukan penilaian penerapan.
  Bukti halaman tersedia melalui pratinjau PDF.
  Fallback semantik dapat mengenali uraian komitmen, perilaku, pelaporan dan tanggung
  jawab tanpa judul baku. Kedua aspek harus memiliki kutipan sumber masing-masing.
  Jika salah satu aspek belum terkonfirmasi setelah fallback, status menjadi
  **Perlu diperiksa**, bukan kesimpulan bahwa uraian tidak ada. Timeout, kutipan tidak
  valid, dan pembatasan cakupan dicatat. Status informasi tetap INFO tanpa skor matching.

Pada sampel Tuku Emas, nomor dokumen cocok, pengesahan berada di halaman 2, dan uraian
budaya pada halaman 5–7. Alamat belum ditemukan sehingga REVIEW, bukan disalin dari formulir.
Pada sampel CV Mulia, identitas/alamat dan nomor cocok, pengesahan di halaman 2, uraian
budaya pada halaman 7–9. Nomor halaman berasal dari dokumen, bukan konstanta per batch.

Pengujian `backend/tests/test_management.py` memeriksa pemisahan acuan nomor,
alamat tidak terbaca, konflik/mismatch nomor, status INFO, serta bukti budaya dan daftar isi.
Variasi judul dan kegagalan model diuji di `backend/tests/test_semantic_fallback.py`.
