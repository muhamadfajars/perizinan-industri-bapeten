import { Activity, AlertCircle, CircleHelp, FileCheck2, LoaderCircle, Search } from 'lucide-react';
import { SectionHeading } from '../components/Common';
import { MatchingSection } from '../components/MatchingSection';
import type { EvaluationWorkspace } from '../hooks/useEvaluationWorkspace';
import { analysisDateLabel } from '../lib/presentation';
import { Filter } from '../types/workspace';

type Props = Pick<
  EvaluationWorkspace,
  | 'active'
  | 'result'
  | 'query'
  | 'setQuery'
  | 'filter'
  | 'setFilter'
  | 'filterTotals'
  | 'working'
  | 'progressTitle'
  | 'progressMessage'
  | 'analysisProgress'
  | 'analysisStage'
  | 'backendError'
  | 'goTo'
  | 'visibleMatchingSections'
  | 'setSelectedDetail'
>;

export function MatchingPage({
  active,
  result,
  query,
  setQuery,
  filter,
  setFilter,
  filterTotals,
  working,
  progressTitle,
  progressMessage,
  analysisProgress,
  analysisStage,
  backendError,
  goTo,
  visibleMatchingSections,
  setSelectedDetail,
}: Props) {
  return (
    <section className="page-section" id="matching" hidden={active !== 'matching'}>
      <SectionHeading
        eyebrow="LANGKAH 03"
        title="Hasil Matching"
        description="Perbandingan data Formulir dan Dokumen, dengan status MATCH, REVIEW, atau MISMATCH per field."
        action={
          result ? (
            <span className="outline-label">
              <FileCheck2 size={14} /> {result.analyzed_documents} dokumen dianalisis
            </span>
          ) : undefined
        }
      />
      <div className="surface matching-surface">
        {result && (
          <div className="matching-toolbar">
            <div className="match-toolbar-summary">
              <strong>Hasil Validasi Dokumen</strong>
              <p>{`Selesai dianalisis pada ${analysisDateLabel(result.finished_at)}`}</p>
            </div>
            <div className="filter-group">
              <label className="search-field">
                <Search size={17} />
                <input
                  type="search"
                  placeholder="Cari field atau nilai..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <div className="filter-buttons" role="group" aria-label="Filter status">
                {(['ALL', 'MATCH', 'REVIEW', 'MISMATCH'] as Filter[]).map((f) => (
                  <button
                    key={f}
                    className={filter === f ? 'active' : ''}
                    aria-pressed={filter === f}
                    onClick={() => setFilter(f)}
                  >
                    {f === 'ALL' ? 'Semua' : f === 'MATCH' ? 'Match' : f === 'REVIEW' ? 'Review' : 'Mismatch'}{' '}
                    (
                    {f === 'ALL'
                      ? filterTotals.total
                      : f === 'MATCH'
                        ? filterTotals.match
                        : f === 'REVIEW'
                          ? filterTotals.review
                          : filterTotals.mismatch}
                    )
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        {working && (
          <div className="analysis-progress">
            <div className="analysis-progress-heading">
              <LoaderCircle className="analysis-spinner" size={28} aria-hidden="true" />
              <div role="status">
                <strong>{progressTitle}</strong>
                <p>{progressMessage}</p>
              </div>
            </div>
            <div
              className={`progress-track ${analysisProgress === undefined ? 'progress-indeterminate' : ''}`}
              role="progressbar"
              aria-label={analysisStage === 'uploading' ? 'Pengiriman dokumen' : 'Progres analisis'}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={analysisProgress}
              aria-valuetext={progressMessage}
            >
              <span style={analysisProgress === undefined ? undefined : { width: `${analysisProgress}%` }} />
            </div>
            {analysisProgress !== undefined && <small>{analysisProgress}%</small>}
            <p className="analysis-progress-hint">Anda dapat membuka menu lain. Proses tetap berjalan.</p>
          </div>
        )}
        {backendError && !working && (
          <div className="analysis-error" role="alert">
            <AlertCircle size={24} />
            <div>
              <strong>Analisis belum berhasil diselesaikan</strong>
              <p>{backendError}</p>
              <button className="button button-soft" type="button" onClick={() => goTo('upload')}>
                Kembali ke Upload
              </button>
            </div>
          </div>
        )}
        {result?.warnings?.length ? (
          <div className="analysis-errors">
            <strong>Peringatan parser formulir</strong>
            {result.warnings.map((e, i) => (
              <p key={i}>{e}</p>
            ))}
          </div>
        ) : null}
        {result?.errors?.length ? (
          <div className="analysis-errors">
            <strong>{result.errors.length} dokumen gagal diekstrak</strong>
            {result.errors.map((e, idx) => (
              <p key={`${e.document_id}-${idx}`}>
                {e.filename}: {e.error}
              </p>
            ))}
          </div>
        ) : null}
        {!working && !result && !backendError && (
          <div className="analysis-empty">
            <Activity size={35} />
            <strong>Belum ada hasil matching</strong>
            <p>
              Unggah berkas permohonan, kemudian klik Mulai Analisis untuk melihat hasil verifikasi dokumen.
            </p>
            <button className="button button-soft" onClick={() => goTo('upload')}>
              Ke halaman Upload
            </button>
          </div>
        )}
        <div className="matching-sections">
          {visibleMatchingSections.map((s, i) => (
            <MatchingSection
              key={`${filter}:${s.id}`}
              section={s}
              search={query}
              filter={filter}
              onRowClick={(row, section) => setSelectedDetail({ row, section })}
              expandedByDefault={i === 0}
            />
          ))}
          {result && visibleMatchingSections.length === 0 && (
            <div className="matching-filter-empty">
              Tidak ada field dengan status atau kata kunci yang dipilih.
            </div>
          )}
        </div>
        <div className="matching-footer">
          <CircleHelp size={18} />
          <span>
            Status adalah hasil pencocokan data, <strong>bukan keputusan izin</strong>. Bukti pengesahan tetap
            memerlukan pemeriksaan evaluator.
          </span>
        </div>
      </div>
    </section>
  );
}
