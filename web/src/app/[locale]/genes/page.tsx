'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { searchGene, geneChatStream, type AgentStreamHandlers, type ChatHistoryMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { SPECIES, VARIANT_SPECIES, readGeneDeepLink } from '@/lib/species';
import { useTranslations } from 'next-intl';
import AgentMarkdown from '@/components/AgentMarkdown';
import AiSignInGate from '@/components/AiSignInGate';
import GeneAnnotation from '@/components/genes/GeneAnnotation';
import SequenceInfo from '@/components/genes/SequenceInfo';
import GeneStructure from '@/components/genes/GeneStructure';
import GoTerms from '@/components/genes/GoTerms';
import PfamDomains from '@/components/genes/PfamDomains';
import NaturalVariants from '@/components/genes/NaturalVariants';
import { DEMO_GENES } from '@/lib/demoGenes';
import OrthologMatrix from '@/components/genes/OrthologMatrix';
import {
  DnaIcon,
  MapPinIcon,
  TagIcon,
  PuzzleIcon,
  AtomIcon,
  RefreshCwIcon,
  NetworkIcon,
  FileTextIcon,
} from '@/components/ui/icons';

type SummaryTurn = { role: 'user' | 'assistant'; content: string };

export default function GenesPage() {
  const t = useTranslations('genes');
  const [species, setSpecies] = useState('Cucumber');
  const [geneId, setGeneId] = useState('');

  const [searchData, setSearchData] = useState<any>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [hasSearched, setHasSearched] = useState(false);

  // AI Summary sits on top of search results (not a parallel entry).
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryTurns, setSummaryTurns] = useState<SummaryTurn[]>([]);
  const [summaryStatuses, setSummaryStatuses] = useState<string[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState('');
  const [followUp, setFollowUp] = useState('');
  const summaryGeneRef = useRef('');
  const { isSignedIn } = useAuth();

  const resetSummary = () => {
    setSummaryOpen(false);
    setSummaryTurns([]);
    setSummaryStatuses([]);
    setSummaryLoading(false);
    setSummaryError('');
    setFollowUp('');
    summaryGeneRef.current = '';
  };

  // Deep links from ChatPanel evidence cards: /genes?gene=…&species=…
  useEffect(() => {
    const { geneId: gene, species: sp } = readGeneDeepLink();
    if (gene) runSearch(gene, sp || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runSearch = async (geneOverride?: string, speciesOverride?: string) => {
    const id = (geneOverride ?? geneId).trim();
    if (!id) return;
    const sp = speciesOverride ?? species;
    if (speciesOverride) setSpecies(speciesOverride);
    setGeneId(id);
    resetSummary();
    setHasSearched(true);
    setSearchData(null);
    setSearchError('');
    setSearchLoading(true);
    try {
      const data = await searchGene(sp, id);
      setSearchData(data);
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setSearchLoading(false);
    }
  };

  const streamSummary = async (question: string = '') => {
    const id = (searchData?.gene_id || geneId).trim();
    if (!id || summaryLoading) return;
    if (!isSignedIn) return;

    const sp = searchData?.species || species;
    const qLabel = question.trim()
      ? question.trim()
      : `Overview summary of ${id}`;

    setSummaryOpen(true);
    setSummaryError('');
    setSummaryStatuses([]);
    setSummaryLoading(true);
    summaryGeneRef.current = id;

    // Prior turns give the backend context for follow-up questions
    // ("What about its orthologs?" needs to know what came before).
    const history: ChatHistoryMessage[] = summaryTurns
      .filter((t) => t.content.trim())
      .map((t) => ({ role: t.role, content: t.content }));

    setSummaryTurns((prev) => [
      ...prev,
      { role: 'user', content: qLabel },
      { role: 'assistant', content: '' },
    ]);

    let text = '';
    const handlers: AgentStreamHandlers = {
      onStatus: (m) => setSummaryStatuses((prev) => [...prev, m]),
      onToken: (t) => {
        text += t;
        setSummaryTurns((prev) => {
          const next = [...prev];
          const last = next.length - 1;
          if (last >= 0 && next[last].role === 'assistant') {
            next[last] = { ...next[last], content: text };
          }
          return next;
        });
      },
      onError: (m) => setSummaryError(m),
      onDone: () => {},
    };

    try {
      await geneChatStream(id, sp, handlers, question, history);
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : 'AI Summary failed');
    } finally {
      setSummaryLoading(false);
    }
  };

  const onFollowUp = async () => {
    const q = followUp.trim();
    if (!q || summaryLoading) return;
    setFollowUp('');
    await streamSummary(q);
  };

  const showResults = hasSearched;
  const canSummarize = Boolean(searchData) && !searchLoading && !searchError;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <div className="max-w-[1100px] mx-auto px-4 py-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-teal-brand">{t('title')}</h1>
          <p className="text-slate-muted mt-2 text-sm">
            {t('subtitle')}
          </p>
        </div>

        <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm p-5 mb-6">
          <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-end">
            <div className="flex-1">
              <label className="block text-xs text-slate-500 mb-1">{t('species')}</label>
              <select
                value={species}
                onChange={(e) => setSpecies(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:border-teal-500 focus:outline-none"
              >
                {SPECIES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="flex-[2]">
              <label className="block text-xs text-slate-500 mb-1">{t('geneId')}</label>
              <input
                value={geneId}
                onChange={(e) => setGeneId(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
                placeholder={t('geneIdPlaceholder')}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:border-teal-500 focus:outline-none"
              />
            </div>
            <button
              onClick={() => runSearch()}
              disabled={!geneId.trim() || searchLoading}
              className="px-5 py-2 rounded-lg bg-[#0D9488] text-white text-sm font-semibold hover:bg-[#0F766E] transition-colors whitespace-nowrap disabled:cursor-not-allowed"
            >
              {searchLoading ? t('searching') : `🔍 ${t('search')}`}
            </button>
          </div>
        </div>

        {!showResults && (
          <GenesLanding onTryExample={(sp, gid) => runSearch(gid, sp)} />
        )}

        {showResults && (
          <div className="space-y-5">
            {/* AI Summary — only after a successful search */}
            {canSummarize && (
              <div className="rounded-xl border border-[#CCFBF1] bg-gradient-to-br from-[#F0FDFA] to-white shadow-sm overflow-hidden">
                <div className="px-5 py-3 border-b border-[#CCFBF1] flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                      <span aria-hidden>✨</span> {t('aiSummary')}
                    </h3>
                  </div>
                  {isSignedIn && (
                    !summaryOpen ? (
                      <button
                        type="button"
                        onClick={() => streamSummary()}
                        disabled={summaryLoading}
                        className="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700 transition-colors whitespace-nowrap"
                      >
                        ✨ {t('geneChat')}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={resetSummary}
                        className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-white transition"
                      >
                        Clear summary
                      </button>
                    )
                  )}
                </div>

                <div className="p-5">
                  <AiSignInGate feature="Gene Chat" compact>
                    {summaryOpen ? (
                      <div className="space-y-4">
                        {summaryTurns.map((t, i) => (
                          <div key={i} className={t.role === 'user' ? '' : ''}>
                            {t.role === 'user' ? (
                              <div className="text-xs text-slate-500 mb-1">Q: {t.content}</div>
                            ) : (
                              <div className="rounded-lg bg-white border border-[#E2E8F0] px-4 py-3">
                                {t.content ? (
                                  <AgentMarkdown content={t.content} />
                                ) : summaryLoading ? (
                                  <span className="text-sm text-[#0D9488] inline-flex items-center gap-1">
                                    <span className="cuagent-thinking-dot" />
                                    <span className="cuagent-thinking-dot" />
                                    <span className="cuagent-thinking-dot" />
                                  </span>
                                ) : null}
                              </div>
                            )}
                          </div>
                        ))}

                        {summaryStatuses.length > 0 && (
                          <div className="rounded-lg bg-[#F0FDFA] border border-[#CCFBF1] p-3 text-xs text-[#0F766E] space-y-1">
                            {summaryStatuses.slice(-4).map((s, i) => (
                              <div key={`${s}-${i}`}>• {s}</div>
                            ))}
                          </div>
                        )}
                        {summaryError && <p className="text-sm text-red-600">{summaryError}</p>}

                        <div className="flex gap-2 items-stretch pt-1">
                          <input
                            value={followUp}
                            onChange={(e) => setFollowUp(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') onFollowUp(); }}
                            disabled={summaryLoading}
                            placeholder={t('followUp')}
                            className="flex-1 px-3 py-2 rounded-lg border border-slate-200 text-sm focus:border-teal-500 focus:outline-none disabled:opacity-50"
                          />
                          <button
                            type="button"
                            onClick={onFollowUp}
                            disabled={summaryLoading || !followUp.trim()}
                            className="px-4 py-2 rounded-lg bg-[#0D9488] text-white text-sm font-medium hover:bg-[#0F766E] disabled:opacity-50 whitespace-nowrap"
                          >
                            {t('ask')}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500">
                        {t('summaryHint')}
                      </p>
                    )}
                  </AiSignInGate>
                </div>
              </div>
            )}

            <SearchResult data={searchData} loading={searchLoading} error={searchError} />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * 完整的基因结构化展示组件树。
 *
 * 排版设计（每个大组件独占一行，避免 grid 两列挤压）：
 *   ┌─────────────────────────────────┐
 *   │ Gene Annotation (位置/版本/功能) │  <- 顶部 banner
 *   ├─────────────────────────────────┤
 *   │ Gene Structure (外显子图)        │  <- 独占一行
 *   ├─────────────────────────────────┤
 *   │ GO Terms (InterPro GO)          │  <- 独占一行
 *   ├─────────────────────────────────┤
 *   │ Protein Domain Architecture     │  <- 独占一行
 *   ├─────────────────────────────────┤
 *   │ InterPro (Pfam 链接汇总表)      │  <- 独占一行
 *   ├─────────────────────────────────┤
 *   │ Sequence Info (CDS + Protein)   │  <- 独占一行
 *   ├─────────────────────────────────┤
 *   │ Plant Orthologs                 │  <- 独占一行
 *   ├─────────────────────────────────┤
 *   │ Natural Variants                │  <- 独占一行
 *   └─────────────────────────────────┘
 */
function SearchResult({ data, loading, error }: { data: any; loading: boolean; error: string }) {
  const t = useTranslations('genes');
  if (loading) {
    return (
      <div className="rounded-xl border border-[#E2E8F0] bg-white p-8 text-center text-slate-500 text-sm">
        {t('loading')}
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded-xl border border-[#E2E8F0] bg-white p-8 text-center text-slate-500 text-sm">
        {t('noData')}
      </div>
    );
  }

  const proteinLength = data.protein_sequence?.length_aa;
  const pfamDomains = data.pfam_domains || [];

  return (
    <div className="space-y-5">
      {/* 顶部：基因位置 + 版本映射 + 功能描述 */}
      <Card>
        <GeneAnnotation data={data} />
      </Card>

      {/* 独占一行：基因结构（外显子/intron 可视化） */}
      {data.gene_structure && (
        <Card title={t('secStructure')}>
          <GeneStructure structure={data.gene_structure} />
        </Card>
      )}

      {/* 独占一行：GO terms */}
      {data.go_terms ? (
        <Card title={t('secGo')}>
          <GoTerms terms={data.go_terms} />
        </Card>
      ) : (
        <EmptyStateCard
          title={t('secGo')}
          hint={t('emptyGo')}
        />
      )}

      {/* 独占一行：Pfam 蛋白结构域架构图 */}
      {pfamDomains.length > 0 ? (
        <Card title={t('secPfam')}>
          <PfamDomains domains={pfamDomains} proteinLength={proteinLength} />
        </Card>
      ) : (
        <EmptyStateCard
          title={t('secPfam')}
          hint={
            proteinLength != null && proteinLength < 80
              ? t('emptyPfamShort', { len: proteinLength })
              : t('emptyPfam')
          }
        />
      )}

      {/* 独占一行：InterPro 链接汇总表（Pfam domain 的快速外链） */}
      {pfamDomains.length > 0 && (
        <Card title={t('secInterpro')}>
          <InterProTable domains={pfamDomains} />
        </Card>
      )}

      {/* 独占一行：序列信息 */}
      {(data.cds_sequence || data.protein_sequence) && (
        <Card title={t('secSequence')}>
          <SequenceInfo
            geneId={data.gene_id}
            cds={data.cds_sequence}
            protein={data.protein_sequence}
          />
        </Card>
      )}

      {/* 独占一行：同源基因矩阵 */}
      {data.plant_orthologs_matrix && (
        <Card title={t('secOrthologs')}>
          <OrthologMatrix matrix={data.plant_orthologs_matrix} />
        </Card>
      )}

      {/* 独占一行：自然变异 — 只给有变异索引的物种渲染（见 lib/species.ts） */}
      {VARIANT_SPECIES.has(data.species) ? (
        <Card title={t('secVariants')}>
          <NaturalVariants
            species={data.species}
            geneId={data.gene_id}
            initial={data.natural_variants}
          />
        </Card>
      ) : (
        <EmptyStateCard
          title={t('secVariants')}
          hint={t('emptyVariants', { species: data.species })}
        />
      )}
    </div>
  );
}

/**
 * 统一的卡片容器：白底圆角 + 可选标题栏，让每个组件视觉上独立成块。
 */
function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
      {title && (
        <div className="px-5 py-3 border-b border-[#E2E8F0] bg-gradient-to-r from-slate-50 to-white">
          <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

/**
 * EmptyStateCard — visual twin of <Card> used when a section has no data.
 *
 * Instead of silently hiding the section (which leaves users wondering whether
 * the system is broken), this keeps the section header visible and shows a
 * muted hint explaining WHY data is missing. The hint is tuned to the two
 * common cases:
 *   - very short protein (likely fails domain thresholds)
 *   - novel / unannotated gene (no official functional curation yet)
 */
function EmptyStateCard({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
      <div className="px-5 py-3 border-b border-[#E2E8F0] bg-gradient-to-r from-slate-50 to-white">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      </div>
      <div className="p-5">
        <div className="flex items-start gap-3 text-sm text-slate-500">
          <span aria-hidden className="text-base leading-5">🚫</span>
          <p className="leading-relaxed">{hint}</p>
        </div>
      </div>
    </div>
  );
}

/** Demo genes: shared with Expression / Protein via `@/lib/demoGenes`. */

/**
 * Idle 状态下的数据资产导览。让用户进页面就知道：
 *   1. 这个数据库覆盖多少物种/基因
 *   2. 每次搜索能看到什么内容
 *   3. AI Summary can interpret a search result
 *   4. 可以试什么示例 ID
 *
 * 统计数字是静态的（基因注释相对稳定，每次扫库反而增加延迟）。
 */
function GenesLanding({ onTryExample }: { onTryExample?: (species: string, geneId: string) => void }) {
  const t = useTranslations('genes');
  return (
    <div className="space-y-5">
      {/* 数据统计 banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <LandingStat label={t('statSpecies')} value="9" hint={t('hintSpecies')} />
        <LandingStat label={t('statGenes')} value="255,874" hint={t('hintGenes')} />
        <LandingStat label={t('statVariants')} value="✓" hint={t('hintVariants')} />
        <LandingStat label={t('statOrthologs')} value="13" hint={t('hintOrthologs')} />
      </div>

      {/* 功能矩阵表 */}
      <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-[#E2E8F0] bg-gradient-to-r from-[#F0FDFA] to-[#ECFDF5]">
          <h3 className="text-sm font-semibold text-[#0F766E]">{t('matrixTitle')}</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <tbody className="divide-y divide-[#E2E8F0]">
              <LandingRow icon={<MapPinIcon className="size-4" />} name={t('rowAnnotationName')} desc={t('rowAnnotationDesc')} />
              <LandingRow icon={<DnaIcon className="size-4" />} name={t('rowStructureName')} desc={t('rowStructureDesc')} />
              <LandingRow icon={<TagIcon className="size-4" />} name={t('rowGoName')} desc={t('rowGoDesc')} />
              <LandingRow icon={<AtomIcon className="size-4" />} name={t('rowPfamName')} desc={t('rowPfamDesc')} />
              <LandingRow
                icon={<RefreshCwIcon className="size-4" />}
                name={t('rowVariantsName')}
                desc={t('rowVariantsDesc')}
                availability={t('rowVariantsAvail')}
              />
              <LandingRow icon={<NetworkIcon className="size-4" />} name={t('rowOrthologsName')} desc={t('rowOrthologsDesc')} />
              <LandingRow icon={<FileTextIcon className="size-4" />} name={t('rowSequencesName')} desc={t('rowSequencesDesc')} />
            </tbody>
          </table>
        </div>
      </div>

      {/* AI Summary 说明 */}
      <div className="rounded-xl border border-[#CCFBF1] bg-gradient-to-br from-[#F0FDFA] to-white p-5">
        <h3 className="text-sm font-semibold text-[#0F766E] mb-2">✨ {t('aiSummary')}</h3>
        <ul className="text-xs text-slate-700 space-y-1.5 list-disc pl-5">
          <li>{t('aiBullet1')}</li>
          <li>{t('aiBullet2')}</li>
          <li>{t('aiBullet3')}</li>
        </ul>
      </div>
      {/* 示例 ID — curated so GO / Pfam / Variants are populated */}
      <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-xs text-slate-600">
        <strong className="text-slate-700">{t('tryThese')}</strong>{' '}
        {DEMO_GENES.map((d, i) => (
          <span key={d.geneId}>
            {i > 0 ? ' · ' : null}
            <button
              type="button"
              className="font-mono text-[#0D9488] hover:underline underline-offset-2"
              title={`${d.species} / ${d.geneId}`}
              onClick={() => onTryExample?.(d.species, d.geneId)}
            >
              {d.geneId}
            </button>{' '}
            ({d.label})
          </span>
        ))}
      </div>
    </div>
  );
}

function LandingStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-white border border-[#E2E8F0] px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className="text-xl font-bold text-slate-800">{value}</div>
      {hint && <div className="text-[10px] text-slate-500">{hint}</div>}
    </div>
  );
}

function LandingRow({
  icon,
  name,
  desc,
  availability,
}: {
  icon: ReactNode;
  name: string;
  desc: string;
  /** Optional availability badge, e.g. "Cucumber + Watermelon only". */
  availability?: string;
}) {
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-4 py-2.5 w-12 text-[#0D9488]">{icon}</td>
      <td className="px-2 py-2.5 font-semibold text-slate-800 whitespace-nowrap min-w-[140px]">
        {name}
      </td>
      <td className="px-4 py-2.5 text-slate-600">{desc}</td>
      {availability ? (
        <td className="px-3 py-2.5 whitespace-nowrap">
          <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
            {availability}
          </span>
        </td>
      ) : (
        <td className="px-3 py-2.5" />
      )}
    </tr>
  );
}

/**
 * InterPro 链接汇总表：把 Pfam domain 列成表格形式，每行可点链接到 EBI InterPro。
 * PfamDomains 组件是可视化架构图，这个表格是补充——方便复制 ID / 批量查看。
 */
function InterProTable({ domains }: { domains: any[] }) {
  const t = useTranslations('genes');
  if (!domains?.length) return null;
  const sorted = [...domains].sort((a, b) => a.start - b.start);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs text-slate-500">
            <th className="text-left py-2 pr-4 font-normal">{t('thDomain')}</th>
            <th className="text-left py-2 pr-4 font-normal">{t('thPfamId')}</th>
            <th className="text-left py-2 pr-4 font-normal">{t('thLink')}</th>
            <th className="text-right py-2 pr-4 font-normal">{t('thStart')}</th>
            <th className="text-right py-2 pr-4 font-normal">{t('thEnd')}</th>
            <th className="text-right py-2 font-normal">{t('thLength')}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((d, i) => (
            <tr key={`${d.pfam_id || d.name}-${i}`} className="border-b border-slate-100 last:border-0">
              <td className="py-2 pr-4 font-medium text-slate-800">{d.name}</td>
              <td className="py-2 pr-4 font-mono text-xs text-slate-600">{d.pfam_id || '—'}</td>
              <td className="py-2 pr-4">
                {d.pfam_id ? (
                  <a
                    href={`https://www.ebi.ac.uk/interpro/entry/pfam/${d.pfam_id}/`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[#2980b9] hover:text-[#1f6391] underline text-xs"
                  >
                    {t('viewOnInterPro')} ↗
                  </a>
                ) : (
                  <span className="text-slate-400 text-xs">—</span>
                )}
              </td>
              <td className="py-2 pr-4 text-right font-mono text-xs text-slate-700">{d.start}</td>
              <td className="py-2 pr-4 text-right font-mono text-xs text-slate-700">{d.end}</td>
              <td className="py-2 text-right font-mono text-xs text-slate-700">{d.length_aa ?? (d.end - d.start + 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
