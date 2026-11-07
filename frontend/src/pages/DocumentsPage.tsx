import { CalendarDays, ExternalLink, FileText, Search, Trash2 } from 'lucide-react';
import { EmptyDocuments, SectionHeading } from '../components/Common';
import { categoryById } from '../data/categories';
import type { EvaluationWorkspace } from '../hooks/useEvaluationWorkspace';
import { dateLabel, sizeLabel } from '../lib/presentation';

type Props = Pick<
  EvaluationWorkspace,
  'active' | 'items' | 'docSearch' | 'setDocSearch' | 'visibleDocuments' | 'goTo' | 'removeFile' | 'viewFile'
>;

export function DocumentsPage({
  active,
  items,
  docSearch,
  setDocSearch,
  visibleDocuments,
  goTo,
  removeFile,
  viewFile,
}: Props) {
  return (
    <section className="page-section documents-section" id="dokumen" hidden={active !== 'dokumen'}>
      <SectionHeading
        eyebrow="LANGKAH 04"
        title="Dokumen yang Diunggah"
        description="Daftar berkas untuk permohonan aktif; berkas yang terkirim disimpan di server secara privat."
        action={<span className="tiny-counter">{items.length} file</span>}
      />
      <div className="surface documents-surface">
        {items.length > 0 && (
          <div className="documents-toolbar">
            <label className="search-field">
              <Search size={17} />
              <input
                type="search"
                value={docSearch}
                onChange={(e) => setDocSearch(e.target.value)}
                placeholder="Cari nama atau kategori dokumen..."
              />
            </label>
            <span>{visibleDocuments.length} file ditampilkan</span>
          </div>
        )}
        {items.length === 0 ? (
          <EmptyDocuments goUpload={() => goTo('upload')} />
        ) : (
          <div className="documents-grid">
            {visibleDocuments.map((item) => (
              <article className="document-card" key={item.id}>
                <div className="document-card-top">
                  <span className={`document-file-icon category-${item.category}`}>
                    <FileText size={25} />
                  </span>
                  <button
                    className="icon-button"
                    aria-label={`Hapus ${item.name}`}
                    title="Hapus dari daftar sementara"
                    onClick={() => removeFile(item.id)}
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
                <strong title={item.name}>{item.name}</strong>
                <span className="document-type">
                  {item.name.split('.').at(-1)?.toUpperCase()} · {sizeLabel(item.size)}
                </span>
                <div className="document-meta">
                  <span>{categoryById(item.category)?.name ?? 'Perlu Pilih Kategori'}</span>
                  {item.subtype && <small>{item.subtype}</small>}
                </div>
                <div className="document-card-footer">
                  <span>
                    <CalendarDays size={13} />
                    {dateLabel(item.addedAt)}
                  </span>
                  <button className="open-file" onClick={() => viewFile(item.file, item.serverId)}>
                    <ExternalLink size={15} /> Buka
                  </button>
                </div>
              </article>
            ))}
            {!visibleDocuments.length && (
              <p className="doc-no-results">Tidak ada dokumen yang cocok dengan pencarian.</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
