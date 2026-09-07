'use client';

import { useTranslations } from 'next-intl';

type TissueEntry = { tissue: string; mean: number; max?: number; count?: number };

export default function TissueBarChart({ tissues }: { tissues: TissueEntry[] }) {
  const t = useTranslations('fields');
  if (!tissues || tissues.length === 0) {
    return (
      <div className="text-xs text-slate-500 bg-slate-50 rounded-lg px-4 py-6 text-center">
        {t('noTissueData')}
      </div>
    );
  }

  const ordered = [...tissues].sort((a, b) => (b.mean ?? 0) - (a.mean ?? 0));
  const topTissue = ordered[0]?.tissue;
  const maxMean = Math.max(...ordered.map((r) => Number(r.mean) || 0), 0.001);

  return (
    <div className="space-y-1.5" role="img" aria-label={t('meanFpkm')}>
      {ordered.map((r) => {
        const mean = Number(r.mean) || 0;
        const pct = Math.max(0, Math.min(100, (mean / maxMean) * 100));
        const isTop = r.tissue === topTissue;
        return (
          <div key={r.tissue} className="flex items-center gap-2 text-xs">
            <div
              className="w-[7.5rem] shrink-0 text-right text-slate-600 truncate"
              title={r.tissue}
            >
              {r.tissue}
            </div>
            <div className="flex-1 h-4 rounded-sm bg-slate-100 overflow-hidden min-w-0">
              <div
                className="h-full rounded-sm transition-[width] duration-300"
                style={{
                  width: `${pct}%`,
                  backgroundColor: isTop ? '#B01A75' : '#0D9488',
                }}
                title={`${r.tissue}: ${mean.toFixed(1)} FPKM`}
              />
            </div>
            <div className="w-14 shrink-0 font-mono text-slate-700 text-right tabular-nums">
              {mean.toFixed(1)}
            </div>
          </div>
        );
      })}
      <div className="pt-1 text-[10px] text-slate-400 text-right">{t('meanFpkm')}</div>
    </div>
  );
}
