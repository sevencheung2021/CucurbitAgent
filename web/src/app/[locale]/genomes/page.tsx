'use client';

import { useEffect, useState } from 'react';
import { fetchGenomeCatalog, fetchGenomeFiles, apiUrl } from '@/lib/api';
import { useTranslations } from 'next-intl';

const citations: Record<string, string> = {
  Cucumber: 'Chinese Long v3 and Cucurbit Genome Database resources.',
  Watermelon: 'Watermelon 97103 reference genome and related cucurbit assemblies.',
  Melon: 'Melon DHL92 and related reference genome assemblies.',
};

function formatSize(n: number) {
  if (!n) return '';
  if (n > 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n > 1024 ** 2) return `${(n / 1024 ** 2).toFixed(2)} MB`;
  return `${(n / 1024).toFixed(1)} KB`;
}

export default function GenomesPage() {
  const t = useTranslations('genomes');
  const [catalog, setCatalog] = useState<Record<string, Record<string, Record<string, string>>>>({});
  const [catalogError, setCatalogError] = useState('');
  const [files, setFiles] = useState<Record<string, { name: string; size_bytes: number }[]>>({});
  const [fileErrors, setFileErrors] = useState<Record<string, string>>({});
  const [loadingSuffix, setLoadingSuffix] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchGenomeCatalog()
      .then((d) => { if (!cancelled) { setCatalog(d.catalog || {}); setCatalogError(''); } })
      .catch((e) => { if (!cancelled) setCatalogError(e instanceof Error ? e.message : 'Failed to load genome catalog'); });
    return () => { cancelled = true; };
  }, []);

  async function loadFiles(suffix: string) {
    if (files[suffix] || loadingSuffix) return;
    setLoadingSuffix(suffix);
    setFileErrors((prev) => ({ ...prev, [suffix]: '' }));
    try {
      const d = await fetchGenomeFiles(suffix);
      setFiles((prev) => ({ ...prev, [suffix]: d.files || [] }));
    } catch (e) {
      setFileErrors((prev) => ({ ...prev, [suffix]: e instanceof Error ? e.message : 'Failed to list files' }));
    } finally {
      setLoadingSuffix('');
    }
  }

  return (
    <div className="max-w-content mx-auto px-4 py-8">
      <h1 className="mb-2 text-4xl font-extrabold text-[#0f172a]">💾 {t('title')}</h1>
      <div className="mb-8 rounded-lg border-l-4 border-[#475569] bg-[#ECFDF5] p-5 text-[#115E59]">
        {t('intro')}
      </div>
      <div className="space-y-5">
        {catalogError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {catalogError}
          </div>
        )}
        {Object.entries(catalog).map(([species, varieties]) => (
          <details key={species} className="overflow-hidden rounded-xl border border-[#DADDE1] bg-white shadow-sm" open={species === 'Cucumber'}>
            <summary className="cursor-pointer bg-gradient-to-r from-[#f8fafc] to-white px-5 py-4 text-xl font-extrabold text-[#334155]">
              {species}
            </summary>
            <div className="p-5">
              <div className="mb-4 rounded-lg bg-[#F8FAFC] p-4 text-sm text-[#475569]">
                📌 {t('citation')} {citations[species] || t('citationFallback')}
              </div>
              {Object.entries(varieties).map(([variety, versions]) => (
                <details key={variety} className="mb-4 rounded-lg border border-[#E2E8F0] bg-[#FDFEFE] p-4">
                  <summary className="cursor-pointer font-bold text-[#34495e]">{variety}</summary>
                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    {Object.entries(versions).map(([version, suffix]) => (
                      <div key={`${version}-${suffix}`} className="rounded-lg border border-[#E2E8F0] bg-white p-4">
                        <button onClick={() => loadFiles(suffix)} className="mb-2 text-left text-sm font-bold text-[#2980b9] underline">
                          {t('version')} {version} · {suffix}
                        </button>
                        {loadingSuffix === suffix && <p className="text-sm text-[#64748B]">{t('loadingFiles')}</p>}
                        {fileErrors[suffix] && (
                          <p className="mt-2 text-sm text-red-600">{fileErrors[suffix]}</p>
                        )}
                        {files[suffix] && <div className="mt-3 space-y-2">
                          {files[suffix].length ? files[suffix].map((f) => (
                            <a key={f.name} href={apiUrl(`/api/genomes/download?path_suffix=${encodeURIComponent(suffix)}&filename=${encodeURIComponent(f.name)}`)} className="flex items-center justify-between rounded-md border border-[#E2E8F0] px-3 py-2 text-sm hover:bg-[#f8fafc]">
                              <span>⬇️ {f.name}</span><span className="text-[#64748B]">{formatSize(f.size_bytes)}</span>
                            </a>
                          )) : <p className="text-sm text-[#64748B]">{t('noFiles')}</p>}
                        </div>}
                      </div>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
