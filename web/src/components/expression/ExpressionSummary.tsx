'use client';

import type { GeneExpressionResult } from '@/lib/api';
import { useTranslations } from 'next-intl';

function StatBox({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-[#E2E8F0] bg-white px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className="text-base font-semibold text-slate-800">{value}</div>
      {hint && <div className="text-[10px] text-slate-500">{hint}</div>}
    </div>
  );
}

export default function ExpressionSummary({ data }: { data: GeneExpressionResult }) {
  const t = useTranslations('fields');
  const tau = data.tau_specificity;
  // tau >= 0.9: highly specific; 0.6-0.9: moderate; <0.6: ubiquitous
  const specificityLabel =
    tau === null || tau === undefined
      ? 'N/A'
      : tau >= 0.85
      ? 'Highly tissue-specific'
      : tau >= 0.6
      ? 'Moderately specific'
      : 'Broadly expressed';

  const reliabilityColor =
    data.reliability === '★★★'
      ? 'bg-emerald-50 text-emerald-700'
      : data.reliability === '★★'
      ? 'bg-teal-50 text-teal-700'
      : data.reliability === '★'
      ? 'bg-amber-50 text-amber-700'
      : 'bg-slate-100 text-slate-600';

  return (
    <div className="rounded-xl border border-[#E2E8F0] bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xs text-slate-500">{data.species_label}</div>
          <div className="text-lg font-bold font-mono text-slate-900">{data.gene_id}</div>
        </div>
        <span
          className={`inline-block rounded-full px-3 py-1 text-xs font-bold ${reliabilityColor}`}
          title={t('reliabilityHint')}
        >
          {data.reliability}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <StatBox label={t('samples')} value={data.n_samples} hint={t('projectsHint', { n: data.n_projects })} />
        <StatBox label={t('meanFpkm')} value={data.mean_fpkm} />
        <StatBox label={t('maxFpkm')} value={data.max_fpkm} />
        <StatBox
          label="τ Specificity"
          value={tau === null || tau === undefined ? '—' : tau.toFixed(3)}
          hint={specificityLabel}
        />
      </div>

      <div className="rounded-lg bg-gradient-to-r from-[#F0FDFA] to-[#ECFDF5] border border-[#CCFBF1] px-3 py-2">
        <div className="text-[10px] uppercase tracking-wider text-[#0F766E]">{t('topTissue')}</div>
        <div className="text-sm font-semibold text-[#134E4A]">
          {data.top_tissue || '—'}
          {data.top_tissue_fpkm !== null && data.top_tissue_fpkm !== undefined && (
            <span className="ml-2 text-xs text-slate-500 font-normal">
              mean {data.top_tissue_fpkm.toFixed(1)} FPKM
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
