import { PERSONNEL_TYPES } from '../types/models.ts';
import type { CategoryId, ExtraCategory, UploadItem } from '../types/models';
import type { ClassificationResult } from './classifier';

export function normalizeExtraCategories(
  primaryCategory: CategoryId | 'unknown',
  primarySubtype: string | undefined,
  extras?: ReadonlyArray<{ category: CategoryId | string; subtype?: string | null }>,
): ExtraCategory[] {
  if (!extras?.length || primaryCategory === 'formulir' || primaryCategory === 'unknown') return [];
  const seen = new Set<string>([
    `${primaryCategory}:${primaryCategory === 'personel' ? (primarySubtype ?? '').trim() : ''}`,
  ]);
  const out: ExtraCategory[] = [];
  for (const item of extras) {
    const cat = item?.category as CategoryId | undefined;
    if (!cat || cat === 'formulir' || (cat as string) === 'unknown') continue;
    let sub: string | undefined;
    if (cat === 'personel') {
      const rawSub = (item.subtype ?? '').trim();
      if (!(PERSONNEL_TYPES as readonly string[]).includes(rawSub)) continue;
      sub = rawSub;
    }
    const key = `${cat}:${sub ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(sub ? { category: cat, subtype: sub } : { category: cat });
  }
  return out;
}

export function toggleCategorySelection(
  primaryCategory: CategoryId | 'unknown',
  primarySubtype: string | undefined,
  extras: ReadonlyArray<ExtraCategory> | undefined,
  targetCategory: CategoryId,
  targetSubtype?: string,
): { category: CategoryId; subtype?: string; extraCategories: ExtraCategory[] } {
  const cleanTargetSubtype = targetCategory === 'personel' ? targetSubtype : undefined;
  if (targetCategory === 'formulir') {
    return { category: 'formulir', subtype: undefined, extraCategories: [] };
  }
  if (primaryCategory === 'unknown' || primaryCategory === 'formulir') {
    return { category: targetCategory, subtype: cleanTargetSubtype, extraCategories: [] };
  }
  const cleanPrimarySubtype = primaryCategory === 'personel' ? primarySubtype : undefined;
  const normalizedExtras = normalizeExtraCategories(primaryCategory, cleanPrimarySubtype, extras);
  const all: ExtraCategory[] = [
    cleanPrimarySubtype
      ? { category: primaryCategory, subtype: cleanPrimarySubtype }
      : { category: primaryCategory },
    ...normalizedExtras,
  ];
  const existingIdx = all.findIndex(
    (item) =>
      item.category === targetCategory && (item.subtype ?? '') === (cleanTargetSubtype ?? ''),
  );
  if (existingIdx >= 0) {
    if (all.length === 1) {
      return {
        category: all[0].category,
        subtype: all[0].subtype,
        extraCategories: [],
      };
    }
    const remaining = all.filter((_, idx) => idx !== existingIdx);
    return {
      category: remaining[0].category,
      subtype: remaining[0].subtype,
      extraCategories: remaining.slice(1),
    };
  }
  const added: ExtraCategory = cleanTargetSubtype
    ? { category: targetCategory, subtype: cleanTargetSubtype }
    : { category: targetCategory };
  return {
    category: primaryCategory,
    subtype: cleanPrimarySubtype,
    extraCategories: normalizeExtraCategories(primaryCategory, cleanPrimarySubtype, [
      ...normalizedExtras,
      added,
    ]),
  };
}

export function applyClassification(item: UploadItem, result: ClassificationResult): UploadItem {
  // A manual choice finishes classification; late automatic responses cannot replace it.
  if (!item.isClassifying) return item;
  if (result.category === 'personel' && !(PERSONNEL_TYPES as readonly string[]).includes(result.subtype ?? '')) {
    return { ...item, category: 'unknown', subtype: undefined, extraCategories: undefined, isClassifying: false,
      detectionReason: 'Kategori personel tidak lagi didukung. Unggah ulang atau pilih kategori.' };
  }
  const extraCategories = normalizeExtraCategories(
    result.category,
    result.subtype,
    result.extraCategories,
  );
  return {
    ...item,
    category: result.category,
    subtype: result.subtype,
    ...(extraCategories.length ? { extraCategories } : {}),
    detectedLayer: result.layer,
    detectionReason: result.reason,
    isClassifying: false,
  };
}

export function classificationBlocker(items: UploadItem[]): string | null {
  const pending = items.filter((item) => item.isClassifying).length;
  if (pending)
    return `Sedang mengenali ${pending} dokumen. Tunggu hingga selesai atau pilih kategorinya secara manual.`;
  const unknown = items.filter(
    (item) =>
      item.category === 'unknown' ||
      (item.category === 'personel' && !(PERSONNEL_TYPES as readonly string[]).includes(item.subtype ?? '')) ||
      (item.extraCategories ?? []).some(
        (extra) =>
          extra.category === 'personel' && !(PERSONNEL_TYPES as readonly string[]).includes(extra.subtype ?? ''),
      ),
  ).length;
  if (unknown)
    return `${unknown} dokumen berstatus Perlu Pilih Kategori. Pilih kategori sebelum memulai analisis.`;
  return null;
}

export function analysisBlocker(items: UploadItem[]): string | null {
  if (!items.length) return 'Unggah 1 Formulir Permohonan dan minimal 1 dokumen pendukung.';
  const classification = classificationBlocker(items);
  if (classification) return classification;
  if (items.some((item) => item.category === 'formulir' && (item.extraCategories?.length ?? 0) > 0)) {
    return 'Formulir Permohonan tidak dapat digabung dengan kategori lain.';
  }
  const forms = items.filter((item) => item.category === 'formulir').length;
  if (!forms) return 'Tambahkan 1 Formulir Permohonan sebagai acuan.';
  if (forms > 1) return 'Gunakan tepat 1 Formulir Permohonan sebagai acuan.';
  if (items.length < 2) return 'Tambahkan minimal 1 dokumen pendukung.';
  return null;
}
