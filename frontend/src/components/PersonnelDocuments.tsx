import { Fragment, useState } from 'react';
import { ExternalLink, Users } from 'lucide-react';
import type { MatchRow, MatchSection, MatchStatus } from '../types/models';
import { isPersonnelInformation } from '../lib/matching';
import { EvidenceStatus } from './EvidenceStatus';
import { SourceDocumentViewer } from './SourceDocumentViewer';

interface DocGroup {
  id: string;
  documentId?: string;
  docType: string;
  filename?: string;
  label: string;
  owners: string[];
  isShared: boolean;
  coOwners: string[];
  status: MatchStatus;
  rows: MatchRow[];
}

function cleanFilenameLabel(filename?: string): string {
  if (!filename) return '';
  return filename
    .replace(/^\d{8,14}[-_]\s*/, '')
    .replace(/\.[^.]+$/, '')
    .trim();
}

function extractOwners(docRows: MatchRow[]): string[] {
  const seen = new Set<string>();
  const owners: string[] = [];
  for (const r of docRows) {
    const candidate = (
      r.detail?.person_name || (r.field === 'Nama' ? r.observed : '')
    )?.trim();
    if (
      !candidate ||
      ['—', '-', 'Belum terbaca'].includes(candidate) ||
      candidate.startsWith('Belum')
    ) {
      continue;
    }
    const key = candidate.toLocaleLowerCase('id-ID');
    if (!seen.has(key)) {
      seen.add(key);
      owners.push(candidate);
    }
  }
  return owners;
}

function aggregateDocStatus(docRows: MatchRow[]): MatchStatus {
  if (docRows.some((r) => r.status === 'MISMATCH')) return 'MISMATCH';
  if (docRows.some((r) => r.status === 'REVIEW' || r.detail?.review_required)) return 'REVIEW';
  if (docRows.some((r) => r.status === 'MATCH')) return 'MATCH';
  return 'INFO';
}

export function PersonnelDocuments({
  section,
  rows,
  onRowClick,
  openEvidence,
  loadSourceDocument,
}: {
  section: MatchSection;
  rows: MatchRow[];
  onRowClick: (row: MatchRow, section: MatchSection) => void;
  openEvidence: (id: string, page?: number) => void;
  loadSourceDocument: (id: string) => Promise<Blob>;
}) {
  const [activeTabId, setActiveTabId] = useState<string>('');
  const [source, setSource] = useState<{
    documentId: string;
    title: string;
    page?: number;
    imageOnly?: boolean;
  } | null>(null);

  // Group rows by document_id
  const groupMap = new Map<string, MatchRow[]>();
  for (const row of rows) {
    if (row.field === 'Jenis Dokumen') continue;
    const key = row.document_id ?? section.id;
    groupMap.set(key, [...(groupMap.get(key) ?? []), row]);
  }

  const rawGroups: DocGroup[] = [...groupMap].map(([id, docRows]) => {
    const first = docRows[0];
    const docType = first.detail?.source_label || 'Dokumen Personel';
    const filename = first.detail?.source_filename;
    const owners = extractOwners(docRows);
    const cleaned = cleanFilenameLabel(filename);
    const baseLabel =
      owners.length === 1
        ? `${docType} — ${owners[0]}`
        : owners.length > 1
          ? `${docType} — ${owners.join(', ')}`
          : cleaned && cleaned.toLocaleLowerCase('id-ID') !== docType.toLocaleLowerCase('id-ID')
            ? `${docType} — ${cleaned}`
            : docType;
    const isShared = Boolean(
      first.detail?.shared_document || first.detail?.co_owners?.length || owners.length > 1,
    );
    const coOwners = first.detail?.co_owners ?? [];
    const status = aggregateDocStatus(docRows);

    return {
      id,
      documentId: first.document_id,
      docType,
      filename,
      label: baseLabel,
      owners,
      isShared,
      coOwners,
      status,
      rows: docRows,
    };
  });

  // Disambiguate colliding tab labels automatically without hardcoding
  const baseCounts = new Map<string, number>();
  for (const g of rawGroups) {
    baseCounts.set(g.label, (baseCounts.get(g.label) ?? 0) + 1);
  }
  const usedLabels = new Set<string>();
  const docGroups = rawGroups.map((g) => {
    let label = g.label;
    if ((baseCounts.get(g.label) ?? 0) > 1) {
      const cleaned = cleanFilenameLabel(g.filename);
      if (cleaned && !label.toLocaleLowerCase('id-ID').includes(cleaned.toLocaleLowerCase('id-ID'))) {
        label = `${label} (${cleaned})`;
      }
    }
    if (usedLabels.has(label)) {
      let counter = 2;
      while (usedLabels.has(`${label} (#${counter})`)) {
        counter += 1;
      }
      label = `${label} (#${counter})`;
    }
    usedLabels.add(label);
    return { ...g, label };
  });

  if (!docGroups.length) {
    return <p className="matching-filter-empty">Tidak ada field yang sesuai pencarian atau filter.</p>;
  }

  const activeGroup = docGroups.find((g) => g.id === activeTabId) ?? docGroups[0];
  const comparisonRows = activeGroup.rows.filter((r) => !isPersonnelInformation(r));
  const informationRows = activeGroup.rows.filter(isPersonnelInformation);
  const distinctPeople = new Set(
    comparisonRows.map((r) => r.detail?.person_name).filter((name): name is string => Boolean(name)),
  );
  const showPersonGroups = distinctPeople.size > 1;

  return (
    <div className="personnel-documents">
      {/* Tab Navigasi Dokumen Personel (1 tab per file unggahan) */}
      <div className="personnel-doc-tabs" role="tablist" aria-label="Daftar Dokumen Personel">
        {docGroups.map((group) => {
          const isActive = group.id === activeGroup.id;
          return (
            <button
              key={group.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`personnel-doc-tab ${isActive ? 'active' : ''}`}
              title={group.filename ? `${group.label} (${group.filename})` : group.label}
              onClick={() => setActiveTabId(group.id)}
            >
              <span
                className={`doc-tab-status-dot status-dot-${group.status.toLowerCase()}`}
                aria-hidden="true"
              />
              <span className="doc-tab-label">{group.label}</span>
              {group.isShared && (
                <span
                  className="doc-tab-badge-shared"
                  title={
                    group.owners.length > 1
                      ? `Dokumen bersama: memuat ${group.owners.join(', ')}`
                      : `Dokumen bersama: juga memuat ${group.coOwners.join(', ')}`
                  }
                >
                  Kolektif
                </span>
              )}
              {(group.status === 'REVIEW' || group.status === 'MISMATCH') && (
                <span className={`doc-tab-badge-status status-${group.status.toLowerCase()}`}>
                  {group.status === 'MISMATCH' ? 'Mismatch' : 'Review'}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Konten Dokumen yang Dipilih */}
      <section className="personnel-doc-content" key={activeGroup.id}>
        <div className="personnel-doc-header">
          <div className="personnel-doc-title-group">
            <h3>{activeGroup.label}</h3>
            {activeGroup.filename && (
              <p className="personnel-doc-filename">{activeGroup.filename}</p>
            )}
            {activeGroup.isShared && (
              <div className="personnel-shared-notice" role="note">
                <Users size={16} aria-hidden="true" />
                <span>
                  <strong>Dokumen Bersama / Kolektif:</strong>{' '}
                  {activeGroup.owners.length > 1 ? (
                    <>
                      Dokumen ini memuat data personel untuk{' '}
                      <strong>{activeGroup.owners.join(', ')}</strong>.
                    </>
                  ) : (
                    <>
                      Dokumen ini juga memuat penetapan untuk{' '}
                      <strong>{activeGroup.coOwners.join(', ')}</strong>.
                    </>
                  )}
                </span>
              </div>
            )}
          </div>
          {activeGroup.documentId && (
            <button
              type="button"
              className="button button-source button-sm"
              onClick={() =>
                setSource({
                  documentId: activeGroup.documentId!,
                  title: activeGroup.label,
                  page: activeGroup.rows[0]?.detail?.pages?.[0] ?? activeGroup.rows[0]?.page,
                  imageOnly: activeGroup.rows.some((r) => r.field === 'Pengesahan'),
                })
              }
            >
              <ExternalLink size={15} /> Lihat dokumen sumber
            </button>
          )}
        </div>

        {/* Tabel Terpadu Dokumen Personel (Field yang dicocokkan dengan formulir permohonan) */}
        {comparisonRows.length > 0 && (
          <>
            <p className="matching-table-hint">Klik baris untuk melihat detail dan bukti sumber.</p>
            <div
              className="table-scroll matching-table-scroll"
              tabIndex={0}
              role="region"
              aria-label={`Tabel perbandingan ${activeGroup.label}`}
            >
              <table className="matching-table">
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Formulir</th>
                    <th scope="col">Dokumen</th>
                    <th scope="col">Skor</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisonRows.map((row, idx) => (
                    <Fragment key={row.id}>
                      {showPersonGroups &&
                        row.detail?.person_name &&
                        row.detail.person_name !== comparisonRows[idx - 1]?.detail?.person_name && (
                          <tr className="matching-group-row">
                            <th colSpan={5} scope="rowgroup">
                              {row.detail.person_name}
                            </th>
                          </tr>
                        )}
                      <tr
                        className={`matching-row-${(row.status || 'review').toLowerCase()}`}
                        onClick={() => onRowClick(row, section)}
                      >
                        <td className="field-column">
                          <button
                            type="button"
                            className="field-detail-button"
                            aria-label={`Lihat detail ${row.field}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onRowClick(row, section);
                            }}
                          >
                            {row.field}
                          </button>
                        </td>
                        <td>{row.expected || '—'}</td>
                        <td className={row.observed === '—' ? 'empty-observed' : ''}>{row.observed}</td>
                        <td className="score-column">
                          {row.score == null ? '—' : `${row.score.toFixed(1)}%`}
                        </td>
                        <td>
                          <span
                            className={`matching-status status-text-${(row.status || 'review').toLowerCase()}`}
                          >
                            {row.status}
                          </span>
                        </td>
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Informasi Pendukung (Field yang tidak dicocokkan dengan formulir, misal: Masa Berlaku, Pengesahan) */}
        {informationRows.length > 0 && (
          <section className="protection-information" aria-label="Informasi Pendukung Dokumen">
            <h3>Informasi Pendukung Dokumen</h3>
            {informationRows.map((row) => (
              <PersonnelEvidenceCard
                key={row.id}
                row={row}
                documentId={row.document_id || activeGroup.documentId}
                openSource={(documentId, page, imageOnly) =>
                  setSource({
                    documentId,
                    title: `${activeGroup.label} — ${row.field}`,
                    page,
                    imageOnly,
                  })
                }
              />
            ))}
          </section>
        )}
      </section>

      {/* Modal Penampil Dokumen Sumber */}
      {source?.documentId && (
        <SourceDocumentViewer
          documentId={source.documentId}
          page={source.page}
          title={source.title}
          imageOnly={source.imageOnly}
          loadDocument={loadSourceDocument}
          openExternal={openEvidence}
          close={() => setSource(null)}
        />
      )}
    </div>
  );
}

function PersonnelEvidenceCard({
  row,
  documentId,
  openSource,
}: {
  row: MatchRow;
  documentId?: string;
  openSource: (documentId: string, page?: number, imageOnly?: boolean) => void;
}) {
  const rawPages = row.detail?.pages ?? (row.page != null ? [row.page] : []);
  const pages = [...new Set(rawPages)];
  const [pageIndex, setPageIndex] = useState(0);

  const isPengesahan = row.field === 'Pengesahan' || row.detail?.group === 'Pengesahan';
  const isMasaBerlaku = row.field === 'Masa Berlaku';

  const review = Boolean(row.detail?.review_required || row.status === 'REVIEW');
  const found = pages.length > 0 && !row.observed?.startsWith('Belum');
  const foundLabel = isPengesahan
    ? 'Halaman pengesahan ditemukan'
    : isMasaBerlaku
      ? 'Masa berlaku teridentifikasi'
      : 'Ditemukan';

  const defaultNote = isPengesahan
    ? 'Periksa tanda tangan pada gambar sumber.'
    : isMasaBerlaku
      ? 'Pastikan masa berlaku dokumen masih aktif saat permohonan diajukan.'
      : undefined;

  const targetDocId = row.document_id || documentId;
  const targetPage = pages.length > 0 ? pages[pageIndex] : undefined;

  return (
    <article className="protection-evidence protection-evidence-compact">
      <h4>{row.field}</h4>
      <EvidenceStatus found={found} review={review} foundLabel={foundLabel} />

      {!isPengesahan && row.observed && row.observed !== '—' && (
        <p className="protection-value" style={{ margin: '6px 0', fontWeight: 600 }}>
          {row.observed}
        </p>
      )}

      {row.detail?.review_required && row.detail.review_reason && (
        <p className="protection-note">{row.detail.review_reason}</p>
      )}

      {isPengesahan ? (
        <p className="protection-note">{defaultNote}</p>
      ) : row.note && row.note !== row.observed && row.note !== row.detail?.review_reason ? (
        <p className="protection-note">{row.note}</p>
      ) : defaultNote ? (
        <p className="protection-note">{defaultNote}</p>
      ) : null}

      <div className="protection-source">
        {pages.length > 1 ? (
          <div className="protection-page-control">
            <label>
              Halaman sumber{' '}
              <select value={pageIndex} onChange={(e) => setPageIndex(Number(e.target.value))}>
                {pages.map((p, i) => (
                  <option key={p} value={i}>
                    Halaman {p}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : pages.length === 1 ? (
          <p className="protection-page-label">Halaman {pages[0]}</p>
        ) : null}

        {targetDocId && (
          <button
            type="button"
            className="button button-source"
            onClick={() => openSource(targetDocId, targetPage, isPengesahan)}
          >
            <ExternalLink size={16} /> Lihat dokumen sumber
          </button>
        )}
      </div>
    </article>
  );
}
