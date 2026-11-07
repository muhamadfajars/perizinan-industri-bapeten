import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CloudUpload,
  Eye,
  FolderOpen,
  Search,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import { SectionHeading } from '../components/Common';
import Glyph from '../components/Glyph';
import { CATEGORIES, categoryById } from '../data/categories';
import type { EvaluationWorkspace } from '../hooks/useEvaluationWorkspace';
import { sizeLabel } from '../lib/presentation';
import type { CategoryId } from '../types/models';
import { PERSONNEL_TYPES } from '../types/models';

type Props = Pick<
  EvaluationWorkspace,
  | 'active'
  | 'items'
  | 'dragged'
  | 'setDragged'
  | 'onDrop'
  | 'working'
  | 'savingCategory'
  | 'globalInput'
  | 'setManualCategory'
  | 'manualDialog'
  | 'handleBatchFiles'
  | 'categoryCount'
  | 'formCount'
  | 'recognizingCount'
  | 'clearAllFiles'
  | 'showUnclassified'
  | 'setShowUnclassified'
  | 'unclassifiedCount'
  | 'uploadSearch'
  | 'setUploadSearch'
  | 'reviewItems'
  | 'updateItemCategory'
  | 'viewFile'
  | 'removeFile'
  | 'analysisMessage'
  | 'progressMessage'
  | 'runAnalysis'
  | 'syncCount'
  | 'job'
>;

export function UploadPage({
  active,
  items,
  dragged,
  setDragged,
  onDrop,
  working,
  savingCategory,
  globalInput,
  setManualCategory,
  manualDialog,
  handleBatchFiles,
  categoryCount,
  formCount,
  recognizingCount,
  clearAllFiles,
  showUnclassified,
  setShowUnclassified,
  unclassifiedCount,
  uploadSearch,
  setUploadSearch,
  reviewItems,
  updateItemCategory,
  viewFile,
  removeFile,
  analysisMessage,
  progressMessage,
  runAnalysis,
  syncCount,
  job,
}: Props) {
  return (
    <section className="page-section" id="upload" hidden={active !== 'upload'}>
      <SectionHeading
        eyebrow="LANGKAH 01"
        title="Upload Dokumen Permohonan"
        description="Unggah berkas, periksa kategori, lalu mulai analisis."
      />
      <div className="surface upload-surface">
        <div
          className={`dropzone ${items.length ? 'dropzone-compact' : ''} ${dragged ? 'drag-active' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragged(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setDragged(false);
          }}
          onDrop={onDrop}
        >
          <div className="dropzone-icon">
            <CloudUpload size={33} />
          </div>
          <div className="dropzone-copy">
            <h3>{items.length ? 'Tambahkan berkas permohonan' : 'Unggah berkas permohonan'}</h3>
            <p>
              {items.length
                ? 'PDF, JPG, PNG, DOCX · Maks. 40 MB/file'
                : 'Tarik berkas ke sini atau pilih dari komputer. Kategori akan dikenali otomatis.'}
            </p>
          </div>
          <div className="dropzone-actions">
            <button
              className="button button-primary"
              type="button"
              disabled={working || savingCategory}
              onClick={() => globalInput.current?.click()}
            >
              <UploadCloud size={17} /> Pilih Berkas
            </button>
            <button
              className="button button-new-evaluation"
              type="button"
              disabled={working || savingCategory}
              onClick={() => {
                setManualCategory('');
                manualDialog.current?.showModal();
              }}
            >
              <FolderOpen size={17} /> Tambah ke Kategori
            </button>
          </div>
          <input
            ref={globalInput}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff,.docx"
            hidden
            onChange={(event) => {
              handleBatchFiles(event.target.files);
              event.target.value = '';
            }}
          />
          {!items.length && <small>PDF, JPG, PNG, DOCX · Maks. 40 MB/file</small>}
        </div>

        {items.length > 0 && (
          <div className="batch-review-section">
            <div className="batch-summary-header">
              <div className="batch-summary-left">
                <div className="batch-heading">
                  <h4>Daftar Dokumen</h4>
                  <span>
                    {items.length} dokumen · {categoryCount} kategori
                  </span>
                </div>
                {formCount === 1 ? (
                  <span className="status-pill success">
                    <CheckCircle2 size={14} /> 1 Formulir Permohonan
                  </span>
                ) : formCount === 0 ? (
                  <span className="status-pill danger">
                    <AlertCircle size={14} /> Formulir belum tersedia
                  </span>
                ) : (
                  <span className="status-pill warning">
                    <AlertCircle size={14} /> Terdeteksi {formCount} Formulir (Wajib tepat 1)
                  </span>
                )}
                {recognizingCount > 0 && (
                  <span className="tiny-counter" role="status">
                    Mengenali {recognizingCount} dokumen…
                  </span>
                )}
              </div>
              <button
                className="text-action"
                type="button"
                disabled={working || savingCategory}
                onClick={clearAllFiles}
              >
                <Trash2 size={14} /> Kosongkan
              </button>
            </div>

            <div className="upload-toolbar">
              <div className="upload-filters" role="group" aria-label="Filter klasifikasi dokumen">
                <button
                  type="button"
                  aria-pressed={!showUnclassified}
                  onClick={() => setShowUnclassified(false)}
                >
                  Semua ({items.length})
                </button>
                {unclassifiedCount > 0 && (
                  <button
                    type="button"
                    className="unclassified-filter"
                    aria-pressed={showUnclassified}
                    onClick={() => setShowUnclassified(true)}
                  >
                    <AlertCircle size={14} aria-hidden="true" /> Perlu Pilih Kategori ({unclassifiedCount})
                  </button>
                )}
              </div>
              <label className="search-field">
                <Search size={17} />
                <input
                  type="search"
                  aria-label="Cari dokumen unggahan"
                  placeholder="Cari dokumen…"
                  value={uploadSearch}
                  onChange={(event) => setUploadSearch(event.target.value)}
                />
              </label>
            </div>
            <div className="batch-table-wrapper">
              <div className="table-scroll">
                <table className="batch-table">
                  <thead>
                    <tr>
                      <th className="batch-th-doc">Dokumen</th>
                      <th className="batch-th-category">Kategori Dokumen</th>
                      <th className="batch-th-action">Aksi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reviewItems.map((item) => {
                      const currentVal =
                        item.category === 'personel'
                          ? `personel:${item.subtype || PERSONNEL_TYPES[0]}`
                          : item.category;

                      const isCustomSubtype =
                        item.category === 'personel' &&
                        Boolean(item.subtype) &&
                        !(PERSONNEL_TYPES as readonly string[]).includes(item.subtype!);

                      return (
                        <tr
                          key={item.id}
                          className={
                            item.category === 'unknown' && !item.isClassifying
                              ? 'unclassified-row'
                              : undefined
                          }
                        >
                          <td className="batch-td-doc">
                            <div className="batch-file-info">
                              <span className={`category-icon category-${item.category} batch-file-icon`}>
                                <Glyph name={categoryById(item.category)?.icon ?? 'file'} />
                              </span>
                              <div className="batch-file-text">
                                <div className="batch-file-name" title={item.name}>
                                  {item.name}
                                </div>
                                <span className="batch-file-size">{sizeLabel(item.size)}</span>
                              </div>
                            </div>
                          </td>
                          <td className="batch-td-category">
                            <select
                              className="table-category-select"
                              aria-label={`Kategori ${item.name}`}
                              disabled={working || savingCategory}
                              value={currentVal}
                              onChange={(e) => {
                                const val = e.target.value;
                                if (val.startsWith('personel:')) {
                                  updateItemCategory(item.id, 'personel', val.slice('personel:'.length));
                                } else {
                                  updateItemCategory(item.id, val as CategoryId);
                                }
                              }}
                            >
                              {item.category === 'unknown' && (
                                <option value="unknown" disabled>
                                  {item.isClassifying ? 'Mengenali…' : 'Perlu Pilih Kategori'}
                                </option>
                              )}
                              {CATEGORIES.map((c) => {
                                if (c.id === 'personel') {
                                  return (
                                    <optgroup key="personel-group" label="Dokumen Personel">
                                      {PERSONNEL_TYPES.map((t) => (
                                        <option key={`personel:${t}`} value={`personel:${t}`}>
                                          Personel: {t}
                                        </option>
                                      ))}
                                      {isCustomSubtype && (
                                        <option
                                          key={`personel:${item.subtype}`}
                                          value={`personel:${item.subtype}`}
                                        >
                                          Personel: {item.subtype}
                                        </option>
                                      )}
                                    </optgroup>
                                  );
                                }
                                return (
                                  <option key={c.id} value={c.id}>
                                    {c.name}
                                  </option>
                                );
                              })}
                            </select>
                          </td>
                          <td className="batch-td-action">
                            <div className="batch-file-actions">
                              <button
                                className="button button-soft button-sm"
                                type="button"
                                onClick={() => viewFile(item.file, item.serverId)}
                                aria-label={`Lihat ${item.name}`}
                              >
                                <Eye size={16} aria-hidden="true" /> Lihat
                              </button>
                              <button
                                className="icon-button delete-icon"
                                type="button"
                                disabled={working || savingCategory}
                                onClick={() => removeFile(item.id)}
                                aria-label={`Hapus ${item.name}`}
                                title="Hapus berkas"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {!reviewItems.length && (
                      <tr>
                        <td colSpan={3} className="upload-no-results">
                          Tidak ada dokumen yang cocok dengan pencarian.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {items.length > 0 && (
          <div className="classification-disclaimer">
            <AlertCircle size={16} />
            <span>
              <strong>Catatan Evaluator:</strong> Periksa kembali kategori setiap dokumen sebelum memulai
              analisis.
            </span>
          </div>
        )}

        <div className={`analysis-action-bar ${analysisMessage && !working ? 'analysis-blocked' : ''}`}>
          <div className="analysis-readiness" role="status">
            {working ? (
              <Activity size={22} />
            ) : analysisMessage ? (
              <AlertCircle size={22} />
            ) : (
              <CheckCircle2 size={22} />
            )}
            <div>
              <strong>
                {working
                  ? progressMessage
                  : savingCategory
                    ? 'Menyimpan kategori…'
                    : analysisMessage || 'Dokumen siap dianalisis'}
              </strong>
              {!working && !analysisMessage && (
                <small>Data dokumen akan dicocokkan dengan Formulir Permohonan.</small>
              )}
            </div>
          </div>
          <button
            className="button button-primary"
            type="button"
            disabled={working || savingCategory || Boolean(analysisMessage)}
            onClick={runAnalysis}
          >
            <Activity size={17} />
            {working
              ? `Memproses... ${syncCount ? `unggah ${syncCount}` : `${job?.progress ?? 0}%`}`
              : 'Mulai Analisis'}
          </button>
        </div>
      </div>
    </section>
  );
}
