import { ExternalLink, FolderOpen, Info, X } from 'lucide-react';
import { matchingSectionTitle } from '../lib/matchingDisplay';
import type { CategoryId, MatchRow, MatchSection } from '../types/models';
import { DataPair, ScoreBadge } from './Common';
import { ApprovalEvidence } from './Evidence';
import { FieldSourceEvidence } from './FieldSourceEvidence';
import { protectionFieldLabel } from '../lib/protectionDisplay';

export function DetailPanel({
  selected,
  close,
  openRelated,
  openEvidence,
}: {
  selected: { row: MatchRow; section: MatchSection } | null;
  close: () => void;
  openRelated: (category: CategoryId) => void;
  openEvidence: (documentId: string, page?: number) => void;
}) {
  if (!selected) return null;
  const { row, section } = selected;
  return (
    <>
      <button className="detail-backdrop" type="button" aria-label="Tutup detail" onClick={close} />
      <aside className="detail-panel" role="dialog" aria-modal="true" aria-label="Detail matching">
        <div className="detail-panel-header">
          <span className="eyebrow">DETAIL BUKTI</span>
          <button className="icon-button" onClick={close} aria-label="Tutup">
            <X size={20} />
          </button>
        </div>
        <h3>{protectionFieldLabel(row)}</h3>
        <p className="detail-origin">{matchingSectionTitle(section)}</p>
        <ScoreBadge status={row.status} />
        <div className="detail-divider" />
        <DataPair label="Acuan dari formulir" value={row.expected} />
        <DataPair label="Hasil pembacaan dokumen" value={row.observed} />
        <DataPair
          label="Kemiripan karakter / skor field"
          value={row.score === null ? 'Tidak tersedia' : `${row.score.toFixed(1)}%`}
        />
        {row.detail?.type !== 'protection' && (
          <DataPair
            label="Halaman bukti"
            value={row.page ? `Halaman ${row.page}` : 'Tidak dicatat pada hasil pemeriksaan'}
          />
        )}
        {row.note && (
          <div className="detail-note">
            <Info size={17} />
            {row.note.replaceAll(
              'v43_address_components',
              'Alamat dibandingkan berdasarkan komponen alamat yang terbaca pada dokumen.',
            )}
          </div>
        )}
        <div className="detail-divider" />
        {row.detail?.type === 'protection' && (
          <FieldSourceEvidence key={row.id} row={row} openDocument={openEvidence} />
        )}
        {row.document_id && row.detail?.type === 'approval' && <ApprovalEvidence row={row} />}
        {row.document_id && row.detail?.type !== 'approval' && row.detail?.type !== 'protection' && (
          <button
            className="button button-soft button-full"
            type="button"
            onClick={() => openEvidence(row.document_id!, row.page)}
          >
            <ExternalLink size={16} /> Buka PDF sumber {row.page ? `· Halaman ${row.page}` : ''}
          </button>
        )}
        <p className="detail-disclaimer">
          Nilai dibaca dari dokumen yang diunggah. Status MATCH tidak menyatakan keabsahan izin atau tanda
          tangan.
        </p>
        <button
          className="button button-primary button-full"
          type="button"
          onClick={() => {
            close();
            openRelated(section.category);
          }}
        >
          <FolderOpen size={17} /> Lihat dokumen kategori ini
        </button>
      </aside>
    </>
  );
}
