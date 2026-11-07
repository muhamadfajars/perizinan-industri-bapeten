import { AlertCircle, Check, ChevronRight, Info, Menu, X } from 'lucide-react';
import { DetailPanel } from './components/DetailPanel';
import { Sidebar } from './components/Layout';
import { WorkspaceDialogs } from './components/WorkspaceDialogs';
import { categoryById } from './data/categories';
import { useEvaluationWorkspace } from './hooks/useEvaluationWorkspace';
import { DashboardPage } from './pages/DashboardPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { FormPage } from './pages/FormPage';
import { MatchingPage } from './pages/MatchingPage';
import { UploadPage } from './pages/UploadPage';

export default function App() {
  const workspace = useEvaluationWorkspace();
  const {
    active,
    goTo,
    mobileNav,
    setMobileNav,
    working,
    backendError,
    result,
    selectedDetail,
    setSelectedDetail,
    openEvidence,
    announce,
    toast,
    setToast,
  } = workspace;
  return (
    <div className="app-shell">
      <Sidebar
        active={active}
        navigate={goTo}
        open={mobileNav}
        close={() => setMobileNav(false)}
        working={working}
      />
      <main className="main-area">
        <div className="topbar">
          <div className="topbar-left">
            <button
              className="mobile-menu icon-button"
              onClick={() => setMobileNav(true)}
              aria-label="Buka menu"
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb">Workspace</span>
            <ChevronRight size={15} />
            <span className="breadcrumb-current">Evaluasi Permohonan</span>
          </div>
          <div className="topbar-right">
            <span className="demo-indicator">
              <span />{' '}
              {working
                ? 'Analisis Berlangsung'
                : backendError
                  ? 'Perlu Diperiksa'
                  : result
                    ? 'Hasil Tersedia'
                    : 'Menunggu Analisis'}
            </span>
            <span className="user-avatar">EV</span>
            <span className="user-label">Evaluator</span>
          </div>
        </div>
        <div className="content-wrap">
          <DashboardPage {...workspace} />

          <UploadPage {...workspace} />

          <FormPage {...workspace} />

          <MatchingPage {...workspace} />

          <DocumentsPage {...workspace} />
        </div>
      </main>
      <WorkspaceDialogs {...workspace} />
      <DetailPanel
        selected={selectedDetail}
        close={() => setSelectedDetail(null)}
        openEvidence={openEvidence}
        openRelated={(category) => {
          goTo('dokumen');
          announce(
            'info',
            `Cari dokumen kategori ${categoryById(category)?.name} pada daftar file yang diunggah.`,
          );
        }}
      />
      {toast && (
        <div className={`toast toast-${toast.tone}`} role="status">
          <span className="toast-icon">
            {toast.tone === 'success' ? (
              <Check size={18} />
            ) : toast.tone === 'warning' ? (
              <AlertCircle size={18} />
            ) : (
              <Info size={18} />
            )}
          </span>
          <p>{toast.message}</p>
          <button className="icon-button" onClick={() => setToast(null)} aria-label="Tutup pesan">
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
