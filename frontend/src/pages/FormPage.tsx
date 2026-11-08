import { Home, Info, Layers3, UsersRound } from 'lucide-react';
import { Accordion, DataPair, SectionHeading } from '../components/Common';
import type { EvaluationWorkspace } from '../hooks/useEvaluationWorkspace';

type Props = Pick<
  EvaluationWorkspace,
  'active' | 'displayForm' | 'formNeedsReview' | 'formOpen' | 'toggleForm' | 'reviewBadge'
>;

export function FormPage({ active, displayForm, formNeedsReview, formOpen, toggleForm, reviewBadge }: Props) {
  return (
    <section className="page-section" id="formulir" hidden={active !== 'formulir'}>
      <SectionHeading
        eyebrow="LANGKAH 02"
        title="Formulir Permohonan"
        description="Ringkasan data acuan untuk mencocokkan informasi pada dokumen pendukung."
        action={
          <span className="outline-label">
            <Info size={14} />
            {displayForm ? 'Data tersedia' : 'Belum dianalisis'}
          </span>
        }
      />
      <div className="form-overview-grid">
        <div className="form-stat">
          <span className="form-stat-icon tone-blue">
            <UsersRound size={25} />
          </span>
          <div>
            <small>Total Personel</small>
            <strong>{displayForm?.personnel.length ?? 0}</strong>
            <span>Data formulir</span>
          </div>
        </div>
        <div className="form-stat">
          <span className="form-stat-icon tone-green">
            <Layers3 size={25} />
          </span>
          <div>
            <small>Total Peralatan</small>
            <strong>{displayForm?.equipment.length ?? 0}</strong>
            <span>Pesawat sinar-X</span>
          </div>
        </div>
      </div>
      {Object.values(formNeedsReview).some(Boolean) && (
        <div className="form-controls">
          <span>Data belum lengkap terbaca. Periksa kembali dengan dokumen formulir.</span>
        </div>
      )}
      <div className="surface form-surface">
        <Accordion
          title="Informasi Instansi"
          icon={<Home size={20} />}
          open={formOpen.facility}
          onToggle={() => toggleForm('facility')}
          count={reviewBadge(formNeedsReview.facility)}
        >
          <div className="facility-info">
            <DataPair label="Nama instansi" value={displayForm?.institution || '—'} />
            <DataPair label="Alamat proyek" value={displayForm?.address || '—'} />
            <DataPair label="Nomor Program Proteksi" value={displayForm?.protectionDocument?.number || '—'} />
            <DataPair
              label="Tanggal pengesahan Program Proteksi"
              value={displayForm?.protectionDocument?.date || '—'}
            />
          </div>
        </Accordion>
        <Accordion
          title="Data Personel"
          icon={<UsersRound size={20} />}
          open={formOpen.personnel}
          onToggle={() => toggleForm('personnel')}
          count={reviewBadge(formNeedsReview.personnel)}
        >
          {!displayForm?.personnel.length && (
            <p>
              {displayForm
                ? 'Data personel belum terbaca. Periksa dokumen formulir.'
                : 'Belum ada hasil analisis formulir.'}
            </p>
          )}
          <div className="list-data">
            {(displayForm?.personnel ?? []).map((p, i) => (
              <div key={`${p.name}-${i}`} className="list-data-row">
                <span className="numbered">{i + 1}</span>
                <div>
                  <strong>{p.name}</strong>
                  <small>
                    {p.role?.trim() ? `Keahlian: ${p.role}` : 'Keahlian tidak tercantum dalam formulir'}
                  </small>
                </div>
              </div>
            ))}
          </div>
        </Accordion>
        <Accordion
          title="Data Peralatan"
          icon={<Layers3 size={20} />}
          open={formOpen.equipment}
          onToggle={() => toggleForm('equipment')}
          count={reviewBadge(formNeedsReview.equipment)}
        >
          {!displayForm?.equipment.length && (
            <p>
              {displayForm
                ? 'Data peralatan belum terbaca. Periksa dokumen formulir.'
                : 'Belum ada hasil analisis formulir.'}
            </p>
          )}
          <div className="equipments-grid">
            {(displayForm?.equipment ?? []).map((e) => (
              <article key={e.label} className="equipment-card">
                <div className="equipment-head">
                  <strong>{e.label}</strong>
                  <span>{e.tipe_unit}</span>
                </div>
                <DataPair label="Merek unit" value={e.merk_unit} />
                <DataPair label="Nomor seri unit" value={e.nomor_seri_unit} />
                <DataPair label="Merek tabung" value={e.merk_tabung} />
                <DataPair label="Tipe tabung" value={e.tipe_tabung} />
                <DataPair label="Nomor seri insersi tabung" value={e.nomor_seri_tabung} />
              </article>
            ))}
          </div>
        </Accordion>
      </div>
    </section>
  );
}
