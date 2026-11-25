import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  Box,
  ClipboardList,
  FileCheck2,
  FileText,
  FlaskConical,
  Gauge,
  Radiation,
  ScanLine,
  Settings2,
  ShieldCheck,
  Tag,
  UsersRound,
  Wrench,
} from 'lucide-react';

const mapping: Record<string, LucideIcon> = {
  file: FileText,
  shield: ShieldCheck,
  wrench: Wrench,
  settings: Settings2,
  gauge: Gauge,
  users: UsersRound,
  clipboard: ClipboardList,
  box: Box,
  scan: ScanLine,
  filecheck: FileCheck2,
  flask: FlaskConical,
  radiation: Radiation,
  activity: Activity,
  tag: Tag,
};

export default function Glyph({ name, className = '' }: { name: string; className?: string }) {
  const Icon = mapping[name] ?? FileText;
  return <Icon size={19} strokeWidth={2} className={className} />;
}
