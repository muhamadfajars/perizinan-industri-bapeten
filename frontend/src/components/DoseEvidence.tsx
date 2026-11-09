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
      <h4>Pembatas Dosis</h4>
      <EvidenceStatus found={pages.length > 0} />
      <p className="protection-note">Pernyataan pembatas dosis operasional dalam dokumen:</p>
      <p className="protection-value">
        {statement.split(/(\d+(?:[.,]\d+)?\s*mSv\s*\/\s*tahun)/gi).map((part, index) =>
          index % 2 ? (
            <mark className="dose-highlight" key={index}>
              {part}
            </mark>
          ) : (
            part
          ),
        )}
      </p>
      {pages.length > 0 && (
        <div className="protection-source">
          <p className="protection-page-label">Halaman {page}</p>
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
