'use client';

import { MicroscopeIcon, WarningIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

/**
 * Compact protein structure panel for the Agent chat.
 *
 * Evidence card under the LLM summary. Shows ESMFold pLDDT + predicted
 * binding sites + residue sites summary, no 3D viewer.
 *
 * Props shape from /api/proteins/search.
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

function plddtColor(score: number): string {
  if (score >= 90) return '#0D9488';   // excellent - teal
  if (score >= 70) return '#16A34A';   // good - green
  if (score >= 50) return '#F59E0B';   // low - amber
  return '#DC2626';                     // very low - red
}

export default function ProteinDataCard({ data }: { data: any }) {
  const t = useTranslations('cards');
  if (!data || data.status !== 'success') {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 flex items-start gap-2">
        <WarningIcon className="size-4 shrink-0 mt-[1px]" />
        <span>{data?.message || 'No protein structure available.'}</span>
      </div>
    );
  }

  const plddt = Number(data.plddt_score);
  const sites = (data.binding_sites || []).filter(
    (s: any) => s?.site && String(s.site).toUpperCase() !== 'HEM',
  );
  const residueSites = (data.residue_sites || []).filter(
    (r: any) => r?.site_type && String(r.site_type).toUpperCase() !== 'HEM',
  );
  // Group residue sites by type for a compact count summary
  const siteTypeCount: Record<string, number> = {};
  for (const r of residueSites) {
    const t = r.site_type || 'Other';
    siteTypeCount[t] = (siteTypeCount[t] || 0) + 1;
  }
  // Show a few representative residue examples
  const sampleResidues = residueSites.slice(0, 6);

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 overflow-hidden">
      <div className="px-3 py-1.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700 inline-flex items-center gap-1.5">
          <MicroscopeIcon className="size-3.5 text-[#0D9488]" />
          {data.gene_id} <span className="text-slate-400 font-normal">· ESMFold</span>
        </span>
        {data.pdb_url && <span className="text-[10px] text-[#0D9488]">3D structure available</span>}
      </div>

      <div className="p-3 space-y-3">
        {/* pLDDT — the headline score, with color band */}
        <Section title={t('foldQuality')}>
          <div className="flex items-center gap-3">
            <span
              className="text-2xl font-bold tabular-nums"
              style={{ color: plddtColor(plddt) }}
            >
              {fmt1(plddt)}
            </span>
            <span className="text-xs font-medium" style={{ color: plddtColor(plddt) }}>
              {data.plddt_label}
            </span>
            <div className="flex-1 h-2 bg-slate-200 rounded-sm overflow-hidden">
              <div
                className="h-full rounded-sm"
                style={{ width: `${Math.min(100, plddt)}%`, backgroundColor: plddtColor(plddt) }}
              />
            </div>
          </div>
        </Section>

        {/* Binding sites — confidence-ranked list */}
        {sites.length > 0 && (
          <Section title={t('bindingSites')} count={sites.length}>
            {sites.map((s: any, i: number) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-slate-700">{s.site}</span>
                <span className="text-[#0F766E] tabular-nums">
                  {(s.confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </Section>
        )}

        {/* Residue sites — count by type + a few examples */}
        {residueSites.length > 0 && (
          <Section title={t('residues')} count={residueSites.length}>
            {Object.entries(siteTypeCount).length > 0 && (
              <div className="text-xs text-slate-600">
                {Object.entries(siteTypeCount).map(([type, cnt], i) => (
                  <span key={type}>
                    {i > 0 && ' · '}
                    {cnt} {type}{cnt > 1 ? 's' : ''}
                  </span>
                ))}
              </div>
            )}
            {sampleResidues.length > 0 && (
              <div className="text-[11px] text-slate-400 leading-relaxed">
                e.g. {sampleResidues.map((r: any, i: number) => (
                  <span key={i}>
                    {i > 0 && ', '}
                    <span className="text-slate-600">{r.resname}{r.resno}</span>
                    <span className="text-slate-400"> ({r.site_type})</span>
                  </span>
                ))}
                {residueSites.length > sampleResidues.length && ' …'}
              </div>
            )}
          </Section>
        )}

        {!data.has_pdb && (
          <div className="text-[11px] text-slate-400 italic">
            No PDB file for this gene — structure not modeled.
          </div>
        )}
      </div>
    </div>
  );
}
