import type { DocumentCategory } from '../types/models';

export const CATEGORIES: DocumentCategory[] = [
  {
    id: 'formulir',
    name: 'Formulir Permohonan',
    icon: 'file',
    description: 'Dokumen acuan utama untuk proses matching',
  },
  {
    id: 'proteksi',
    name: 'Dokumen Program Proteksi',
    icon: 'shield',
    description: 'Identitas fasilitas, personel, alat, pengesahan',
  },
  {
    id: 'manajemen',
    name: 'Dokumen Sistem Manajemen',
    icon: 'settings',
    description: 'Identitas fasilitas dan pengesahan',
  },
  {
    id: 'personel',
    name: 'Dokumen Personel',
    icon: 'users',
    description: 'SIB, sertifikat kompetensi PPR, pelatihan, dan penugasan',
    requiresSubtype: true,
  },
  {
    id: 'spesifikasi',
    name: 'Spesifikasi Alat',
    icon: 'box',
    description: 'Merk, tipe, dan data spesifikasi alat',
  },
  {
    id: 'label',
    name: 'Label Unit dan Tabung',
    icon: 'scan',
    description: 'Label fisik unit pesawat dan tabung',
  },
  {
    id: 'impor',
    name: 'Persetujuan Impor',
    icon: 'filecheck',
    description: 'Identitas alat dalam dokumen impor',
  },
  {
    id: 'fungsi',
    name: 'Uji Fungsi / Acceptance Test',
    icon: 'flask',
    description: 'Uploader gabungan, matching identitas saja',
  },
  {
    id: 'mutu',
    name: 'Sertifikat Uji Mutu',
    icon: 'filecheck',
    description: 'Identitas alat, QC pabrikan, pengesahan',
  },
  {
    id: 'kalibrasi',
    name: 'Sertifikat Kalibrasi',
    icon: 'gauge',
    description: 'Data alat yang sesuai formulir (kondisional)',
  },
  {
    id: 'paparan',
    name: 'Uji Paparan Radiasi',
    icon: 'radiation',
    description: 'Fasilitas, alamat, peralatan, pengesahan',
  },
  {
    id: 'kebocoran',
    name: 'Uji Kebocoran Tabung',
    icon: 'activity',
    description: 'Fasilitas, alamat, peralatan, pengesahan',
  },
];

export const categoryById = (id: string): DocumentCategory | undefined =>
  CATEGORIES.find((cat) => cat.id === id);
