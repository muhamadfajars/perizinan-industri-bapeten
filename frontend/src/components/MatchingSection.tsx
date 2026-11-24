import { AlertCircle, CheckCircle2, ChevronDown, Clock, XCircle } from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import { categoryById } from '../data/categories';
import { matchingTotals } from '../lib/matching';
import { matchingSectionTitle, rowMatchesFilter, summaryRingTone } from '../lib/matchingDisplay';
import type { MatchRow, MatchSection } from '../types/models';
import { Filter } from '../types/workspace';
import { ApprovalEvidence, MaintenanceEvidence } from './Evidence';
import { PersonnelDocuments } from './PersonnelDocuments';
import Glyph from './Glyph';
import { SectionTopicSplitView } from './SectionTopicSplitView';
import {
  buildSectionTopicTabs,
  isAdditionalLocation,
  isManagementInformation,
  isSupportingInformation,
  personnelGroups,
  orderProtectionRows,
  protectionFieldLabel,
} from '../lib/protectionDisplay';

export function MatchingEvidence({
  section,
  filter,
  search,
}: {
  section: MatchSection;
  filter: Filter;
  search: string;
}) {
  const specials = section.rows.filter(
    (r) =>
      (r.detail?.type === 'approval' || r.detail?.type === 'maintenance') &&
      rowMatchesFilter(r, filter, search),
  );
  return (
    <div className="matching-extras">
      {specials
        .filter((r) => r.detail?.type === 'approval')
        .map((r) => (
          <ApprovalEvidence key={r.id} row={r} />
        ))}
      {specials
        .filter((r) => r.detail?.type === 'maintenance')
        .map((r) => (
          <MaintenanceEvidence key={r.id} row={r} />
        ))}
    </div>
  );
}

export function MatchingSection({
  section,
  search,
  filter,
  onRowClick,
  openEvidence,
  loadSourceDocument,
  expandedByDefault = false,
  open,
  onToggle,
}: {
  section: MatchSection;
  search: string;
  filter: Filter;
  onRowClick: (r: MatchRow, s: MatchSection) => void;
  openEvidence: (documentId: string, page?: number) => void;
  loadSourceDocument: (documentId: string) => Promise<Blob>;
  expandedByDefault?: boolean;
  open?: boolean;
  onToggle?: () => void;
}) {
  const [internalOpen, setInternalOpen] = useState(expandedByDefault);
  const isOpen = open ?? internalOpen;
  const handleToggle = onToggle ?? (() => setInternalOpen((previous) => !previous));
  const scopedRows = useMemo(() => {
    const rows = section.rows.filter(
      (row) =>
        !isAdditionalLocation(row) &&
        !(section.category === 'personel' && row.field === 'Jenis Dokumen') &&
        row.detail?.group !== 'Catatan pembacaan' &&
        row.field !== 'Catatan pembacaan',
    );
    return section.category === 'proteksi' ? orderProtectionRows(rows) : rows;
  }, [section]);
  const stats = useMemo(() => matchingTotals([{ ...section, rows: scopedRows }]), [section, scopedRows]);
  const filtered = scopedRows.filter((row) => rowMatchesFilter(row, filter, search));
  const isPerson = (row: MatchRow) => row.detail?.type === 'protection' && row.detail.group === 'Petugas';
  const managementRows = filtered.filter(isManagementInformation);
  const comparisonRows = filtered.filter(
    (row) => !isSupportingInformation(row) && !isManagementInformation(row),
  );
  const personLabels = new Map(
    personnelGroups(scopedRows).flatMap((person, index) =>
      person.rows.map(
        (row) => [row.id, `Petugas ${/^\d+$/.test(person.id) ? person.id : index + 1}`] as const,
      ),
    ),
  );
  const informationRows = filtered.filter(isSupportingInformation);
  const isTopicSplitSection = section.category === 'proteksi' || section.category === 'manajemen';
  const topicTabs =
    section.category === 'proteksi'
      ? buildSectionTopicTabs('proteksi', comparisonRows, informationRows)
      : section.category === 'manajemen'
        ? buildSectionTopicTabs('manajemen', comparisonRows, managementRows)
        : [];
  const renderComparisonTable = () => (
    <>
      <p className="matching-table-hint">Klik baris untuk melihat detail dan bukti sumber.</p>
      <div
        className="table-scroll matching-table-scroll"
        tabIndex={0}
        role="region"
        aria-label={`Tabel ${matchingSectionTitle(section)}`}
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
            {comparisonRows.map((row, i) => (
              <Fragment key={row.id}>
                {row.detail?.type === 'personnel' &&
                  (i === 0 || row.document_id !== comparisonRows[i - 1]?.document_id) && (
                    <tr className="matching-group-row">
                      <th colSpan={5} scope="rowgroup">
                        {row.detail.source_label}
                      </th>
                    </tr>
                  )}
                {isPerson(row) &&
                  personLabels.get(row.id) !== personLabels.get(comparisonRows[i - 1]?.id) && (
                    <tr className="matching-group-row">
                      <th colSpan={5} scope="rowgroup">
                        {personLabels.get(row.id)}
                      </th>
                    </tr>
                  )}
                {!isPerson(row) && i > 0 && isPerson(comparisonRows[i - 1]) && (
                  <tr className="matching-group-row">
                    <th colSpan={5} scope="rowgroup">
                      {row.detail?.group ?? 'Data acuan'}
                    </th>
                  </tr>
                )}
                <tr
                  className={`matching-row-${row.status.toLowerCase()}`}
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
                      {isPerson(row)
                        ? (row.detail?.field_label ?? row.field.split(': ').pop())
                        : protectionFieldLabel(row)}
                    </button>
                  </td>
                  <td>{row.expected}</td>
                  <td className={row.observed === '—' ? 'empty-observed' : ''}>{row.observed}</td>
                  <td className="score-column">{row.score === null ? '—' : `${row.score.toFixed(1)}%`}</td>
                  <td>
                    <span className={`matching-status status-text-${row.status.toLowerCase()}`}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              </Fragment>
            ))}
            {!comparisonRows.length && (
              <tr>
                <td colSpan={5} className="empty-table">
                  Tidak ada field yang sesuai pencarian atau filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <MatchingEvidence section={section} filter={filter} search={search} />
    </>
  );
  return (
    <div className="matching-section matching-report">
      <button className="match-section-header" type="button" onClick={handleToggle} aria-expanded={isOpen}>
        <span className="match-heading-group">
          <span className={`category-icon category-${section.category}`}>
            <Glyph name={categoryById(section.category)?.icon ?? 'file'} />
          </span>
          <span>
            <strong>{matchingSectionTitle(section)}</strong>
            <small>
              {section.category === 'personel' &&
              !section.name.startsWith('Dokumen Personel · ') &&
              !section.name.startsWith('Dokumen Personel — ')
                ? 'Pemilik perlu diperiksa'
                : filtered.length === scopedRows.length
                  ? `${filtered.length} field`
                  : `${filtered.length} dari ${scopedRows.length} field ditampilkan`}
            </small>
          </span>
        </span>
        <span className="match-pills">
          <span className="pill green">{stats.match} Match</span>
          {stats.review > 0 && <span className="pill amber">{stats.review} Review</span>}
          {stats.mismatch > 0 && <span className="pill red">{stats.mismatch} Mismatch</span>}
          {stats.info > 0 && <span className="pill">{stats.info} Informasi</span>}
        </span>
        <ChevronDown size={19} className={`match-chevron ${isOpen ? 'rotated' : ''}`} />
      </button>
      {isOpen && (
        <div className="match-section-content">
          <div className="matching-summary" aria-label="Ringkasan kecocokan dengan formulir">
            <div className="matching-summary-main">
              {stats.compared ? (
                <>
                  {(() => {
                    const pct = Math.max(0, Math.min(100, Number(stats.percentage) || 0));
                    const radius = 26;
                    const circumference = 2 * Math.PI * radius;
                    const dashOffset = circumference - (pct / 100) * circumference;
                    const tone = summaryRingTone(pct);
                    return (
                      <div className={`matching-summary-ring tone-${tone}`} aria-hidden="true">
                        <svg viewBox="0 0 64 64">
                          <circle className="ring-track" cx="32" cy="32" r={radius} />
                          <circle
                            className="ring-progress"
                            cx="32"
                            cy="32"
                            r={radius}
                            strokeDasharray={circumference}
                            strokeDashoffset={dashOffset}
                          />
                        </svg>
                        <span className="matching-summary-ring-value">{stats.percentage}%</span>
                      </div>
                    );
                  })()}
                  <p className="matching-summary-title">
                    <strong>Total field sesuai</strong>
                    <span>
                      {stats.match} dari {stats.compared} field
                    </span>
                  </p>
                </>
              ) : (
                <p className="matching-summary-title">
                  <span>Tidak ada data yang dibandingkan dengan formulir</span>
                </p>
              )}
            </div>
            <ul className="matching-summary-counts" aria-label="Jumlah hasil per status">
              <li>
                <span className="summary-icon-badge tone-green" aria-hidden="true">
                  <CheckCircle2 size={20} />
                </span>
                <div className="summary-count-text">
                  <strong>{stats.match}</strong>
                  <span>Match</span>
                </div>
              </li>
              <li>
                <span className="summary-icon-badge tone-amber" aria-hidden="true">
                  <Clock size={20} />
                </span>
                <div className="summary-count-text">
                  <strong>{stats.review}</strong>
                  <span>Review</span>
                </div>
              </li>
              <li>
                <span className="summary-icon-badge tone-red" aria-hidden="true">
                  <XCircle size={20} />
                </span>
                <div className="summary-count-text">
                  <strong>{stats.mismatch}</strong>
                  <span>Mismatch</span>
                </div>
              </li>
              {stats.missing > 0 && (
                <li>
                  <span className="summary-icon-badge tone-muted" aria-hidden="true">
                    <AlertCircle size={20} />
                  </span>
                  <div className="summary-count-text">
                    <strong>{stats.missing}</strong>
                    <span>Missing</span>
                  </div>
                </li>
              )}
            </ul>
          </div>
          {section.category === 'personel' ? (
            <PersonnelDocuments
              section={section}
              rows={filtered}
              onRowClick={onRowClick}
              openEvidence={openEvidence}
              loadSourceDocument={loadSourceDocument}
            />
          ) : isTopicSplitSection ? (
            <SectionTopicSplitView
              category={section.category as 'proteksi' | 'manajemen'}
              tabs={topicTabs}
              renderComparison={renderComparisonTable}
              openEvidence={openEvidence}
              loadSourceDocument={loadSourceDocument}
            />
          ) : (
            renderComparisonTable()
          )}
        </div>
      )}
    </div>
  );
}
