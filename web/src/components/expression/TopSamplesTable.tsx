'use client';

import type { TopSampleEntry } from '@/lib/api';
import ExpandableText from '@/components/expression/ExpandableText';
import { useTranslations } from 'next-intl';

export default function TopSamplesTable({ samples }: { samples: TopSampleEntry[] }) {
  const t = useTranslations('fields');
  if (!samples || samples.length === 0) {
    return (
      <div className="text-xs text-slate-500 bg-slate-50 rounded-lg px-4 py-3 text-center">
        No sample-level data
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[#E2E8F0]">
      <table className="min-w-full text-xs">
        <thead className="bg-[#f8fafc] text-[#334155]">
          <tr>
            <th className="text-left px-3 py-2 font-semibold">{t('fpkm')}</th>
            <th className="text-left px-3 py-2 font-semibold">{t('tissue')}</th>
            <th className="text-left px-3 py-2 font-semibold">{t('condition')}</th>
            <th className="text-left px-3 py-2 font-semibold">{t('sample')}</th>
            <th className="text-left px-3 py-2 font-semibold">{t('description')}</th>
            <th className="text-left px-3 py-2 font-semibold">{t('project')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#E2E8F0]">
          {samples.map((s, i) => (
            <tr key={`${s.sample_id}-${i}`} className="hover:bg-slate-50">
              <td className="px-3 py-2 font-mono font-semibold text-[#475569]">
                {s.fpkm.toFixed(1)}
              </td>
              <td className="px-3 py-2 text-slate-700">{s.tissue || '—'}</td>
              <td className="px-3 py-2">
                {s.condition ? (
                  <span className="inline-block rounded-full bg-[#F1F5F9] px-2 py-0.5 text-[10px] text-slate-600">
                    {s.condition}
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className="px-3 py-2 font-mono text-slate-600">{s.sample_id || '—'}</td>
              <td className="px-3 py-2 align-top">
                <ExpandableText text={s.description} />
              </td>
              <td className="px-3 py-2 font-mono text-slate-500">{s.project || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
