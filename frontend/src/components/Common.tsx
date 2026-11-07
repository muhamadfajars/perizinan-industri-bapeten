import { ChevronDown, FolderOpen, UploadCloud } from 'lucide-react';
import type { ReactNode } from 'react';
import type { MatchStatus } from '../types/models';

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {action && <div className="section-action">{action}</div>}
    </div>
  );
}

export function SummaryCard({
  icon,
  label,
  value,
  note,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  note: string;
  tone: string;
}) {
  return (
    <div className="summary-card">
      <div className={`summary-icon tone-${tone}`}>{icon}</div>
      <div className="summary-content">
        <div className="metric-caption">{label}</div>
        <div className="metric-value">{value}</div>
        <div className="metric-note">{note}</div>
      </div>
    </div>
  );
}

export function ScoreBadge({ status }: { status: MatchStatus }) {
  return (
    <span className={`status-chip status-${status.toLowerCase()}`}>
      <span className="status-dot" />
      {status}
    </span>
  );
}

export function Accordion({
  title,
  subtitle,
  icon,
  children,
  open,
  onToggle,
  count,
}: {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  children: ReactNode;
  open: boolean;
  onToggle: () => void;
  count?: ReactNode;
}) {
  return (
    <div className={`accordion ${open ? 'accordion-open' : ''}`}>
      <button className="accordion-toggle" type="button" onClick={onToggle} aria-expanded={open}>
        <div className="accordion-label">
          {icon && <span className="accordion-icon">{icon}</span>}
          <span>
            <strong>{title}</strong>
            {subtitle && <small>{subtitle}</small>}
          </span>
        </div>
        <div className="accordion-right">
          {count}
          <ChevronDown className="accordion-chevron" size={19} />
        </div>
      </button>
      {open && <div className="accordion-body">{children}</div>}
    </div>
  );
}

export function DataPair({ label, value }: { label: string; value: string }) {
  return (
    <div className="data-pair">
      <div>{label}</div>
      <strong>{value}</strong>
    </div>
  );
}

export function EmptyDocuments({ goUpload }: { goUpload: () => void }) {
  return (
    <div className="empty-documents">
      <span className="empty-illustration">
        <FolderOpen size={34} />
      </span>
      <h3>Belum ada dokumen diunggah</h3>
      <p>
        File yang sudah dikirim lewat Mulai Analisis tersimpan privat di server dan dapat dibuka kembali pada
        sesi ini.
      </p>
      <button className="button button-soft" onClick={goUpload}>
        <UploadCloud size={17} /> Tambah dokumen
      </button>
    </div>
  );
}
