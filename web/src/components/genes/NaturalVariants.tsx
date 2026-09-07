'use client';

import { useEffect, useState } from 'react';
import { fetchGeneVariants } from '@/lib/api';
import { DnaIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

type Props = { species: string; geneId: string; initial?: any };
const tabs = [
  ['all', 'tabOverview'],
  ['cds', 'tabCds'],
  ['non_cds', 'tabNonCds'],
] as const;
const filters = ['all', 'synonymous', 'missense', 'nonsense'] as const;
const palette: Record<string, string> = { Synonymous: '#94A3B8', Missense: '#B01A75', Nonsense: '#DC2626', 'Intron/UTR': '#0D9488', Other: '#64748B' };

export default function NaturalVariants({ species, geneId, initial }: Props) {
  const t = useTranslations('genes');
  const [tab, setTab] = useState<'all' | 'cds' | 'non_cds'>('all');
  const [filter, setFilter] = useState<'all' | 'synonymous' | 'missense' | 'nonsense'>('all');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<any>(initial);

  useEffect(() => {
    fetchGeneVariants(species, geneId, page, tab === 'all' ? 'all' : tab, tab === 'cds' ? filter : 'all').then(setData).catch(() => setData(null));
  }, [species, geneId, tab, filter, page]);

  // Species has a variant index, but this gene may have zero SNP/InDel rows.
  // Don't return null — parent <Card> would otherwise show an empty white box.
  if (!data?.summary?.total) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
        <p className="font-medium text-slate-700">{t('noVariants')}</p>
        <p className="mt-1 text-slate-500">
          {species} has a curated SNP / InDel index, but <code className="font-mono text-[#0D9488]">{geneId}</code> has
          no records in it (common for very short genes or loci outside the called set). Try another gene — e.g.
          Watermelon <code className="font-mono text-[#0D9488]">Cla97C08G154570</code>.
        </p>
      </div>
    );
  }
  const summary = data.summary;
  const max = Math.max(...(data.chart?.counts || [1]));

  return (
    <section className="mt-10">
      <h2 className="mb-6 text-3xl font-extrabold text-[#1a252f] inline-flex items-center gap-3">
        <DnaIcon className="size-7 text-[#0D9488]" /> Natural Variants
      </h2>
      <div className="grid grid-cols-4 gap-6 text-left mb-5">
        <Metric label={t('metricTotal')} value={summary.total} />
        <Metric label={t('metricCds')} value={summary.cds_total} />
        <Metric label={t('metricNonCds')} value={summary.non_cds} />
        <Metric label={t('metricProteinAltering')} value={summary.protein_altering} />
      </div>
      <p className="mb-8 text-sm text-[#64748B]">{t('cdsBreakdown', { synonymous: summary.synonymous, missense: summary.missense, nonsense: summary.nonsense })}</p>
      <div className="mb-4 flex justify-center gap-10 border-b border-[#DADDE1]">
        {tabs.map(([key, label]) => (
          <button key={key} onClick={() => { setTab(key); setPage(1); }} className={`pb-3 text-2xl font-extrabold border-b-4 ${tab === key ? 'text-[#B01A75] border-[#B01A75]' : 'text-[#1a252f] border-transparent'}`}>
            {t(label)}
          </button>
        ))}
      </div>
      {tab === 'all' ? (
        <div className="rounded-xl bg-white border border-[#E2E8F0] p-4 shadow-sm">
          <h3 className="mb-4 text-sm font-bold">{t('variantComposition')}</h3>
          <div className="space-y-5">
            {data.chart?.categories?.map((cat: string, i: number) => (
              <div key={cat} className="grid grid-cols-[110px_1fr_40px] items-center gap-3 text-sm">
                <span className="text-right text-[#64748B]">{cat}</span>
                <div className="relative h-10 border-l border-[#E2E8F0]">
                  <div className="h-full" style={{ width: `${(data.chart.counts[i] / max) * 100}%`, background: palette[cat] || '#0D9488' }} />
                </div>
                <span>{data.chart.counts[i]}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 text-center text-sm text-[#64748B]">{t('variantCount')}</div>
        </div>
      ) : (
        <div>
          {tab === 'cds' && (
            <div className="mb-5 flex flex-wrap gap-6 text-sm">
              {filters.map((f) => (
                <label key={f} className="inline-flex items-center gap-2 capitalize">
                  <input type="radio" checked={filter === f} onChange={() => { setFilter(f); setPage(1); }} /> {f}
                </label>
              ))}
            </div>
          )}
          <div className="mb-3 text-sm">{t('page')}</div>
          <div className="mb-5 flex items-center justify-between rounded-lg bg-white px-4 py-3 text-sm shadow-sm">
            <span>{data.page || page}</span>
            <span className="space-x-4 text-[#CBD5E1]"><button disabled={(data.page || 1) <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>−</button><button disabled={(data.page || 1) >= (data.pages || 1)} onClick={() => setPage((p) => p + 1)}>＋</button></span>
          </div>
          <table className="w-full overflow-hidden rounded-lg bg-white text-sm shadow-sm">
            <thead className="text-[#64748B]"><tr className="border-b">{Object.keys(data.rows?.[0] || {}).filter((k) => !['impact_class'].includes(k)).map((k) => <th key={k} className="p-3 text-left font-normal">{k}</th>)}</tr></thead>
            <tbody>
              {data.rows?.map((r: any, i: number) => (
                <tr key={i} className="border-b border-[#E2E8F0]">
                  {Object.entries(r).filter(([k]) => k !== 'impact_class').map(([k, v]) => <td key={k} className="p-3">{String(v)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><div className="mb-2 text-sm">{label}</div><div className="text-4xl font-light text-[#1a252f]">{value}</div></div>;
}
