'use client';

import { BarChart3Icon, WarningIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

/**
 * Compact expression profile panel for the Agent chat.
 *
 * Layout mirrors GeneDataCard: LLM summary renders above, this is the
 * supporting evidence card. Plain text + simple bar chart of tissue FPKM,
 * no heavy visualization components.
 *
 * Props shape from /api/expression/gene.
 */
function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-xs">
      <span className="text-slate-400 min-w-[110px] flex-shrink-0">{label}</span>
      <span className="text-slate-700">{children ?? '—'}</span>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] font-semibold text-[#0F766E] uppercase tracking-wider mb-1.5">
        {title}{typeof count === 'number' ? ` (${count})` : ''}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function fmt1(n: any): string {
  const x = Number(n);
  return Number.isFinite(x) ? x.toFixed(1) : '—';
}

export default function ExpressionDataCard({ data }: { data: any }) {
  const t = useTranslations('cards');
  const tf = useTranslations('fields');
  if (!data || data.status !== 'success') {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 flex items-start gap-2">
        <WarningIcon className="size-4 shrink-0 mt-[1px]" />
        <span>{data?.message || 'No expression data for this gene.'}</span>
      </div>
    );
  }

  const tissues = (data.tissue_profile || []).slice(0, 8);
  const maxFpkm = Math.max(...tissues.map((t: any) => t.mean || 0), 1);
  const topSamples = (data.top_samples || []).slice(0, 5);
  const conds = (data.condition_distribution || []).slice(0, 4);

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 overflow-hidden">
      <div className="px-3 py-1.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700 inline-flex items-center gap-1.5">
          <BarChart3Icon className="size-3.5 text-[#0D9488]" />
          {data.gene_id} <span className="text-slate-400 font-normal">· {data.species_common}</span>
        </span>
        <span className="text-[10px] text-slate-400">{data.reliability} · {data.n_samples} samples</span>
      </div>

      <div className="p-3 space-y-3">
        {/* Headline stats */}
        <Section title={t('specificity')}>
          <Cell label={tf('topTissue')}>{data.top_tissue} <span className="text-[#0F766E]">({fmt1(data.top_tissue_fpkm)} FPKM)</span></Cell>
          <Cell label={t('meanMax')}>{fmt1(data.mean_fpkm)} / {fmt1(data.max_fpkm)} FPKM</Cell>
          <Cell label={t('tauSpecificity')}>{fmt1(data.tau_specificity)} <span className="text-slate-400">({Number(data.tau_specificity) > 0.8 ? t('tissueSpecific') : Number(data.tau_specificity) > 0.6 ? t('moderatelySpecific') : t('ubiquitous')})</span></Cell>
          <Cell label={t('samplesProjects')}>{data.n_samples} / {data.n_projects}</Cell>
        </Section>

        {/* Tissue profile — simple horizontal bars */}
        {tissues.length > 0 && (
          <Section title={t('tissueFpkm')}>
            {tissues.map((t: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="text-slate-600 w-28 truncate flex-shrink-0">{t.tissue}</span>
                <div className="flex-1 h-3 bg-slate-200 rounded-sm overflow-hidden">
                  <div
                    className="h-full bg-[#0D9488] rounded-sm"
                    style={{ width: `${Math.max(4, (t.mean / maxFpkm) * 100)}%` }}
                  />
                </div>
                <span className="text-slate-500 tabular-nums w-12 text-right">{fmt1(t.mean)}</span>
              </div>
            ))}
          </Section>
        )}

        {/* Condition distribution — compact inline */}
        {conds.length > 0 && (
          <Section title={t('conditions')}>
            <div className="text-xs text-slate-600">
              {conds.map((c: any, i: number) => (
                <span key={i}>
                  {i > 0 && ' · '}
                  {c.condition} <span className="text-slate-400">{c.count}</span>
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* Top samples — mini table */}
        {topSamples.length > 0 && (
          <Section title={t('topSamples')} count={(data.top_samples || []).length}>
            {topSamples.map((s: any, i: number) => (
              <div key={i} className="flex justify-between text-xs gap-2">
                <span className="text-slate-700 truncate">
                  {s.tissue} <span className="text-slate-400">{s.condition}</span>
                </span>
                <span className="text-[#0F766E] tabular-nums flex-shrink-0">{fmt1(s.fpkm)}</span>
              </div>
            ))}
          </Section>
        )}
      </div>
    </div>
  );
}
