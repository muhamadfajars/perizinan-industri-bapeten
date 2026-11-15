# Evaluasi Dokumen Personel

Nama merupakan field utama yang dicocokkan dengan petugas pada formulir permohonan.
Nama yang belum terbaca atau belum pasti pemiliknya diberi REVIEW. Dokumen hanya
digabung dalam satu bagian per petugas jika pemilik tunggalnya telah cocok.
Setiap baris tetap menyimpan ID file dan halaman sumber aslinya.

- Profesi/keahlian dibandingkan jika tersedia bukti teks dan acuan petugas.
  Pada SIB, klasifikasi tanpa label dapat dibaca dari posisinya di antara nomor
  izin dan nama pemegang. Jika informasi wajib izin belum terbaca, statusnya REVIEW.
- Masa berlaku selalu diperiksa pada dokumen izin seperti SIB, dan pada jenis
  lain hanya ditampilkan jika memiliki bukti. Nilainya hanya diambil dari pernyataan
  yang memiliki label masa berlaku.
  Tanggal terbit, pelatihan, atau pemantauan tidak otomatis menjadi tanggal akhir.
  Tanggal akhir yang telah lewat atau ambigu diberi REVIEW. Tanggal pemeriksaan
  menggunakan zona Asia/Jakarta. Ketiadaan informasi bukan berarti berlaku selamanya.
- Evaluasi dosis/Zero Check menampilkan Periode Pemakaian atau pemantauan, bukan
  Masa Berlaku. Periode harus berasal dari isi dokumen, bukan nama file.
- Jenis dokumen ditampilkan sebagai judul, tanpa field terpisah yang mengulang judul.
- Untuk surat penunjukan/perintah/keterangan kerja, kandidat pengesahan ditampilkan
  sebagai informasi. Tanda tangan harus diperiksa evaluator pada sumber; deteksi
  teks tidak membuktikan keberadaan tanda tangan secara visual.
- Nomor dokumen tidak menjadi field ekstraksi, matching, atau tampilan personel.

Analisis menggunakan teks/OCR dan parser personel, kebijakan kondisional di
`backend/app/personnel_policy.py`, kemudian pemeriksaan semantik di
`backend/app/personnel_semantic.py`. Hasil aturan saat ini belum membuktikan
hubungan pemilik–penandatangan, sehingga meskipun skor namanya 100, hasil tersebut
tetap memicu LLM untuk memverifikasi pemilik. Ini merupakan penggunaan hybrid:
OCR membaca, LLM menafsirkan hubungan, kode memvalidasi bukti dan melakukan matching.

LLM tidak diberi nama/profesi jawaban dari formulir. Output terstruktur memuat
pemilik, profesi, dan masa berlaku, beserta halaman dan rentang nomor baris sumber.
Kode mengambil kutipan langsung dari rentang itu; model tidak perlu menyalin
ulang paragraf. Nomor baris tetap mengacu ke halaman penuh meskipun halaman
dibagi menjadi beberapa potongan. Rentang harus valid dan kutipan harus ditemukan secara literal
setelah normalisasi spasi pada konteks yang dikirim.
Nama dan nilai harus tercantum dalam kutipan yang sama. Bukti profesi orang lain
tidak digunakan untuk pemilik dokumen. Nomor dokumen tidak diminta dari LLM.
Nama pemilik dipetakan ke petugas formulir secara konservatif: kecocokan persis
diterima, sedangkan variasi gelar/OCR kecil hanya diterima jika kandidat terbaik
kuat dan memiliki jarak yang cukup dari kandidat berikutnya.

Permintaan memakai konfigurasi model/server, batas waktu, dan antrean lintas
proses yang sama dengan proteksi/manajemen (`protection/llm.py`), termasuk
`BAPETEN_LLM_MODEL`, `BAPETEN_OLLAMA_URL`, `BAPETEN_LLM_TIMEOUT`, dan sakelar
bersama `BAPETEN_PROTECTION_LLM`. Maksimal dua permintaan per dokumen, konteks
9000 karakter teks sebelum penomoran baris per permintaan, tanpa thinking,
dengan maksimal 450 token keluaran. Potongan halaman panjang saling
tumpang tindih dan tetap memiliki nomor halaman asli. Dokumen yang melampaui
batas cakupan ditandai untuk pemeriksaan, bukan dianggap telah dibaca lengkap.

Jika model gagal/dinonaktifkan atau bukti pemilik tidak valid, hasil nama tetap
REVIEW. Dokumen hanya dikelompokkan ke petugas jika pemilik sumber sudah terbaca
dan cocok secara unik; status REVIEW pada field lain tidak memisahkan dokumennya.
Kegagalan ini tidak disimpan dalam extraction cache sehingga dapat dicoba ulang.
Kunci cache personel mencakup konfigurasi model dan tanggal Jakarta agar status
masa berlaku dihitung kembali pada hari berikutnya.

Batas saat ini: kutipan harus menghubungkan nama dan informasi pada halaman
yang sama. Hubungan yang hanya dapat dibuktikan lintas halaman, PDF multi-pemilik,
dan scan tidak terbaca masih memerlukan pemeriksaan. Verifikasi kutipan mencegah
nilai tanpa sumber, tetapi bukan jaminan bahwa interpretasi model selalu benar.
Pengesahan tetap berupa kandidat halaman untuk pemeriksaan tanda tangan manual.
Ketentuan di atas adalah cakupan aplikasi, bukan kesimpulan kelengkapan hukum.

Hasil analisis lama tidak berubah otomatis; jalankan analisis ulang untuk memakai
kebijakan ini.
