'use client';

import { useMemo, useState } from 'react';
import type { MolStarViewerHandle } from './MolStarViewer';
import { useTranslations } from 'next-intl';

type ResidueSite = {
  resname?: string;
  resno: number;
  site_type: string;
  confidence?: number;
};

type GlobalSite = { site: string; confidence: number };

type Props = {
  bindingSites?: GlobalSite[] | null;
  residueSites?: ResidueSite[] | null;
  viewerRef?: React.RefObject<MolStarViewerHandle | null>;
};

const SITE_COLORS: Record<string, string> = {
  RNA: '#10b981',
  Peptide: '#3b82f6',
  Protein: '#f59e0b',
  ATP: '#8b5cf6',
  DNA: '#ec4899',
  Metal: '#6366f1',
};
const DEFAULT_COLOR = '#0f766e';
const HIDDEN_SITE_TYPES = new Set(['HEM']);

function isHiddenSite(siteType: string) {
  return HIDDEN_SITE_TYPES.has(siteType.trim().toUpperCase());
}

function siteColor(siteType: string) {
  const key = Object.keys(SITE_COLORS).find((k) => siteType.includes(k));
  return key ? SITE_COLORS[key] : DEFAULT_COLOR;
}

const AA_FULL: Record<string, string> = {
  A: 'Ala', R: 'Arg', N: 'Asn', D: 'Asp', C: 'Cys', E: 'Glu', Q: 'Gln',
  G: 'Gly', H: 'His', I: 'Ile', L: 'Leu', K: 'Lys', M: 'Met', F: 'Phe',
  P: 'Pro', S: 'Ser', T: 'Thr', W: 'Trp', Y: 'Tyr', V: 'Val',
};

export default function BindingSitesTable({ bindingSites, residueSites, viewerRef }: Props) {
  const t = useTranslations('proteins');
  const [selected, setSelected] = useState<number | null>(null);

  const visibleBindingSites = useMemo(
    () => (bindingSites || []).filter((s) => s && !isHiddenSite(s.site)),
    [bindingSites],
  );

  const grouped = useMemo(() => {
    // 严格类型守卫：必须是数组才处理。后端 residue_sites 可能因数据格式变化、
    // 文件解析失败或路径问题返回各种非数组形态（dict / null / 字符串），
    // 直接 for...of 会抛 "not iterable"。这里过滤掉所有非数组输入。
    if (!Array.isArray(residueSites) || residueSites.length === 0) return null;
    const map = new Map<string, ResidueSite[]>();
    for (const r of residueSites) {
      if (!r || typeof r !== 'object' || r.site_type == null) continue;
      if (isHiddenSite(r.site_type)) continue;
      if (!map.has(r.site_type)) map.set(r.site_type, []);
      map.get(r.site_type)!.push(r);
    }
    const entries = Array.from(map.entries()).sort((a, b) => b[1].length - a[1].length);
    return entries.length > 0 ? entries : null;
  }, [residueSites]);

  const handleRowClick = (resno: number | null) => {
    setSelected((prev) => (prev === resno ? null : resno));
    viewerRef?.current?.highlight(resno);
  };

  // 一个残基可同时带多种结合注释（如 Arg150 ∈ Protein/RNA/MN/MG/CA）——
  // 头部显示去重后的真实残基数，分类型列表各自计数（标注 per-type）。
  const annotationCount = grouped?.reduce((n, [, residues]) => n + residues.length, 0) ?? 0;
  const residueCount = new Set(
    (grouped ?? []).flatMap(([, residues]) => residues.map((r) => r.resno))
  ).size;
  if (!grouped && visibleBindingSites.length === 0) {
    return (
      <div className="text-xs text-slate-500 italic">
        No predicted binding sites for this protein.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-slate-800">
          Predicted Binding Sites
        </h4>
        {(visibleBindingSites.length > 0 || residueCount > 0) && (
          <span className="text-xs text-slate-500">
            {visibleBindingSites.length || grouped?.length || 0} types · {residueCount} residues
            {annotationCount > residueCount ? ` (${annotationCount} annotations)` : ''}
          </span>
        )}
      </div>

      {grouped ? (
        <div className="space-y-2">
          {grouped.map(([siteType, residues]) => {
            const color = siteColor(siteType);
            return (
              <div
                key={siteType}
                className="rounded-lg border border-slate-200 bg-slate-50/60 overflow-hidden"
              >
                <div className="flex items-center px-3 py-1.5 bg-white border-b border-slate-200">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full mr-2"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-xs font-semibold text-slate-700">{siteType}</span>
                  <span className="ml-auto text-[11px] text-slate-500">{residues.length} residues</span>
                </div>
                <div className="flex flex-wrap gap-1.5 p-2">
                  {residues.map((r, i) => {
                    const isSel = selected === r.resno;
                    const label = AA_FULL[r.resname || ''] || r.resname || '?';
                    return (
                      <button
                        key={`${r.resno}-${i}`}
                        onClick={() => handleRowClick(r.resno)}
                        title={`${label} ${r.resno}`}
                        className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors border ${
                          isSel
                            ? 'text-white border-transparent'
                            : 'bg-white text-slate-700 border-slate-200 hover:border-slate-400'
                        }`}
                        style={isSel ? { backgroundColor: color } : {}}
                      >
                        {label}<sub>{r.resno}</sub>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : visibleBindingSites.length > 0 ? (
        <div className="grid grid-cols-2 gap-2">
          {visibleBindingSites.map((s, i) => {
            const color = siteColor(s.site);
            return (
              <div
                key={i}
                className="flex items-center px-3 py-2 rounded-lg border border-slate-200 bg-white"
              >
                <span
                  className="inline-block w-2.5 h-2.5 rounded-full mr-2"
                  style={{ backgroundColor: color }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-slate-700 truncate">{s.site}</div>
                  <div className="text-[10px] text-slate-500">conf {s.confidence.toFixed(2)}</div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-slate-500 italic">{t('noSites')}</div>
      )}

      {selected !== null && (
        <button
          onClick={() => handleRowClick(null)}
          className="text-[11px] text-teal-700 hover:text-teal-900 underline"
        >
          Clear highlight
        </button>
      )}
    </div>
  );
}
