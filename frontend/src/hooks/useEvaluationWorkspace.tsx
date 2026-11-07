import type { DragEvent } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AnalysisJob, AnalysisResult } from '../api';
import {
  analyze,
  deleteFile,
  fetchPreviewFile,
  jobResults,
  jobStatus,
  latestJob,
  listFiles,
  newApplication,
  updateFileCategory,
  uploadFile,
} from '../api';
import { categoryById } from '../data/categories';
import { monitorAnalysis, retryRead } from '../lib/analysisMonitor';
import { matchingTotals, sortMatchingSections } from '../lib/matching';
import { rowMatchesFilter } from '../lib/matchingDisplay';
import { analysisBlocker } from '../lib/uploadState';
import type { CategoryId, MatchRow, MatchSection, UploadItem } from '../types/models';
import { PERSONNEL_TYPES } from '../types/models';
import { Filter, PageId, Toast } from '../types/workspace';
import { useUploadIntake } from './useUploadIntake';

export function useEvaluationWorkspace() {
  const [active, setActive] = useState<PageId>('ringkasan');
  const [applicationId, setApplicationId] = useState<string | null>(
    sessionStorage.getItem('bapeten_application_id'),
  );
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [working, setWorking] = useState(Boolean(applicationId));
  const [reconnecting, setReconnecting] = useState(false);
  const submitting = useRef(false);
  const monitorController = useRef<AbortController | null>(null);
  useEffect(() => () => monitorController.current?.abort(), []);
  const [savingCategory, setSavingCategory] = useState(false);
  const categorySaveLock = useRef(false);
  const [syncCount, setSyncCount] = useState(0);
  const [syncTotal, setSyncTotal] = useState(0);
  const [analysisStage, setAnalysisStage] = useState<'restoring' | 'preparing' | 'uploading' | 'processing'>(
    'restoring',
  );
  const [backendError, setBackendError] = useState('');
  const displayForm = result?.form_reference ?? null;
  const displaySections = useMemo(() => sortMatchingSections(result?.matching_sections ?? []), [result]);
  const [mobileNav, setMobileNav] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [showUnclassified, setShowUnclassified] = useState(false);
  const [manualCategory, setManualCategory] = useState('');
  const [uploadSearch, setUploadSearch] = useState('');
  const [dragged, setDragged] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('ALL');
  const [selectedDetail, setSelectedDetail] = useState<{ row: MatchRow; section: MatchSection } | null>(null);
  const [docSearch, setDocSearch] = useState('');
  const [formOpen, setFormOpen] = useState({ facility: true, personnel: true, equipment: true });
  const formNeedsReview = useMemo(() => {
    const missing = (value?: string) => !value?.trim() || ['—', '-'].includes(value.trim());
    return {
      facility: Boolean(displayForm && (missing(displayForm.facility) || missing(displayForm.address))),
      personnel: Boolean(
        displayForm &&
        (!displayForm.personnel.length ||
          displayForm.personnel.some((p) => missing(p.name) || missing(p.role))),
      ),
      equipment: Boolean(
        displayForm &&
        (!displayForm.equipment.length ||
          displayForm.equipment.some((e) =>
            [
              e.merk_unit,
              e.tipe_unit,
              e.nomor_seri_unit,
              e.merk_tabung,
              e.tipe_tabung,
              e.nomor_seri_tabung,
            ].some(missing),
          )),
      ),
    };
  }, [displayForm]);
  useEffect(() => {
    setFormOpen({ facility: true, personnel: true, equipment: true });
  }, [formNeedsReview]);
  const toggleForm = (section: keyof typeof formOpen) =>
    setFormOpen((previous) => ({ ...previous, [section]: !previous[section] }));
  const reviewBadge = (needsReview: boolean) =>
    needsReview ? <span className="form-review-badge">Perlu diperiksa</span> : undefined;
  const globalInput = useRef<HTMLInputElement>(null);
  const resetDialog = useRef<HTMLDialogElement>(null);
  const manualDialog = useRef<HTMLDialogElement>(null);
  const manualInput = useRef<HTMLInputElement>(null);
  const toastRef = useRef<number | null>(null);
  const totals = useMemo(() => matchingTotals(displaySections), [displaySections]);
  const filterTotals = useMemo(
    () =>
      matchingTotals(
        displaySections.map((section) => ({
          ...section,
          rows: section.rows.filter((row) => rowMatchesFilter(row, 'ALL', query)),
        })),
      ),
    [displaySections, query],
  );
  // Hide entire document panels that have no rows for the selected filter.
  const visibleMatchingSections = useMemo(
    () =>
      displaySections.filter((section) => section.rows.some((row) => rowMatchesFilter(row, filter, query))),
    [displaySections, filter, query],
  );
  const categoryCount = useMemo(
    () => new Set(items.filter((f) => f.category !== 'unknown').map((f) => f.category)).size,
    [items],
  );
  const analysisMessage = analysisBlocker(items);
  const unclassifiedCount = items.filter((item) => item.category === 'unknown' && !item.isClassifying).length;
  const recognizingCount = items.filter((item) => item.isClassifying).length;
  const reviewItems = useMemo(() => {
    const unclassified = items.filter((item) => item.category === 'unknown' && !item.isClassifying);
    const visible =
      showUnclassified && unclassified.length
        ? unclassified
        : [
            ...unclassified,
            ...items.filter((item) => item.isClassifying),
            ...items.filter((item) => item.category !== 'unknown' && !item.isClassifying),
          ];
    const search = uploadSearch.trim().toLowerCase();
    return visible.filter((item) =>
      `${item.name} ${categoryById(item.category)?.name ?? ''} ${item.subtype ?? ''}`
        .toLowerCase()
        .includes(search),
    );
  }, [items, showUnclassified, uploadSearch]);
  useEffect(() => {
    if (unclassifiedCount === 0) setShowUnclassified(false);
  }, [unclassifiedCount]);
  const formCount = useMemo(() => items.filter((f) => f.category === 'formulir').length, [items]);
  const progressTitle =
    analysisStage === 'restoring' ? 'Memulihkan sesi evaluasi…' : 'Analisis sedang berjalan…';
  const progressMessage = reconnecting
    ? 'Koneksi terputus. Mencoba tersambung kembali…'
    : analysisStage === 'restoring'
      ? 'Memeriksa dokumen dan status analisis terakhir.'
      : analysisStage === 'preparing'
        ? 'Menyiapkan pengiriman dokumen…'
        : analysisStage === 'uploading'
          ? `Mengirim dokumen ${syncCount} dari ${syncTotal}…`
          : job?.status === 'completed'
            ? 'Menyiapkan hasil matching…'
            : job?.message || 'Memulai analisis dokumen…';
  const analysisProgress = job ? Math.max(0, Math.min(100, job.progress)) : undefined;

  useEffect(
    () => () => {
      if (toastRef.current !== null) window.clearTimeout(toastRef.current);
    },
    [],
  );
  const announce = useCallback((tone: 'success' | 'warning' | 'info', message: string) => {
    setToast({ tone, message });
    if (toastRef.current !== null) window.clearTimeout(toastRef.current);
    toastRef.current = window.setTimeout(() => setToast(null), 4600);
  }, []);

  const goTo = useCallback((id: PageId) => {
    setActive(id);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const followAnalysis = useCallback(
    (aid: string, initial: AnalysisJob, signal: AbortSignal) =>
      monitorAnalysis(initial, {
        signal,
        readJob: () => jobStatus(aid, initial.id, signal),
        readResult: () => jobResults(aid, initial.id, signal),
        onJob: setJob,
        onConnection: setReconnecting,
      }),
    [],
  );

  useEffect(() => {
    if (!applicationId || submitting.current) return;
    const aid = applicationId;
    const controller = new AbortController();
    monitorController.current = controller;
    const { signal } = controller;
    setWorking(true);
    setAnalysisStage('restoring');
    setBackendError('');
    goTo('matching');
    const read = <T,>(fn: () => Promise<T>) => retryRead(fn, signal, setReconnecting);
    void (async () => {
      const r = await read(() => listFiles(aid, signal));
      setItems((old) => {
        const ids = new Set(old.map((f) => f.serverId));
        return [
          ...old,
          ...r.documents
            .filter((d) => !ids.has(d.id))
            .map((d) => ({
              id: d.id,
              serverId: d.id,
              name: d.filename,
              size: d.size,
              category: d.category,
              subtype: d.subtype,
              sha256: d.sha256,
              addedAt: new Date(d.uploaded * 1000).toISOString(),
            })),
        ];
      });
      const { job: latest } = await read(() => latestJob(aid, signal));
      if (!latest) return;
      setAnalysisStage('processing');
      setResult(null);
      const analyzed = await followAnalysis(aid, latest, signal).catch((error) => {
        // An already completed result can be invalidated by a category correction.
        if (latest.status === 'completed' && error?.status === 404) return null;
        throw error;
      });
      if (!analyzed) return;
      const fingerprint = (pairs: string[][]) =>
        JSON.stringify([...pairs].sort((a, b) => a[0].localeCompare(b[0])));
      if (
        fingerprint(analyzed.document_fingerprint) === fingerprint(r.documents.map((d) => [d.id, d.sha256]))
      ) {
        setResult(analyzed);
      }
    })()
      .catch((error) => {
        if (signal.aborted) return;
        setBackendError(error instanceof Error ? error.message : 'Gagal memulihkan status analisis');
      })
      .finally(() => {
        if (!signal.aborted) {
          setWorking(false);
          setReconnecting(false);
        }
      });
    return () => controller.abort();
  }, [applicationId, followAnalysis, goTo]);

  const runAnalysis = async () => {
    if (working || submitting.current || categorySaveLock.current) return;
    if (analysisMessage) {
      announce('warning', analysisMessage);
      goTo('upload');
      return;
    }
    submitting.current = true;
    monitorController.current?.abort();
    const controller = new AbortController();
    monitorController.current = controller;
    setBackendError('');
    setWorking(true);
    setResult(null);
    setJob(null);
    setReconnecting(false);
    setAnalysisStage('preparing');
    setSyncCount(0);
    setSyncTotal(0);
    setToast(null);
    setQuery('');
    setFilter('ALL');
    setSelectedDetail(null);
    goTo('matching');
    try {
      let aid = applicationId;
      if (!aid) {
        const data = await newApplication();
        aid = data.application_id;
        setApplicationId(aid);
        sessionStorage.setItem('bapeten_application_id', aid);
      }
      const pending = items.filter((x) => !x.serverId);
      setSyncTotal(pending.length);
      for (let i = 0; i < pending.length; i++) {
        const item = pending[i];
        if (item.category === 'unknown')
          throw new Error('Pilih kategori untuk semua dokumen terlebih dahulu.');
        if (!item.file) throw new Error('File lokal telah hilang. Tambahkan ulang dokumen.');
        setSyncCount(i + 1);
        setAnalysisStage('uploading');
        const uploaded = await uploadFile(aid, item.category, item.file, item.subtype);
        setItems((old) =>
          old.map((x) =>
            x.id === item.id ? { ...x, serverId: uploaded.document.id, sha256: uploaded.document.sha256 } : x,
          ),
        );
      }
      setAnalysisStage('processing');
      setSyncCount(0);
      const started = await analyze(aid);
      const initial: AnalysisJob = {
        id: started.job_id,
        status: 'queued',
        progress: 0,
        message: 'Menunggu antrean analisis',
        error: null,
      };
      const analyzed = await followAnalysis(aid, initial, controller.signal);
      setResult(analyzed);
      if (analyzed.errors?.length)
        announce(
          'warning',
          `${analyzed.errors.length} dokumen gagal dianalisis. Lihat rincian pada halaman Hasil Matching.`,
        );
      else announce('success', 'Analisis selesai. Hasil verifikasi dokumen berhasil diperbarui.');
    } catch (e) {
      if (controller.signal.aborted) return;
      const message = e instanceof Error ? e.message : 'Gagal menjalankan analisis';
      setBackendError(message);
      announce('warning', message);
    } finally {
      submitting.current = false;
      if (!controller.signal.aborted) {
        setWorking(false);
        setSyncCount(0);
        setReconnecting(false);
      }
    }
  };
  const resetApplication = () => {
    if (working || categorySaveLock.current) return;
    resetDialog.current?.close();
    sessionStorage.removeItem('bapeten_application_id');
    setApplicationId(null);
    setItems([]);
    setResult(null);
    setJob(null);
    setBackendError('');
    setActive('upload');
    setQuery('');
    setFilter('ALL');
    setDocSearch('');
    setUploadSearch('');
    setManualCategory('');
    setShowUnclassified(false);
    setSelectedDetail(null);
    setToast(null);
  };
  const { addFiles, handleBatchFiles } = useUploadIntake({
    items,
    working,
    categorySaveLock,
    setItems,
    setResult,
    announce,
  });

  const updateItemCategory = async (id: string, category: CategoryId, subtype?: string) => {
    if (working || categorySaveLock.current) return;
    const item = items.find((it) => it.id === id);
    if (!item) return;
    const actualSubtype = categoryById(category)?.requiresSubtype
      ? subtype || item.subtype || PERSONNEL_TYPES[0]
      : undefined;
    categorySaveLock.current = true;
    setSavingCategory(true);
    try {
      if (item.serverId) {
        if (!applicationId) throw new Error('Permohonan tidak tersedia. Muat ulang halaman.');
        await updateFileCategory(applicationId, item.serverId, category, actualSubtype);
      }
      setItems((old) =>
        old.map((it) =>
          it.id === id
            ? {
                ...it,
                category,
                subtype: actualSubtype,
                isClassifying: false,
                detectedLayer: undefined,
                detectionReason: 'Dipilih manual oleh evaluator',
              }
            : it,
        ),
      );
      setResult(null);
    } catch (error) {
      announce(
        'warning',
        `Kategori gagal disimpan: ${error instanceof Error ? error.message : String(error)}`,
      );
    } finally {
      categorySaveLock.current = false;
      setSavingCategory(false);
    }
  };

  const clearAllFiles = () => {
    if (working || categorySaveLock.current || !items.length) return;
    if (!window.confirm(`Hapus semua ${items.length} dokumen dari permohonan ini?`)) return;
    items.forEach((item) => {
      if (item.serverId && applicationId) {
        deleteFile(applicationId, item.serverId).catch(() => {});
      }
    });
    setItems([]);
    setResult(null);
    announce('info', 'Semua berkas dihapus dari permohonan.');
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragged(false);
    handleBatchFiles(event.dataTransfer.files);
  };
  const removeFile = (id: string) => {
    const item = items.find((x) => x.id === id);
    if (!item || working || categorySaveLock.current) return;
    if (item.serverId && applicationId)
      deleteFile(applicationId, item.serverId).catch((e) => announce('warning', String(e)));
    setItems((prev) => prev.filter((x) => x.id !== id));
    setResult(null);
    announce('info', 'File dihapus dari daftar. Analisis perlu dijalankan ulang.');
  };
  const openEvidence = (documentId: string, page?: number) => {
    if (!applicationId) return;
    const win = window.open('about:blank', '_blank');
    fetchPreviewFile(applicationId, documentId)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        if (win) win.location.href = url + (page ? `#page=${page}` : '');
        else window.open(url + (page ? `#page=${page}` : ''), '_blank');
        window.setTimeout(() => URL.revokeObjectURL(url), 120000);
      })
      .catch((e) => {
        win?.close();
        announce('warning', String(e));
      });
  };
  const viewFile = (file?: File, serverId?: string) => {
    if (!file) {
      if (!applicationId || !serverId) {
        announce('warning', 'File belum tersedia di server.');
        return;
      }
      const win = window.open('about:blank', '_blank');
      fetchPreviewFile(applicationId, serverId)
        .then((blob) => {
          const uri = URL.createObjectURL(blob);
          if (win) win.location.href = uri;
          else window.open(uri, '_blank');
          window.setTimeout(() => URL.revokeObjectURL(uri), 120000);
        })
        .catch((e) => {
          if (win) win.close();
          announce('warning', String(e));
        });
      return;
    }
    const url = URL.createObjectURL(file);
    const win = window.open('about:blank', '_blank');
    if (win) {
      win.opener = null;
      win.location.href = url;
    }
    if (!win) announce('warning', 'Popup diblokir browser. Izinkan popup untuk membuka dokumen.');
    window.setTimeout(() => URL.revokeObjectURL(url), 120000);
  };
  const visibleDocuments = items.filter((item) =>
    `${item.name} ${categoryById(item.category)?.name ?? 'Perlu Pilih Kategori'} ${item.subtype || ''}`
      .toLowerCase()
      .includes(docSearch.toLowerCase()),
  );

  return {
    active,
    goTo,
    mobileNav,
    setMobileNav,
    working,
    backendError,
    result,
    savingCategory,
    resetDialog,
    items,
    categoryCount,
    totals,
    dragged,
    setDragged,
    onDrop,
    globalInput,
    setManualCategory,
    manualDialog,
    handleBatchFiles,
    formCount,
    recognizingCount,
    clearAllFiles,
    showUnclassified,
    setShowUnclassified,
    unclassifiedCount,
    uploadSearch,
    setUploadSearch,
    reviewItems,
    updateItemCategory,
    viewFile,
    removeFile,
    analysisMessage,
    progressMessage,
    runAnalysis,
    syncCount,
    job,
    displayForm,
    formNeedsReview,
    formOpen,
    toggleForm,
    reviewBadge,
    query,
    setQuery,
    filter,
    setFilter,
    filterTotals,
    progressTitle,
    analysisProgress,
    analysisStage,
    visibleMatchingSections,
    setSelectedDetail,
    docSearch,
    setDocSearch,
    visibleDocuments,
    manualCategory,
    manualInput,
    addFiles,
    resetApplication,
    selectedDetail,
    openEvidence,
    announce,
    toast,
    setToast,
  };
}

export type EvaluationWorkspace = ReturnType<typeof useEvaluationWorkspace>;
