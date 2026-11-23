import { useEffect, useRef, useState } from 'react';
import { InlineSourcePreview } from './Evidence';
import { searchDocumentText, type DocumentSearchMatch } from '../api';
import { ChevronDown, ChevronUp, ExternalLink, Maximize2, Minimize2, Search, X } from 'lucide-react';

export function SourceDocumentViewer({
  documentId,
  imageOnly = false,
  enableSearch = true,
  enableMinimize = true,
  showSubtitle = true,
  title,
  page,
  loadDocument,
  openExternal,
  close,
}: {
  documentId: string;
  imageOnly?: boolean;
  enableSearch?: boolean;
  enableMinimize?: boolean;
  showSubtitle?: boolean;
  title: string;
  page?: number;
  loadDocument: (documentId: string) => Promise<Blob>;
  openExternal: (documentId: string, page?: number) => void;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState('');
  const [isImageBlob, setIsImageBlob] = useState(false);
  const [error, setError] = useState('');
  const [activePage, setActivePage] = useState(page ?? 1);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [matches, setMatches] = useState<DocumentSearchMatch[]>([]);
  const [matchIndex, setMatchIndex] = useState(0);
  const [searchedQuery, setSearchedQuery] = useState('');
  const [minimized, setMinimized] = useState(false);

  useEffect(() => {
    setActivePage(page ?? 1);
  }, [page, documentId]);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    if (!minimized) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = previousOverflow;
    }
    dialog.current?.showModal();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [minimized]);

  useEffect(() => {
    if (imageOnly || minimized || !enableSearch) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        event.stopPropagation();
        setSearchOpen(true);
        requestAnimationFrame(() => {
          searchInput.current?.focus();
          searchInput.current?.select();
        });
      }
    };
    window.addEventListener('keydown', handleKeyDown, true);
    return () => window.removeEventListener('keydown', handleKeyDown, true);
  }, [imageOnly, minimized, enableSearch]);

  useEffect(() => {
    if (imageOnly) return;
    let disposed = false;
    let objectUrl = '';
    setUrl('');
    setIsImageBlob(false);
    setError('');
    loadDocument(documentId)
      .then((blob) => {
        if (disposed) return;
        objectUrl = URL.createObjectURL(blob);
        setIsImageBlob(blob.type.startsWith('image/'));
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

  const jumpToMatch = (nextMatches: DocumentSearchMatch[], idx: number) => {
    if (!nextMatches.length) return;
    const safeIdx = ((idx % nextMatches.length) + nextMatches.length) % nextMatches.length;
    setMatchIndex(safeIdx);
    setActivePage(nextMatches[safeIdx].page);
  };

  const runSearch = async () => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setMatches([]);
      setSearchedQuery('');
      return;
    }
    if (trimmed === searchedQuery && matches.length > 0) {
      jumpToMatch(matches, matchIndex + 1);
      return;
    }
    setSearching(true);
    try {
      const found = await searchDocumentText(documentId, trimmed);
      setMatches(found);
      setSearchedQuery(trimmed);
      if (found.length > 0) {
        jumpToMatch(found, 0);
      }
    } finally {
      setSearching(false);
    }
  };

  const currentMatch = matches[matchIndex];

  return (
    <dialog
      ref={dialog}
      className={`source-viewer ${minimized ? 'source-viewer-minimized' : ''}`}
      aria-labelledby="source-viewer-title"
      onCancel={close}
    >
      <div className="source-viewer-layout">
        <header className="source-viewer-header">
          <div className="source-viewer-caption">
            <h3 id="source-viewer-title" title={title}>
              {title}
            </h3>
            {showSubtitle && <span>Dokumen sumber{activePage ? ` — Halaman ${activePage}` : ''}</span>}
          </div>
          <div className="source-viewer-actions">
            {enableSearch && !imageOnly && !minimized && (
              <button
                type="button"
                className="button button-source"
                onClick={() => {
                  setSearchOpen((prev) => {
                    const next = !prev;
                    if (next) {
                      requestAnimationFrame(() => searchInput.current?.focus());
                    }
                    return next;
                  });
                }}
              >
                <Search size={16} /> Cari (Ctrl+F)
              </button>
            )}
            {!minimized && (
              <button className="button button-source" onClick={() => openExternal(documentId, activePage)}>
                <ExternalLink size={16} /> Buka di tab baru
              </button>
            )}
            {enableMinimize && (
              <button
                className="icon-button"
                type="button"
                aria-label={minimized ? 'Perbesar dokumen sumber' : 'Perkecil dokumen sumber'}
                title={minimized ? 'Perbesar' : 'Perkecil (Minimize)'}
                onClick={() => setMinimized(!minimized)}
              >
                {minimized ? <Maximize2 size={18} /> : <Minimize2 size={18} />}
              </button>
            )}
            <button className="icon-button" aria-label="Tutup dokumen sumber" title="Tutup" onClick={close}>
              <X size={22} />
            </button>
          </div>
        </header>
        {!minimized && (
          <>
            {enableSearch && !imageOnly && searchOpen && (
              <form
                className="source-viewer-search"
                onSubmit={(event) => {
                  event.preventDefault();
                  void runSearch();
                }}
              >
                <Search size={15} className="source-viewer-search-icon" />
                <input
                  ref={searchInput}
                  type="search"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    if (event.target.value.trim() !== searchedQuery) {
                      setMatches([]);
                      setSearchedQuery('');
                    }
                  }}
                  placeholder="Cari teks dalam PDF (tekan Enter)…"
                  aria-label="Cari teks dalam dokumen sumber"
                />
                <button type="submit" className="button button-source" disabled={searching || query.trim().length < 2}>
                  {searching ? 'Mencari…' : 'Cari'}
                </button>
                {searchedQuery && (
                  <span className="source-viewer-search-status" role="status">
                    {matches.length > 0
                      ? `${matchIndex + 1}/${matches.length} · Hal. ${currentMatch?.page}`
                      : 'Tidak ditemukan'}
                  </span>
                )}
                {matches.length > 1 && (
                  <>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Hasil sebelumnya"
                      onClick={() => jumpToMatch(matches, matchIndex - 1)}
                    >
                      <ChevronUp size={16} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Hasil berikutnya"
                      onClick={() => jumpToMatch(matches, matchIndex + 1)}
                    >
                      <ChevronDown size={16} />
                    </button>
                  </>
                )}
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Tutup pencarian"
                  onClick={() => {
                    setSearchOpen(false);
                    setQuery('');
                    setMatches([]);
                    setSearchedQuery('');
                  }}
                >
                  <X size={16} />
                </button>
              </form>
            )}
            {imageOnly ? (
              <div className="source-viewer-image">
                <InlineSourcePreview documentId={documentId} page={activePage} />
              </div>
            ) : error ? (
              <p className="source-viewer-message" role="alert">
                {error}
              </p>
            ) : url ? (
              isImageBlob ? (
                <div className="source-viewer-image">
                  <img src={url} alt={title} />
                </div>
              ) : (
                <iframe key={`${url}-${activePage}`} title="Pratinjau dokumen sumber" src={`${url}#page=${activePage}`} />
              )
            ) : (
              <p className="source-viewer-message" role="status">
                Memuat dokumen sumber…
              </p>
            )}
          </>
        )}
      </div>
    </dialog>
  );
}
