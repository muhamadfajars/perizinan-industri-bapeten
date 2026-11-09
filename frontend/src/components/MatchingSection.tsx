import { ChevronDown } from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import { categoryById } from '../data/categories';
import { matchingTotals } from '../lib/matching';
import { matchingSectionTitle, rowMatchesFilter } from '../lib/matchingDisplay';
import type { MatchRow, MatchSection } from '../types/models';
import { Filter } from '../types/workspace';
import { ApprovalEvidence, MaintenanceEvidence } from './Evidence';
import { ManagementInformation } from './ManagementInformation';
import Glyph from './Glyph';
import { ProtectionEvidence, ProtectionInformationSection } from './ProtectionEvidence';
import {
  isAdditionalLocation,
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
}: {
  section: MatchSection;
  search: string;
  filter: Filter;
  onRowClick: (r: MatchRow, s: MatchSection) => void;
  openEvidence: (documentId: string, page?: number) => void;
  loadSourceDocument: (documentId: string) => Promise<Blob>;
  expandedByDefault?: boolean;
}) {
  const [open, setOpen] = useState(expandedByDefault);
  const scopedRows = useMemo(() => {
    const rows = section.rows.filter((row) => !isAdditionalLocation(row));
    return section.category === 'proteksi' ? orderProtectionRows(rows) : rows;
  }, [section]);
  const stats = useMemo(() => matchingTotals([{ ...section, rows: scopedRows }]), [section, scopedRows]);
  const filtered = scopedRows.filter((row) => rowMatchesFilter(row, filter, search));
  const isPerson = (row: MatchRow) => row.detail?.type === 'protection' && row.detail.group === 'Petugas';
  const isManagementInfo = (row: MatchRow) =>
    row.detail?.type === 'management' && ['Pengesahan', 'Budaya'].includes(row.detail.group ?? '');
  const managementRows = filtered.filter(isManagementInfo);
  const comparisonRows = filtered.filter(
    (row) =>
      !isSupportingInformation(row) && !isManagementInfo(row) && row.detail?.group !== 'Catatan pembacaan',
  );
  const personLabels = new Map(
    personnelGroups(scopedRows).flatMap((person, index) =>
      person.rows.map(
        (row) => [row.id, `Petugas ${/^\d+$/.test(person.id) ? person.id : index + 1}`] as const,
      ),
    ),
  );
  const informationRows = filtered.filter(isSupportingInformation);
  const readingNotes = filtered.filter((row) => row.detail?.group === 'Catatan pembacaan');
  return (
    <div className="matching-section matching-report">
      <button
        className="match-section-header"
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="match-heading-group">
          <span className={`category-icon category-${section.category}`}>
            <Glyph name={categoryById(section.category)?.icon ?? 'file'} />
          </span>
          <span>
            <strong>{matchingSectionTitle(section)}</strong>
            <small>
              {filtered.length === scopedRows.length
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
        <ChevronDown size={19} className={`match-chevron ${open ? 'rotated' : ''}`} />
      </button>
      {open && (
        <div className="match-section-content">
          <div className="matching-stats" aria-label="Ringkasan seluruh field dalam kategori">
            <div>
              <span>Kecocokan data acuan ({stats.compared} field)</span>
              <strong>{stats.compared ? `${stats.percentage.toFixed(1)}%` : '—'}</strong>
            </div>
            <div>
              <span>MATCH</span>
              <strong>{stats.match}</strong>
            </div>
            <div>
              <span>REVIEW</span>
              <strong>{stats.review}</strong>
            </div>
            <div>
              <span>MISMATCH</span>
              <strong>{stats.mismatch}</strong>
            </div>
          </div>
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
                      <td className="score-column">
                        {row.score === null ? '—' : `${row.score.toFixed(1)}%`}
                      </td>
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
          {readingNotes.map((row) => (
            <ProtectionEvidence key={row.id} row={row} openEvidence={openEvidence} />
          ))}
          {managementRows.length > 0 && (
            <ManagementInformation
              rows={managementRows}
              openEvidence={openEvidence}
              loadSourceDocument={loadSourceDocument}
            />
          )}
          {informationRows.length > 0 && (
            <ProtectionInformationSection
              rows={informationRows}
              openEvidence={openEvidence}
              loadSourceDocument={loadSourceDocument}
            />
          )}
        </div>
      )}
    </div>
  );
}
