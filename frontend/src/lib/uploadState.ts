import { PERSONNEL_TYPES } from '../types/models.ts';
import type { UploadItem } from '../types/models';
import type { ClassificationResult } from './classifier';

export function applyClassification(item: UploadItem, result: ClassificationResult): UploadItem {
  // A manual choice finishes classification; late automatic responses cannot replace it.
  if (!item.isClassifying) return item;
  if (result.category === 'personel' && !(PERSONNEL_TYPES as readonly string[]).includes(result.subtype ?? '')) {
    return { ...item, category: 'unknown', subtype: undefined, isClassifying: false,
      detectionReason: 'Kategori personel tidak lagi didukung. Unggah ulang atau pilih kategori.' };
  }
  return {
    ...item,
    category: result.category,
    subtype: result.subtype,
    detectedLayer: result.layer,
    detectionReason: result.reason,
    isClassifying: false,
  };
}

export function classificationBlocker(items: UploadItem[]): string | null {
  const pending = items.filter((item) => item.isClassifying).length;
  if (pending)
    return `Sedang mengenali ${pending} dokumen. Tunggu hingga selesai atau pilih kategorinya secara manual.`;
  const unknown = items.filter((item) => item.category === 'unknown' ||
    (item.category === 'personel' && !(PERSONNEL_TYPES as readonly string[]).includes(item.subtype ?? ''))).length;
  if (unknown)
    return `${unknown} dokumen berstatus Perlu Pilih Kategori. Pilih kategori sebelum memulai analisis.`;
  return null;
}

export function analysisBlocker(items: UploadItem[]): string | null {
  if (!items.length) return 'Unggah 1 Formulir Permohonan dan minimal 1 dokumen pendukung.';
  const classification = classificationBlocker(items);
  if (classification) return classification;
  const forms = items.filter((item) => item.category === 'formulir').length;
  if (!forms) return 'Tambahkan 1 Formulir Permohonan sebagai acuan.';
  if (forms > 1) return 'Gunakan tepat 1 Formulir Permohonan sebagai acuan.';
  if (items.length < 2) return 'Tambahkan minimal 1 dokumen pendukung.';
  return null;
}
