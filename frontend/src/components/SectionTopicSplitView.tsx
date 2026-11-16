import { useState, type ReactNode } from 'react';
import type { MatchRow } from '../types/models';
import type { ProtectionTabKey, SectionTopicTab } from '../lib/protectionDisplay';
import { ManagementCard } from './ManagementInformation';
import { ProtectionInformationCards } from './ProtectionEvidence';
import { SourceDocumentViewer } from './SourceDocumentViewer';

export function SectionTopicSplitView({
  category,
  tabs,
  renderComparison,
  openEvidence,
  loadSourceDocument,
}: {
  category: 'proteksi' | 'manajemen';
  tabs: SectionTopicTab[];
  renderComparison: () => ReactNode;
  openEvidence: (documentId: string, page?: number) => void;
  loadSourceDocument: (documentId: string) => Promise<Blob>;
}) {
  const [activeKey, setActiveKey] = useState('');
  const [source, setSource] = useState<{
    documentId: string;
    page?: number;
    title: string;
    imageOnly?: boolean;
  } | null>(null);

  if (!tabs.length) {
    return <p className="matching-filter-empty">Tidak ada field yang sesuai pencarian atau filter.</p>;
  }

  const activeTab = tabs.find((tab) => tab.key === activeKey) ?? tabs[0];
  const label = category === 'proteksi' ? 'Program Proteksi' : 'Sistem Manajemen';

  return (
    <div className="personnel-documents">
      <aside className="personnel-doc-sidebar">
        <div className="personnel-doc-list-title">Bagian Evaluasi ({tabs.length})</div>
        <div className="personnel-doc-tabs" role="tablist" aria-label={`Bagian ${label}`}>
          {tabs.map((tab) => {
            const isActive = tab.key === activeTab.key;
            const showBadge = tab.status === 'REVIEW' || tab.status === 'MISMATCH';
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`personnel-doc-tab ${isActive ? 'active' : ''}`}
                onClick={() => setActiveKey(tab.key)}
              >
                <div className="doc-tab-top">
                  <span
                    className={`doc-tab-status-dot status-dot-${tab.status.toLowerCase()}`}
                    aria-hidden="true"
                  />
                  <span className="doc-tab-title">{tab.label}</span>
                  {showBadge && (
                    <span className="doc-tab-badges">
                      <span className={`doc-tab-badge-status status-${tab.status.toLowerCase()}`}>
                        {tab.status === 'MISMATCH' ? 'Mismatch' : 'Review'}
                      </span>
                    </span>
                  )}
                </div>
                <div className="doc-tab-owner">{tab.subtitle}</div>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="personnel-doc-content" key={activeTab.key} role="tabpanel">
        <div className="personnel-doc-header">
          <div className="personnel-doc-title-group">
            <h3>{activeTab.headerTitle}</h3>
          </div>
        </div>

        {activeTab.key === 'perbandingan' ? (
          renderComparison()
        ) : category === 'proteksi' ? (
          <div className="protection-tab-panel">
            <ProtectionInformationCards
              tabKey={activeTab.key as ProtectionTabKey}
              rows={activeTab.rows}
              openEvidence={(documentId, page, title) => setSource({ documentId, page, title })}
            />
          </div>
        ) : (
          <div className="protection-tab-panel">
            {activeTab.rows.map((row: MatchRow) => (
              <ManagementCard
                key={row.id}
                row={row}
                open={(page) =>
                  row.document_id &&
                  setSource({
                    documentId: row.document_id,
                    page,
                    title: row.field,
                    imageOnly: row.detail?.group === 'Pengesahan',
                  })
                }
              />
            ))}
          </div>
        )}
      </section>

      {source?.documentId && (
        <SourceDocumentViewer
          documentId={source.documentId}
          page={source.page}
          title={source.title}
          imageOnly={source.imageOnly}
          loadDocument={loadSourceDocument}
          openExternal={openEvidence}
          close={() => setSource(null)}
        />
      )}
    </div>
  );
}
