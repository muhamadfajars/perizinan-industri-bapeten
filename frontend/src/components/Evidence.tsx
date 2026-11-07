import { ChevronDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchEvidencePage } from '../api';
import type { MatchRow } from '../types/models';

export function InlineSourcePreview({ documentId, page }: { documentId: string; page?: number }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!page || page < 1) return;
    let active = true;
    let allocated: string | null = null;
    const application = sessionStorage.getItem('bapeten_application_id');
    if (!application) {
      setError('Permohonan belum tersedia');
      return;
    }
    fetchEvidencePage(application, documentId, page)
      .then((blob) => {
        if (!active) return;
        allocated = URL.createObjectURL(blob);
        setBlobUrl(allocated);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'Halaman gagal dimuat');
      });
    return () => {
      active = false;
      if (allocated) URL.revokeObjectURL(allocated);
    };
  }, [documentId, page]);
  return (
    <div className="inline-source-preview">
      {(!page || page < 1) && (
        <span className="inline-preview-state">Halaman pengesahan belum terdeteksi.</span>
      )}
      {page && !blobUrl && !error && <span className="inline-preview-state">Memuat halaman pengesahan…</span>}
      {error && <span className="inline-preview-error">{error}</span>}
      {blobUrl && (
        <img
          src={blobUrl}
          alt={`Bukti pengesahan hanya halaman PDF ${page}`}
          className="inline-evidence-image"
        />
      )}
    </div>
  );
}

export function ApprovalEvidence({ row }: { row: MatchRow }) {
  const [opened, setOpened] = useState(false);
  const pages = row.detail?.pages || [];
  const sourcePage = pages[0] || row.page;
  return (
    <details className="evidence-accordion" onToggle={(ev) => setOpened(ev.currentTarget.open)}>
      <summary>
        <span>Lihat halaman Lembar Pengesahan (verifikasi visual)</span>
        <ChevronDown size={18} />
      </summary>
      {opened && (
        <div className="evidence-body">
          <strong>{row.detail?.heading || 'Lembar Pengesahan'}</strong>
          <p>
            {sourcePage
              ? `Hanya PDF halaman ${sourcePage} ditampilkan.`
              : 'Halaman pengesahan belum dapat ditentukan otomatis.'}{' '}
            Tanda tangan/stempel tetap memerlukan verifikasi visual.
          </p>
          {row.document_id && sourcePage && (
            <InlineSourcePreview documentId={row.document_id} page={sourcePage} />
          )}
        </div>
      )}
    </details>
  );
}

export function MaintenanceEvidence({ row }: { row: MatchRow }) {
  const [opened, setOpened] = useState(false);
  const pages = row.detail?.pages || [];
  const freqs = row.detail?.frequencies || [];
  const params = row.detail?.parameters || [];
  return (
    <details
      className="evidence-accordion maintenance-accordion"
      onToggle={(ev) => setOpened(ev.currentTarget.open)}
    >
      <summary>
        <span>Klausul Uji Kesesuaian</span>
        <ChevronDown size={18} />
      </summary>
      {opened && (
        <div className="evidence-body maintenance-detail" aria-label="Klausul Uji Kesesuaian">
          <p className="maintenance-source">
            Sumber: PDF{' '}
            {pages.length > 1
              ? `halaman ${pages[0]}–${pages[pages.length - 1]}`
              : pages.length
                ? `halaman ${pages[0]}`
                : 'belum diketahui'}
          </p>
          <div className="maintenance-columns">
            <div>
              <h4>Frekuensi</h4>
              {freqs.length ? (
                <ul>
                  {freqs.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              ) : (
                <p>Frekuensi belum dapat diekstrak.</p>
              )}
            </div>
            <div>
              <h4>Parameter yang diuji</h4>
              {params.length ? (
                <ul>
                  {params.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              ) : (
                <p>Parameter belum dapat diekstrak.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </details>
  );
}
