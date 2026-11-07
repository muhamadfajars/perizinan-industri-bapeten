# BAPETEN Industri — Asisten Evaluasi Dokumen

Aplikasi React/TypeScript dan FastAPI untuk mengunggah dokumen permohonan,
membaca PDF/OCR, membandingkan data dengan formulir, dan menampilkan bukti sumber.
Hasil pencocokan membantu evaluator; keputusan izin tetap dilakukan melalui
proses penilaian yang berlaku.

Identitas aplikasi sudah Industri. Parser dan aturan domain masih berasal dari
kebutuhan RDI dan perlu disesuaikan berdasarkan jenis kegiatan industri yang
akan didukung. Perapihan struktur tidak mengubah aturan domain tersebut.

## Menjalankan aplikasi

Gunakan Python >=3.10. Lingkungan pengembangan yang telah diperiksa menggunakan
Node.js 24 (pengujian TypeScript langsung membutuhkan Node.js >=22.18).

```bash
bash setup_bapeten_fullstack.sh
bash start_bapeten_fullstack.sh
bash status_bapeten_fullstack.sh
bash stop_bapeten_fullstack.sh
```

Peluncur menyajikan frontend dan API pada satu port, bawaan
`http://127.0.0.1:8010`. `backend/.env` dapat mengubah port dan konfigurasi.
Lokasi data bawaan peluncur adalah `~/bapeten-industri-private-data`.
Akses dari komputer lain menggunakan SSH tunnel:

```bash
ssh -L 8010:127.0.0.1:8010 USER@HPC_HOST
```

Untuk backend saja:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Konfigurasi `.env` dibaca sebelum layanan penyimpanan diinisialisasi.
Tanpa `BAPETEN_DATA_DIR`, backend langsung menggunakan `backend/runtime_data`.

## Struktur kode

```text
backend/
  app/
    main.py              # Perakitan aplikasi dan middleware
    config.py            # Konfigurasi lingkungan
    schemas.py           # Model permintaan HTTP
    api/                 # Endpoint permohonan, dokumen, klasifikasi, analisis
    services/jobs.py     # Pelaksanaan pekerjaan latar
    analysis/            # Koordinasi, handler kategori, format hasil, bukti
    storage.py           # SQLite dan berkas per permohonan
    performance.py       # Pool OCR dan cache
    *_evidence.py        # Kebijakan bukti dan pemeriksaan identitas
  engine/src/
    extraction/          # Pembacaan dokumen, OCR, parser
    matching/            # Pencocokan label, personel, peralatan
  engine/tests/          # Regresi mesin evaluasi
  tests/                 # API dan klasifikasi
  scripts/               # Pemeriksaan dan alat diagnosis
frontend/src/
  App.tsx                # Tata letak dan penggabungan halaman
  pages/                 # Lima halaman aplikasi
  components/            # Komponen tampilan dan bukti
  hooks/                 # Sesi evaluasi dan penerimaan berkas
  styles/                # Tema dan stylesheet menurut bagian tampilan
  lib/                   # Klasifikasi, pemantauan analisis, utilitas
  api.ts                 # Klien HTTP
  types/                 # Model data
docs/
  CLEANUP.md             # Catatan perapihan dan hasil pemeriksaan
```

Modul dinamai menurut fungsinya. Riwayat perubahan disimpan di Git.
Nomor versi API, format cache, dan hasil analisis tetap dapat digunakan untuk
menjaga kompatibilitas data. Import Python di dalam handler/OCR sebagian sengaja
ditunda agar dependensi berat tidak dimuat saat aplikasi mulai.

## Mengubah warna

Edit `frontend/src/styles/theme.css`. Variabel utama meliputi
`--accent`, `--accent-light`, `--accent-strong`, `--accent-pale`,
`--accent-rgb`, dan warna permukaan/border aksen.
Sidebar serta tombol menggunakan variabel tersebut.
Warna status evaluasi berada pada stylesheet komponen terkait.

```bash
cd frontend
npm run build
```

Jika Node.js belum berada di PATH, aktifkan instalasi Node.js Anda terlebih dahulu.
`styles/index.css` mempertahankan urutan stylesheet; urutan tersebut penting
untuk aturan responsif dan penimpaan gaya. Metadata warna browser pada
`frontend/index.html` perlu disesuaikan jika tema diganti.

## Pemeriksaan

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python backend/scripts/run_checks.py
backend/.venv/bin/ruff check backend/app backend/engine/src
backend/.venv/bin/ruff format --check backend/app backend/engine/src

cd frontend
npm test
npm run test:static
npm run build
```

Runner backend memakai penyimpanan sementara, token pengujian, dan proses
terpisah untuk setiap modul pengujian OCR. Ia tetap mengembalikan kegagalan
untuk regresi lama yang belum terselesaikan; lihat `docs/CLEANUP.md`.
Pengujian dengan dokumen lokal yang tidak tersedia dilewati secara eksplisit.

Aturan klasifikasi nama berkas berasal dari
`backend/app/classification_rules.json`, digunakan bersama oleh Python dan
frontend. Setelah aturan berubah, bangun ulang frontend dan mulai ulang backend.

## Operasional

- Satu worker Uvicorn mengoordinasikan pekerjaan analisis dan pool OCR.
- Metadata/hasil tersimpan di SQLite; berkas unggahan tersimpan privat.
- Pekerjaan yang terputus saat restart ditandai gagal, bukan dilanjutkan otomatis.
- Sesi browser menyimpan ID permohonan di sessionStorage. Berkas yang belum
  dikirim masih berada dalam memori browser.
- Klien dapat membaca token dari parameter URL atau localStorage.
  Endpoint selain health memerlukan token, kecuali mode pengembangan lokal.
- Pemisahan pemilik permohonan melalui gateway tersedia ketika
  `BAPETEN_VPN_MULTIUSER=1`; ini bukan sistem SSO lengkap.
- OCR membutuhkan dependensi sistem/model yang sesuai. Gunakan
  `backend/scripts/doctor_ocr.py` untuk diagnosis.
- `frontend/dist`, lingkungan virtual, log, cache, dan data unggahan merupakan
  hasil build/runtime dan tidak dimasukkan ke Git.
