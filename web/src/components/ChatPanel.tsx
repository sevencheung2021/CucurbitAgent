'use client';

import { useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/routing';
import {
  agentChatStream,
  type AgentStreamHandlers,
  type ChatHistoryMessage,
} from '@/lib/api';
import AgentComposer from '@/components/AgentComposer';
import AgentMarkdown, { stripDsmlMarkup } from '@/components/AgentMarkdown';
import LiteratureDataCard from '@/components/LiteratureDataCard';
import GeneDataCard from '@/components/GeneDataCard';
import ExpressionDataCard from '@/components/ExpressionDataCard';
import ProteinDataCard from '@/components/ProteinDataCard';
import AiSignInGate from '@/components/AiSignInGate';
import { useAuth } from '@/lib/auth';
import {
  BookOpenIcon,
  DnaIcon,
  BarChart3Icon,
  MicroscopeIcon,
  BotIcon,
  UserIcon,
} from '@/components/ui/icons';

type EvidenceItem = { tool: string; data: any };

type Msg = {
  role: 'user' | 'assistant';
  content: string;
  /** Full-agent tool evidence cards */
  evidence?: EvidenceItem[];
  /** Local capability intro (no API call) */
  kind?: 'capability';
};

const EXAMPLE_PROMPTS = [
  {
    label: 'Gene function + expression + literature',
    prompt:
      'What is the function, tissue expression profile, and related papers for CsaV3_3G027830?',
  },
  {
    label: 'Structure & binding sites',
    prompt:
      'Interpret the protein structure and predicted binding sites of CsaV3_1G000080',
  },
  {
    label: 'Disease resistance genes',
    prompt: 'Cucumber Fusarium wilt resistance-related genes and literature',
  },
  {
    label: 'Fruit color & carotenoids',
    prompt: 'Watermelon flesh color and carotenoid-related genes',
  },
];

const CAPABILITY_EN =
  "I'm **CucurbitAgent**, a research assistant for Cucurbitaceae genomics and molecular breeding (cucumber, watermelon, melon, and related species).\n\n" +
  'I can help with:\n' +
  '- **Gene annotation**: structure, GO, Pfam, natural variants, orthologs\n' +
  '- **Expression**: tissue profiles, tau specificity, co-expression\n' +
  '- **Protein structure**: ESMFold pLDDT and predicted binding sites\n' +
  '- **Local literature**: hybrid search over ~20k curated cucurbit papers\n\n' +
  'Ask a research question, or try an example below:';

const CAPABILITY_ZH =
  '我是 **CucurbitAgent**，面向葫芦科（黄瓜、西瓜、甜瓜等）基因组学与分子育种的研究助手。\n\n' +
  '我可以帮你：\n' +
  '- **基因注释**：结构、GO、Pfam、自然变异、同源基因\n' +
  '- **表达谱**：组织表达、tau、共表达\n' +
  '- **蛋白结构**：ESMFold pLDDT、预测结合位点\n' +
  '- **本地文献**：约 2 万篇葫芦科论文的混合检索与引用回答\n\n' +
  '请直接问科研问题，或点下方示例开始：';

const CAPABILITY_KO =
  '저는 **CucurbitAgent**입니다. 박과(오이, 수박, 멜론 등) 유전체학·분자육종 연구 도우미입니다.\n\n' +
  '도와드릴 수 있는 것:\n' +
  '- **유전자 주석**: 구조, GO, Pfam, 변이, 오솔로그\n' +
  '- **발현**: 조직 발현, tau, 공발현\n' +
  '- **단백질 구조**: ESMFold pLDDT, 예측 결합 부위\n' +
  '- **문헌**: 약 2만 편 박과 논문 하이브리드 검색\n\n' +
  '연구 질문을 입력하거나 아래 예시를 눌러 보세요:';

/** Lightweight UI-language guess for local capability replies (answers follow input). */
function guessReplyLang(text: string): 'zh' | 'ko' | 'ja' | 'en' {
  if (/[가-힣]/.test(text)) return 'ko';
  if (/[ぁ-ゖァ-ヾ]/.test(text)) return 'ja';
  if (/[一-鿿]/.test(text)) return 'zh';
  return 'en';
}

function capabilityReplyFor(text: string): string {
  const lang = guessReplyLang(text);
  if (lang === 'zh') return CAPABILITY_ZH;
  if (lang === 'ko') return CAPABILITY_KO;
  // Japanese / default: English chrome; research answers still follow input via backend.
  return CAPABILITY_EN;
}

/** Greetings / meta questions — answer locally, do not search. */
function isChitchatOrMeta(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (!t || t.length > 80) return false;
  const compact = t.replace(/[\s.,，。!?？！]+/g, '');
  if (
    /^(你好|您好|嗨|哈喽|谢谢|感谢|早上好|下午好|晚上好|再见)$/.test(compact) ||
    /^(hi|hello|hey|thanks|thankyou|bye|goodbye)$/i.test(compact)
  ) {
    return true;
  }
  if (
    /(你能做什么|你会什么|你是谁|介绍一下你自己|功能介绍)/.test(t) ||
    /\b(what can you do|who are you|what are you|help me)\b/i.test(t)
  ) {
    return true;
  }
  return false;
}

function moduleDeepLink(tool: string, data: any): { href: string; labelKey: string } | null {
  const geneId = data?.gene_id || data?.geneId;
  const species = data?.species ? `&species=${encodeURIComponent(data.species)}` : '';
  if (tool === 'search_gene_comprehensive' && geneId) {
    return { href: `/genes?gene=${encodeURIComponent(geneId)}${species}`, labelKey: 'openGenes' };
  }
  if (tool === 'search_gene_expression' && geneId) {
    return { href: `/expression?gene=${encodeURIComponent(geneId)}`, labelKey: 'openExpression' };
  }
  if (tool === 'search_protein_structure' && geneId) {
    return { href: `/proteins?gene=${encodeURIComponent(geneId)}${species}`, labelKey: 'openProteins' };
  }
  if (tool === 'search_literatureDB') {
    return { href: '/literatures', labelKey: 'browseLiteratures' };
  }
  return null;
}

/** Map agent tool JSON → ExpressionDataCard props (field-name differences). */
function adaptExpressionForCard(data: any) {
  if (!data) return data;
  const rawTissues = data.tissue_profile || data.tissue_profile_top8 || [];
  const tissues = rawTissues.map((t: any) => ({
    tissue: t.tissue,
    mean: t.mean ?? t.mean_fpkm ?? 0,
  }));
  return {
    ...data,
    species_common: data.species_common || data.species || '',
    tissue_profile: tissues,
    condition_distribution: data.condition_distribution || data.condition_distribution_top5 || [],
    top_samples: data.top_samples || [],
  };
}

function EvidenceBlock({ items }: { items: EvidenceItem[] }) {
  const t = useTranslations('chat');
  return (
    <div className="space-y-3">
      {items.map((ev, i) => {
        const link = moduleDeepLink(ev.tool, ev.data);
        let card: ReactNode = null;
        if (ev.tool === 'search_gene_comprehensive') {
          card = <GeneDataCard data={ev.data} />;
        } else if (ev.tool === 'search_gene_expression') {
          card = <ExpressionDataCard data={adaptExpressionForCard(ev.data)} />;
        } else if (ev.tool === 'search_protein_structure') {
          card = <ProteinDataCard data={ev.data} />;
        } else if (ev.tool === 'search_literatureDB') {
          card = (
            <LiteratureDataCard
              data={{
                status: ev.data?.status || 'success',
                query: ev.data?.query || '',
                papers: ev.data?.papers || [],
                message: ev.data?.message,
              }}
            />
          );
        }
        if (!card) return null;
        return (
          <div key={`${ev.tool}-${i}`} className="space-y-1.5">
            {card}
            {link && (
              <div>
                <Link
                  href={link.href}
                  className="text-[11px] font-medium text-[#334155] hover:underline"
                >
                  → {t(`links.${link.labelKey}`)}
                </Link>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ModuleDeepLinks() {
  const t = useTranslations('chat');
  return (
    <div className="rounded-xl border border-[#E2E8F0] bg-slate-50 px-5 py-3 flex flex-wrap gap-x-4 gap-y-2">
      <Link href="/genes" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
        <DnaIcon className="size-4 text-[#475569]" /> {t('geneSearch')}
      </Link>
      <Link href="/expression" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
        <BarChart3Icon className="size-4 text-[#475569]" /> {t('expressionAnalyze')}
      </Link>
      <Link href="/proteins" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
        <MicroscopeIcon className="size-4 text-[#475569]" /> {t('proteinPredict')}
      </Link>
      <Link href="/literatures" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
        <BookOpenIcon className="size-4 text-[#475569]" /> {t('paperChat')}
      </Link>
    </div>
  );
}

function IdleShowcase({ onPick }: { onPick: (prompt: string) => void }) {
  const t = useTranslations('chat');
  return (
    <div className="rounded-2xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
      <div className="px-5 py-3 bg-gradient-to-r from-[#f8fafc] to-white border-b border-[#E2E8F0]">
        <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
          <BookOpenIcon className="size-4 text-[#475569]" />
          <span>{t('examplesTitle')}</span>
        </h3>
      </div>
      <ul className="divide-y divide-[#F1F5F9]">
        {EXAMPLE_PROMPTS.map((ex, i) => (
          <li key={ex.label} className="px-5 py-3.5 flex gap-3 items-start hover:bg-[#FAFEFC] transition">
            <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[#475569] text-white text-xs font-bold flex items-center justify-center">
              {i + 1}
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-semibold text-slate-800 mb-1">{ex.label}</h4>
              <p className="text-xs text-slate-600 leading-relaxed mb-2 line-clamp-2">{ex.prompt}</p>
              <button
                type="button"
                onClick={() => onPick(ex.prompt)}
                className="inline-flex items-center gap-1.5 rounded-full border border-[#f1f5f9] bg-[#f8fafc] px-2.5 py-1 text-[11px] text-[#334155] hover:bg-[#f1f5f9] transition"
              >
                <span aria-hidden className="text-[10px]">▶</span>
                {t('askThis')}
              </button>
            </div>
          </li>
        ))}
      </ul>
      <div className="px-5 py-3 bg-slate-50 border-t border-[#E2E8F0] flex flex-wrap gap-x-4 gap-y-2">
        <Link href="/genes" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
          <DnaIcon className="size-4 text-[#475569]" /> {t('geneSearch')}
        </Link>
        <Link href="/expression" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
          <BarChart3Icon className="size-4 text-[#475569]" /> {t('expressionAnalyze')}
        </Link>
        <Link href="/proteins" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
          <MicroscopeIcon className="size-4 text-[#475569]" /> {t('proteinPredict')}
        </Link>
        <Link href="/literatures" className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:text-[#475569] hover:underline">
          <BookOpenIcon className="size-4 text-[#475569]" /> {t('paperChat')}
        </Link>
      </div>
    </div>
  );
}

export default function ChatPanel({ title, subtitle }: { title?: string; subtitle?: string }) {
  const t = useTranslations('chat');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statuses, setStatuses] = useState<string[]>([]);
  const hasConversation = messages.length > 0 || statuses.length > 0 || Boolean(error);
  const { isSignedIn } = useAuth();

  async function runFullAgent(userText: string) {
    setError('');
    setStatuses(['Question received — starting…']);
    const history: ChatHistoryMessage[] = messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .filter((m) => m.kind !== 'capability')
      .map((m) => ({ role: m.role, content: m.content }))
      .filter((m) => m.content.trim());

    const assistantIndex = messages.length + 1;
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: userText },
      { role: 'assistant', content: '', evidence: [] },
    ]);
    setLoading(true);

    let rawSummary = '';
    const evidence: EvidenceItem[] = [];
    const updateAssistant = (patch: Partial<Msg>) =>
      setMessages((prev) => prev.map((m, i) => (i === assistantIndex ? { ...m, ...patch } : m)));

    try {
      const handlers: AgentStreamHandlers = {
        onStatus: (message: string) => setStatuses((prev) => [...prev, message]),
        onToken: (token: string) => {
          // Keep raw accumulation; strip only for display so an in-progress
          // DSML block can still close and reveal any text that follows it.
          rawSummary += token;
          updateAssistant({ content: stripDsmlMarkup(rawSummary), evidence: [...evidence] });
        },
        onToolResult: (tool: string, data: any) => {
          evidence.push({ tool, data });
          updateAssistant({ evidence: [...evidence] });
        },
        onPapers: (papers: any[]) => {
          // Backward-compatible if backend also emits papers
          evidence.push({
            tool: 'search_literatureDB',
            data: { status: 'success', query: userText, papers: papers || [] },
          });
          updateAssistant({ evidence: [...evidence] });
        },
        onError: (message: string) => setError(message),
        onDone: () => {},
      };
      await agentChatStream(userText, history, handlers);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }

  async function sendText(text: string) {
    const t = text.trim();
    if (!t || loading) return;
    if (!isSignedIn) return;
    setInput('');

    if (isChitchatOrMeta(t)) {
      setError('');
      setStatuses([]);
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: t },
        { role: 'assistant', content: capabilityReplyFor(t), kind: 'capability' },
      ]);
      return;
    }

    await runFullAgent(t);
  }

  async function send() {
    await sendText(input);
  }

  return (
    <div className="max-w-[760px] mx-auto px-4 py-8">
      {title && <h1 className="text-3xl font-bold text-teal-brand text-center mb-2">{title}</h1>}
      {subtitle && <p className="text-center text-slate-muted mb-2">{subtitle}</p>}
      <p className="text-center text-[11px] text-slate-400 mb-6">
        {t('toolsHint')}
      </p>
      <div className="space-y-4">
        <AiSignInGate feature="CucurbitAgent">
          <AgentComposer
            value={input}
            onChange={setInput}
            onSend={send}
            disabled={loading}
            placeholder={t('placeholder')}
          />
          {hasConversation ? (
            <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 min-h-[220px] space-y-4 shadow-sm mt-4">
              {messages.map((m, i) => {
                const isLastAssistant =
                  m.role === 'assistant' && i === messages.length - 1;
                const showLiveProgress = isLastAssistant && loading && statuses.length > 0;
                return (
                <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
                  <div className="mb-1 text-xs text-slate-card inline-flex items-center gap-1.5">
                    {m.role === 'user' ? (
                      <>
                        <UserIcon className="size-3.5" /> {t('you')}
                      </>
                    ) : (
                      <>
                        <BotIcon className="size-3.5 text-[#475569]" /> CucurbitAgent
                      </>
                    )}
                  </div>
                  <div
                    className={`inline-block max-w-[92%] rounded-lg px-4 py-2 text-left ${
                      m.role === 'user'
                        ? 'bg-teal-accent text-white text-sm leading-relaxed whitespace-pre-wrap'
                        : (m.evidence && m.evidence.length > 0) || showLiveProgress
                          ? 'bg-white'
                          : 'bg-[#f4f6f7]'
                    }`}
                  >
                    {m.role === 'user' ? (
                      m.content
                    ) : (
                      <div className="space-y-3">
                        {isLastAssistant && loading && !m.content && (
                          <div className="space-y-2">
                            <div className="flex items-center gap-2 text-sm text-[#475569]">
                              <span className="inline-flex items-center" aria-label="Working">
                                <span className="cuagent-thinking-dot" />
                                <span className="cuagent-thinking-dot" />
                                <span className="cuagent-thinking-dot" />
                              </span>
                              <span className="text-xs font-medium">
                                {statuses.length > 0 ? t('working') : t('questionReceived')}
                              </span>
                            </div>
                            <div className="rounded-lg bg-[#f8fafc] border border-[#f1f5f9] p-2.5 text-[11px] text-[#334155] space-y-1 text-left">
                              {(statuses.length > 0 ? statuses.slice(-8) : [t('connecting')]).map(
                                (s, si, arr) => (
                                  <div
                                    key={`${s}-${si}`}
                                    className={si === arr.length - 1 ? 'cuagent-status-live font-medium' : 'opacity-80'}
                                  >
                                    • {s}
                                  </div>
                                ),
                              )}
                            </div>
                          </div>
                        )}
                        {m.content ? (
                          <>
                            {statuses.length > 0 && isLastAssistant && !loading && (
                              <details className="rounded-lg border border-[#E2E8F0] bg-slate-50/80 px-2.5 py-1.5 text-[11px] text-slate-600">
                                <summary className="cursor-pointer select-none text-[#334155] font-medium">
                                  {t('showWorkLog', { count: Math.min(statuses.length, 12) })}
                                </summary>
                                <div className="mt-1.5 space-y-1 border-t border-[#E2E8F0] pt-1.5">
                                  {statuses.slice(-12).map((s, si) => (
                                    <div key={`${s}-${si}`}>• {s}</div>
                                  ))}
                                </div>
                              </details>
                            )}
                            <AgentMarkdown content={m.content} />
                          </>
                        ) : null}
                        {m.kind === 'capability' && (
                          <div className="flex flex-wrap gap-2 pt-1">
                            {EXAMPLE_PROMPTS.map((ex) => (
                              <button
                                key={ex.label}
                                type="button"
                                disabled={loading}
                                onClick={() => sendText(ex.prompt)}
                                className="rounded-full border border-[#f1f5f9] bg-[#f8fafc] px-2.5 py-1 text-[11px] text-[#334155] hover:bg-[#f1f5f9] transition"
                              >
                                {ex.label}
                              </button>
                            ))}
                          </div>
                        )}
                        {m.evidence && m.evidence.length > 0 && <EvidenceBlock items={m.evidence} />}
                      </div>
                    )}
                  </div>
                </div>
                );
              })}
              {error && <p className="text-sm text-red-600">{error}</p>}
            </div>
          ) : (
            <div className="mt-4">
              <IdleShowcase onPick={(p) => sendText(p)} />
            </div>
          )}
        </AiSignInGate>
        {!isSignedIn && <ModuleDeepLinks />}
      </div>
    </div>
  );
}
