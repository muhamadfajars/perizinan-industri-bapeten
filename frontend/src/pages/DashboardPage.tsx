import { AlertCircle, ArrowRight, CheckCircle2, FileClock, FolderOpen, Info, RotateCcw } from 'lucide-react';
import { SummaryCard } from '../components/Common';
import { CATEGORIES } from '../data/categories';
import type { EvaluationWorkspace } from '../hooks/useEvaluationWorkspace';

type Props = Pick<
  EvaluationWorkspace,
  | 'active'
  | 'working'
  | 'savingCategory'
  | 'resetDialog'
  | 'goTo'
  | 'items'
  | 'categoryCount'
  | 'totals'
  | 'result'
>;

export function DashboardPage({
  active,
  working,
  savingCategory,
  resetDialog,
  goTo,
  items,
  categoryCount,
  totals,
  result,
}: Props) {
  return (
    <section className="page-section overview-section" id="ringkasan" hidden={active !== 'ringkasan'}>
      <div className="page-hero">
        <div>
          <span className="eyebrow">DASHBOARD · WORKSPACE EVALUASI</span>
          <h1>
            Evaluasi Dokumen <span>Permohonan</span>
          </h1>
          <div className="hero-scope-subtitle">Industri</div>
          <p>
            Pusat pemeriksaan dokumen, perbandingan data formulir, dan penelusuran hasil matching per
            kategori.
          </p>
        </div>
        <div className="hero-actions">
          <button
            className="button button-new-evaluation hero-button"
            disabled={working || savingCategory}
            onClick={() => resetDialog.current?.showModal()}
          >
            <RotateCcw size={17} aria-hidden="true" />
            Mulai Evaluasi Baru
          </button>
          <button className="button button-primary hero-button" onClick={() => goTo('upload')}>
            Upload Dokumen <ArrowRight size={17} />
          </button>
        </div>
      </div>
      <div className="summary-grid">
        <SummaryCard
          icon={<FolderOpen size={25} />}
          label="Dokumen di permohonan"
          value={items.length}
          note={`${categoryCount} dari ${CATEGORIES.length} kategori terisi`}
          tone="rose"
        />
        <SummaryCard
          icon={<CheckCircle2 size={25} />}
          label="Field MATCH"
          value={totals.match}
          note={`${totals.percentage.toFixed(1)}% dari ${totals.compared} field dengan acuan formulir`}
          tone="green"
        />
        <SummaryCard
          icon={<FileClock size={25} />}
          label="Perlu Review"
          value={totals.review}
          note="Belum terkonfirmasi di sumber"
          tone="amber"
        />
        <SummaryCard
          icon={<AlertCircle size={25} />}
          label="Mismatch"
          value={totals.mismatch}
          note="Perbedaan identitas yang terdeteksi"
          tone="red"
        />
      </div>
      <div className="overview-banner">
        <div className="overview-banner-icon">
          <Info size={19} />
        </div>
        <p>
          <strong>{result ? 'Hasil evaluasi dokumen tersedia.' : 'Belum ada hasil analisis.'}</strong>{' '}
          {result
            ? `${result.analyzed_documents} dokumen dianalisis; ${result.errors.length} gagal. Field REVIEW memerlukan pemeriksaan evaluator.`
            : 'Unggah dokumen melalui menu Upload Dokumen, lalu klik Mulai Analisis. Ringkasan hasil akan muncul di sini setelah analisis selesai.'}
        </p>
        {result && (
          <button className="text-action" onClick={() => goTo('matching')}>
            Lihat hasil analisis <ArrowRight size={15} />
          </button>
        )}
      </div>
    </section>
  );
}
