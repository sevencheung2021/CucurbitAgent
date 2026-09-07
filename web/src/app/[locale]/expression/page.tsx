'use client';

import { useEffect, useState } from 'react';
import {
  fetchExpressionOverview,
  fetchGeneExpression,
  fetchCoexpression,
  expressionChatStream,
  type ExpressionOverview,
  type GeneExpressionResult,
  type CoexpressionResult,
  type AgentStreamHandlers,
  type ChatHistoryMessage,
} from '@/lib/api';
import { SPECIES, readGeneDeepLink } from '@/lib/species';
import { useTranslations } from 'next-intl';
import AgentMarkdown from '@/components/AgentMarkdown';
import OverviewTable from '@/components/expression/OverviewTable';
import ExpressionSummary from '@/components/expression/ExpressionSummary';
import TissueBarChart from '@/components/expression/TissueBarChart';
import TopSamplesTable from '@/components/expression/TopSamplesTable';
import CoexpressionTable from '@/components/expression/CoexpressionTable';
import AiSignInGate from '@/components/AiSignInGate';
import { useAuth } from '@/lib/auth';
import {
  BarChart3Icon,
  DnaIcon,
  ClipboardListIcon,
  TargetIcon,
  LinkIcon,
  SparklesIcon,
  InfoIcon,
  WarningIcon,
} from '@/components/ui/icons';
import { DEMO_GENES } from '@/lib/demoGenes';

type Mode = 'idle' | 'search';
type Tab = 'overview' | 'gene';
type SummaryTurn = { role: 'user' | 'assistant'; content: string };

export default function ExpressionPage() {
  const t = useTranslations('expression');
  const tf = useTranslations('fields');
  const [species, setSpecies] = useState('Cucumber');
  const [geneId, setGeneId] = useState('');
  const [topK, setTopK] = useState(20);
  const [minCorr, setMinCorr] = useState(0.5);

  const [mode, setMode] = useState<Mode>('idle');
  const [tab, setTab] = useState<Tab>('overview');

  const [overview, setOverview] = useState<ExpressionOverview | null>(null);
  const [overviewError, setOverviewError] = useState('');

  const [exprData, setExprData] = useState<GeneExpressionResult | null>(null);
  const [exprLoading, setExprLoading] = useState(false);
  const [exprError, setExprError] = useState('');

  const [coexpData, setCoexpData] = useState<CoexpressionResult | null>(null);
  const [coexpLoading, setCoexpLoading] = useState(false);
  const [coexpError, setCoexpError] = useState('');

  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryTurns, setSummaryTurns] = useState<SummaryTurn[]>([]);
  const [summaryStatuses, setSummaryStatuses] = useState<string[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState('');
  const [followUp, setFollowUp] = useState('');
  const { isSignedIn } = useAuth();

  useEffect(() => {
    let cancelled = false;
    fetchExpressionOverview()
      .then((data) => {
        if (!cancelled) {
          setOverview(data);
          setOverviewError('');
        }
      })
      .catch((e) => {
        if (!cancelled) setOverviewError(e instanceof Error ? e.message : 'Failed to load overview');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Deep links from ChatPanel evidence cards: /expression?gene=…
  useEffect(() => {
    const { geneId: gene, species: sp } = readGeneDeepLink();
    if (gene) runSearch(gene, sp || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resetSummary = () => {
    setSummaryOpen(false);
    setSummaryTurns([]);
    setSummaryStatuses([]);
    setSummaryLoading(false);
    setSummaryError('');
    setFollowUp('');
  };

  async function runSearch(geneOverride?: string, speciesOverride?: string) {
    const id = (geneOverride ?? geneId).trim();
    if (!id) return;
    const sp = speciesOverride ?? species;
    setGeneId(id);
    if (speciesOverride) setSpecies(speciesOverride);
    resetSummary();
    setMode('search');
    setTab('gene');
    setExprData(null);
    setCoexpData(null);
    setExprError('');
    setCoexpError('');
    setExprLoading(true);
    setCoexpLoading(true);

    fetchGeneExpression(id, sp)
      .then((data) => setExprData(data))
      .catch((e) => setExprError(e instanceof Error ? e.message : 'Expression query failed'))
      .finally(() => setExprLoading(false));

    fetchCoexpression(id, sp, topK, minCorr)
      .then((data) => setCoexpData(data))
      .catch((e) => setCoexpError(e instanceof Error ? e.message : 'Co-expression query failed'))
      .finally(() => setCoexpLoading(false));
  }

  async function streamSummary(question: string = '') {
    const id = (exprData?.gene_id || geneId).trim();
    if (!id || summaryLoading) return;
    if (!isSignedIn) return;
    const sp = species;
    const qLabel = question.trim() ? question.trim() : `Overview summary of ${id} expression`;

    setSummaryOpen(true);
    setSummaryError('');
    setSummaryStatuses([]);
    setSummaryLoading(true);

    // Prior turns give the backend context for follow-up questions.
    const history: ChatHistoryMessage[] = summaryTurns
      .filter((t) => t.content.trim())
      .map((t) => ({ role: t.role, content: t.content }));

    setSummaryTurns((prev) => [...prev, { role: 'user', content: qLabel }, { role: 'assistant', content: '' }]);

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
      await expressionChatStream(id, sp, handlers, question, history);
    } catch (e) {
      setSummaryError(e instanceof Error ? e.message : 'AI Summary failed');
    } finally {
      setSummaryLoading(false);
    }
  }

  async function onFollowUp() {
    const q = followUp.trim();
    if (!q || summaryLoading) return;
    setFollowUp('');
    await streamSummary(q);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') runSearch();
  }

  const canSummarize =
    mode === 'search' &&
    Boolean(exprData) &&
    exprData?.status === 'success' &&
    !exprLoading &&
    !exprError;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <div className="max-w-content mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-teal-brand inline-flex items-center gap-2">
            <BarChart3Icon className="size-7 text-[#475569]" /> {t('title')}
          </h1>
          <p className="text-slate-600 mt-1">
            {t('subtitle')} ·
            <span className="text-slate-500"> 251,227 {tf('genes')} · 37.3M {tf('samples')}</span>
          </p>
        </div>

        <div className="rounded-2xl border border-[#f1f5f9] bg-white shadow-sm p-5 mb-6">
          <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-end">
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t('species')}</label>
              <select
                value={species}
                onChange={(e) => setSpecies(e.target.value)}
                className="w-full md:w-auto rounded-lg border border-[#CBD5E1] bg-white px-3 py-2 text-sm text-slate-800 min-w-[200px] focus:border-[#475569] focus:outline-none"
              >
                {SPECIES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-xs text-slate-500 mb-1">
                Gene ID (e.g. <span className="font-mono">{DEMO_GENES[0].geneId}</span>)
              </label>
              <input
                type="text"
                value={geneId}
                onChange={(e) => setGeneId(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder={t('geneIdPlaceholder')}
                className="w-full rounded-lg border border-[#CBD5E1] px-3 py-2 text-sm font-mono text-slate-800 focus:outline-none focus:border-[#475569]"
              />
            </div>
            <button
              onClick={() => runSearch()}
              disabled={!geneId.trim() || exprLoading}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-[#475569] text-white text-sm font-semibold hover:bg-[#334155] transition-colors whitespace-nowrap disabled:cursor-not-allowed"
            >
              <BarChart3Icon className="size-4" />
              {exprLoading ? t('analyzing') : t('analyze')}
            </button>
          </div>

          {mode === 'search' && (
            <div className="flex flex-wrap items-center gap-4 mt-3 pt-3 border-t border-[#E2E8F0]">
              <span className="text-[11px] text-slate-500">{t('coexpLabel')}:</span>
              <label className="text-xs text-slate-600 flex items-center gap-1.5">
                {t('topK')}
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={topK}
                  onChange={(e) => setTopK(Math.max(1, Math.min(200, Number(e.target.value) || 20)))}
                  className="w-16 rounded border border-[#CBD5E1] px-2 py-1 text-xs"
                />
              </label>
              <label className="text-xs text-slate-600 flex items-center gap-1.5">
                {t('minCorr')}
                <input
                  type="number"
                  step={0.05}
                  min={0}
                  max={1}
                  value={minCorr}
                  onChange={(e) => setMinCorr(Math.max(0, Math.min(1, Number(e.target.value) || 0)))}
                  className="w-16 rounded border border-[#CBD5E1] px-2 py-1 text-xs"
                />
              </label>
            </div>
          )}
        </div>

        {mode === 'idle' && (
          <div className="space-y-4">
            {overviewError && <ErrorBanner message={overviewError} />}
            {!overview && !overviewError && <LoadingBanner label={t("loadingOverview")} />}
            {overview && (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <SummaryStat label={t('statSpecies')} value={overview.total.species} />
                  <SummaryStat label={t('statGenes')} value={overview.total.genes.toLocaleString()} />
                  <SummaryStat label={t('statSamples')} value={overview.total.samples.toLocaleString()} />
                  <SummaryStat label={t('statRows')} value={`${(overview.total.rows / 1_000_000).toFixed(1)}M`} />
                </div>
                <OverviewTable species={overview.species} />
                <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-xs text-slate-600">
                  <strong className="text-slate-700">{t('reliabilityTiers')}:</strong>{' '}
                  {t('reliabilityDesc')}
                </div>

                <div className="rounded-xl border border-[#f1f5f9] bg-gradient-to-br from-[#f8fafc] to-white p-5">
                  <h3 className="text-sm font-semibold text-[#334155] mb-2 inline-flex items-center gap-2">
                    <SparklesIcon className="size-4" /> {t('aiSummary')}
                  </h3>
                  <ul className="text-xs text-slate-700 space-y-1.5 list-disc pl-5">
                    <li>{t('aiBullet1')}</li>
                    <li>{t('aiBullet2')}</li>
                    <li>{t('aiBullet3')}</li>
                  </ul>
                </div>

                <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-xs text-slate-600">
                  <strong className="text-slate-700 inline-flex items-center gap-1.5">
                    <InfoIcon className="size-3.5 text-[#475569]" /> {t('tryThese')}:
                  </strong>{' '}
                  {DEMO_GENES.map((d, i) => (
                    <span key={d.geneId}>
                      {i > 0 ? ' · ' : null}
                      <button
                        type="button"
                        className="font-mono text-[#475569] hover:underline underline-offset-2"
                        title={`${d.species} / ${d.geneId}`}
                        onClick={() => runSearch(d.geneId, d.species)}
                      >
                        {d.geneId}
                      </button>{' '}
                      ({d.label})
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {mode === 'search' && (
          <>
            {canSummarize && (
              <div className="rounded-xl border border-[#f1f5f9] bg-gradient-to-br from-[#f8fafc] to-white shadow-sm overflow-hidden mb-6">
                <div className="px-5 py-3 border-b border-[#f1f5f9] flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                    <SparklesIcon className="size-4 text-[#475569]" /> AI Summary
                  </h3>
                  {isSignedIn && (
                    !summaryOpen ? (
                      <button
                        type="button"
                        onClick={() => streamSummary()}
                        disabled={summaryLoading}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700 transition-colors whitespace-nowrap"
                      >
                        <SparklesIcon className="size-4" /> {t('expressionChat')}
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
                  <AiSignInGate feature="Expression Chat" compact>
                    {summaryOpen ? (
                      <div className="space-y-4">
                        {summaryTurns.map((t, i) => (
                          <div key={i}>
                            {t.role === 'user' ? (
                              <div className="text-xs text-slate-500 mb-1">Q: {t.content}</div>
                            ) : (
                              <div className="rounded-lg bg-white border border-[#E2E8F0] px-4 py-3">
                                {t.content ? (
                                  <AgentMarkdown content={t.content} />
                                ) : summaryLoading ? (
                                  <span className="text-sm text-[#475569] inline-flex items-center gap-1">
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
                          <div className="rounded-lg bg-[#f8fafc] border border-[#f1f5f9] p-3 text-xs text-[#334155] space-y-1">
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
                            className="px-4 py-2 rounded-lg bg-[#475569] text-white text-sm font-medium hover:bg-[#334155] disabled:opacity-50 whitespace-nowrap"
                          >
                            {t('ask')}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-500">
                        Click <strong>Expression Chat</strong> to generate an AI interpretation of this expression profile.
                      </p>
                    )}
                  </AiSignInGate>
                </div>
              </div>
            )}

            <div className="flex gap-2 border-b border-[#E2E8F0] mb-6">
              <TabButton active={tab === 'overview'} onClick={() => setTab('overview')}>
                <span className="inline-flex items-center gap-1.5"><ClipboardListIcon className="size-4" /> 9-Species Overview</span>
              </TabButton>
              <TabButton active={tab === 'gene'} onClick={() => setTab('gene')}>
                <span className="inline-flex items-center gap-1.5"><DnaIcon className="size-4" /> Gene Profile</span>
              </TabButton>
            </div>

            {tab === 'overview' && (
              <div className="space-y-4">
                {overviewError && <ErrorBanner message={overviewError} />}
                {!overview && !overviewError && <LoadingBanner label={t("loadingOverview")} />}
                {overview && (
                  <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <SummaryStat label={t('statSpecies')} value={overview.total.species} />
                      <SummaryStat label={t('statGenes')} value={overview.total.genes.toLocaleString()} />
                      <SummaryStat label={t('statSamples')} value={overview.total.samples.toLocaleString()} />
                      <SummaryStat label={t('statRows')} value={`${(overview.total.rows / 1_000_000).toFixed(1)}M`} />
                    </div>
                    <OverviewTable species={overview.species} />
                    <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-xs text-slate-600">
                      <strong className="text-slate-700">{t('reliabilityTiers')}:</strong>{' '}
                      {t('reliabilityDesc')}
                    </div>
                  </>
                )}
              </div>
            )}

            {tab === 'gene' && (
              <div className="space-y-6">
                {exprError && <ErrorBanner message={exprError} />}
                {exprLoading && <LoadingBanner label={t("querying")} />}

                {exprData && exprData.status === 'success' && (
                  <>
                    <ExpressionSummary data={exprData} />

                    <div className="rounded-xl border border-[#E2E8F0] bg-white p-4 shadow-sm">
                      <h3 className="text-sm font-semibold text-slate-700 mb-3 inline-flex items-center gap-2">
                        <BarChart3Icon className="size-4 text-[#475569]" /> Tissue Expression Profile
                        <span className="text-xs text-slate-400 font-normal">
                          (mean FPKM across {exprData.n_samples} samples · top tissue highlighted in pink)
                        </span>
                      </h3>
                      <TissueBarChart tissues={exprData.tissue_profile} />
                    </div>

                    <div className="rounded-xl border border-[#E2E8F0] bg-white p-4 shadow-sm">
                      <h3 className="text-sm font-semibold text-slate-700 mb-3 inline-flex items-center gap-2">
                        <TargetIcon className="size-4 text-[#475569]" /> Top {exprData.top_samples.length} High-Expression Samples
                      </h3>
                      <TopSamplesTable samples={exprData.top_samples} />
                    </div>
                  </>
                )}

                <div className="rounded-xl border border-[#E2E8F0] bg-white p-4 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5">
                      <LinkIcon className="size-4 text-[#475569]" /> Co-expressed Genes (Pearson)
                    </span>
                    {coexpData && (
                      <span className="text-xs font-normal text-slate-500">
                        {coexpData.count} hits · {coexpData.n_samples} samples · {coexpData.reliability}
                      </span>
                    )}
                  </h3>

                  {coexpData?.warning && (
                    <div className="rounded-lg bg-amber-50 border border-amber-300 px-4 py-3 text-xs text-amber-800 mb-3">
                      {coexpData.warning}
                    </div>
                  )}

                  {coexpError && <ErrorBanner message={coexpError} />}
                  {coexpLoading && <LoadingBanner label={t("computing")} />}
                  {coexpData && coexpData.status === 'success' && (
                    <CoexpressionTable genes={coexpData.coexpressed} />
                  )}
                  {coexpData && coexpData.status === 'no_results' && (
                    <div className="text-xs text-slate-500 bg-slate-50 rounded-lg px-4 py-3 text-center">
                      {coexpData.message}
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-semibold border-b-2 transition-colors ${
        active
          ? 'text-[#B01A75] border-[#475569]'
          : 'text-slate-500 border-transparent hover:text-[#B01A75]'
      }`}
    >
      {children}
    </button>
  );
}

function SummaryStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-white border border-[#E2E8F0] px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className="text-xl font-bold text-slate-800">{value}</div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 flex items-start gap-2">
      <WarningIcon className="size-4 shrink-0 mt-[2px]" />
      <span>{message}</span>
    </div>
  );
}

function LoadingBanner({ label }: { label: string }) {
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-6 text-sm text-slate-500 text-center">
      <span className="inline-block w-2 h-2 bg-teal-600 rounded-full animate-pulse mr-2 align-middle" />
      {label}
    </div>
  );
}
