import { FileText } from 'lucide-react';
import type { DocumentType, IndexedDocument } from '../types';

const TYPE_LABEL: Record<DocumentType, string> = {
  CG: 'Conditions générales',
  CP: 'Conditions particulières',
  AVENANT: 'Avenant',
  ANNEXE: 'Annexe',
};

export function ContractCard({ documents }: { documents: IndexedDocument[] }) {
  if (documents.length === 0) return null;

  return (
    <section className="contract" aria-label="Documents indexés">
      <div className="contract__head">
        <div>
          <p className="contract__name">Documents indexés</p>
          <p className="contract__meta">{documents.length} document{documents.length === 1 ? '' : 's'} disponibles pour cette conversation</p>
        </div>
      </div>
      <ul className="contract__list">
        {documents.map((document) => (
          <li key={document.documentId} className="contract__item">
            <FileText size={16} aria-hidden="true" />
            <span className="contract__item-copy">
              <span className="contract__item-name">{document.filename}</span>
              <span className="contract__meta">{TYPE_LABEL[document.documentType]} · {document.pageCount} page{document.pageCount === 1 ? '' : 's'}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
