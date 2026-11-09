import { ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { SourceDocumentViewer } from './SourceDocumentViewer';
import { protectionFieldLabel } from '../lib/protectionDisplay';
import type { MatchRow } from '../types/models';

export function FieldSourceEvidence({
  row,
  openDocument,
  loadDocument,
}: {
  row: MatchRow;
  loadDocument: (documentId: string) => Promise<Blob>;
  openDocument: (documentId: string, page?: number) => void;
}) {
  const [preview, setPreview] = useState(false);
  const pages = [...new Set(row.detail?.pages?.length ? row.detail.pages : row.page ? [row.page] : [])];
  const page = pages[0];
  return (
    <section className="field-source-evidence protection-source" aria-label="Dokumen Sumber">
      <h4>Dokumen Sumber</h4>
      {pages.length > 0 ? <p>Halaman {pages.join(', ')}</p> : <p>Halaman bukti belum ditemukan.</p>}
      {row.document_id && (
        <button
          type="button"
          className="button button-source button-full source-pdf-link"
          onClick={() => setPreview(true)}
        >
          <ExternalLink size={16} /> Lihat dokumen sumber
        </button>
      )}
      {preview && row.document_id && (
        <SourceDocumentViewer
          documentId={row.document_id}
          page={page}
          title={
            row.detail?.person_id
              ? `Petugas ${row.detail.person_id} — ${row.detail.field_label}`
              : protectionFieldLabel(row)
          }
          loadDocument={loadDocument}
          openExternal={openDocument}
          close={() => setPreview(false)}
        />
      )}
    </section>
  );
}
