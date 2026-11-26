import { Fragment, useState } from 'react';
import { AlertCircle, ArrowUpRight, CheckCircle2, FileText, Users } from 'lucide-react';
import type { MatchRow, MatchSection, MatchStatus } from '../types/models';
import { isPersonnelInformation } from '../lib/matching';
import {
  extractUsagePeriods,
  findDuplicatePersonnelTabIds,
  stripUploadTimestamp,
} from '../lib/matchingDisplay';
import { SourceActionButton } from './ProtectionEvidence';
import { SourceDocumentViewer } from './SourceDocumentViewer';

interface DocGroup {
  id: string;
  documentId?: string;
  docType: string;
  filename?: string;
  shortFilename?: string;
  headerTitle: string;
  owners: string[];
  isShared: boolean;
  coOwners: string[];
  status: MatchStatus;
  rows: MatchRow[];
}

function formatOwnerSummary(owners: string[]): string {
  if (owners.length <= 2) return owners.join(', ');
  return `${owners[0]}, ${owners[1]} (+${owners.length - 2} lainnya)`;
}

function extractOwners(docRows: MatchRow[]): string[] {
  const seen = new Set<string>();
  const owners: string[] = [];
  for (const r of docRows) {
    const candidate = (r.detail?.person_name || (r.field === 'Nama' ? r.observed : ''))?.trim();
    if (!candidate || ['—', '-', 'Belum terbaca'].includes(candidate) || candidate.startsWith('Belum')) {
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
  } | null>(null);

  // Group rows by document_id + personnel document label so bundled multi-subtype files stay distinct tabs
  const groupMap = new Map<string, MatchRow[]>();
  for (const row of rows) {
    if (row.field === 'Jenis Dokumen') continue;
    const docKey = row.document_id ?? section.id;
    const labelKey = row.detail?.source_label?.trim() || '';
    const key = labelKey ? `${docKey}::${labelKey}` : docKey;
    groupMap.set(key, [...(groupMap.get(key) ?? []), row]);
  }

  const docGroups: DocGroup[] = [...groupMap].map(([id, docRows]) => {
    const first = docRows[0];
    const docType = first.detail?.source_label || 'Dokumen Personel';
    const filename = first.detail?.source_filename;
    const shortFilename = stripUploadTimestamp(filename);
    const owners = extractOwners(docRows);
    const headerTitle =
      owners.length === 1
        ? `${docType} — ${owners[0]}`
        : owners.length > 1
          ? `${docType} — ${formatOwnerSummary(owners)}`
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
      shortFilename,
      headerTitle,
      owners,
      isShared,
      coOwners,
      status,
      rows: docRows,
    };
  });

  if (!docGroups.length) {
    return <p className="matching-filter-empty">Tidak ada field yang sesuai pencarian atau filter.</p>;
  }

  const duplicateTabIds = findDuplicatePersonnelTabIds(docGroups);
  const activeGroup = docGroups.find((g) => g.id === activeTabId) ?? docGroups[0];
  const displayHeaderFilename = activeGroup.shortFilename || activeGroup.filename;
  const comparisonRows = activeGroup.rows.filter((r) => !isPersonnelInformation(r));
  const informationRows = activeGroup.rows.filter(isPersonnelInformation);
  const distinctPeople = new Set(
    comparisonRows.map((r) => r.detail?.person_name).filter((name): name is string => Boolean(name)),
  );
  const showPersonGroups = distinctPeople.size > 1;

  return (
    <div className="personnel-documents">
      {/* Daftar Dokumen Personel di Kolom Kiri (1 item per file unggahan) */}
      <aside className="personnel-doc-sidebar">
        <div className="personnel-doc-list-title">Daftar Dokumen ({docGroups.length})</div>
        <div className="personnel-doc-tabs" role="tablist" aria-label="Daftar Dokumen Personel">
          {docGroups.map((group) => {
            const isActive = group.id === activeGroup.id;
            const ownerText = group.owners.length > 0 ? formatOwnerSummary(group.owners) : null;
            const showDisambiguator = duplicateTabIds.has(group.id) && Boolean(group.shortFilename);
            const tooltipFilename = group.shortFilename || group.filename;
            return (
              <button
                key={group.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`personnel-doc-tab ${isActive ? 'active' : ''}`}
                title={tooltipFilename ? `${group.docType} — ${tooltipFilename}` : group.docType}
                onClick={() => setActiveTabId(group.id)}
              >
                <div className="doc-tab-top">
                  <span
                    className={`doc-tab-status-dot status-dot-${group.status.toLowerCase()}`}
                    aria-hidden="true"
                  />
                  <span className="doc-tab-title">{group.docType}</span>
                  {(group.status === 'REVIEW' || group.status === 'MISMATCH') && (
                    <span className="doc-tab-badges">
                      <span className={`doc-tab-badge-status status-${group.status.toLowerCase()}`}>
                        {group.status === 'MISMATCH' ? 'Mismatch' : 'Review'}
                      </span>
                    </span>
                  )}
                </div>
                <div className="doc-tab-meta">
                  <span className={ownerText ? 'doc-tab-owner' : 'doc-tab-owner doc-tab-owner-unknown'}>
                    {ownerText ?? 'Pemilik belum terbaca'}
                  </span>
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
                </div>
                {showDisambiguator && <div className="doc-tab-file">{group.shortFilename}</div>}
              </button>
            );
          })}
        </div>
      </aside>

      {/* Konten Dokumen yang Dipilih di Kolom Kanan */}
      <section className="personnel-doc-content" key={activeGroup.id}>
        <div className="personnel-doc-header">
          <div className="personnel-doc-title-group">
            <h3>{activeGroup.headerTitle}</h3>
            {displayHeaderFilename && (
              <p className="personnel-doc-filename" title={activeGroup.filename}>
                {displayHeaderFilename}
              </p>
            )}
            {activeGroup.isShared && (
              <div className="personnel-shared-notice" role="note">
                <Users size={16} aria-hidden="true" />
                <span>
                  <strong>Dokumen Bersama / Kolektif:</strong>{' '}
                  {activeGroup.owners.length > 1 ? (
                    <>
                      Dokumen ini memuat data personel untuk <strong>{activeGroup.owners.join(', ')}</strong>.
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
        </div>

        {/* Tabel Terpadu Dokumen Personel (Field yang dicocokkan dengan formulir permohonan) */}
        {comparisonRows.length > 0 && (
          <>
            <p className="matching-table-hint">Klik baris untuk melihat detail dan bukti sumber.</p>
            <div
              className="table-scroll matching-table-scroll"
              tabIndex={0}
              role="region"
              aria-label={`Tabel perbandingan ${activeGroup.headerTitle}`}
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
          <div className="law-group law-group-personnel" aria-label="Informasi Pendukung Dokumen">
            <div className="law-group-header">
              <h4 className="law-group-title">Informasi Pendukung Dokumen</h4>
              <span className="law-group-count">{informationRows.length} item</span>
            </div>
            <ul className="law-list">
              {informationRows.map((row) => (
                <PersonnelEvidenceCard
                  key={row.id}
                  row={row}
                  documentId={row.document_id || activeGroup.documentId}
                  openSource={(documentId, page) =>
                    setSource({
                      documentId,
                      title: `${activeGroup.headerTitle} — ${row.field}`,
                      page,
                    })
                  }
                />
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Modal Penampil Dokumen Sumber */}
      {source?.documentId && (
        <SourceDocumentViewer
          documentId={source.documentId}
          page={source.page}
          title={source.title}
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
  openSource: (documentId: string, page?: number) => void;
}) {
  const rawPages = row.detail?.pages ?? (row.page != null ? [row.page] : []);
  const pages = [...new Set(rawPages)];

  const isPengesahan = row.field === 'Pengesahan' || row.detail?.group === 'Pengesahan';
  const isMasaBerlaku = row.field === 'Masa Berlaku';
  const isPeriodePemakaian = row.field === 'Periode Pemakaian';

  const review = Boolean(row.detail?.review_required || row.status === 'REVIEW');
  const found = pages.length > 0 && !row.observed?.startsWith('Belum');
  const confirmed = found && !review;
  const periodItems = isPeriodePemakaian && found ? extractUsagePeriods(row) : [];
  const hideGenericPeriodNote =
    isPeriodePemakaian &&
    found &&
    !review &&
    row.note === 'Periode pemakaian ditampilkan sebagai informasi dokumen.';

  const defaultNote = isPengesahan
    ? 'Periksa keberadaan tanda tangan pada dokumen sumber.'
    : isMasaBerlaku
      ? 'Pastikan masa berlaku dokumen masih aktif saat permohonan diajukan.'
      : undefined;

  const targetDocId = row.document_id || documentId;
  const hasPerPeriodActions =
    periodItems.length > 0 && Boolean(targetDocId) && periodItems.every((item) => item.page != null);

  return (
    <li className={`law-item ${confirmed ? '' : 'law-item-missing'}`.trim()}>
      <span
        className={`law-item-icon ${confirmed ? 'is-found' : 'is-missing'}`}
        aria-hidden="true"
      >
        {confirmed ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
      </span>
      <div className="law-item-body">
        <div className="law-item-head">
          <span className="law-item-code">{row.field}</span>
          {!confirmed && (
            <span className="law-status-missing">
              {review ? 'Perlu diperiksa' : 'Belum ditemukan'}
            </span>
          )}
        </div>

        {!isPengesahan &&
          (periodItems.length > 0 ? (
            <ul className="personnel-period-list">
              {periodItems.map((item, idx) => (
                <li key={`${item.page ?? 'p'}-${idx}`} className="personnel-period-item">
                  {targetDocId && item.page != null ? (
                    <button
                      type="button"
                      className="law-source-link law-source-link-compact"
                      onClick={() => openSource(targetDocId, item.page)}
                    >
                      <FileText size={13} aria-hidden="true" />
                      <span>{confirmed ? `Lihat · Hal. ${item.page}` : `Periksa · Hal. ${item.page}`}</span>
                      <ArrowUpRight size={13.5} aria-hidden="true" />
                    </button>
                  ) : (
                    item.page != null && <span className="personnel-period-page">Hal. {item.page}</span>
                  )}
                  <span className="personnel-period-value">{item.value}</span>
                </li>
              ))}
            </ul>
          ) : (
            row.observed &&
            row.observed !== '—' && <p className="law-item-value">{row.observed}</p>
          ))}

        {row.detail?.review_required && row.detail.review_reason && (
          <p className="law-item-reason">{row.detail.review_reason}</p>
        )}

        {isPengesahan ? (
          <p className="law-item-subject">{defaultNote}</p>
        ) : !hideGenericPeriodNote &&
          row.note &&
          row.note !== row.observed &&
          row.note !== row.detail?.review_reason ? (
          <p className="law-item-subject">{row.note}</p>
        ) : defaultNote ? (
          <p className="law-item-subject">{defaultNote}</p>
        ) : null}

        {!hasPerPeriodActions && (pages.length > 0 || targetDocId) && (
          <div className="law-item-actions">
            {pages.length > 1 ? (
              pages.map((pageNum) => (
                <SourceActionButton
                  key={pageNum}
                  documentId={targetDocId}
                  page={pageNum}
                  found={confirmed}
                  hasPages
                  onOpen={openSource}
                />
              ))
            ) : (
              <SourceActionButton
                documentId={targetDocId}
                page={pages[0] ?? 1}
                found={confirmed}
                hasPages={pages.length > 0}
                onOpen={openSource}
              />
            )}
          </div>
        )}
      </div>
    </li>
  );
}
