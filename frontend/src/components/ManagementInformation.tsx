import { useState } from 'react';
import { AlertCircle, CheckCircle2 } from 'lucide-react';
import type { MatchRow } from '../types/models';
import { SourceActionButton } from './ProtectionEvidence';
import { SourceDocumentViewer } from './SourceDocumentViewer';

export function ManagementInformation({
  rows,
  openEvidence,
  loadSourceDocument,
}: {
  rows: MatchRow[];
  openEvidence: (documentId: string, page?: number) => void;
  loadSourceDocument: (documentId: string) => Promise<Blob>;
}) {
  const [source, setSource] = useState<{ row: MatchRow; page: number } | null>(null);
  return (
    <section className="protection-information" aria-label="Informasi Sistem Manajemen">
      <h3>Informasi Pendukung Sistem Manajemen</h3>
      {rows.map((row) => (
        <ManagementCard key={row.id} row={row} open={(page) => setSource({ row, page })} />
      ))}
      {source?.row.document_id && (
        <SourceDocumentViewer
          documentId={source.row.document_id}
          title={source.row.field}
          page={source.page}
          loadDocument={loadSourceDocument}
          openExternal={openEvidence}
          close={() => setSource(null)}
        />
      )}
    </section>
  );
}

function managementCardLabel(row: MatchRow) {
  if (row.detail?.group === 'Pengesahan') return 'Pengesahan';
  if (row.detail?.group === 'Budaya') return 'Kelengkapan Uraian';
  return row.field;
}

export function ManagementCard({ row, open }: { row: MatchRow; open: (page: number) => void }) {
  const pages = [...new Set(row.detail?.pages ?? [])];
  const primaryPage = pages[0];
  const hasPages = pages.length > 0;
  const isReview = Boolean(row.detail?.review_required);

  if (row.detail?.group === 'Budaya') {
    const topics = row.detail?.topics ?? [];
    const allFound = topics.length ? topics.every((topic) => topic.found) : hasPages;
    const partial = !allFound && topics.some((topic) => topic.found);
    const confirmed = allFound && !isReview;
    const statusLabel = confirmed
      ? 'Ditemukan'
      : isReview
        ? 'Perlu diperiksa'
        : partial
          ? 'Belum lengkap'
          : 'Belum ditemukan';

    return (
      <div className="law-ledger">
        <div className="law-group">
          <div className="law-group-header">
            <h4 className="law-group-title">{managementCardLabel(row)}</h4>
          </div>
          <ul className="law-list">
            <li className={`law-item ${confirmed ? '' : 'law-item-missing'}`.trim()}>
              <span
                className={`law-item-icon ${confirmed ? 'is-found' : 'is-missing'}`}
                aria-hidden="true"
              >
                {confirmed ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
              </span>
              <div className="law-item-body">
                <div className="law-item-head">
                  <span className="law-item-code">Budaya Keselamatan dan Keamanan</span>
                  <span className={confirmed ? 'law-status-found' : 'law-status-missing'}>
                    {statusLabel}
                  </span>
                </div>
                <p className="law-item-subject">
                  {confirmed
                    ? 'Uraian budaya keselamatan dan keamanan ditemukan — status menunjukkan keberadaan penjelasan, bukan penilaian penerapannya.'
                    : partial
                      ? 'Sebagian uraian budaya ditemukan — periksa kelengkapan penjelasan keselamatan dan keamanan pada dokumen sumber.'
                      : 'Uraian budaya keselamatan dan keamanan belum terdeteksi otomatis; periksa dokumen sumber.'}
                </p>
                {isReview && row.detail?.review_reason && (
                  <p className="law-item-reason">{row.detail.review_reason}</p>
                )}
                {(hasPages || row.document_id) && (
                  <div className="law-item-actions">
                    <SourceActionButton
                      documentId={row.document_id}
                      page={primaryPage ?? 1}
                      found={confirmed}
                      hasPages={hasPages}
                      onOpen={(_docId, pageNum) => open(pageNum ?? 1)}
                    />
                  </div>
                )}
              </div>
            </li>
          </ul>
        </div>
      </div>
    );
  }

  const found = hasPages && !isReview;
  const isApproval = row.detail?.group === 'Pengesahan';

  return (
    <div className="law-ledger">
      <div className="law-group">
        <div className="law-group-header">
          <h4 className="law-group-title">
            {isApproval ? 'Pengesahan Dokumen' : managementCardLabel(row)}
          </h4>
        </div>
        <ul className="law-list">
          <li className={`law-item ${found ? '' : 'law-item-missing'}`.trim()}>
            <span className={`law-item-icon ${found ? 'is-found' : 'is-missing'}`} aria-hidden="true">
              {found ? <CheckCircle2 size={17} /> : <AlertCircle size={17} />}
            </span>
            <div className="law-item-body">
              <div className="law-item-head">
                <span className="law-item-code">{managementCardLabel(row)}</span>
                {!found && (
                  <span className="law-status-missing">
                    {isReview ? 'Perlu diperiksa' : 'Belum ditemukan'}
                  </span>
                )}
              </div>
              <p className="law-item-subject">
                {isApproval
                  ? hasPages
                    ? 'Halaman pengesahan ditemukan — periksa keberadaan tanda tangan pimpinan atau penanggung jawab pada dokumen sumber.'
                    : 'Halaman pengesahan belum ditemukan otomatis; periksa dokumen sumber.'
                  : row.observed}
              </p>
              {isReview && row.detail?.review_reason && (
                <p className="law-item-reason">{row.detail.review_reason}</p>
              )}
              {(hasPages || row.document_id) && (
                <div className="law-item-actions">
                  <SourceActionButton
                    documentId={row.document_id}
                    page={primaryPage ?? 1}
                    found={found}
                    hasPages={hasPages}
                    onOpen={(_docId, pageNum) => open(pageNum ?? 1)}
                  />
                </div>
              )}
            </div>
          </li>
        </ul>
      </div>
    </div>
  );
}
