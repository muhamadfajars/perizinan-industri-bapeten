import { Info, X } from 'lucide-react';
import { matchingSectionTitle } from '../lib/matchingDisplay';
import type { MatchRow, MatchSection } from '../types/models';
import { FieldSourceEvidence } from './FieldSourceEvidence';
import { DataPair, ScoreBadge } from './Common';
import { protectionFieldLabel, fieldExplanation } from '../lib/protectionDisplay';

export function DetailPanel({
  selected,
  close,
  openEvidence,
  loadSourceDocument,
}: {
  selected: { row: MatchRow; section: MatchSection } | null;
  close: () => void;
  loadSourceDocument: (documentId: string) => Promise<Blob>;
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
        <h3>
          {row.detail?.person_id
            ? `Petugas ${row.detail.person_id} — ${row.detail.field_label}`
            : protectionFieldLabel(row)}
        </h3>
        <p className="detail-origin">{matchingSectionTitle(section)}</p>
        <ScoreBadge status={row.status} />
        <DataPair label="Acuan dari formulir" value={row.expected || 'Tidak tersedia'} />
        <DataPair label="Hasil pembacaan dokumen" value={row.observed || 'Tidak tersedia'} />
        <DataPair
          label="Kemiripan karakter / skor field"
          value={row.score == null ? 'Tidak tersedia' : `${row.score}%`}
        />
        <div className="detail-note" aria-label="Alasan hasil">
          <Info size={17} />
          {fieldExplanation(row)}
        </div>
        <div className="detail-divider" />
        <FieldSourceEvidence
          key={row.id}
          row={row}
          openDocument={openEvidence}
          loadDocument={loadSourceDocument}
        />
      </aside>
    </>
  );
}
