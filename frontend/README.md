# Frontend BAPETEN Industri

Lima halaman: Dashboard, Upload Dokumen, Formulir Permohonan, Hasil Matching,
dan Dokumen. Backend menyimpan unggahan dan hasil; frontend memantau status
analisis dan menampilkan bukti halaman.

## Pengembangan

Gunakan Node.js 24, lalu jalankan:

```bash
npm install
npm run dev
```

Lihat `vite.config.ts` untuk tujuan proxy API. Produksi menggunakan
`npm run build`; FastAPI dapat menyajikan hasil di `dist/`.

## Struktur

- `src/pages/`: tampilan setiap halaman.
- `src/components/`: navigasi, dialog, tabel, pratinjau, dan bukti.
- `src/hooks/useEvaluationWorkspace.tsx`: sesi, pemulihan, dan pengelolaan analisis.
- `src/hooks/useUploadIntake.ts`: validasi berkas serta klasifikasi unggahan.
- `src/lib/`: utilitas dan logika yang dapat diuji terpisah.
- `src/styles/theme.css`: pengaturan warna; urutan stylesheet di `styles/index.css`.
- `src/types/`: kontrak model data.
- `src/api.ts`: komunikasi dengan backend.

## Pemeriksaan

```bash
npm test
npm run test:static
npm run build
npm run format:check
```

ID permohonan disimpan di sessionStorage. Berkas yang belum diunggah tidak
bertahan setelah refresh. Token dapat dibaca dari URL atau localStorage
sesuai integrasi klien yang sudah ada.
