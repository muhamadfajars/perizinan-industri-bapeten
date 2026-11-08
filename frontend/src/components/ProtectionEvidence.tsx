import { useState } from 'react';
import type { MatchRow } from '../types/models';
import { InlineSourcePreview } from './Evidence';
import { protectionFieldLabel } from '../lib/protectionDisplay';
import { DoseEvidence } from './DoseEvidence';

export function ProtectionEvidence({ row, compact = false }: { row: MatchRow; compact?: boolean }) {
  const [opened, setOpened] = useState(false);
  const pages = row.detail?.pages ?? [];
  const [pageIndex, setPageIndex] = useState(0);
  const page = pages[pageIndex];
  const evidence = row.detail?.evidence?.filter((item) => item.page === page) ?? [];
  const law = row.detail?.group === 'Dasar hukum';
  const dose = row.field === 'Pembatas Dosis';
  const approval = row.detail?.group === 'Pengesahan';
  if (compact && dose) return <DoseEvidence key={row.id} row={row} />;
  return (
    <article className={`protection-evidence${compact ? ' protection-evidence-compact' : ''}`}>
      <div className="protection-evidence-heading">
        <h4>{compact && law ? row.field.replace(/^Dasar hukum:\s*/, '') : protectionFieldLabel(row)}</h4>
        {compact && law && (
          <span className={`outline-label ${pages.length ? 'evidence-found' : 'evidence-missing'}`}>
            {pages.length ? 'Ditemukan' : 'Belum ditemukan'}
          </span>
        )}
      </div>
      {row.detail?.required && <small>{compact ? 'Wajib' : 'Dasar hukum yang wajib dicantumkan'}</small>}
      {!compact && (
        <>
          <p className="protection-value">{row.observed}</p>
          <p className="protection-note">{row.note}</p>
        </>
      )}
      {compact && !law && !dose && !pages.length && <p className="protection-note">Belum ditemukan</p>}
      {compact && pages.length > 0 && (
        <p className="protection-page-label">
          Halaman {pages.slice(0, 3).join(', ')}
          {pages.length > 3 ? `, … (${pages.length} halaman)` : ''}
        </p>
      )}
      {(pages.length > 0 || (compact && row.note)) && (
        <details onToggle={(event) => setOpened(event.currentTarget.open)}>
          <summary>
            {compact
              ? !pages.length
                ? 'Keterangan'
                : row.detail?.images
                  ? 'Lihat gambar'
                  : dose
                    ? 'Lihat selengkapnya'
                    : 'Lihat bukti'
              : 'Tampilkan bukti sumber'}
          </summary>
          {opened && (
            <div className="protection-source">
              {compact && !approval && !dose && <p className="protection-note">{row.note}</p>}
              {pages.length > 0 && (
                <label>
                  Halaman sumber{' '}
                  <select value={pageIndex} onChange={(event) => setPageIndex(Number(event.target.value))}>
                    {pages.map((number, index) => (
                      <option key={number} value={index}>
                        Halaman {number}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {!approval &&
                !dose &&
                evidence.map((item, index) => <blockquote key={index}>{item.quote}</blockquote>)}
              {row.document_id && page && (
                <InlineSourcePreview key={page} documentId={row.document_id} page={page} />
              )}
            </div>
          )}
        </details>
      )}
    </article>
  );
}
