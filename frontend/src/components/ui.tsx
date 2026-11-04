import { useEffect, useRef, type ReactNode } from 'react';
import { LoaderCircle, X } from 'lucide-react';

export const Spinner = ({ size = 16 }: { size?: number }) => (
  <LoaderCircle className="spin" size={size} aria-hidden="true" />
);

/** Modale basée sur <dialog> natif : focus piégé, Échap et inertie du fond gérés par le navigateur. */
export function Dialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-label={title}
      onClose={onClose}
      onMouseDown={(e) => e.target === ref.current && onClose()}
    >
      {open && (
        <div className="dialog__panel">
          <header className="dialog__head">
            <h2>{title}</h2>
            <button className="icon-btn" aria-label="Fermer" onClick={onClose}>
              <X size={18} />
            </button>
          </header>
          {children}
        </div>
      )}
    </dialog>
  );
}
