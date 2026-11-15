import { CheckCircle2, CircleAlert } from 'lucide-react';

export function EvidenceStatus({
  found,
  partial = false,
  review = false,
  foundLabel = 'Ditemukan',
}: {
  found: boolean;
  partial?: boolean;
  review?: boolean;
  foundLabel?: string;
}) {
  found = found && !review;
  return (
    <span className={`law-presence ${found ? 'law-presence-found' : 'law-presence-missing'}`}>
      {found ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}
      {review ? 'Perlu diperiksa' : found ? foundLabel : partial ? 'Belum lengkap' : 'Belum ditemukan'}
    </span>
  );
}
