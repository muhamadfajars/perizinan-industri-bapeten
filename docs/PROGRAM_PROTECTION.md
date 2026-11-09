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
Dasar hukum diambil dari bagian Dasar Hukum / Referensi (termasuk Landasan Hukum),
berdasarkan judul, tanpa mengunci nomor subbab. Lima peraturan wajib menggunakan
nama singkat (UU/PP/Perba No.) beserta judul tentang dan selalu tampil. Ringkasan Lengkap/Belum lengkap menyebut jumlah
dasar hukum yang ditemukan (misalnya “Lengkap — 5 dari 5 dasar hukum ditemukan”),
bukan kesimpulan kepatuhan hukum. Peraturan tambahan
ditampilkan terpisah; manual dan dokumen internal tidak termasuk. Kutipan isi tidak
ditampilkan pada tab dasar hukum; evaluator membuka dokumen sumber.
Nama peraturan wajib mengacu pada JDIH BAPETEN:
- https://jdih.bapeten.go.id/id/dokumen/peraturan/jenis/pp
- https://www.peraturan.go.id/files/peraturan-bapeten-no-4-tahun-2024.pdf
- https://www.peraturan.go.id/files/peraturan-bapeten-no-5-tahun-2025.pdf
Zonasi hanya menyediakan halaman berketerangan gambar pembagian daerah kerja yang
memuat visual (Tuku: 44–45; CV Mulia: 41), bukan halaman penyebutan istilah saja.
Halaman zonasi dipilih melalui dropdown; tombol Lihat dokumen sumber membuka
pratinjau pada halaman terpilih.
Pembatas Dosis memakai satu halaman utama tanpa dropdown, label pernyataan operasional,
dan sorotan pada nilai mSv/tahun. Pengesahan memilih satu kandidat halaman pengesahan
utama, bukan penyebutan tanda tangan di uraian tugas. Tanda tangan tetap diperiksa manual.
Tab Dasar Hukum, Zonasi Kerja, Pembatas Dosis dan Lembar Pengesahan tidak memakai
badge jumlah item. Tombol sumber membuka dialog PDF besar dengan navigasi halaman
dan zoom dari penampil PDF browser. Dialog menyediakan Buka di tab baru,
penutupan dengan tombol/Escape, dan pengembalian fokus ke tombol asal. Judul
pratinjau menyebut nama informasi/field dan halaman sumber; nama panjang dibatasi
satu baris agar ruang dokumen tetap luas. Status peraturan ditempatkan di bawah
judul dengan ikon dan warna, tanpa mengulang label kelompok pada setiap item.
Pembatas Dosis dipilih dari pernyataan eksplisit dengan angka dosis; pernyataan
tentang operasi saat ini diprioritaskan atas tabel tahapan atau uraian umum.
Halaman default mengikuti pernyataan tersebut, tanpa nomor halaman tetap
(sampel Tuku: 48; CV Mulia: 45). Paragraf ditampilkan utuh satu kali. Uraian NBD
umum saja tidak dianggap penetapan pembatas dosis.
Petunjuk klik berada tepat di atas tabel. Panel detail berisi nama field, status,
acuan formulir, hasil pembacaan dokumen, skor, alasan hasil yang ringkas, keterangan
halaman berupa teks (tanpa dropdown), dan tombol Lihat dokumen sumber yang
membuka dialog PDF pada halaman pertama bukti, dengan opsi tab baru. Tombol sumber memakai latar sidebar
dan teks putih. Preview serta navigasi kategori tidak diulang di panel.
PDF diambil dengan autentikasi lalu dibuka sebagai blob URL dengan #page sesuai
pilihan. PDF lengkap tetap dapat dinavigasi di penampil dokumen. Token tidak masuk URL.
Browser yang memblokir pop-up menampilkan pesan untuk mengizinkannya.

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
