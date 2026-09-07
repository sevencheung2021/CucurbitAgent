'use client';

import Link from 'next/link';
import type { CoexpressedGene } from '@/lib/api';
import ExpandableText from '@/components/expression/ExpandableText';
import { useTranslations } from 'next-intl';

export default function CoexpressionTable({ genes }: { genes: CoexpressedGene[] }) {
  const t = useTranslations('fields');
  if (!genes || genes.length === 0) {
    return (
      <div className="text-xs text-slate-500 bg-slate-50 rounded-lg px-4 py-3 text-center">
        No co-expressed genes found (try lowering min correlation)
      </div>
    );
  }

  const absMax = Math.max(...genes.map((g) => g.abs_r), 0.001);

  return (
    <div className="overflow-x-auto rounded-lg border border-[#E2E8F0]">
      <table className="min-w-full text-xs">
        <thead className="bg-[#f8fafc] text-[#334155]">
          <tr>
            <th className="text-left px-3 py-2 font-semibold w-16">{t('rank')}</th>
            <th className="text-left px-3 py-2 font-semibold">{t('geneId')}</th>
            <th className="text-left px-3 py-2 font-semibold w-24">{t('pearsonR')}</th>
            <th className="text-left px-3 py-2 font-semibold w-32">{t('strength')}</th>
            <th className="text-left px-3 py-2 font-semibold">{t('description')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#E2E8F0]">
          {genes.map((g, i) => {
            const strength = (g.abs_r / absMax) * 100;
            const positive = g.pearson_r >= 0;
            return (
              <tr key={`${g.gene_id}-${i}`} className="hover:bg-slate-50">
                <td className="px-3 py-2 text-slate-500">#{i + 1}</td>
                <td className="px-3 py-2 font-mono">
                  <Link
                    href={`/genes?gene=${encodeURIComponent(g.gene_id)}`}
                    className="text-[#475569] hover:text-[#B01A75] hover:underline"
                  >
                    {g.gene_id}
                  </Link>
                </td>
                <td className="px-3 py-2 font-mono font-semibold">
                  <span className={positive ? 'text-[#475569]' : 'text-[#B01A75]'}>
                    {g.pearson_r >= 0 ? '+' : ''}
                    {g.pearson_r.toFixed(3)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="h-2 rounded-full bg-slate-100 overflow-hidden w-full">
                    <div
                      className={`h-full ${positive ? 'bg-[#475569]' : 'bg-[#B01A75]'}`}
                      style={{ width: `${strength}%` }}
                    />
                  </div>
                </td>
                <td className="px-3 py-2 align-top">
                  <ExpandableText text={g.description} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
