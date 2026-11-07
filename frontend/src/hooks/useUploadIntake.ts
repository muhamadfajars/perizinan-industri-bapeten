import { useCallback } from 'react';
import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import type { AnalysisResult } from '../api';
import { categoryById } from '../data/categories';
import { classifyByFilename, classifyFile } from '../lib/classifier';
import { ID, MAX_FILE, SUPPORTED_EXTENSIONS } from '../lib/presentation';
import { applyClassification } from '../lib/uploadState';
import type { CategoryId, UploadItem } from '../types/models';
import type { Toast } from '../types/workspace';

type Options = {
  items: UploadItem[];
  working: boolean;
  categorySaveLock: MutableRefObject<boolean>;
  setItems: Dispatch<SetStateAction<UploadItem[]>>;
  setResult: Dispatch<SetStateAction<AnalysisResult | null>>;
  announce: (tone: NonNullable<Toast>['tone'], message: string) => void;
};

export function useUploadIntake({
  items,
  working,
  categorySaveLock,
  setItems,
  setResult,
  announce,
}: Options) {
  const addFiles = useCallback(
    (category: CategoryId, files: FileList | File[] | null, subtype?: string) => {
      if (working || categorySaveLock.current || !files || !files.length) return;
      const incoming = Array.from(files);
      const valid = incoming.filter(
        (f) =>
          SUPPORTED_EXTENSIONS.has(f.name.split('.').pop()?.toLowerCase() ?? '') &&
          f.size <= MAX_FILE &&
          f.size > 0,
      );
      const invalid = incoming.length - valid.length;
      if (!valid.length) {
        announce('warning', `${invalid} file ditolak. Gunakan PDF/gambar/DOCX, maksimal 40 MB per file.`);
        return;
      }
      if (valid.every((file) => items.some((item) => item.name === file.name && item.size === file.size))) {
        announce(
          'warning',
          'Berkas sudah ada dalam daftar. Ubah kategori melalui daftar dokumen jika diperlukan.',
        );
        return;
      }
      setResult(null);
      setItems((old) => {
        const next = [...old];
        for (const file of valid) {
          const duplicate = next.some((item) => item.name === file.name && item.size === file.size);
          if (!duplicate) {
            next.push({
              id: ID(),
              name: file.name,
              size: file.size,
              category,
              subtype,
              detectedLayer: 1,
              detectionReason: 'Ditambahkan manual ke kategori',
              addedAt: new Date().toISOString(),
              file,
            });
          }
        }
        return next;
      });
      if (invalid)
        announce('warning', `${invalid} file ditolak. Gunakan PDF/gambar/DOCX, maksimal 40 MB per file.`);
      else announce('success', `File ditambahkan untuk kategori ${categoryById(category)?.name}.`);
    },
    [announce, working, items],
  );

  const handleBatchFiles = useCallback(
    async (files: FileList | File[] | null) => {
      if (working || categorySaveLock.current || !files || !files.length) return;
      const incoming = Array.from(files);
      const valid = incoming.filter(
        (f) =>
          SUPPORTED_EXTENSIONS.has(f.name.split('.').pop()?.toLowerCase() ?? '') &&
          f.size <= MAX_FILE &&
          f.size > 0,
      );
      const invalid = incoming.length - valid.length;
      setResult(null);

      const newItems: UploadItem[] = [];
      const pendingLayer2: { item: UploadItem; file: File }[] = [];

      for (const file of valid) {
        const duplicate = [...items, ...newItems].some(
          (item) => item.name === file.name && item.size === file.size,
        );
        if (duplicate) continue;

        const l1 = classifyByFilename(file.name);
        if (l1 && l1.category !== 'unknown') {
          newItems.push({
            id: ID(),
            name: file.name,
            size: file.size,
            category: l1.category,
            subtype: l1.subtype,
            detectedLayer: 1,
            detectionReason: l1.reason,
            isClassifying: false,
            addedAt: new Date().toISOString(),
            file,
          });
        } else {
          const item: UploadItem = {
            id: ID(),
            name: file.name,
            size: file.size,
            category: 'unknown',
            detectedLayer: 0,
            detectionReason: 'Sedang mengenali dokumen…',
            isClassifying: true,
            addedAt: new Date().toISOString(),
            file,
          };
          newItems.push(item);
          pendingLayer2.push({ item, file });
        }
      }

      if (!newItems.length) {
        if (invalid)
          announce('warning', `${invalid} file ditolak. Format tidak didukung atau melebihi 40 MB.`);
        return;
      }

      setItems((old) => [...old, ...newItems]);
      announce(
        invalid ? 'warning' : 'info',
        `${newItems.length} berkas ditambahkan.${invalid ? ` ${invalid} file ditolak karena format atau ukuran tidak sesuai.` : ''}${pendingLayer2.length ? ' Pengenalan isi dokumen sedang berjalan.' : ''}`,
      );

      // Trigger Layer 2 for pending items in background
      for (const { item, file } of pendingLayer2) {
        classifyFile(file)
          .then((res) => {
            setItems((current) =>
              current.map((it) => {
                if (it.id !== item.id) return it;
                return applyClassification(it, res);
              }),
            );
          })
          .catch(() => {
            setItems((current) =>
              current.map((it) =>
                it.id === item.id
                  ? applyClassification(it, {
                      category: 'unknown',
                      layer: 0,
                      confidence: 0,
                      reason: 'Pengenalan gagal. Silakan pilih kategori secara manual.',
                    })
                  : it,
              ),
            );
          });
      }
    },
    [items, announce, working],
  );

  return { addFiles, handleBatchFiles };
}
