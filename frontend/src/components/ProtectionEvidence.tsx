import { useMemo, useState, type ReactNode } from 'react';
import { AlertCircle, ArrowUpRight, CheckCircle2, ExternalLink, FileText } from 'lucide-react';
import type { MatchRow } from '../types/models';
import {
  getProtectionTabKey,
  protectionFieldLabel,
  regulationDisplayTitle,
  splitRegulationTitle,
  type ProtectionTabKey,
} from '../lib/protectionDisplay';
import { SourceDocumentViewer } from './SourceDocumentViewer';
import { EvidenceStatus } from './EvidenceStatus';
import { DoseEvidence } from './DoseEvidence';

interface ProtectionTab {
  key: ProtectionTabKey;
  label: string;
}

const PROTECTION_TABS: ProtectionTab[] = [
  { key: 'dasar-hukum', label: 'Dasar Hukum' },
  { key: 'zonasi', label: 'Zonasi Kerja' },
  { key: 'pembatas-dosis', label: 'Pembatas Dosis' },
  { key: 'pengesahan', label: 'Lembar Pengesahan' },
];

function zonasiDescription(row: MatchRow, hasPages: boolean): string {
  if (!hasPages) {
    return 'Belum terdeteksi otomatis — periksa bab pembagian daerah kerja atau lampiran denah pada dokumen sumber.';
  }
  if (row.field.includes('Pengendalian')) {
    return 'Uraian atau denah daerah pengendalian terdeteksi — pastikan pembatasan akses, tanda bahaya radiasi, dan batas area kerja telah sesuai.';
  }
  if (row.field.includes('Pengawasan') || row.field.includes('Supervisi')) {
    return 'Uraian atau denah daerah pengawasan/supervisi terdeteksi — pastikan ketentuan pemantauan paparan dan batas area sekitar telah jelas.';
  }
  return 'Uraian atau denah zonasi daerah kerja terdeteksi — periksa kesesuaian pembagian area pada dokumen sumber.';
}

export function SourceActionButton({
  documentId,
  page,
  pageLabel,
  found,
  hasPages,
  fullPagesTitle,
  onOpen,
  multiPageLabel,
}: {
  documentId?: string;
  page: number;
  pageLabel?: string;
  found: boolean;
  hasPages: boolean;
  fullPagesTitle?: string;
  onOpen: (documentId: string, page?: number) => void;
  multiPageLabel?: string;
}) {
  const displayPage = pageLabel ?? String(page);
  const text = multiPageLabel
    ? multiPageLabel
    : found
      ? `Lihat sumber · Halaman ${displayPage}`
      : hasPages
        ? `Periksa sumber · Halaman ${displayPage}`
        : 'Periksa dokumen sumber';

  if (documentId) {
    return (
      <button
        type="button"
        className="law-source-link"
        title={fullPagesTitle}
        onClick={() => onOpen(documentId, page)}
      >
        <FileText size={13.5} aria-hidden="true" />
        <span>{text}</span>
        <ArrowUpRight size={14} aria-hidden="true" />
      </button>
    );
  }
  if (hasPages) {
    return <span className="law-page-static">Halaman {displayPage}</span>;
  }
  return null;
}

export function LedgerSummary({
  title,
  description,
  foundCount,
  totalCount,
  isComplete,
  footer,
}: {
  title: string;
  description: string;
  foundCount: number;
  totalCount: number;
  isComplete: boolean;
  footer?: ReactNode;
}) {
  return (
    <div
      className={`law-summary ${isComplete ? 'law-summary-complete' : 'law-summary-attention'}`}
      role="status"
    >
      <div className="law-summary-top">
        <span className="law-summary-icon" aria-hidden="true">
          {isComplete ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
        </span>
        <div className="law-summary-copy">
          <div className="law-summary-title-row">
            <strong>{title}</strong>
            {totalCount > 0 && (
              <span className={`law-summary-badge ${isComplete ? 'is-complete' : 'is-attention'}`}>
                {isComplete ? 'Lengkap' : 'Perlu diperiksa'} · {foundCount}/{totalCount}
              </span>
            )}
          </div>
          <p>{description}</p>
        </div>
      </div>
      {footer && <div className="law-summary-footer">{footer}</div>}
    </div>
  );
}

function LawLedgerRow({
  row,
  openEvidence,
}: {
  row: MatchRow;
  openEvidence: (documentId: string, page?: number) => void;
}) {
  const uniquePages = [...new Set(row.detail?.pages ?? [])];
  const hasPages = uniquePages.length > 0;
  const isReview = Boolean(row.detail?.review_required);
  const found = hasPages && !isReview;
  const { code, subject } = splitRegulationTitle(row.field);
  const pageSummary =
    uniquePages.length <= 2
      ? uniquePages.join(', ')
      : `${uniquePages.slice(0, 2).join(', ')} +${uniquePages.length - 2}`;

  return (
    <li className={`law-item ${found ? '' : 'law-item-missing'}`.trim()}>
      <span className={`law-item-icon ${found ? 'is-found' : 'is-missing'}`} aria-hidden="true">
        {found ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
      </span>
      <div className="law-item-body">
        <div className="law-item-head">
          <span className="law-item-code">{code}</span>
          {!found && (
            <span className="law-status-missing">
              {isReview ? 'Perlu diperiksa' : 'Belum ditemukan'}
            </span>
          )}
        </div>
        {subject && <p className="law-item-subject">{subject}</p>}
        {isReview && row.detail?.review_reason && (
          <p className="law-item-reason">{row.detail.review_reason}</p>
        )}
        {(hasPages || row.document_id) && (
          <div className="law-item-actions">
            <SourceActionButton
              documentId={row.document_id}
              page={uniquePages[0] ?? 1}
              pageLabel={pageSummary}
              found={found}
              hasPages={hasPages}
              fullPagesTitle={hasPages ? `Halaman ${uniquePages.join(', ')}` : undefined}
              onOpen={openEvidence}
            />
          </div>
        )}
      </div>
    </li>
  );
}

export function ProtectionInformationCards({
  tabKey,
  rows,
  openEvidence,
}: {
  tabKey: ProtectionTabKey;
  rows: MatchRow[];
  openEvidence: (documentId: string, page: number | undefined, title: string) => void;
}) {
  const requiredLaws = rows.filter((row) => row.detail?.required);
  const missingLaws = requiredLaws.filter((row) => !row.detail?.pages?.length);
  const reviewLaws = requiredLaws.some((row) => row.detail?.review_required);
  const openRow = (row: MatchRow) => (documentId: string, page?: number) =>
    openEvidence(
      documentId,
      page,
      row.detail?.group === 'Dasar hukum' ? regulationDisplayTitle(row.field) : protectionFieldLabel(row),
    );

  if (tabKey === 'dasar-hukum') {
    const foundRequiredCount = requiredLaws.length - missingLaws.length;
    const otherLaws = rows.filter((row) => !row.detail?.required);
    const isComplete = !reviewLaws && missingLaws.length === 0;

    return (
      <div className="law-ledger">
        <LedgerSummary
          title={
            isComplete
              ? 'Seluruh dasar hukum wajib ditemukan'
              : `${foundRequiredCount} dari ${requiredLaws.length} dasar hukum wajib ditemukan`
          }
          description={
            reviewLaws
              ? 'Sebagian referensi belum terbaca lengkap; periksa halaman sumber.'
              : missingLaws.length > 0
                ? 'Periksa peraturan berlabel “Belum ditemukan” pada dokumen sumber.'
                : 'Rujukan peraturan perundang-undangan tercantum lengkap pada bagian referensi.'
          }
          foundCount={foundRequiredCount}
          totalCount={requiredLaws.length}
          isComplete={isComplete}
        />

        <div className="law-group">
          <div className="law-group-header">
            <h4 className="law-group-title">Dasar Hukum Wajib</h4>
            <span className="law-group-count">{requiredLaws.length} peraturan</span>
          </div>
          <ul className="law-list">
            {requiredLaws.map((row) => (
              <LawLedgerRow key={row.id} row={row} openEvidence={openRow(row)} />
            ))}
          </ul>
        </div>

        <div className="law-group">
          <div className="law-group-header">
            <h4 className="law-group-title">Dasar Hukum Lainnya</h4>
            {otherLaws.length > 0 && (
              <span className="law-group-count">{otherLaws.length} terdeteksi</span>
            )}
          </div>
          {otherLaws.length > 0 ? (
            <ul className="law-list">
              {otherLaws.map((row) => (
                <LawLedgerRow key={row.id} row={row} openEvidence={openRow(row)} />
              ))}
            </ul>
          ) : (
            <p className="law-empty-state">
              Tidak ada peraturan tambahan lain yang tercantum pada bagian referensi.
            </p>
          )}
        </div>
      </div>
    );
  }

  if (tabKey === 'zonasi') {
    const foundCount = rows.filter(
      (row) => (row.detail?.pages?.length ?? 0) > 0 && !row.detail?.review_required,
    ).length;
    const hasReview =
      foundCount < rows.length || rows.some((row) => Boolean(row.detail?.review_required));
    const isComplete = rows.length > 0 && !hasReview;

    return (
      <div className="law-ledger">
        <LedgerSummary
          title={
            isComplete
              ? 'Seluruh zonasi kerja ditemukan'
              : `${foundCount} dari ${rows.length} zonasi kerja ditemukan`
          }
          description="Periksa uraian zonasi kerja radiasi dan lampiran denah pada dokumen sumber."
          foundCount={foundCount}
          totalCount={rows.length}
          isComplete={isComplete}
        />

        <div className="law-group">
          <div className="law-group-header">
            <h4 className="law-group-title">Zonasi Daerah Kerja</h4>
            <span className="law-group-count">{rows.length} daerah</span>
          </div>
          <ul className="law-list">
            {rows.map((row) => {
              const uniquePages = [...new Set(row.detail?.pages ?? [])];
              const primaryPage = uniquePages[0];
              const hasPages = uniquePages.length > 0;
              const isReview = Boolean(row.detail?.review_required);
              const found = hasPages && !isReview;
              const openZone = openRow(row);

              return (
                <li key={row.id} className={`law-item ${found ? '' : 'law-item-missing'}`.trim()}>
                  <span
                    className={`law-item-icon ${found ? 'is-found' : 'is-missing'}`}
                    aria-hidden="true"
                  >
                    {found ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
                  </span>
                  <div className="law-item-body">
                    <div className="law-item-head">
                      <span className="law-item-code">{protectionFieldLabel(row)}</span>
                      {!found && (
                        <span className="law-status-missing">
                          {isReview ? 'Perlu diperiksa' : 'Belum ditemukan'}
                        </span>
                      )}
                    </div>
                    {isReview && row.detail?.review_reason ? (
                      <p className="law-item-reason">{row.detail.review_reason}</p>
                    ) : (
                      <p className="law-item-subject">{zonasiDescription(row, hasPages)}</p>
                    )}
                    {(hasPages || row.document_id) && (
                      <div className="law-item-actions">
                        <SourceActionButton
                          documentId={row.document_id}
                          page={primaryPage ?? 1}
                          found={found}
                          hasPages={hasPages}
                          onOpen={openZone}
                        />
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    );
  }

  if (tabKey === 'pembatas-dosis') {
    return rows.length > 0 ? (
      <>
        {rows.map((row) => (
          <DoseEvidence key={row.id} row={row} openEvidence={openRow(row)} />
        ))}
      </>
    ) : (
      <p className="law-empty-state">Data pembatas dosis belum tersedia.</p>
    );
  }

  if (tabKey === 'pengesahan') {
    return (
      <div className="law-ledger">
        <div className="law-group">
          <div className="law-group-header">
            <h4 className="law-group-title">Pengesahan Dokumen</h4>
          </div>
          {rows.length > 0 ? (
            <ul className="law-list">
              {rows.map((row) => {
                const uniquePages = [...new Set(row.detail?.pages ?? [])];
                const hasPages = uniquePages.length > 0;
                const isReview = Boolean(row.detail?.review_required);
                const found = hasPages && !isReview;
                const pageSummary =
                  uniquePages.length <= 2
                    ? uniquePages.join(', ')
                    : `${uniquePages.slice(0, 2).join(', ')} +${uniquePages.length - 2}`;
                const openApproval = openRow(row);

                return (
                  <li key={row.id} className={`law-item ${found ? '' : 'law-item-missing'}`.trim()}>
                    <span
                      className={`law-item-icon ${found ? 'is-found' : 'is-missing'}`}
                      aria-hidden="true"
                    >
                      {found ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
                    </span>
                    <div className="law-item-body">
                      <div className="law-item-head">
                        <span className="law-item-code">Pengesahan</span>
                        {!found && (
                          <span className="law-status-missing">
                            {isReview ? 'Perlu diperiksa' : 'Belum ditemukan'}
                          </span>
                        )}
                      </div>
                      <p className="law-item-subject">
                        {hasPages
                          ? 'Halaman pengesahan ditemukan — periksa keberadaan tanda tangan pimpinan atau penanggung jawab pada dokumen sumber.'
                          : 'Halaman pengesahan belum ditemukan otomatis; periksa dokumen sumber.'}
                      </p>
                      {isReview && row.detail?.review_reason && (
                        <p className="law-item-reason">{row.detail.review_reason}</p>
                      )}
                      {(hasPages || row.document_id) && (
                        <div className="law-item-actions">
                          <SourceActionButton
                            documentId={row.document_id}
                            page={uniquePages[0] ?? 1}
                            pageLabel={pageSummary}
                            found={found}
                            hasPages={hasPages}
                            fullPagesTitle={hasPages ? `Halaman ${uniquePages.join(', ')}` : undefined}
                            onOpen={openApproval}
                          />
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="law-empty-state">Informasi lembar pengesahan belum tersedia.</p>
          )}
        </div>
      </div>
    );
  }

  return rows.length > 0 ? (
    <>
      {rows.map((row) => (
        <ProtectionEvidence key={row.id} row={row} compact openEvidence={openRow(row)} />
      ))}
    </>
  ) : (
    <p className="protection-tab-empty">Tidak ada item pada kategori ini.</p>
  );
}

export function ProtectionInformationSection({
  rows,
  openEvidence,
  loadSourceDocument,
}: {
  rows: MatchRow[];
  loadSourceDocument: (documentId: string) => Promise<Blob>;
  openEvidence: (documentId: string, page?: number) => void;
}) {
  const [source, setSource] = useState<{ documentId: string; page?: number; title: string } | null>(null);
  const [activeTab, setActiveTab] = useState<ProtectionTabKey>('dasar-hukum');

  const rowsByTab = useMemo(() => {
    const map = new Map<ProtectionTabKey, MatchRow[]>([
      ['dasar-hukum', []],
      ['zonasi', []],
      ['pembatas-dosis', []],
      ['pengesahan', []],
    ]);
    for (const r of rows) {
      const key = getProtectionTabKey(r);
      map.get(key)?.push(r);
    }
    return map;
  }, [rows]);

  const effectiveActiveTab = useMemo(() => {
    if ((rowsByTab.get(activeTab)?.length ?? 0) > 0) return activeTab;
    const firstNonEmpty = PROTECTION_TABS.find((t) => (rowsByTab.get(t.key)?.length ?? 0) > 0);
    return firstNonEmpty ? firstNonEmpty.key : activeTab;
  }, [activeTab, rowsByTab]);

  const activeRows = rowsByTab.get(effectiveActiveTab) ?? [];

  return (
    <section className="protection-information" aria-label="Informasi Program Proteksi">
      <div className="protection-info-header">
        <h3>Informasi Pendukung Program Proteksi</h3>
      </div>

      <div className="protection-tabs-bar" role="tablist">
        {PROTECTION_TABS.map((tab) => {
          const isActive = effectiveActiveTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`protection-tab-btn ${isActive ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      <div className="protection-tab-panel" role="tabpanel">
        <ProtectionInformationCards
          tabKey={effectiveActiveTab}
          rows={activeRows}
          openEvidence={(documentId, page, title) => setSource({ documentId, page, title })}
        />
      </div>
      {source && (
        <SourceDocumentViewer
          documentId={source.documentId}
          page={source.page}
          title={source.title}
          loadDocument={loadSourceDocument}
          openExternal={openEvidence}
          close={() => setSource(null)}
        />
      )}
    </section>
  );
}

export function ProtectionEvidence({
  row,
  compact = false,
  openEvidence,
}: {
  row: MatchRow;
  compact?: boolean;
  openEvidence: (documentId: string, page?: number) => void;
}) {
  const uniquePages = [...new Set(row.detail?.pages ?? [])];
  const page = uniquePages[0];
  const law = row.detail?.group === 'Dasar hukum';
  const dose = row.field === 'Pembatas Dosis';
  if (compact && dose) return <DoseEvidence key={row.id} row={row} openEvidence={openEvidence} />;
  return (
    <article className={`protection-evidence${compact ? ' protection-evidence-compact' : ''}`}>
      <div className="protection-evidence-heading">
        <h4>{compact && law ? regulationDisplayTitle(row.field) : protectionFieldLabel(row)}</h4>
      </div>
      {compact && (
        <EvidenceStatus
          found={uniquePages.length > 0}
          review={row.detail?.review_required}
          foundLabel={row.detail?.group === 'Pengesahan' ? 'Halaman pengesahan ditemukan' : 'Ditemukan'}
        />
      )}
      {compact && row.detail?.review_required && (
        <p className="protection-note">{row.detail.review_reason}</p>
      )}
      {compact && row.detail?.group === 'Pengesahan' && (
        <p className="protection-note">Periksa keberadaan tanda tangan pada dokumen sumber.</p>
      )}
      {!compact && (
        <>
          <p className="protection-value">{row.observed}</p>
          <p className="protection-note">{row.note}</p>
        </>
      )}
      {(uniquePages.length > 0 || row.document_id) && (
        <div className="protection-source">
          {uniquePages.length === 0 ? (
            <p className="protection-page-label">Halaman 1</p>
          ) : law || row.detail?.group === 'Pengesahan' ? (
            <p className="protection-page-label">Halaman {uniquePages.join(', ')}</p>
          ) : (
            <p className="protection-page-label">Halaman {page}</p>
          )}
          {row.document_id && (
            <button
              type="button"
              className="button button-source"
              onClick={() => openEvidence(row.document_id!, page ?? 1)}
            >
              <ExternalLink size={16} /> Lihat dokumen sumber
            </button>
          )}
        </div>
      )}
    </article>
  );
}
