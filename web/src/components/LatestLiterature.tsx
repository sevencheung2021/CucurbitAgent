import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/routing';
import { BookOpenIcon } from '@/components/ui/icons';

export type LatestPaper = {
  title?: string;
  journal?: string;
  pub_date?: string;
  year?: string;
  abstract?: string;
  doi?: string;
  pmid?: string;
};

const MONTHS: Record<string, string> = {
  jan: '01', january: '01',
  feb: '02', february: '02',
  mar: '03', march: '03',
  apr: '04', april: '04',
  may: '05',
  jun: '06', june: '06',
  jul: '07', july: '07',
  aug: '08', august: '08',
  sep: '09', sept: '09', september: '09',
  oct: '10', october: '10',
  nov: '11', november: '11',
  dec: '12', december: '12',
};

/** Prefer YYYY-MM-DD from the first paper's pub_date (e.g. "2026 Jul 16"). */
function headerDateFromPaper(paper?: LatestPaper): string | null {
  if (!paper) return null;
  const raw = (paper.pub_date || paper.year || '').trim();
  if (!raw) return null;

  // Already ISO-ish: 2026-07-16 / 2026-07 / 2026
  const iso = raw.match(/^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$/);
  if (iso) {
    const y = iso[1];
    const m = iso[2] ? iso[2].padStart(2, '0') : null;
    const d = iso[3] ? iso[3].padStart(2, '0') : null;
    if (m && d) return `${y}-${m}-${d}`;
    if (m) return `${y}-${m}`;
    return y;
  }

  // "2026 Jul 16" / "2026 Jul" / "Jul 16, 2026"
  const m1 = raw.match(/^(\d{4})\s+([A-Za-z]+)\s+(\d{1,2})\b/);
  if (m1) {
    const mon = MONTHS[m1[2].toLowerCase()];
    if (mon) return `${m1[1]}-${mon}-${m1[3].padStart(2, '0')}`;
  }
  const m2 = raw.match(/^(\d{4})\s+([A-Za-z]+)\b/);
  if (m2) {
    const mon = MONTHS[m2[2].toLowerCase()];
    if (mon) return `${m2[1]}-${mon}`;
  }
  const m3 = raw.match(/^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b/);
  if (m3) {
    const mon = MONTHS[m3[1].toLowerCase()];
    if (mon) return `${m3[3]}-${mon}-${m3[2].padStart(2, '0')}`;
  }

  return raw;
}

function formatMeta(paper: LatestPaper) {
  const journal = (paper.journal || '').trim() || 'Journal N/A';
  const date = (paper.pub_date || paper.year || '').trim() || 'N/A';
  return `${journal} | ${date}`;
}

function paperHref(paper: LatestPaper) {
  const doi = (paper.doi || '').trim();
  if (doi) return `https://doi.org/${doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, '')}`;
  const pmid = (paper.pmid || '').trim();
  if (pmid) return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
  return '/literatures';
}

export default function LatestLiterature({
  papers,
}: {
  papers: LatestPaper[];
}) {
  const t = useTranslations('home');
  const items = (papers || []).slice(0, 3);
  const asOf = headerDateFromPaper(items[0]);

  return (
    <section className="max-w-content mx-auto px-4 mb-10">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 mb-4">
        <h3 className="text-teal-brand font-bold text-lg flex items-center gap-2">
          <BookOpenIcon className="size-5 text-[#475569]" />
          {t('latestTitle')}
        </h3>
        {asOf && <span className="text-sm text-slate-400">({asOf})</span>}
      </div>

      {items.length === 0 ? (
        <div className="rounded-xl border border-[#E2E8F0] bg-white px-4 py-6 text-center text-sm text-slate-500">
          {t('noPapers')}
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((paper, i) => {
            const title = (paper.title || '').trim() || `Paper ${i + 1}`;
            const abstract = (paper.abstract || '').replace(/\s+/g, ' ').trim();
            return (
              <a
                key={`${paper.doi || paper.pmid || title}-${i}`}
                href={paperHref(paper)}
                target={paper.doi || paper.pmid ? '_blank' : undefined}
                rel={paper.doi || paper.pmid ? 'noopener noreferrer' : undefined}
                className="block rounded-xl border border-[#E2E8F0] border-l-4 border-l-[#475569] bg-white px-4 py-3.5 shadow-sm hover:bg-[#FAFEFC] hover:border-[#f1f5f9] transition no-underline"
              >
                <div className="font-semibold text-[#334155] text-sm leading-snug">
                  {title}
                </div>
                <div className="mt-1 text-[11px] text-slate-500">
                  {formatMeta(paper)}
                </div>
                {abstract && (
                  <p className="mt-1.5 text-xs text-slate-600 leading-relaxed line-clamp-2">
                    {abstract}
                  </p>
                )}
              </a>
            );
          })}
        </div>
      )}

      <div className="mt-5 flex justify-center">
        <Link
          href="/literatures"
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#475569] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#334155] transition-colors no-underline"
        >
          {t('viewAll')} →
        </Link>
      </div>
    </section>
  );
}
