import { ChevronDown } from 'lucide-react';
import { useMemo, useState } from 'react';
import { categoryById } from '../data/categories';
import { matchingTotals } from '../lib/matching';
import { matchingSectionTitle, rowMatchesFilter } from '../lib/matchingDisplay';
import type { MatchRow, MatchSection } from '../types/models';
import { Filter } from '../types/workspace';
import { ApprovalEvidence, MaintenanceEvidence } from './Evidence';
import Glyph from './Glyph';

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
  expandedByDefault = false,
}: {
  section: MatchSection;
  search: string;
  filter: Filter;
  onRowClick: (r: MatchRow, s: MatchSection) => void;
  expandedByDefault?: boolean;
}) {
  const [open, setOpen] = useState(expandedByDefault);
  const stats = useMemo(() => matchingTotals([section]), [section]);
  const filtered = section.rows.filter((row) => rowMatchesFilter(row, filter, search));
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
              {filtered.length === section.rows.length
                ? `${filtered.length} field`
                : `${filtered.length} dari ${section.rows.length} field ditampilkan`}
            </small>
          </span>
        </span>
        <span className="match-pills">
          <span className="pill green">{stats.match} Match</span>
          {stats.review > 0 && <span className="pill amber">{stats.review} Review</span>}
          {stats.mismatch > 0 && <span className="pill red">{stats.mismatch} Mismatch</span>}
        </span>
        <ChevronDown size={19} className={`match-chevron ${open ? 'rotated' : ''}`} />
      </button>
      {open && (
        <div className="match-section-content">
          <div className="matching-stats" aria-label="Ringkasan seluruh field dalam kategori">
            <div>
              <span>Kecocokan terbukti</span>
              <strong>{stats.percentage.toFixed(1)}%</strong>
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
                {filtered.map((row, i) => (
                  <tr
                    key={`${row.id}-${i}`}
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
                        {row.field}
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
                ))}
                {!filtered.length && (
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
          <div className="table-footer">
            <span>Pilih field untuk melihat detail dan sumber dokumen.</span>
            <span>
              {filtered.length} dari {section.rows.length} field
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
