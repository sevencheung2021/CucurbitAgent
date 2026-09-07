'use client';

import { BookOpenIcon, LinkIcon, WarningIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

/**
 * Compact literature results panel for the Agent chat.
 *
 * Evidence card under the LLM summary. Shows the top retrieved papers with
 * title / snippet / DOI link, no heavy visualization.
 *
 * Props shape from /api/literature/search (or the paper-chat SSE `papers`
 * event, which carries the same paper objects).
 */
export default function LiteratureDataCard({ data }: { data: any }) {
  const t = useTranslations('literatures');
  if (!data || data.status !== 'success') {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 flex items-start gap-2">
        <WarningIcon className="size-4 shrink-0 mt-[1px]" />
        <span>{data?.message || 'No matching papers found.'}</span>
      </div>
    );
  }

  // Cap at 5 displayed papers. The header count uses this same number so they
  // can never disagree (data.count counts raw retrieval hits including dup
  // chunks from the same paper, which is misleading).
  const papers = (data.papers || []).slice(0, 5);
  const displayCount = papers.length;

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 overflow-hidden">
      <div className="px-3 py-1.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700 inline-flex items-center gap-1.5">
          <BookOpenIcon className="size-3.5 text-[#475569]" />
          Literature <span className="text-slate-400 font-normal">· {data.query}</span>
        </span>
        <span className="text-[10px] text-slate-400">{displayCount} papers</span>
      </div>

      <div className="p-3 space-y-2.5">
        {/* Papers — numbered list with snippet. Uniform left border (teal),
            no per-source color tag since the user doesn't want the labels. */}
        {displayCount === 0 ? (
          <div className="text-xs text-slate-500 italic">{t('noPapers')}</div>
        ) : (
          papers.map((p: any, i: number) => {
            const snippet = (p.match_snippet || p.abstract || '')
              .replace(/\[来源:[^\]]*\]\n?/g, '')
              .slice(0, 180);
            const title = p.title && p.title !== 'RESEARCH ARTICLE' && p.title.length > 3
              ? p.title : (snippet.slice(0, 60) + (snippet.length > 60 ? '…' : ''));
            // Only accept real DOI strings (CrossRef/DataCite form: 10.<registrant>/<suffix>).
            // Empty / placeholder / URL-shaped junk are never rendered as links.
            const rawDoi = (typeof p.doi === 'string' ? p.doi.trim() : '')
              .replace(/^https?:\/\/(dx\.)?doi\.org\//i, '');
            const doi = /^10\.\d{4,9}\/\S+$/i.test(rawDoi) ? rawDoi : '';
            const doiUrl = doi ? `https://doi.org/${doi}` : '';
            return (
              <div key={i} className="border-l-2 border-[#475569] pl-2.5 py-0.5">
                <div className="text-xs font-medium text-slate-800">
                  {i + 1}. {title || `Paper ${i + 1}`}
                </div>
                {snippet && (
                  <div className="text-[11px] text-slate-500 leading-relaxed mt-0.5 line-clamp-2">
                    {snippet}
                  </div>
                )}
                <div className="text-[10px] text-slate-400 mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  {p.year && p.year !== '0' && <span>{p.year}</span>}
                  {p.species && <span className="italic">{p.species}</span>}
                  {doi && (
                    <a
                      href={doiUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[#334155] hover:text-[#0c5a52] hover:underline"
                      title={`Open ${doi} in a new tab`}
                    >
                      <LinkIcon className="size-3" /> {doi}
                    </a>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
