# Program Proteksi dan Keselamatan Radiasi

Kategori `proteksi` memakai evaluator di `backend/app/protection/`. Kategori
lain masih memakai evaluator sebelumnya. Formulir permohonan tetap menjadi
acuan utama; nilainya tidak diganti dengan isi dokumen pendukung.

## Perilaku hasil

- Nomor dan tanggal dokumen mengacu pada baris Program Proteksi dalam tabel
  persyaratan formulir, bukan nomor registrasi permohonan atau Sistem Manajemen.
- Identitas acuan hanya Instansi dan Alamat Proyek pada formulir. Alamat kantor
  dan nama fasilitas tidak menjadi field identitas tambahan pada tampilan.
  Urutan awal tabel: Nama Instansi, Alamat, Nomor Dokumen, Tanggal Dokumen.
  Label Alamat tetap merujuk Alamat Proyek pada formulir.
- Petugas berada dalam tabel matching utama dengan pemisah Petugas 1, Petugas 2,
  dan seterusnya. Baris Nama dan Profesi/Keahlian memuat nilai formulir/dokumen,
  skor serta status; klik baris untuk membuka catatan dan bukti sumber.
  Kemiripan nama tidak otomatis menjadi MATCH. Kecocokan profesi dinilai tersendiri
  dan tidak mengonfirmasi identitas nama yang berbeda.
- Unit dan tabung dipertahankan sebagai pasangan satu baris. Data dari beberapa
  alat tidak digabung demi memperoleh hasil cocok. Alat/petugas cabang lain yang
  tidak menjadi kandidat data formulir tidak ditampilkan sebagai baris tambahan.
- Kondisi Maksimal (tegangan dan arus maksimum) tidak diekstrak sebagai field
  terstruktur dan tidak ditampilkan atau dicocokkan. Teks asli pada halaman bukti
  tetap utuh.
- Lima dasar hukum yang diminta selalu tampil: UU 10/1997, PP 45/2023,
  PP 28/2025, Perba 4/2024, dan Perba 5/2025. Jika belum terbaca, diberi keterangan
  tersebut. Dasar hukum tambahan dalam dokumen juga ditampilkan. Ini merupakan
  daftar pemeriksaan pengguna, bukan pemeriksaan status berlaku peraturan.
- Daerah pengendalian, pengawasan/supervisi, Pembatas Dosis, dan pengesahan adalah
  INFO. Bagian ini tidak masuk pembilang maupun penyebut persentase kecocokan.
- Bukti memiliki kutipan dan halaman. Gambar berupa halaman sumber utuh dengan
  pilihan halaman, sehingga denah beberapa cabang tetap dapat diperiksa.
- Pengesahan membutuhkan pemeriksaan visual tanda tangan oleh evaluator;
  keberadaan judul/nama/jabatan tidak mengesahkan tanda tangan. Stempel tidak wajib.

## Skor pencocokan

- Nilai identik setelah normalisasi: MATCH 100. Tanggal dengan format berbeda
  dinormalisasi terlebih dahulu; tanggal sama mendapat MATCH meskipun label sumber
  menyebut tanggal dibuat. Perbedaan konteks label tetap dicatat.
- Operator dan Operator Alat XRF: profesi setara, MATCH 95 (skor aturan), karena
  uraian tidak identik. Profesi dengan teks identik setelah normalisasi mendapat 100.
- PPR dan kepanjangannya: MATCH 90 bila rincian keahlian tidak seluruhnya disebutkan.
  Ini skor aturan, bukan probabilitas ataupun verifikasi kompetensi. Bidang yang
  eksplisit bertentangan tetap REVIEW.
- Instansi: kemiripan karakter minimal 90% dapat MATCH dengan skor kemiripan.
  Nama inti yang sama dengan tambahan PT/CV tetap MATCH, tetapi skor memakai
  kemiripan teks lengkap sehingga kurang dari 100.
- Alamat: kesamaan token minimal 85%, nama jalan sama dan tanpa konflik komponen
  angka dapat MATCH. Singkatan dan pengulangan dinormalisasi; skor variasi maksimal 99.
- Nama orang berbeda tetap REVIEW dengan skor kemiripan, tidak diubah agar sama
  dengan formulir. Nomor seri berbeda tetap MISMATCH.
- Nilai belum terbaca tidak diberi skor. Ringkasan persentase tetap proporsi jumlah
  field MATCH, bukan rata-rata skor atau persentase kepatuhan perizinan.

Informasi Pendukung hanya berisi dasar hukum, daerah pengendalian/pengawasan,
Pembatas Dosis, dan pengesahan. Catatan kegagalan pembacaan ditampilkan terpisah.
Field acuan yang kosong pada formulir tetap INFO pada kelompok datanya sendiri.
Tampilan ringkas menampilkan status ditemukan untuk dasar hukum, halaman sumber
dan tombol gambar untuk daerah/pengesahan, serta kutipan pendek Pembatas Dosis.
Pembatas Dosis dipilih dari pernyataan eksplisit dengan angka dosis; pernyataan
tentang operasi saat ini diprioritaskan atas tabel tahapan atau uraian umum.
Halaman default mengikuti pernyataan tersebut, tanpa nomor halaman tetap
(sampel Tuku: 48; CV Mulia: 45). Paragraf ditampilkan utuh satu kali. Uraian NBD
umum saja tidak dianggap penetapan pembatas dosis. Pengesahan hanya menampilkan
gambar dan kontrol halaman setelah dibuka, tanpa kutipan atau catatan berulang.
Kutipan lengkap dan pilihan halaman tetap tersedia pada bukti lainnya.
Petunjuk klik berada tepat di atas tabel. Panel detail Program Proteksi hanya
memiliki satu area Bukti sumber (pilihan halaman, kutipan, gambar, dan tombol
sekunder Buka PDF lengkap). Nilai dan catatan tidak diulang dalam area tersebut.
Pembatas Dosis menggunakan komponen khusus: satu paragraf utuh, tanpa potongan
ringkasan, catatan umum, atau kutipan lain ketika Lihat gambar dibuka.

## Pembacaan hybrid

Teks dan tabel PDF dibaca dahulu. OCR Tesseract digunakan untuk halaman minim
teks serta halaman awal dengan gambar yang mungkin memuat pengesahan hasil scan.
Jika suatu kelompok data belum menghasilkan record terstruktur, halaman kandidat
diproses melalui Ollama lokal. Keluaran Qwen harus memiliki halaman dan kutipan
yang terdapat dalam teks sumber; nilai yang tidak ada dalam kutipan dibuang.
Pencocokan akhir menggunakan aturan aplikasi, bukan keputusan LLM.

Konfigurasi opsional di `backend/.env` (restart backend setelah mengubah):

```dotenv
BAPETEN_PROTECTION_LLM=1
BAPETEN_OLLAMA_URL=http://127.0.0.1:11434
BAPETEN_LLM_MODEL=qwen3:8b
BAPETEN_LLM_THREADS=8
BAPETEN_LLM_TIMEOUT=180
```

Thinking dimatikan, konteks dibatasi 8192 token, maksimal 6 halaman kandidat
per kelompok, satu halaman per panggilan. File lock membatasi satu panggilan
Qwen pada satu direktori data aplikasi; ini tidak membatasi pengguna Ollama
lain atau aplikasi dengan direktori data berbeda. Kegagalan pembacaan muncul
sebagai catatan; hasil dengan catatan tidak disimpan dalam cache ekstraksi.
`BAPETEN_PROTECTION_LLM=0` menonaktifkan fallback, bukan pembacaan teks/tabel/OCR.

## Batasan tahap ini

Validasi utama menggunakan dua batch PDF sampel. Belum ada uji kapasitas untuk
15–20 pengguna bersamaan. Angka durasi sampel tidak menjamin kapasitas produksi.
Denah dan tanda tangan ditampilkan untuk pemeriksaan manusia, belum dideteksi
atau dinilai sah secara otomatis. Alamat yang tidak memenuhi aturan kemiripan
dan bukti yang bertentangan memerlukan REVIEW.

Kecocokan nilai tanggal tidak membuktikan bahwa tanggal dibuat merupakan tanggal
pengesahan. Label tanggal yang belum jelas perlu diperiksa pada sumber.
Fallback berjalan per kelompok data; record tabel yang terbaca tidak menjamin
semua uraian bebas atau semua kolom kelompok tersebut sudah tertangkap.
Pratinjau halaman bukti saat ini tersedia untuk PDF.

## Verifikasi

- Pengujian aturan baru ada di `backend/tests/test_protection.py`.
- Pengujian frontend memastikan INFO tidak memengaruhi skor.
- Kedua batch sampel diuji melalui unggah API, analisis, dan render halaman bukti.
  Browser memeriksa lima hukum wajib, gambar kedua daerah dan pengesahan,
  tampilan ponsel, serta tidak adanya error JavaScript.
- Fallback Qwen lokal diuji dengan teks personel sintetis dan kutipan pendukung.
- Regresi mesin lama tetap dicatat di `docs/CLEANUP.md`; implementasi kategori
  ini tidak memperbaiki seluruh kategori lain atau menghapus pengujian lama.

Untuk melihat evaluator baru pada permohonan yang sudah memiliki hasil,
jalankan analisis ulang. Riwayat hasil sebelumnya tidak ditulis ulang otomatis.
