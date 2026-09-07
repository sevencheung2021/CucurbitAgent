'use client';

import { useEffect, useRef, useState } from 'react';
import {
  fetchLiteraturePapers,
  paperChatStream,
  type AgentStreamHandlers,
} from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useTranslations } from 'next-intl';
import AgentMarkdown from '@/components/AgentMarkdown';
import LiteratureDataCard from '@/components/LiteratureDataCard';
import AiSignInGate from '@/components/AiSignInGate';
import {
  BookOpenIcon,
  BotIcon,
  SendIcon,
  SparklesIcon,
} from '@/components/ui/icons';

const EXAMPLE_QUESTIONS = [
  'Cucumber Fusarium wilt resistance genes and related papers',
  'Watermelon flesh color and carotenoid biosynthesis',
  'Melon fruit ripening and ethylene signaling literature',
];

type ChatTurn = {
  role: 'user' | 'assistant';
  content: string;
  papers?: any[];
};

export default function LiteraturesPage() {
  const t = useTranslations('literatures');
  const [q, setQ] = useState('');
  const [inputQ, setInputQ] = useState('');
  const [page, setPage] = useState(1);
  const [jumpInput, setJumpInput] = useState('1');
  const [data, setData] = useState<any>(null);
  const [subject, setSubject] = useState('');
  const [searching, setSearching] = useState(false);
  const listTopRef = useRef<HTMLDivElement>(null);

  // Paper Chat state
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [chatStatuses, setChatStatuses] = useState<string[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState('');
  const { isSignedIn, ready: authReady } = useAuth();

  useEffect(() => {
    const isKeywordSearch = q.trim().length > 0;
    let cancelled = false;
    if (isKeywordSearch) setSearching(true);
    fetchLiteraturePapers(q, page, subject)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [q, page, subject]);

  // Keep the jump box in sync when page changes (Prev/Next/search/subject).
  useEffect(() => {
    setJumpInput(String(page));
  }, [page]);

  function pickSubject(s: string) {
    setSubject(s);
    setPage(1);
  }

  function submitSearch() {
    const trimmed = inputQ.trim();
    if (trimmed === q) return;
    setQ(trimmed);
    setPage(1);
  }

  function goToPage() {
    const total = Number(data?.pages) || 1;
    const n = parseInt(jumpInput, 10);
    if (!Number.isFinite(n)) {
      setJumpInput(String(page));
      return;
    }
    const target = Math.min(total, Math.max(1, n));
    setJumpInput(String(target));
    if (target !== page) setPage(target);
    // Scroll to the paper list so the user isn't left at the footer.
    requestAnimationFrame(() => {
      listTopRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function resetChat() {
    setChatOpen(false);
    setChatTurns([]);
    setChatStatuses([]);
    setChatLoading(false);
    setChatError('');
    setChatInput('');
  }

  async function askPaper(question: string) {
    const text = question.trim();
    if (!text || chatLoading) return;
    if (!isSignedIn) return;

    setChatOpen(true);
    setChatError('');
    setChatStatuses([]);
    setChatLoading(true);
    setChatInput('');
    setChatTurns((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '', papers: undefined },
    ]);

    let answer = '';
    const handlers: AgentStreamHandlers = {
      onStatus: (m) => setChatStatuses((prev) => [...prev, m]),
      onToken: (t) => {
        answer += t;
        setChatTurns((prev) => {
          const next = [...prev];
          const last = next.length - 1;
          if (last >= 0 && next[last].role === 'assistant') {
            next[last] = { ...next[last], content: answer };
          }
          return next;
        });
      },
      onPapers: (papers) => {
        setChatTurns((prev) => {
          const next = [...prev];
          const last = next.length - 1;
          if (last >= 0 && next[last].role === 'assistant') {
            next[last] = { ...next[last], papers: papers || [] };
          }
          return next;
        });
      },
      onError: (m) => setChatError(m),
      onDone: () => {},
    };

    try {
      await paperChatStream(text, handlers);
    } catch (e) {
      setChatError(e instanceof Error ? e.message : 'Paper chat failed');
    } finally {
      setChatLoading(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* ---------- Paper Chat ---------- */}
      <section className="mb-8 rounded-xl border border-[#CCFBF1] bg-gradient-to-br from-[#F0FDFA] to-white shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-[#CCFBF1] flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <BotIcon className="size-4 text-[#0D9488]" />
              Paper Chat
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {t('chatDesc')}
            </p>
          </div>
          {chatOpen && (
            <button
              type="button"
              onClick={resetChat}
              className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600 hover:bg-white transition"
            >
              {t('clearChat')}
            </button>
          )}
        </div>

        <div className="p-5 space-y-4">
          <AiSignInGate feature="Paper Chat">
            {!chatOpen && (
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_QUESTIONS.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => askPaper(ex)}
                    disabled={chatLoading}
                    className="rounded-full border border-[#CCFBF1] bg-white px-3 py-1.5 text-[11px] text-[#0F766E] hover:bg-[#CCFBF1] transition text-left disabled:opacity-50"
                  >
                    <span className="inline-flex items-center gap-1">
                      <SparklesIcon className="size-3 shrink-0" />
                      {ex}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {chatOpen && (
              <div className="space-y-4">
                {chatTurns.map((t, i) => (
                  <div key={i}>
                    {t.role === 'user' ? (
                      <div className="text-xs text-slate-500 mb-1">Q: {t.content}</div>
                    ) : (
                      <div className="space-y-3">
                        <div className="rounded-lg bg-white border border-[#E2E8F0] px-4 py-3">
                          {t.content ? (
                            <AgentMarkdown content={t.content} />
                          ) : chatLoading ? (
                            <span className="text-sm text-[#0D9488] inline-flex items-center gap-1">
                              <span className="cuagent-thinking-dot" />
                              <span className="cuagent-thinking-dot" />
                              <span className="cuagent-thinking-dot" />
                            </span>
                          ) : null}
                        </div>
                        {t.papers && t.papers.length > 0 && (
                          <LiteratureDataCard
                            data={{
                              status: 'success',
                              query: chatTurns[i - 1]?.content || '',
                              papers: t.papers,
                            }}
                          />
                        )}
                      </div>
                    )}
                  </div>
                ))}

                {chatStatuses.length > 0 && chatLoading && (
                  <div className="rounded-lg bg-[#F0FDFA] border border-[#CCFBF1] p-3 text-xs text-[#0F766E] space-y-1">
                    {chatStatuses.slice(-4).map((s, i) => (
                      <div key={`${s}-${i}`}>• {s}</div>
                    ))}
                  </div>
                )}

                {chatError && <p className="text-sm text-red-600">{chatError}</p>}
              </div>
            )}

            <div className="flex gap-2 items-stretch">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    askPaper(chatInput);
                  }
                }}
                disabled={chatLoading || !authReady}
                placeholder={t('placeholder')}
                className="flex-1 px-3 py-2.5 rounded-lg border border-slate-200 text-sm focus:border-[#0D9488] focus:outline-none focus:ring-2 focus:ring-[#0D9488]/15 disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => askPaper(chatInput)}
                disabled={chatLoading || !chatInput.trim()}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-[#0D9488] text-white text-sm font-medium hover:bg-[#0F766E] disabled:opacity-50 whitespace-nowrap"
                aria-label="Ask Paper Chat"
              >
                <SendIcon className="size-4" />
                {t('ask')}
              </button>
            </div>
          </AiSignInGate>
        </div>
      </section>

      {/* ---------- Literature Hub ---------- */}
      <section>
        <h1 className="mb-3 text-2xl font-extrabold text-[#0f766e] inline-flex items-center gap-2">
          <BookOpenIcon className="size-6 text-[#0D9488]" />
          {t('hubTitle')}
        </h1>
        <div className="mb-5 grid gap-3 md:grid-cols-[1fr_auto]">
          <input
            className="rounded-lg border border-[#E2E8F0] px-4 py-3 focus:outline-none focus:border-[#0f766e] focus:ring-2 focus:ring-[#0f766e]/20"
            placeholder={t('searchPlaceholder')}
            value={inputQ}
            onChange={(e) => setInputQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitSearch();
            }}
          />
          <button
            onClick={submitSearch}
            className="flex items-center justify-center gap-2 rounded-lg bg-[#0f766e] px-6 py-3 font-semibold text-white hover:bg-[#0c5a52] transition-colors"
          >
            {t('search')}
          </button>
        </div>
        {data && (
          <>
            <div className="mb-3 flex flex-wrap gap-2">
              {[
                { key: '', label: '__ALL__', color: '#0f766e' },
                {
                  key: 'cgi',
                  label: 'Cucurbit Genetic Improvement and Resistance',
                  color: '#15803d',
                },
                { key: 'other', label: 'Other', color: '#475569' },
              ].map((opt) => {
                const active = subject === opt.key;
                return (
                  <button
                    key={opt.key || 'all'}
                    onClick={() => pickSubject(opt.key)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                      active
                        ? 'border-transparent text-white'
                        : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                    }`}
                    style={active ? { backgroundColor: opt.color } : {}}
                  >
                    {opt.key === '' ? t('all') : opt.key === 'cgi' ? t('subjectCgi') : t('subjectOther')}
                  </button>
                );
              })}
            </div>
            {searching ? (
              <div className="mb-4 flex items-center gap-2 text-sm text-[#0f766e]">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-[#0f766e]"></span>
                {t('searching')}
              </div>
            ) : null}
            <div ref={listTopRef} className="space-y-3 scroll-mt-4">
              {data.papers.map((p: any, i: number) => (
                <PaperCard key={p.pmid || p.doi || `${p.title}-${i}`} paper={p} />
              ))}
            </div>
            {data.pages > 1 && (
              <div className="mt-6 flex flex-col gap-3 sm:relative sm:flex-row sm:items-center sm:justify-center">
                {/* Prev / page / Next stay centered */}
                <div className="flex items-center justify-center gap-2 sm:gap-3">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                    className="rounded border border-[#DADDE1] px-4 py-2 text-sm disabled:opacity-40"
                  >
                    {t('prev')}
                  </button>
                  <span className="px-2 py-2 text-sm text-[#64748B] tabular-nums">
                    {t('pageOf', { page, pages: data.pages })}
                  </span>
                  <button
                    type="button"
                    disabled={page >= data.pages}
                    onClick={() => setPage(page + 1)}
                    className="rounded border border-[#DADDE1] px-4 py-2 text-sm disabled:opacity-40"
                  >
                    {t('next')}
                  </button>
                </div>
                {/* Jump controls: right edge (desktop), below on small screens */}
                <div className="flex items-center justify-end gap-1.5 sm:absolute sm:right-0 sm:top-1/2 sm:-translate-y-1/2">
                  <label className="inline-flex items-center gap-1.5 text-sm text-[#64748B]">
                    <span className="whitespace-nowrap">{t('goTo')}</span>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={data.pages}
                      value={jumpInput}
                      onChange={(e) => setJumpInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          goToPage();
                        }
                      }}
                      className="w-16 rounded border border-[#DADDE1] px-2 py-2 text-center text-sm text-slate-700 tabular-nums focus:border-[#0f766e] focus:outline-none focus:ring-2 focus:ring-[#0f766e]/20"
                      aria-label={t('pageLabel')}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={goToPage}
                    className="rounded border border-[#DADDE1] px-3 py-2 text-sm font-medium text-slate-700 hover:border-[#0f766e] hover:text-[#0f766e]"
                  >
                    {t('go')}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

const SUBJECT_BADGES: Record<string, { label: string; color: string }> = {
  cgi: {
    label: 'Cucurbit Genetic Improvement and Resistance',
    color: '#15803d',
  },
  other: { label: 'Other', color: '#475569' },
  // Legacy labels (pre two-way reclassify) — map to nearest display.
  agri: {
    label: 'Cucurbit Genetic Improvement and Resistance',
    color: '#15803d',
  },
  biomed: { label: 'Other', color: '#475569' },
  food: { label: 'Other', color: '#475569' },
  chem: { label: 'Other', color: '#475569' },
};

function PaperCard({ paper }: { paper: any }) {
  const t2 = useTranslations('literatures');
  const year = paper.year || paper.pub_date || 'N/A';
  const subj = paper.subject || 'other';
  const badge = SUBJECT_BADGES[subj] || SUBJECT_BADGES.other;
  return (
    <details className="rounded-lg border border-[#E2E8F0] bg-white p-4 shadow-sm">
      <summary className="cursor-pointer text-base font-bold text-[#1a252f]">
        <span
          className="mr-2 inline-block rounded-full px-2 py-0.5 align-middle text-xs font-semibold text-white"
          style={{ backgroundColor: badge.color }}
        >
          {badge.label}
        </span>
        {year} · {paper.title}
      </summary>
      <div className="mt-3 space-y-2 text-sm text-[#475569]">
        {paper.authors && <p>{paper.authors}</p>}
        {paper.journal && <p className="italic">{paper.journal}</p>}
        <div className="flex flex-wrap gap-3">
          {paper.doi && (
            <a className="text-[#2980b9] underline" href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer">
              DOI
            </a>
          )}
          {paper.pmid && (
            <a className="text-[#2980b9] underline" href={`https://pubmed.ncbi.nlm.nih.gov/${paper.pmid}/`} target="_blank" rel="noreferrer">
              PubMed
            </a>
          )}
        </div>
        {paper.abstract && <p className="leading-relaxed">{paper.abstract}</p>}
        {paper.match_snippet && paper.match_snippet !== paper.abstract && (
          <p className="mt-2 rounded-lg bg-[#F0FDFA] p-3 text-xs leading-relaxed text-[#0F766E]">
            <span className="font-semibold">{t2('matchedExcerpt', { source: paper.match_source || 'hybrid' })}</span>
            {paper.match_snippet}
          </p>
        )}
      </div>
    </details>
  );
}
