import { CheckCircle2, CircleAlert } from 'lucide-react';

export function EvidenceStatus({ found, partial = false }: { found: boolean; partial?: boolean }) {
  return (
    <span className={`law-presence ${found ? 'law-presence-found' : 'law-presence-missing'}`}>
      {found ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}
      {found ? 'Ditemukan' : partial ? 'Belum lengkap' : 'Belum ditemukan'}
    </span>
  );
}
