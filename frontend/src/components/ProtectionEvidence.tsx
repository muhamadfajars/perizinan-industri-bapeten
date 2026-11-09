import { useMemo, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import type { MatchRow } from '../types/models';
import { protectionFieldLabel, regulationDisplayTitle } from '../lib/protectionDisplay';
import { SourceDocumentViewer } from './SourceDocumentViewer';
import { EvidenceStatus } from './EvidenceStatus';
import { DoseEvidence } from './DoseEvidence';

type ProtectionTabKey = 'dasar-hukum' | 'zonasi' | 'pembatas-dosis' | 'pengesahan';

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

export function getProtectionTabKey(row: MatchRow): ProtectionTabKey {
  if (row.detail?.group === 'Dasar hukum') return 'dasar-hukum';
  if (row.detail?.group === 'Pengesahan' || row.field.includes('Pengesahan')) return 'pengesahan';
  if (row.field === 'Pembatas Dosis' || row.field.includes('Dosis')) return 'pembatas-dosis';
  return 'zonasi';
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

  const requiredLaws = (rowsByTab.get('dasar-hukum') ?? []).filter((row) => row.detail?.required);
  const missingLaws = requiredLaws.filter((row) => !row.detail?.pages?.length);
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
        {effectiveActiveTab === 'dasar-hukum' && (
          <div
            className={missingLaws.length ? 'protection-law-warning' : 'protection-law-complete'}
            role="status"
          >
            <strong>
              {`${missingLaws.length ? 'Belum lengkap' : 'Lengkap'} — ${requiredLaws.length - missingLaws.length} dari 5 dasar hukum ditemukan`}
            </strong>
            {missingLaws.length > 0 && (
              <p>Periksa peraturan berlabel “Belum ditemukan” pada dokumen sumber.</p>
            )}
          </div>
        )}
        {effectiveActiveTab === 'dasar-hukum' ? (
          <>
            <h4 className="protection-law-group">Dasar hukum wajib</h4>
            {requiredLaws.map((row) => (
              <ProtectionEvidence
                key={row.id}
                row={row}
                compact
                openEvidence={(documentId, page) =>
                  setSource({
                    documentId,
                    page,
                    title:
                      row.detail?.group === 'Dasar hukum'
                        ? regulationDisplayTitle(row.field)
                        : protectionFieldLabel(row),
                  })
                }
              />
            ))}
            <h4 className="protection-law-group">Peraturan tambahan</h4>
            {activeRows.filter((row) => !row.detail?.required).length ? (
              activeRows
                .filter((row) => !row.detail?.required)
                .map((row) => (
                  <ProtectionEvidence
                    key={row.id}
                    row={row}
                    compact
                    openEvidence={(documentId, page) =>
                      setSource({
                        documentId,
                        page,
                        title:
                          row.detail?.group === 'Dasar hukum'
                            ? regulationDisplayTitle(row.field)
                            : protectionFieldLabel(row),
                      })
                    }
                  />
                ))
            ) : (
              <p className="protection-note">Tidak ada peraturan tambahan yang ditemukan.</p>
            )}
          </>
        ) : activeRows.length > 0 ? (
          activeRows.map((row) => (
            <ProtectionEvidence
              key={row.id}
              row={row}
              compact
              openEvidence={(documentId, page) =>
                setSource({
                  documentId,
                  page,
                  title:
                    row.detail?.group === 'Dasar hukum'
                      ? regulationDisplayTitle(row.field)
                      : protectionFieldLabel(row),
                })
              }
            />
          ))
        ) : (
          <p className="protection-tab-empty">Tidak ada item pada kategori ini.</p>
        )}
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
  const pages = row.detail?.pages ?? [];
  const [pageIndex, setPageIndex] = useState(0);
  const page = pages[pageIndex];
  const law = row.detail?.group === 'Dasar hukum';
  const dose = row.field === 'Pembatas Dosis';
  if (compact && dose) return <DoseEvidence key={row.id} row={row} openEvidence={openEvidence} />;
  return (
    <article className={`protection-evidence${compact ? ' protection-evidence-compact' : ''}`}>
      <div className="protection-evidence-heading">
        <h4>{compact && law ? regulationDisplayTitle(row.field) : protectionFieldLabel(row)}</h4>
      </div>
      {compact && <EvidenceStatus found={pages.length > 0} />}
      {compact && row.detail?.group === 'Pengesahan' && (
        <p className="protection-note">Periksa tanda tangan pada gambar sumber.</p>
      )}
      {!compact && (
        <>
          <p className="protection-value">{row.observed}</p>
          <p className="protection-note">{row.note}</p>
        </>
      )}
      {pages.length > 0 && (
        <div className="protection-source">
          {law || row.detail?.group === 'Pengesahan' ? (
            <p className="protection-page-label">Halaman {[...new Set(pages)].join(', ')}</p>
          ) : (
            pages.length > 0 && (
              <div className="protection-page-control">
                <label>
                  Halaman sumber
                  <select value={pageIndex} onChange={(event) => setPageIndex(Number(event.target.value))}>
                    {pages.map((number, index) => (
                      <option key={number} value={index}>
                        Halaman {number}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )
          )}
          {row.document_id && page && (
            <button
              type="button"
              className="button button-source"
              onClick={() => openEvidence(row.document_id!, page)}
            >
              <ExternalLink size={16} /> Lihat dokumen sumber
            </button>
          )}
        </div>
      )}
    </article>
  );
}
