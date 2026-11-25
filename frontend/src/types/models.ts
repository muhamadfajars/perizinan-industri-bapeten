export type MatchStatus = 'MATCH' | 'REVIEW' | 'MISMATCH' | 'MISSING' | 'INFO';

export type CategoryId =
  | 'formulir'
  | 'proteksi'
  | 'manajemen'
  | 'personel'
  | 'spesifikasi'
  | 'label'
  | 'impor'
  | 'fungsi'
  | 'mutu'
  | 'kalibrasi'
  | 'paparan'
  | 'kebocoran';

export type DocumentCategory = {
  id: CategoryId;
  name: string;
  description: string;
  icon: string;
  requiresSubtype?: boolean;
};

export type UploadItem = {
  id: string;
  name: string;
  size: number;
  category: CategoryId | 'unknown';
  subtype?: string;
  addedAt: string;
  file?: File;
  serverId?: string;
  sha256?: string;
  detectedLayer?: 1 | 2 | 0;
  detectionReason?: string;
  isClassifying?: boolean;
};

export type MatchRow = {
  id: string;
  field: string;
  expected: string;
  observed: string;
  score: number | null;
  status: MatchStatus;
  page?: number;
  note?: string;
  document_id?: string;
  quote?: string;
  detail?: {
    type: 'approval' | 'maintenance' | 'protection' | 'management' | 'personnel' | 'quality' | 'calibration';
    source_label?: string;
    source_filename?: string;
    topics?: { label: string; found: boolean }[];
    review_required?: boolean;
    review_reason?: string;
    group?: string;
    person_id?: string;
    person_name?: string;
    field_label?: string;
    required?: boolean;
    images?: boolean;
    evidence?: { page: number; quote: string; value?: string; method?: string; has_visual?: boolean }[];
    pages?: number[];
    heading?: string;
    frequencies?: string[];
    parameters?: string[];
    shared_document?: boolean;
    co_owners?: string[];
  } | null;
};

export type MatchSection = {
  id: string;
  category: CategoryId;
  name: string;
  rows: MatchRow[];
  info?: string;
};

export type Person = { name: string; role: string };
export type Equipment = {
  label: string;
  merk_unit: string;
  tipe_unit: string;
  nomor_seri_unit: string;
  merk_tabung: string;
  tipe_tabung: string;
  nomor_seri_tabung: string;
};
export type AdministrationDocument = { document: string; number?: string; date?: string };

export type FormReference = {
  facility: string;
  address: string;
  applicationNumber?: string;
  activityScope?: string;
  institution?: string;
  protectionDocument?: { number?: string; date?: string };
  managementDocument?: { number?: string; date?: string };
  administrationDocuments?: AdministrationDocument[];
  personnel: Person[];
  equipment: Equipment[];
};

export const PERSONNEL_TYPES = [
  'Surat Izin Bekerja (SIB)',
  'Surat Perintah',
  'Sertifikat Kompetensi PPR',
  'Sertifikat Pelatihan',
  'Surat Keterangan Kerja',
  'Surat Penunjukan Tugas',
  'Evaluasi Dosis / Zero Check',
] as const;
