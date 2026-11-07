import {
  Activity,
  FileText,
  FolderOpen,
  HardDriveUpload,
  Home,
  LayoutDashboard,
  LoaderCircle,
} from 'lucide-react';
import bapetenLogo from '../assets/bapeten-logo.png';
import { PageId } from '../types/workspace';

export const NAV: Array<{ id: PageId; label: string; icon: typeof Home }> = [
  { id: 'ringkasan', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'upload', label: 'Upload Dokumen', icon: HardDriveUpload },
  { id: 'formulir', label: 'Formulir Permohonan', icon: FileText },
  { id: 'matching', label: 'Hasil Matching', icon: Activity },
  { id: 'dokumen', label: 'Dokumen', icon: FolderOpen },
];

export function Brand() {
  return (
    <div className="brand-lockup">
      <img src={bapetenLogo} alt="Logo BAPETEN" className="brand-logo" />
      <div className="brand-text">
        <div className="brand-name">BAPETEN</div>
        <div className="brand-description">Badan Pengawas Tenaga Nuklir</div>
      </div>
    </div>
  );
}

export function Sidebar({
  active,
  navigate,
  open,
  close,
  working,
}: {
  active: PageId;
  navigate: (id: PageId) => void;
  open: boolean;
  close: () => void;
  working: boolean;
}) {
  return (
    <>
      {open && <button className="sidebar-mask" onClick={close} aria-label="Tutup menu" />}
      <aside className={`sidebar ${open ? 'mobile-open' : ''}`}>
        <Brand />
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Navigasi utama" className="nav-list">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-link ${active === id ? 'active' : ''}`}
              aria-current={active === id ? 'page' : undefined}
              onClick={() => {
                navigate(id);
                close();
              }}
            >
              <Icon size={19} strokeWidth={1.9} />
              <span>{label}</span>
              {id === 'matching' && working && (
                <span className="nav-progress" title="Analisis sedang berjalan">
                  <LoaderCircle className="analysis-spinner" size={16} aria-hidden="true" />
                  <span className="sr-only"> — Analisis sedang berjalan</span>
                </span>
              )}
              {active === id && <span className="active-marker" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="sidebar-copyright">© 2026 BAPETEN · Asisten Evaluasi Perizinan Industri</div>
        </div>
      </aside>
    </>
  );
}
