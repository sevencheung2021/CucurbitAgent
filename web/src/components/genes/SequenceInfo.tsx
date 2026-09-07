'use client';
import type { ReactNode } from 'react';
import { FileTextIcon, DnaIcon, MicroscopeIcon, DownloadIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

function fasta(name: string, seq?: string) { return `>${name}\n${seq || ''}`; }

export default function SequenceInfo({ geneId, cds, protein }: { geneId: string; cds?: any; protein?: any }) {
  const t = useTranslations('genes');
  if (!cds?.sequence && !protein?.sequence) return null;
  return (
    <section className="mt-10">
      <h2 className="mb-4 text-3xl font-extrabold text-[#1a252f] inline-flex items-center gap-3">
        <FileTextIcon className="size-7 text-[#0D9488]" /> Sequence Info
      </h2>
      <p className="mb-6 text-sm text-[#64748B]">Expand a panel to preview the full sequence or download FASTA.</p>
      <div className="grid gap-4 md:grid-cols-2">
        <SeqPanel
          title={
            <span className="inline-flex items-center gap-1.5">
              <DnaIcon className="size-4 text-[#0D9488]" /> CDS · {cds?.length_bp?.toLocaleString?.() || 0} bp
            </span>
          }
          name={`${geneId}_cds`}
          seq={cds?.sequence}
          file={`${geneId}_cds.fa`}
        />
        <SeqPanel
          title={
            <span className="inline-flex items-center gap-1.5">
              <MicroscopeIcon className="size-4 text-[#0D9488]" /> Protein · {protein?.length_aa?.toLocaleString?.() || 0} aa
            </span>
          }
          name={`${geneId}_pep`}
          seq={protein?.sequence}
          file={`${geneId}_pep.fa`}
        />
      </div>
    </section>
  );
}

function SeqPanel({ title, name, seq, file }: { title: ReactNode; name: string; seq?: string; file: string }) {
  const t = useTranslations('genes');
  const href = seq ? `data:text/plain;charset=utf-8,${encodeURIComponent(fasta(name, seq))}` : '#';
  return (
    <details className="rounded-lg border border-[#DADDE1] bg-white p-4">
      <summary className="cursor-pointer text-sm">{title}</summary>
      {seq ? <>
        <pre className="mt-4 max-h-64 overflow-auto rounded bg-[#F8FAFC] p-3 text-xs whitespace-pre-wrap">{fasta(name, seq).replace(/(.{80})/g, '$1\n')}</pre>
        <a className="mt-3 inline-flex items-center gap-1.5 rounded border border-[#0D9488] px-3 py-2 text-sm text-[#0D9488] hover:bg-[#F0FDFA]" href={href} download={file}>
          <DownloadIcon className="size-3.5" /> {t('downloadFasta')}
        </a>
      </> : <p className="mt-3 text-sm text-[#64748B]">{t('seqUnavailable')}</p>}
    </details>
  );
}
