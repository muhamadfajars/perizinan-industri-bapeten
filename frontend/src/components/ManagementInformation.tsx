import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import type { MatchRow } from '../types/models';
import { EvidenceStatus } from './EvidenceStatus';
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
          imageOnly={source.row.detail?.group === 'Pengesahan'}
          loadDocument={loadSourceDocument}
          openExternal={openEvidence}
          close={() => setSource(null)}
        />
      )}
    </section>
  );
}

function ManagementCard({ row, open }: { row: MatchRow; open: (page: number) => void }) {
  const pages = [...new Set(row.detail?.pages ?? [])];
  const [index, setIndex] = useState(0);
  const topics = row.detail?.topics;
  const found = topics?.length ? topics.every((topic) => topic.found) : pages.length > 0;
  const partial = !found && !!topics?.some((topic) => topic.found);
  return (
    <article className="protection-evidence protection-evidence-compact">
      <h4>{row.field}</h4>
      <EvidenceStatus found={found} partial={partial} />
      <p className="protection-note">
        {row.detail?.group === 'Pengesahan'
          ? 'Periksa tanda tangan pada gambar sumber.'
          : 'Status menunjukkan keberadaan penjelasan, bukan penilaian penerapannya.'}
      </p>
      {pages.length > 0 && (
        <div className="protection-source">
          {pages.length > 1 ? (
            <div className="protection-page-control">
              <label>
                Halaman sumber{' '}
                <select value={index} onChange={(event) => setIndex(Number(event.target.value))}>
                  {pages.map((page, i) => (
                    <option key={page} value={i}>
                      Halaman {page}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : (
            <p className="protection-page-label">Halaman {pages[0]}</p>
          )}
          {row.document_id && (
            <button type="button" className="button button-source" onClick={() => open(pages[index])}>
              <ExternalLink size={16} /> Lihat dokumen sumber
            </button>
          )}
        </div>
      )}
    </article>
  );
}
