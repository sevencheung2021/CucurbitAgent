'use client';

import { ClipboardListIcon, WarningIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

/**
 * Compact gene record panel for the Agent chat.
 *
 * Design intent: the LLM summary is the primary content (rendered above this
 * card in ChatPanel). This card is the supporting evidence — a clean,
 * info-dense snapshot of the structured fields, NOT a full Genes-page clone
 * with visual diagrams. Everything is plain text / simple tables so it stays
 * scannable inside a chat bubble.
 *
 * Props mirror what /api/genes/search returns. Defensive against missing
 * fields — renders "—" for empty values rather than crashing.
 */

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-xs">
      <span className="text-slate-400 min-w-[90px] flex-shrink-0">{label}</span>
      <span className="text-slate-700 break-words">{children || '—'}</span>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] font-semibold text-[#334155] uppercase tracking-wider mb-1.5">
        {title}{typeof count === 'number' ? ` (${count})` : ''}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function fmt(n: any): string {
  const x = Number(n);
  return Number.isFinite(x) ? x.toLocaleString() : '—';
}

export default function GeneDataCard({ data }: { data: any }) {
  const t = useTranslations('cards');
  if (!data || data.status !== 'success') {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 flex items-start gap-2">
        <WarningIcon className="size-4 shrink-0 mt-[1px]" />
        <span>{data?.message || 'Gene not found in local database.'}</span>
      </div>
    );
  }

  const info = data.basic_info || {};
  const gs = data.gene_structure || {};
  const go = data.go_terms || {};
  const domains = data.pfam_domains || [];
  const nv = data.natural_variants || {};
  const orthologs = (data.plant_orthologs || []).slice(0, 5);
  const protLen = data.protein_sequence?.length_aa;
  const cdsLen = data.cds_sequence?.length_bp;

  const nvSummary = nv.summary || {};
  const nvCount = nv.count || 0;
  const nvDetail = Object.entries(nvSummary)
    .filter(([, v]) => Number(v) > 0)
    .map(([k, v]) => `${v} ${k}`)
    .join(' · ') || `${nvCount} total`;

  const funcRaw = (info.function || '').trim();
  const funcMissing = !funcRaw || /^(not provided|n\/a|-|nan)$/i.test(funcRaw);

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 overflow-hidden">
      {/* Title bar — compact */}
      <div className="px-3 py-1.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700 inline-flex items-center gap-1.5">
          <ClipboardListIcon className="size-3.5 text-[#475569]" />
          {data.gene_id} <span className="text-slate-400 font-normal">· {data.species}</span>
        </span>
        {data.version_mapping && (
          <span className="text-[10px] text-slate-400">{Object.keys(data.version_mapping).length} alt IDs</span>
        )}
      </div>

      <div className="p-3 space-y-3">
        {/* Function — hide placeholder strings from the DB */}
        {!funcMissing && (
          <div className="text-xs text-slate-700 leading-relaxed bg-white rounded border border-slate-200 px-2.5 py-1.5">
            <span className="text-slate-400">{t('functionLabel')} </span>{funcRaw}
          </div>
        )}
        {funcMissing && (
          <div className="text-xs text-slate-500 leading-relaxed bg-white rounded border border-dashed border-slate-200 px-2.5 py-1.5">
            No curated function annotation in the local database — see GO terms / literature below.
          </div>
        )}

        {/* Location + size grid */}
        <Section title={t('location')}>
          <Cell label={t('locus')}>{info.chr && `${info.chr}:${fmt(info.start)}-${fmt(info.end)} (${info.strand})`}</Cell>
          <Cell label={t('geneLength')}>{gs.gene_length_bp ? `${fmt(gs.gene_length_bp)} bp` : '—'}</Cell>
          <Cell label={t('exonsCds')}>{gs.num_exons ? `${gs.num_exons} exons · ${fmt(gs.total_cds_bp)} bp CDS` : '—'}</Cell>
          <Cell label={t('proteinLen')}>{protLen ? `${fmt(protLen)} aa` : '—'}</Cell>
        </Section>

        {/* GO terms — 3 buckets as compact inline chips */}
        {go && (go.biological_process?.length || go.molecular_function?.length || go.cellular_component?.length) ? (
          <Section title={t('goTerms')}>
            {go.biological_process?.length > 0 && <Cell label={t('goProcess')}>{go.biological_process.join('; ')}</Cell>}
            {go.molecular_function?.length > 0 && <Cell label={t('goFunction')}>{go.molecular_function.join('; ')}</Cell>}
            {go.cellular_component?.length > 0 && <Cell label={t('goComponent')}>{go.cellular_component.join('; ')}</Cell>}
          </Section>
        ) : null}

        {/* Pfam — simple list */}
        {domains.length > 0 && (
          <Section title={t('pfam')} count={domains.length}>
            {domains.map((d: any, i: number) => (
              <div key={i} className="text-xs text-slate-700">
                • {d.name}{' '}
                {d.pfam_id && <span className="text-slate-400">{d.pfam_id}</span>}
                {d.start && d.end && <span className="text-slate-400"> · {d.start}-{d.end}</span>}
              </div>
            ))}
          </Section>
        )}

        {/* Variants — just the summary counts */}
        {nvCount > 0 && (
          <Section title={t('variants')} count={nvCount}>
            <div className="text-xs text-slate-600">{nvDetail}</div>
          </Section>
        )}

        {/* Orthologs — top 5 only */}
        {orthologs.length > 0 && (
          <Section title={t('orthologs')} count={(data.plant_orthologs || []).length}>
            {orthologs.map((o: any, i: number) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-slate-700">{o.species} <span className="text-slate-400">{o.gene_id}</span></span>
                <span className="text-[#334155] font-medium tabular-nums">{o.identity}</span>
              </div>
            ))}
          </Section>
        )}
      </div>
    </div>
  );
}
