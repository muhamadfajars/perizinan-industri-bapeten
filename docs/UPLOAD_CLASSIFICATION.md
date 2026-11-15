# Klasifikasi upload

Upload otomatis selalu mengirim file untuk pemeriksaan isi. Pencocokan nama file
di browser bukan keputusan akhir. Pilihan manual evaluator tetap dipertahankan,
termasuk jika respons otomatis tiba setelah pilihan manual.

## Keputusan

- Judul isi digunakan untuk mengonfirmasi kategori; daftar persyaratan pada
  formulir dan daftar materi pelatihan tidak dianggap judul dokumen tersendiri.
- Konflik kategori nama dan isi, judul ambigu, serta gabungan beberapa subjenis
  personel meminta pemilihan manual. Sistem belum memecah PDF gabungan.
- Jika kategori personel sama dan judul isi jelas, subjenis mengikuti isi:
  misalnya nama berkas pengangkatan dengan judul Surat Keterangan Kerja.
- Jika isi tidak menunjukkan judul, nama file masih dapat memberikan kategori
  sementara dengan keterangan bahwa isi belum mengonfirmasi. Nilai confidence
  adalah bobot aturan, bukan probabilitas akurasi hasil pengukuran.
- File rusak, terkunci, atau gagal OCR tidak otomatis dipercayai berdasarkan
  nama file. Alasan pemeriksaan ditampilkan di bawah pilihan kategori.

## Batas pembacaan dan beban

- Enam halaman awal PDF; maksimal tiga halaman di-OCR. OCR juga dipicu oleh
  gambar besar walaupun halaman sudah memiliki kop berupa teks native.
- Bahasa mengikuti BAPETEN_TESS_LANG dan bahasa Tesseract yang terpasang.
  OCR otomatis memakai PSM 3; jika hampir kosong, mencoba PSM 11.
- Maksimal 10 detik untuk percobaan pertama dan 8 detik untuk percobaan kedua
  per halaman. Gambar render dibatasi sisi terpanjang 2400 piksel.
- DOCX mencakup paragraf dan tabel; gambar/TIFF menggunakan OCR.
- Dua permintaan aktif per batch browser dan dua pemeriksaan aktif per proses
  API. Pekerjaan CPU berjalan di thread pool, bukan event loop API.
- Batas ukuran dan jumlah mengikuti MAX_FILE/MAX_DOCS. Permintaan browser
  dibatasi 90 detik; jika gagal, evaluator tetap dapat memilih kategori manual.

Ini bukan klasifikasi visual atau pembacaan seluruh dokumen. Foto label buram,
scan berputar, judul di luar batas pembacaan, dan laporan berbahasa lain yang
tidak memiliki ciri cukup jelas masih dapat meminta pilihan manual. Tidak ada
tambahan panggilan LLM pada jalur upload.

## Pemeriksaan 12 November 2026

Isi 30 PDF/gambar pada dua batch industri diperiksa menggunakan teks native dan
OCR. Keputusan akhir diuji ulang dari teks hasil pembacaan: 23 mendapat kategori
dari isi, 7 meminta pilihan manual. Angka ini mengukur cakupan, bukan akurasi
terhadap label evaluator yang belum tersedia untuk seluruh berkas.

Kasus yang sengaja tetap manual termasuk gabungan SIB dan sertifikat Shafira,
foto dengan teks sangat sedikit, gambar lokasi sumber, dan laporan pengujian
umum tanpa bukti kategori yang cukup spesifik. Tidak dibuat aturan merek alat
atau nama instansi untuk memaksakan kategori sampel tersebut.

Pengujian otomatis mencakup konflik nama/isi, formulir dengan daftar dokumen,
materi pelatihan, gabungan personel, DOCX tabel, scan setelah halaman pertama,
batas OCR, TIFF, validasi API, serta respons otomatis setelah pilihan manual.
