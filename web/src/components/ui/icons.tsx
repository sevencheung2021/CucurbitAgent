/**
 * Lightweight inline SVG icons — zero dependencies.
 *
 * Path data adapted from Lucide (ISC license) — the same shapes you'd get
 * from `lucide-react`, but without pulling the package. Add new icons here
 * as needed; keep stroke-width consistent with the design system (1.75).
 *
 * Usage:
 *   <HomeIcon className="size-4" />
 *   <DnaIcon className="size-5 text-brand-600" />
 */

import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & {
  title?: string;
};

const base = (props: IconProps) => ({
  xmlns: 'http://www.w3.org/2000/svg',
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': props.title ? undefined : true,
  role: props.title ? 'img' : undefined,
  ...props,
  className: props.className,
});

// --- Navigation icons ---

export function HomeIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M3 9.5 12 3l9 6.5" />
      <path d="M5 10v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V10" />
      <path d="M9 21v-6h6v6" />
    </svg>
  );
}

export function BotIcon(props: IconProps) {
  // CucurbitAgent — robot/assistant
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <rect x="4" y="8" width="16" height="12" rx="2" />
      <path d="M12 8V4" />
      <circle cx="12" cy="3" r="1" />
      <circle cx="9" cy="13" r="1" />
      <circle cx="15" cy="13" r="1" />
      <path d="M9 17h6" />
      <path d="M2 14h2" />
      <path d="M20 14h2" />
    </svg>
  );
}

export function DnaIcon(props: IconProps) {
  // Genes
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M2 15c6.667-6 13.333 0 20-6" />
      <path d="M9 22c1.798-1.998 2.518-3.995 2.807-5.993" />
      <path d="M15 2c-1.798 1.998-2.518 3.995-2.807 5.993" />
      <path d="m17 6-2.5-2.5" />
      <path d="m14 8-1-1" />
      <path d="m7 18 2.5 2.5" />
      <path d="m3.5 14.5.5.5" />
      <path d="m20 9 .5.5" />
      <path d="m6.5 12.5 1 1" />
      <path d="m16.5 10.5 1 1" />
      <path d="m10 16 1.5 1.5" />
    </svg>
  );
}

export function BarChart3Icon(props: IconProps) {
  // Expression
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M3 3v18h18" />
      <rect x="7" y="11" width="3" height="6" />
      <rect x="12" y="7" width="3" height="10" />
      <rect x="17" y="13" width="3" height="4" />
    </svg>
  );
}

export function MicroscopeIcon(props: IconProps) {
  // Proteins
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M6 18h8" />
      <path d="M3 22h18" />
      <path d="M14 22a7 7 0 1 0 0-14h-1" />
      <path d="M9 14h2" />
      <path d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2Z" />
      <path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3" />
    </svg>
  );
}

export function BookOpenIcon(props: IconProps) {
  // Literatures
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M12 7v14" />
      <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
    </svg>
  );
}

export function DownloadIcon(props: IconProps) {
  // Genomes / Download
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

export function MessageSquareIcon(props: IconProps) {
  // Feedback
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

// --- Action icons ---

export function MenuIcon(props: IconProps) {
  // Hamburger
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  // X / close drawer
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

// --- Status & feedback icons ---

export function SearchIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

export function SparklesIcon(props: IconProps) {
  // AI / ✨ — used for AI Summary, AI Chat buttons
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
      <path d="m5.6 5.6 2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}

export function WarningIcon(props: IconProps) {
  // ⚠️ — filled triangle with !
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  // ✓ — used for "Copied" state
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export function LinkIcon(props: IconProps) {
  // 🔗 — external/hyperlink
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

export function TargetIcon(props: IconProps) {
  // 🎯 — top samples / binding sites
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  );
}

export function FlaskConicalIcon(props: IconProps) {
  // ⚗️ / experimental chemistry — also used for "Protein" sometimes
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M9 2h6" />
      <path d="M10 2v6.5L4.4 18.4a2 2 0 0 0 1.7 3.1h11.8a2 2 0 0 0 1.7-3.1L14 8.5V2" />
      <path d="M7.5 14h9" />
    </svg>
  );
}

export function ClipboardListIcon(props: IconProps) {
  // 📋 — overview / gene record title
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <rect x="8" y="2" width="8" height="4" rx="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <path d="M9 12h.01M9 16h.01M13 12h6M13 16h6" />
    </svg>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  // ➤ — composer send button (replaces ➤ char)
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}

// --- Contact icons (Footer) ---

export function MapPinIcon(props: IconProps) {
  // 📍
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

export function PhoneIcon(props: IconProps) {
  // ☎
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  );
}

export function MailIcon(props: IconProps) {
  // ✉
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

// --- Visit stats (Footer) ---

export function GlobeIcon(props: IconProps) {
  // 🌍 — Global Reach / visit stats
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

export function TrendingUpIcon(props: IconProps) {
  // today's visit growth
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  );
}

// --- Misc ---

export function PuzzleIcon(props: IconProps) {
  // 🧩 — Pfam domain architecture
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.61 1.61a2.404 2.404 0 0 1-1.705.707 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.23 8.77c.24-.24.581-.353.917-.303.515.077.877.528 1.073 1.01a2.5 2.5 0 1 0 3.259-3.259c-.482-.196-.933-.558-1.01-1.073-.05-.336.062-.676.303-.917l1.525-1.525A2.402 2.402 0 0 1 12 1.998c.617 0 1.234.236 1.704.706l1.568 1.568c.23.23.556.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02Z" />
    </svg>
  );
}

export function FileTextIcon(props: IconProps) {
  // 📝 — Sequence info
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="16" y2="17" />
    </svg>
  );
}

export function RefreshCwIcon(props: IconProps) {
  // 🔄 — version mapping
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}

export function InfoIcon(props: IconProps) {
  // 💡 / informational
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

export function MousePointerClickIcon(props: IconProps) {
  // 🖱️ — interaction hint
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="m9 9 5 12 1.8-5.2L21 14Z" />
      <path d="M7.2 2.2 8 5.1M5.1 8 2.2 7.2M14 4.1 12 6M6 12l-1.9 2" />
    </svg>
  );
}

export function NetworkIcon(props: IconProps) {
  // 🌐 — Plant Orthologs (global network)
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <rect x="9" y="2" width="6" height="6" rx="1" />
      <rect x="2" y="16" width="6" height="6" rx="1" />
      <rect x="16" y="16" width="6" height="6" rx="1" />
      <path d="M12 8v4M12 12H5v4M12 12h7v4" />
    </svg>
  );
}

export function TagIcon(props: IconProps) {
  // 🏷️ — labels / GO terms
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" />
      <circle cx="7.5" cy="7.5" r="1.5" />
    </svg>
  );
}

export function AtomIcon(props: IconProps) {
  // ⚛️ — atom symbol, for Pfam domain architecture
  return (
    <svg {...base(props)}>
      {props.title && <title>{props.title}</title>}
      <circle cx="12" cy="12" r="1" />
      <path d="M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5Z" />
      <path d="M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5Z" />
    </svg>
  );
}
