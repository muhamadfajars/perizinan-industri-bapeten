import { ExternalLink } from 'lucide-react';
import { EvidenceStatus } from './EvidenceStatus';
import type { MatchRow } from '../types/models';

/** The operating statement has one rendering location, outside the image viewer. */
export function DoseEvidence({
  row,
  openEvidence,
}: {
  row: MatchRow;
  openEvidence: (documentId: string, page?: number) => void;
}) {
  const pages = [...new Set(row.detail?.pages ?? [])];
  const page = pages[0];
  const statement = row.detail?.evidence?.find((item) => item.page === page)?.quote ?? row.observed;
  return (
    <article className="protection-evidence protection-evidence-compact dose-evidence">
      <h4>Penetapan Pembatas Dosis</h4>
      <EvidenceStatus found={pages.length > 0} review={row.detail?.review_required} />
      <p className="protection-note">
        {row.detail?.review_required
          ? row.detail.review_reason
          : 'Pernyataan pembatas dosis operasional dalam dokumen:'}
      </p>
      <p className="protection-value">
        {statement
          .split(
            /(\d+(?:[.,]\d+)?\s*(?:mSv|µSv|μSv|uSv|Sv)(?:\s*\([^()]{1,40}\))?\s*(?:\/\s*(?:tahun|thn\.?|th\.?)|per\s+tahun))/gi,
          )
          .map((part, index, parts) => {
            if (index % 2 === 0) return part;
            const trailing = parts.slice(index + 1, index + 3).join('');
            if (/^\s*=\s*\d/.test(trailing)) return part;
            return (
              <mark className="dose-highlight" key={index}>
                {part}
              </mark>
            );
          })}
      </p>
      {(pages.length > 0 || row.document_id) && (
        <div className="protection-source">
          <p className="protection-page-label">Halaman {page ?? 1}</p>
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
