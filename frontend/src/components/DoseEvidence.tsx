import { useState } from 'react';
import type { MatchRow } from '../types/models';
import { InlineSourcePreview } from './Evidence';

/** The operating statement has one rendering location, outside the image viewer. */
export function DoseEvidence({ row }: { row: MatchRow }) {
  const pages = [...new Set(row.detail?.pages ?? [])];
  const [pageIndex, setPageIndex] = useState(0);
  const [opened, setOpened] = useState(false);
  const page = pages[pageIndex];
  const statement = row.detail?.evidence?.find((item) => item.page === page)?.quote ?? row.observed;
  return (
    <article className="protection-evidence protection-evidence-compact dose-evidence">
      <h4>Pembatas Dosis</h4>
      <p className="protection-value">{statement}</p>
      {page && !opened && <p className="protection-page-label">Halaman {page}</p>}
      {pages.length > 0 && (
        <details onToggle={(event) => setOpened(event.currentTarget.open)}>
          <summary>Lihat gambar</summary>
          {opened && (
            <div className="protection-source">
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
              {row.document_id && page && <InlineSourcePreview documentId={row.document_id} page={page} />}
            </div>
          )}
        </details>
      )}
    </article>
  );
}
