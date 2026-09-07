'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  searchProtein,
  proteinChatStream,
  fetchProteinSpecies,
  type AgentStreamHandlers,
  type ChatHistoryMessage,
  type ProteinSpeciesCoverage,
} from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { SPECIES, readGeneDeepLink } from '@/lib/species';
import { useTranslations } from 'next-intl';
import {
  MicroscopeIcon,
  DnaIcon,
  TargetIcon,
  LinkIcon,
  FlaskConicalIcon,
  DownloadIcon,
  SparklesIcon,
} from '@/components/ui/icons';
import AgentMarkdown from '@/components/AgentMarkdown';
import AiSignInGate from '@/components/AiSignInGate';
import MolStarViewer, { type MolStarViewerHandle } from '@/components/proteins/MolStarViewer';
import BindingSitesTable from '@/components/proteins/BindingSitesTable';
import { DEMO_GENES } from '@/lib/demoGenes';

type Mode = 'idle' | 'predict';

type ProteinData = {
  pdb_url?: string;
  pdb_file?: string;
  plddt_score?: number;
  plddt_label?: string;
  binding_sites?: { site: string; confidence: number }[];
  residue_sites?: { resname?: string; resno: number; site_type: string; confidence?: number }[];
  gene_id?: string;
  species?: string;
};

type SummaryTurn = { role: 'user' | 'assistant'; content: string };

const FALLBACK_SPECIES = SPECIES;

function plddtColor(label?: string) {
  if (label === 'Excellent') return '#10b981';
  if (label === 'Good') return '#3b82f6';
  if (label === 'Fair') return '#f59e0b';
  return '#ef4444';
}

function formatCount(n: number): string {
  return n > 0 ? n.toLocaleString() : '—';
}

export default function ProteinsPage() {
  const t = useTranslations('proteins');
  const [coverage, setCoverage] = useState<ProteinSpeciesCoverage | null>(null);
  const readySpecies = coverage?.ready?.length ? coverage.ready : FALLBACK_SPECIES;
  const allSpecies = coverage?.species?.length ? coverage.species : FALLBACK_SPECIES;

  const [species, setSpecies] = useState('Cucumber');
  const [geneId, setGeneId] = useState('');
  const [mode, setMode] = useState<Mode>('idle');
  const [predictData, setPredictData] = useState<ProteinData | null>(null);
  const [predictLoading, setPredictLoading] = useState(false);
  const [predictError, setPredictError] = useState('');

  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryTurns, setSummaryTurns] = useState<SummaryTurn[]>([]);
  const [summaryStatuses, setSummaryStatuses] = useState<string[]>([]);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState('');
  const [followUp, setFollowUp] = useState('');
  const { isSignedIn } = useAuth();

  const predictViewerRef = useRef<MolStarViewerHandle>(null);

  // Deep links from ChatPanel evidence cards: /proteins?gene=…&species=…
  useEffect(() => {
    const { geneId: gene, species: sp } = readGeneDeepLink();
    if (gene) runPredict(gene, sp || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchProteinSpecies()
      .then((data) => {
        if (cancelled) return;
        setCoverage(data);
        if (data.ready?.length && !data.ready.includes(species)) {
          setSpecies(data.ready[0]);
        }
      })
      .catch(() => {
        /* keep fallbacks */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only load coverage once
  }, []);

  const resetSummary = () => {
    setSummaryOpen(false);
    setSummaryTurns([]);
    setSummaryStatuses([]);
    setSummaryLoading(false);
    setSummaryError('');
    setFollowUp('');
  };

  const runPredict = async (geneOverride?: string, speciesOverride?: string) => {
    const id = (geneOverride ?? geneId).trim();
    if (!id) return;
    const sp = speciesOverride ?? species;
    setGeneId(id);
    if (speciesOverride) setSpecies(speciesOverride);
    resetSummary();
    setMode('predict');
    setPredictData(null);
    setPredictError('');
    setPredictLoading(true);
    try {
      const data = await searchProtein(sp, id);
      setPredictData(data);
    } catch (e) {
      setPredictError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setPredictLoading(false);
    }
  };

  const streamSummary = async (question: string = '') => {
    const id = (predictData?.gene_id || geneId).trim();
    if (!id || summaryLoading) return;
    if (!isSignedIn) return;
    const sp = predictData?.species || species;
    const qLabel = question.trim() ? question.trim() : `Overview summary of ${id} protein structure`;

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
      await proteinChatStream(id, sp, handlers, question, history);
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

  const canSummarize =
    mode === 'predict' &&
    Boolean(predictData?.pdb_url) &&
    !predictLoading &&
    !predictError;

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
                {allSpecies.map((s) => (
                  <option key={s} value={s} disabled={!readySpecies.includes(s)}>
                    {s}{readySpecies.includes(s) ? '' : t('comingSoon')}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-[2]">
              <label className="block text-xs text-slate-500 mb-1">{t('geneId')}</label>
              <input
                value={geneId}
                onChange={(e) => setGeneId(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void runPredict(); }}
                placeholder={`e.g. ${DEMO_GENES[0].geneId}`}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:border-teal-500 focus:outline-none"
              />
            </div>
            <button
              onClick={() => void runPredict()}
              disabled={!geneId.trim() || predictLoading}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-[#0D9488] text-white text-sm font-semibold hover:bg-[#0F766E] transition-colors whitespace-nowrap disabled:cursor-not-allowed"
            >
              {predictLoading ? t('predicting') : (<><SparklesIcon className="size-4" /> {t('predict')}</>)}
            </button>
          </div>
        </div>

        {mode === 'predict' && (
          <div className="space-y-5">
            {canSummarize && (
              <div className="rounded-xl border border-[#CCFBF1] bg-gradient-to-br from-[#F0FDFA] to-white shadow-sm overflow-hidden">
                <div className="px-5 py-3 border-b border-[#CCFBF1] flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                    <SparklesIcon className="size-4 text-[#0D9488]" /> {t('aiSummary')}
                  </h3>
                  {isSignedIn && (
                    !summaryOpen ? (
                      <button
                        type="button"
                        onClick={() => streamSummary()}
                        disabled={summaryLoading}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700 transition-colors whitespace-nowrap"
                      >
                        <SparklesIcon className="size-4" /> {t('proteinChat')}
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
                  <AiSignInGate feature="Protein Chat" compact>
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

            <PredictPanel
              data={predictData}
              loading={predictLoading}
              error={predictError}
              viewerRef={predictViewerRef}
            />
          </div>
        )}

        {mode === 'idle' && (
          <ProteinsLanding
            coverage={coverage}
            onTryExample={(sp, gid) => runPredict(gid, sp)}
          />
        )}
      </div>
    </div>
  );
}

function PredictPanel({
  data, loading, error, viewerRef,
}: {
  data: ProteinData | null;
  loading: boolean;
  error: string;
  viewerRef: React.RefObject<MolStarViewerHandle | null>;
}) {
  const t = useTranslations('proteins');
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
  if (!data || !data.pdb_url) {
    return (
      <div className="rounded-xl border border-[#E2E8F0] bg-white p-8 text-center text-slate-500 text-sm">
        {t('noData')}
      </div>
    );
  }
  return (
    <div className="space-y-5">
      {data.plddt_score !== undefined && (
        <div className="rounded-xl bg-[#EAF4FF] border border-[#D7EAFE] px-5 py-4">
          <div className="text-xs mb-1" style={{ color: '#1F4E79' }}>{t('confidence')}</div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold" style={{ color: plddtColor(data.plddt_label) }}>
              {data.plddt_score.toFixed(1)}
            </span>
            <span className="text-sm" style={{ color: '#1F4E79' }}>{data.plddt_label}</span>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-2.5 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-800">{t('structure3d')}</h3>
          {data.pdb_file && (
            <a
              href={data.pdb_url}
              download={data.pdb_file}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium text-white bg-teal-accent hover:bg-teal-700 transition-colors"
            >
              <DownloadIcon className="size-3.5" /> {t('downloadPdb')}
            </a>
          )}
        </div>
        <div className="p-3">
          <MolStarViewer pdbUrl={data.pdb_url} label={data.gene_id} />
        </div>
      </div>

      <div className="rounded-xl bg-[#EAF4FF] border border-[#D7EAFE] px-5 py-4">
        <BindingSitesTable
          bindingSites={data.binding_sites}
          residueSites={data.residue_sites}
          viewerRef={viewerRef}
        />
      </div>
    </div>
  );
}

function ProteinsLanding({
  coverage,
  onTryExample,
}: {
  coverage: ProteinSpeciesCoverage | null;
  onTryExample?: (species: string, geneId: string) => void;
}) {
  const t = useTranslations('proteins');
  const details = coverage?.details ?? [];
  // Fallback mirrors data/science/structures (used only if /species has no details).
  const rows =
    details.length > 0
      ? details
      : [
          { species: 'Cucumber', n_pdb: 23736, n_site_json: 23730, ready: true, has_sites: true },
          { species: 'Watermelon', n_pdb: 14901, n_site_json: 0, ready: true, has_sites: false },
          { species: 'Melon', n_pdb: 27757, n_site_json: 27757, ready: true, has_sites: true },
          { species: 'Pumpkin (C. moschata)', n_pdb: 29898, n_site_json: 29898, ready: true, has_sites: true },
          { species: 'Pumpkin (C. pepo)', n_pdb: 26813, n_site_json: 26813, ready: true, has_sites: true },
          { species: 'BitterGourd', n_pdb: 39839, n_site_json: 39839, ready: true, has_sites: true },
          { species: 'BottleGourd', n_pdb: 21629, n_site_json: 21629, ready: true, has_sites: true },
          { species: 'WaxGourd', n_pdb: 26897, n_site_json: 26897, ready: true, has_sites: true },
          { species: 'SpongeGourd', n_pdb: 30846, n_site_json: 30846, ready: true, has_sites: true },
        ];

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-[#E2E8F0] bg-gradient-to-r from-[#EAF4FF] to-white">
          <h3 className="text-sm font-semibold inline-flex items-center gap-2" style={{ color: '#1F4E79' }}>
            <MicroscopeIcon className="size-4" /> {t('coverageTitle')}
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">{t('thSpecies')}</th>
                <th className="text-right px-4 py-2 font-semibold">{t('thPdbs')}</th>
                <th className="text-left px-4 py-2 font-semibold">{t('thSites')}</th>
                <th className="text-center px-4 py-2 font-semibold">{t('thStatus')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E2E8F0]">
              {rows.map((row) => (
                <ProteinLandingRow
                  key={row.species}
                  species={row.species}
                  pdbs={formatCount(row.n_pdb)}
                  sites={
                    row.has_sites
                      ? t('gpsiteGenes', { n: formatCount(row.n_site_json) })
                      : row.ready
                        ? '—'
                        : '—'
                  }
                  status={row.ready ? 'ready' : 'soon'}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-[#E2E8F0] bg-gradient-to-r from-[#F0FDFA] to-[#ECFDF5]">
          <h3 className="text-sm font-semibold text-[#0F766E] inline-flex items-center gap-2">
            <MicroscopeIcon className="size-4" /> {t('whatTitle')}
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <tbody className="divide-y divide-[#E2E8F0]">
              <ProteinLandingFeatureRow
                icon={<DnaIcon className="size-4" />}
                name={t('rowStructureName')}
                desc={t('rowStructureDesc')}
              />
              <ProteinLandingFeatureRow
                icon={<TargetIcon className="size-4" />}
                name={t('rowConfidenceName')}
                desc={t('rowConfidenceDesc')}
              />
              <ProteinLandingFeatureRow
                icon={<LinkIcon className="size-4" />}
                name={t('rowSitesName')}
                desc={t('rowSitesDesc')}
              />
              <ProteinLandingFeatureRow
                icon={<FlaskConicalIcon className="size-4" />}
                name={t('rowResiduesName')}
                desc={t('rowResiduesDesc')}
              />
              <ProteinLandingFeatureRow
                icon={<DownloadIcon className="size-4" />}
                name={t('rowDownloadName')}
                desc={t('rowDownloadDesc')}
              />
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-[#CCFBF1] bg-gradient-to-br from-[#F0FDFA] to-white p-5">
        <h3 className="text-sm font-semibold text-[#0F766E] mb-2 inline-flex items-center gap-2">
          <SparklesIcon className="size-4" /> {t('aiSummary')}
        </h3>
        <ul className="text-xs text-slate-700 space-y-1.5 list-disc pl-5">
          <li>{t('aiBullet1')}</li>
          <li>{t('aiBullet2')}</li>
          <li>{t('aiBullet3')}</li>
        </ul>
      </div>

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

function ProteinLandingRow({
  species,
  pdbs,
  sites,
  status,
}: {
  species: string;
  pdbs: string;
  sites: string;
  status: 'ready' | 'soon';
}) {
  const t = useTranslations('proteins');
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-4 py-2.5 font-semibold text-slate-800">{species}</td>
      <td className="px-4 py-2.5 text-right font-mono text-slate-700">{pdbs}</td>
      <td className="px-4 py-2.5 text-slate-600">{sites}</td>
      <td className="px-4 py-2.5 text-center">
        {status === 'ready' ? (
          <span className="inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
            ✅ {t('ready')}
          </span>
        ) : (
          <span className="inline-block rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
            ⏳ {t('comingSoon').trim()}
          </span>
        )}
      </td>
    </tr>
  );
}

function ProteinLandingFeatureRow({ icon, name, desc }: { icon: ReactNode; name: string; desc: string }) {
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-4 py-2.5 w-12 text-[#0D9488]">{icon}</td>
      <td className="px-2 py-2.5 font-semibold text-slate-800 whitespace-nowrap min-w-[160px]">{name}</td>
      <td className="px-4 py-2.5 text-slate-600">{desc}</td>
    </tr>
  );
}
