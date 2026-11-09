import { useEffect, useRef, useState } from 'react';
import { InlineSourcePreview } from './Evidence';
import { ExternalLink, X } from 'lucide-react';

export function SourceDocumentViewer({
  documentId,
  imageOnly = false,
  title,
  page,
  loadDocument,
  openExternal,
  close,
}: {
  documentId: string;
  imageOnly?: boolean;
  title: string;
  page?: number;
  loadDocument: (documentId: string) => Promise<Blob>;
  openExternal: (documentId: string, page?: number) => void;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current?.showModal();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  useEffect(() => {
    if (imageOnly) return;
    let disposed = false;
    let objectUrl = '';
    setUrl('');
    setError('');
    loadDocument(documentId)
      .then((blob) => {
        if (disposed) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!disposed)
          setError('Dokumen sumber belum dapat dimuat. Tutup dan coba kembali, atau buka di tab baru.');
      });
    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, loadDocument, imageOnly]);

  return (
    <dialog ref={dialog} className="source-viewer" aria-labelledby="source-viewer-title" onCancel={close}>
      <div className="source-viewer-layout">
        <header className="source-viewer-header">
          <div className="source-viewer-caption">
            <h3 id="source-viewer-title" title={title}>
              {title}
            </h3>
            <span>Dokumen sumber{page ? ` — Halaman ${page}` : ''}</span>
          </div>
          <div className="source-viewer-actions">
            <button className="button button-source" onClick={() => openExternal(documentId, page)}>
              <ExternalLink size={16} /> Buka di tab baru
            </button>
            <button className="icon-button" aria-label="Tutup dokumen sumber" onClick={close}>
              <X size={22} />
            </button>
          </div>
        </header>
        {imageOnly ? (
          <div className="source-viewer-image">
            <InlineSourcePreview documentId={documentId} page={page} />
          </div>
        ) : error ? (
          <p className="source-viewer-message" role="alert">
            {error}
          </p>
        ) : url ? (
          <iframe title="Pratinjau dokumen sumber" src={`${url}#page=${page ?? 1}`} />
        ) : (
          <p className="source-viewer-message" role="status">
            Memuat dokumen sumber…
          </p>
        )}
      </div>
    </dialog>
  );
}
