import { TOKEN_KEY, currentLocalePrefix } from '@/lib/token';

const SERVER_API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export function apiUrl(path: string) {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  // Browser: same-origin /api/* is proxied by Next.js (see next.config.mjs rewrites).
  if (typeof window !== 'undefined') return normalized;
  return `${SERVER_API_BASE}${normalized}`;
}

function browserAuthHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function ensureOkOrRedirect(res: Response, fallback: string, requireBody = true) {
  if (res.status === 401 && typeof window !== 'undefined') {
    const next = window.location.pathname + window.location.search;
    const q = next && next !== '/login' && next !== '/register'
      ? `?next=${encodeURIComponent(next)}`
      : '';
    // 保留当前语言前缀（/zh 等），登录页不弹回英文
    const prefix = currentLocalePrefix();
    window.location.href = `${prefix}/login${q}`;
    throw new Error('Sign in required');
  }
  if (!res.ok) {
    let msg = fallback;
    try {
      const text = await res.text();
      try {
        const j = JSON.parse(text);
        if (typeof j.detail === 'string') msg = j.detail;
        else msg = text || fallback;
      } catch {
        msg = text || fallback;
      }
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  if (requireBody && !res.body) throw new Error(fallback);
}

export async function fetchHomeContent(lang = 'en') {
  const res = await fetch(apiUrl(`/api/content/home?lang=${encodeURIComponent(lang)}`), {
    next: { revalidate: 60 },
  });
  if (!res.ok) throw new Error('Failed to load home content');
  return res.json();
}

export type VisitCountryStat = {
  country: string;
  country_code: string;
  lat: number;
  lon: number;
  visits: number;
};

export type VisitStats = {
  total: number;
  today: number;
  countries: number;
  by_country: VisitCountryStat[];
  hq: { lat: number; lon: number; label: string };
};

/**
 * Fetch visit stats with `record=true` so the request itself is counted
 * (server-side increments total / today / by_country). Call once per page
 * load — typically from the Footer on the home page.
 */
export async function fetchVisitStats(): Promise<VisitStats> {
  const res = await fetch(apiUrl('/api/visits/stats?record=true'), { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to load visit stats');
  return res.json();
}

export type ExternalResource = { name: string; description: string; url: string };
export type CiteUsContent = {
  title?: string;
  intro?: string;
  citation?: string;
  bibtex?: string;
};
export type HomeContent = {
  hero: { title: string; subtitle: string; image: string; cta: { label: string; href: string }[] };
  about: { title: string; paragraphs: string[] };
  externalResources: { title: string; items: ExternalResource[] };
  citeUs?: CiteUsContent;
  footer: {
    institution: { cn: string; en: string };
    contact: { address: string; phone: string; email: string };
    affiliations?: { name: string; detail: string }[];
    copyright: string;
  };
};

export type ChatHistoryMessage = { role: string; content: string };
export type AgentStreamHandlers = {
  onStatus?: (message: string) => void;
  onToken?: (text: string) => void;
  onPapers?: (papers: any[]) => void;
  /** Full-agent tool payloads for evidence cards under the answer */
  onToolResult?: (tool: string, data: any) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

export async function agentChatStream(
  message: string,
  history: ChatHistoryMessage[],
  handlers: AgentStreamHandlers,
) {
  const res = await fetch(apiUrl('/api/agent/chat'), {
    method: 'POST',
    headers: browserAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message, history }),
  });
  await ensureOkOrRedirect(res, 'Agent request failed');
  await consumeAgentEventStream(res.body!, handlers);
}

export async function proteinChatStream(
  geneId: string,
  species: string,
  handlers: AgentStreamHandlers,
  question: string = '',
  history: ChatHistoryMessage[] = [],
) {
  const res = await fetch(apiUrl('/api/agent/protein-chat'), {
    method: 'POST',
    headers: browserAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      gene_id: geneId,
      species,
      ...(question.trim() ? { question: question.trim() } : {}),
      ...(history.length ? { history } : {}),
    }),
  });
  await ensureOkOrRedirect(res, 'Protein chat request failed');
  await consumeAgentEventStream(res.body!, handlers);
}

export async function geneChatStream(
  geneId: string,
  species: string,
  handlers: AgentStreamHandlers,
  question: string = '',
  history: ChatHistoryMessage[] = [],
) {
  const res = await fetch(apiUrl('/api/agent/gene-chat'), {
    method: 'POST',
    headers: browserAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      gene_id: geneId,
      species,
      ...(question.trim() ? { question: question.trim() } : {}),
      ...(history.length ? { history } : {}),
    }),
  });
  await ensureOkOrRedirect(res, 'Gene chat request failed');
  await consumeAgentEventStream(res.body!, handlers);
}

export async function paperChatStream(
  message: string,
  handlers: AgentStreamHandlers,
) {
  const res = await fetch(apiUrl('/api/literature/paper-chat'), {
    method: 'POST',
    headers: browserAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message }),
  });
  await ensureOkOrRedirect(res, 'Paper chat request failed');
  await consumeAgentEventStream(res.body!, handlers);
}

async function consumeAgentEventStream(body: ReadableStream<Uint8Array>, handlers: AgentStreamHandlers) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  function handleEvent(raw: string) {
    try {
      const lines = raw.split('\n');
      const event = lines.find((line) => line.startsWith('event:'))?.replace('event:', '').trim();
      // SSE allows multi-line data — join all `data:` lines before parsing.
      const dataLines = lines.filter((line) => line.startsWith('data:'));
      const data = dataLines.length
        ? JSON.parse(dataLines.map((l) => l.replace('data:', '').trim()).join('\n') || '{}')
        : {};
      if (event === 'status') handlers.onStatus?.(data.message || '');
      if (event === 'token') handlers.onToken?.(data.text || '');
      if (event === 'papers') handlers.onPapers?.(data.papers || []);
      if (event === 'tool_result') handlers.onToolResult?.(data.tool || '', data.data || {});
      if (event === 'error') handlers.onError?.(data.message || 'Agent error');
      if (event === 'done') handlers.onDone?.();
    } catch {
      // A malformed event (e.g. non-JSON data line) must not abort the rest
      // of the stream — skip it and keep consuming.
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    events.filter(Boolean).forEach(handleEvent);
  }
  if (buffer.trim()) handleEvent(buffer);
}

export async function agentChatSimple(message: string, history: ChatHistoryMessage[]) {
  const res = await fetch(apiUrl('/api/agent/chat/simple'), {
    method: 'POST',
    headers: browserAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message, history }),
  });
  await ensureOkOrRedirect(res, 'Agent request failed', false);
  return res.json() as Promise<{ content: string }>;
}

export async function searchGene(species: string, geneId: string) {
  const res = await fetch(apiUrl(`/api/genes/search?species=${encodeURIComponent(species)}&gene_id=${encodeURIComponent(geneId)}`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function searchExpression(geneId: string, species: string) {
  const res = await fetch(apiUrl(`/api/expression/gene?gene_id=${encodeURIComponent(geneId)}&species=${encodeURIComponent(species)}&top=15`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchGeneVariants(species: string, geneId: string, page = 1, tab = 'cds', consequence = 'all') {
  const res = await fetch(
    apiUrl(`/api/genes/variants?species=${encodeURIComponent(species)}&gene_id=${encodeURIComponent(geneId)}&page=${page}&tab=${tab}&consequence=${consequence}`)
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchGenomeCatalog() {
  const res = await fetch(apiUrl('/api/genomes/catalog'));
  if (!res.ok) throw new Error('Failed to load genome catalog');
  return res.json();
}

export async function fetchGenomeFiles(pathSuffix: string) {
  const res = await fetch(apiUrl(`/api/genomes/files?path_suffix=${encodeURIComponent(pathSuffix)}`));
  if (!res.ok) throw new Error('Failed to list files');
  return res.json();
}

export async function searchProtein(species: string, geneId: string) {
  const res = await fetch(apiUrl(`/api/proteins/search?species=${encodeURIComponent(species)}&gene_id=${encodeURIComponent(geneId)}`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export type ProteinSpeciesCoverage = {
  species: string[];
  ready: string[];
  with_sites: string[];
  details: {
    species: string;
    pdb_dir: string;
    site_dir: string;
    n_pdb: number;
    n_site_json: number;
    ready: boolean;
    has_sites: boolean;
  }[];
};

export async function fetchProteinSpecies(): Promise<ProteinSpeciesCoverage> {
  const res = await fetch(apiUrl('/api/proteins/species'));
  if (!res.ok) throw new Error('Failed to load protein species');
  return res.json();
}

export async function fetchLiteraturePapers(q: string, page: number, subject = '') {
  const subjParam = subject ? `&subject=${encodeURIComponent(subject)}` : '';
  // Home is an RSC: without no-store, Next Data Cache keeps an old papers page
  // while the client-side Literatures tab always shows fresh SQLite results.
  const res = await fetch(
    apiUrl(`/api/literature/papers?q=${encodeURIComponent(q)}&page=${page}${subjParam}`),
    { cache: 'no-store' },
  );
  if (!res.ok) throw new Error('Failed to load papers');
  return res.json();
}

export async function searchLiterature(q: string, topK = 10) {
  const res = await fetch(apiUrl(`/api/literature/search?q=${encodeURIComponent(q)}&top_k=${topK}`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ============================
// Expression module
// ============================

export type ExpressionOverviewSpecies = {
  species_dir: string;
  label: string;
  common: string;
  genes: number;
  samples: number;
  projects: number;
  tissues: number;
  rows: number;
  reliability: string;
  data_available: boolean;
};

export type ExpressionOverview = {
  status: string;
  total: { species: number; genes: number; samples: number; projects: number; rows: number };
  species: ExpressionOverviewSpecies[];
};

export type TissueProfileEntry = {
  tissue: string;
  mean: number;
  max: number;
  count: number;
};

export type TopSampleEntry = {
  sample_id: string;
  fpkm: number;
  tissue: string;
  condition: string;
  description: string;
  project: string;
};

export type ConditionDistEntry = { condition: string; count: number };

export type GeneExpressionResult = {
  status: string;
  gene_id: string;
  species_dir: string;
  species_label: string;
  species_common: string;
  n_samples: number;
  n_projects: number;
  n_tissues: number;
  mean_fpkm: number;
  max_fpkm: number;
  tau_specificity: number | null;
  top_tissue: string;
  top_tissue_fpkm: number | null;
  reliability: string;
  tissue_profile: TissueProfileEntry[];
  top_samples: TopSampleEntry[];
  condition_distribution: ConditionDistEntry[];
  message?: string;
  suggestions?: string[];
};

export type CoexpressedGene = {
  gene_id: string;
  pearson_r: number;
  abs_r: number;
  description: string;
};

export type CoexpressionResult = {
  status: string;
  gene_id: string;
  species_dir: string;
  species_label: string;
  species_common: string;
  n_samples: number;
  reliability: string;
  reliability_desc?: string;
  warning: string | null;
  min_corr: number;
  top_k: number;
  count: number;
  coexpressed: CoexpressedGene[];
  message?: string;
  suggestions?: string[];
};

export type TissueMatrixResult = {
  status: string;
  gene_id: string;
  species_dir: string;
  species_label: string;
  tissues: { tissue: string; mean_fpkm: number }[];
};

export async function fetchExpressionOverview() {
  const res = await fetch(apiUrl('/api/expression/overview'), { next: { revalidate: 300 } });
  if (!res.ok) throw new Error('Failed to load expression overview');
  return res.json() as Promise<ExpressionOverview>;
}

export async function fetchGeneExpression(geneId: string, species = '', tissue = '', top = 15) {
  const params = new URLSearchParams({ gene_id: geneId, top: String(top) });
  if (species) params.set('species', species);
  if (tissue) params.set('tissue', tissue);
  const res = await fetch(apiUrl(`/api/expression/gene?${params.toString()}`));
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.message || err?.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<GeneExpressionResult>;
}

export async function fetchTissueMatrix(geneId: string, species = '') {
  const params = new URLSearchParams({ gene_id: geneId });
  if (species) params.set('species', species);
  const res = await fetch(apiUrl(`/api/expression/tissue-matrix?${params.toString()}`));
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<TissueMatrixResult>;
}

export async function fetchCoexpression(geneId: string, species = '', topK = 20, minCorr = 0.5) {
  const params = new URLSearchParams({
    gene_id: geneId,
    top_k: String(topK),
    min_corr: String(minCorr),
  });
  if (species) params.set('species', species);
  const res = await fetch(apiUrl(`/api/expression/coexpression?${params.toString()}`));
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.message || err?.detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<CoexpressionResult>;
}

export async function expressionChatStream(
  geneId: string,
  species: string,
  handlers: AgentStreamHandlers,
  question: string = '',
  history: ChatHistoryMessage[] = [],
) {
  const res = await fetch(apiUrl('/api/expression/gene-chat'), {
    method: 'POST',
    headers: browserAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      gene_id: geneId,
      species,
      ...(question.trim() ? { question: question.trim() } : {}),
      ...(history.length ? { history } : {}),
    }),
  });
  await ensureOkOrRedirect(res, 'Expression chat request failed');
  await consumeAgentEventStream(res.body!, handlers);
}

export async function submitFeedback(email: string, description: string) {
  const res = await fetch(apiUrl('/api/feedback'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, description }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const detail = err?.detail;
    let msg = 'Feedback submission failed';
    if (typeof detail === 'string') msg = detail;
    else if (Array.isArray(detail)) {
      msg = detail.map((d: { msg?: string }) => d?.msg).filter(Boolean).join('; ') || msg;
    }
    throw new Error(msg);
  }
  return res.json() as Promise<{ ok: boolean; id: number; message: string }>;
}
