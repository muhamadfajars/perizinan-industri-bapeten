import { ExternalLink } from 'lucide-react';
import { useState } from 'react';
import type { MatchRow } from '../types/models';
import { InlineSourcePreview } from './Evidence';

export function FieldSourceEvidence({
  row,
  openDocument,
}: {
  row: MatchRow;
  openDocument: (documentId: string, page?: number) => void;
}) {
  const pages = [...new Set(row.detail?.pages?.length ? row.detail.pages : row.page ? [row.page] : [])];
  const [pageIndex, setPageIndex] = useState(0);
  const page = pages[pageIndex];
  const imageOnly = row.detail?.group === 'Pengesahan' || row.field === 'Pembatas Dosis';
  const quotes = [
    ...new Set((row.detail?.evidence ?? []).filter((item) => item.page === page).map((item) => item.quote)),
  ];
  return (
    <section className="field-source-evidence protection-source" aria-label="Bukti sumber">
      <h4>Bukti sumber</h4>
      {pages.length > 0 ? (
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
      ) : (
        <p>Halaman bukti belum ditemukan.</p>
      )}
      {!imageOnly && quotes.map((quote) => <blockquote key={quote}>{quote}</blockquote>)}
      {row.document_id && page && <InlineSourcePreview documentId={row.document_id} page={page} />}
      {row.document_id && (
        <button
          type="button"
          className="button button-soft button-full source-pdf-link"
          onClick={() => openDocument(row.document_id!, page)}
        >
          <ExternalLink size={16} /> Buka PDF lengkap
        </button>
      )}
    </section>
  );
}
