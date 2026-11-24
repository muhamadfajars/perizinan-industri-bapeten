import { AlertCircle, ArrowUpRight, CheckCircle2, FileText } from 'lucide-react';
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
  const hasPages = pages.length > 0;
  const isReview = Boolean(row.detail?.review_required);
  const found = hasPages && !isReview;
  const statement = row.detail?.evidence?.find((item) => item.page === page)?.quote ?? row.observed;
  const actionLabel = found
    ? `Lihat sumber · Halaman ${page}`
    : hasPages
      ? `Periksa sumber · Halaman ${page}`
      : 'Periksa dokumen sumber';

  return (
    <div className="law-ledger">
      <article className="info-evidence-card">
        <div className={`info-evidence-head ${found ? '' : 'is-attention'}`.trim()}>
          <div className="info-evidence-title">
            <span className={`law-item-icon ${found ? 'is-found' : 'is-missing'}`} aria-hidden="true">
              {found ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
            </span>
            <h4>Penetapan Pembatas Dosis</h4>
            <span className={found ? 'law-status-found' : 'law-status-missing'}>
              {found ? 'Ditemukan' : isReview ? 'Perlu diperiksa' : 'Belum ditemukan'}
            </span>
          </div>
        </div>
        <div className="info-evidence-body">
          {isReview && row.detail?.review_reason ? (
            <p className="law-item-reason">{row.detail.review_reason}</p>
          ) : (
            <p className="info-evidence-caption">Pernyataan pembatas dosis operasional dalam dokumen:</p>
          )}
          <blockquote className={`dose-statement-box ${found ? '' : 'is-attention'}`.trim()}>
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
          </blockquote>
          <p className="info-evidence-hint">
            Pastikan angka pembatas dosis tidak melebihi Nilai Batas Dosis (NBD) ketentuan BAPETEN.
          </p>
          {(hasPages || row.document_id) && (
            <div className="info-evidence-actions">
              {row.document_id ? (
                <button
                  type="button"
                  className="law-source-link"
                  onClick={() => openEvidence(row.document_id!, page ?? 1)}
                >
                  <FileText size={13.5} aria-hidden="true" />
                  <span>{actionLabel}</span>
                  <ArrowUpRight size={14} aria-hidden="true" />
                </button>
              ) : (
                <span className="law-page-static">Halaman {page}</span>
              )}
            </div>
          )}
        </div>
      </article>
    </div>
  );
}
