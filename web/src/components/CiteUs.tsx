'use client';

import { useState } from 'react';
import { CheckIcon } from '@/components/ui/icons';

const DEFAULT_INTRO =
  'If you find this platform helpful for your research, please cite:';
const DEFAULT_CITATION =
  'CucurbitAgent: An AI-driven interactive assistant for multi-omics and structural analysis in Cucurbitaceae (manuscript in preparation).';
const DEFAULT_BIBTEX = `@unpublished{CucurbitAgent2026,
  title = {CucurbitAgent: An AI-driven interactive assistant for multi-omics and structural analysis in Cucurbitaceae},
  author = {{Beijing Vegetable Research Center}},
  note = {Manuscript in preparation},
  year = {2026}
}`;

export type CiteUsContent = {
  title?: string;
  intro?: string;
  citation?: string;
  bibtex?: string;
};

/** Plain typographic cite block — avoids competing with the teal footer card below. */
export default function CiteUs({ content }: { content?: CiteUsContent | null }) {
  const title = content?.title || 'Cite Us';
  const intro = content?.intro || DEFAULT_INTRO;
  const citation = content?.citation || DEFAULT_CITATION;
  const bibtex = content?.bibtex || DEFAULT_BIBTEX;
  const [copied, setCopied] = useState(false);

  async function copyBibtex() {
    try {
      await navigator.clipboard.writeText(bibtex);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="max-w-content mx-auto px-4 mb-6">
      <div className="border-t border-[#E2E8F0] pt-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 mb-2">
          <h3 className="text-teal-brand font-bold text-lg">{title}</h3>
          <button
            type="button"
            onClick={copyBibtex}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#475569] hover:underline"
          >
            {copied ? (
              <>
                <CheckIcon className="size-3.5" /> Copied
              </>
            ) : (
              'Copy BibTeX'
            )}
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-1.5">{intro}</p>
        <p className="text-sm sm:text-[15px] text-slate-700 leading-relaxed italic border-l-2 border-slate-200 pl-3">
          {citation}
        </p>
      </div>
    </section>
  );
}
