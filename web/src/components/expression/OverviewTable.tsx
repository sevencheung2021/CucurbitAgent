'use client';

import type { ExpressionOverviewSpecies } from '@/lib/api';
import { useTranslations } from 'next-intl';

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function reliabilityColor(stars: string): string {
  if (stars === '★★★') return 'text-emerald-600 bg-emerald-50';
  if (stars === '★★') return 'text-teal-600 bg-teal-50';
  if (stars === '★') return 'text-amber-600 bg-amber-50';
  return 'text-slate-500 bg-slate-100';
}

export default function OverviewTable({ species }: { species: ExpressionOverviewSpecies[] }) {
  const t = useTranslations('fields');
  if (!species || species.length === 0) {
    return (
      <div className="text-xs text-slate-500 bg-slate-50 rounded-lg px-4 py-3 text-center">
        No overview data
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-[#E2E8F0]">
      <table className="min-w-full text-xs">
        <thead className="bg-gradient-to-r from-[#F0FDFA] to-[#ECFDF5] text-[#0F766E]">
          <tr>
            <th className="text-left px-3 py-2.5 font-semibold">{t('species')}</th>
            <th className="text-right px-3 py-2.5 font-semibold">{t('genes')}</th>
            <th className="text-right px-3 py-2.5 font-semibold">{t('samples')}</th>
            <th className="text-right px-3 py-2.5 font-semibold">{t('projects')}</th>
            <th className="text-right px-3 py-2.5 font-semibold">{t('tissues')}</th>
            <th className="text-right px-3 py-2.5 font-semibold">{t('rows')}</th>
            <th className="text-center px-3 py-2.5 font-semibold">{t('reliability')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#E2E8F0]">
          {species.map((s) => (
            <tr key={s.species_dir} className={`hover:bg-slate-50 ${!s.data_available ? 'opacity-50' : ''}`}>
              <td className="px-3 py-2">
                <div className="font-medium text-slate-800">{s.label}</div>
                {!s.data_available && <div className="text-[10px] text-amber-600">data not parsed</div>}
              </td>
              <td className="px-3 py-2 text-right font-mono text-slate-700">{formatNumber(s.genes)}</td>
              <td className="px-3 py-2 text-right font-mono text-slate-700">{formatNumber(s.samples)}</td>
              <td className="px-3 py-2 text-right font-mono text-slate-700">{s.projects}</td>
              <td className="px-3 py-2 text-right font-mono text-slate-700">{s.tissues}</td>
              <td className="px-3 py-2 text-right font-mono text-slate-500">{formatNumber(s.rows)}</td>
              <td className="px-3 py-2 text-center">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-bold ${reliabilityColor(s.reliability)}`}
                  title={
                    s.reliability === '★★★'
                      ? 'reliable for tissue + co-expression'
                      : s.reliability === '★★'
                      ? 'tissue reliable; co-expression reasonable'
                      : s.reliability === '★'
                      ? 'tissue reliable; co-expression weak reference'
                      : 'sample count too low; co-expression unreliable'
                  }
                >
                  {s.reliability}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
