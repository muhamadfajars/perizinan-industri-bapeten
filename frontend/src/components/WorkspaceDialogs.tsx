import { UploadCloud } from 'lucide-react';
import { CATEGORIES } from '../data/categories';
import type { CategoryId } from '../types/models';
import { PERSONNEL_TYPES } from '../types/models';
import type { EvaluationWorkspace } from '../hooks/useEvaluationWorkspace';
type Props = Pick<
  EvaluationWorkspace,
  | 'manualDialog'
  | 'manualCategory'
  | 'savingCategory'
  | 'working'
  | 'setManualCategory'
  | 'manualInput'
  | 'addFiles'
  | 'setShowUnclassified'
  | 'setUploadSearch'
  | 'resetDialog'
  | 'resetApplication'
>;
export function WorkspaceDialogs({
  manualDialog,
  manualCategory,
  savingCategory,
  working,
  setManualCategory,
  manualInput,
  addFiles,
  setShowUnclassified,
  setUploadSearch,
  resetDialog,
  resetApplication,
}: Props) {
  return (
    <>
      {' '}
      <dialog
        ref={manualDialog}
        className="reset-dialog manual-upload-dialog"
        aria-labelledby="manual-upload-title"
        aria-describedby="manual-upload-description"
      >
        <h2 id="manual-upload-title">Tambah ke Kategori</h2>
        <p id="manual-upload-description">Pilih kategori, lalu tambahkan berkas ke daftar dokumen.</p>
        <label className="manual-category-label" htmlFor="manual-category">
          Kategori Dokumen
        </label>
        <select
          id="manual-category"
          className="table-category-select"
          autoFocus
          value={manualCategory}
          disabled={working || savingCategory}
          onChange={(event) => setManualCategory(event.target.value)}
        >
          <option value="" disabled>
            Pilih kategori
          </option>
          {CATEGORIES.map((category) =>
            category.requiresSubtype ? (
              <optgroup key={category.id} label={category.name}>
                {PERSONNEL_TYPES.map((subtype) => (
                  <option key={subtype} value={`personel:${subtype}`}>
                    Personel: {subtype}
                  </option>
                ))}
              </optgroup>
            ) : (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ),
          )}
        </select>
        <input
          ref={manualInput}
          hidden
          type="file"
          multiple
          accept=".pdf,.jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff,.docx"
          onChange={(event) => {
            if (event.target.files?.length && manualCategory) {
              const isPersonnel = manualCategory.startsWith('personel:');
              addFiles(
                isPersonnel ? 'personel' : (manualCategory as CategoryId),
                event.target.files,
                isPersonnel ? manualCategory.slice('personel:'.length) : undefined,
              );
              manualDialog.current?.close();
              setShowUnclassified(false);
              setUploadSearch('');
            }
            event.target.value = '';
          }}
        />
        <div className="reset-dialog-actions">
          <button className="button button-soft" type="button" onClick={() => manualDialog.current?.close()}>
            Batal
          </button>
          <button
            className="button button-primary"
            type="button"
            disabled={!manualCategory || working || savingCategory}
            onClick={() => manualInput.current?.click()}
          >
            <UploadCloud size={17} /> Pilih Berkas
          </button>
        </div>
      </dialog>
      <dialog
        ref={resetDialog}
        className="reset-dialog"
        aria-labelledby="reset-dialog-title"
        aria-describedby="reset-dialog-description"
      >
        <h2 id="reset-dialog-title">Mulai evaluasi baru?</h2>
        <p id="reset-dialog-description">
          Data unggahan dan hasil analisis pada sesi ini akan dikosongkan untuk memulai evaluasi instansi
          berikutnya.
        </p>
        <div className="reset-dialog-actions">
          <button className="button button-soft" autoFocus onClick={() => resetDialog.current?.close()}>
            Batal
          </button>
          <button
            className="button button-primary"
            disabled={working || savingCategory}
            onClick={resetApplication}
          >
            Mulai Evaluasi Baru
          </button>
        </div>
      </dialog>
    </>
  );
}
