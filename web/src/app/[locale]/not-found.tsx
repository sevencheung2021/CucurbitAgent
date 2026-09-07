'use client';

import { useTranslations } from 'next-intl';

/** Light 404 — prefer hard navigation so we never soft-nav into a bad URL. */
export default function NotFound() {
  const t = useTranslations('notFound');
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 text-center bg-white">
      <p className="text-6xl font-extrabold text-[#475569] tabular-nums">404</p>
      <h1 className="mt-3 text-xl font-semibold text-slate-800">{t('title')}</h1>
      <p className="mt-2 max-w-md text-sm text-slate-500">
        If the address bar looks wrong (IP repeated in the path), open{' '}
        <code className="text-xs">http://&lt;host&gt;:3000/</code> with the{' '}
        <code className="text-xs">http://</code> prefix, then use the top menu.
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <a
          href="/"
          className="rounded-lg bg-[#475569] px-4 py-2 text-sm font-semibold text-white hover:bg-[#334155]"
        >
          Go home
        </a>
        <a
          href="/genes"
          className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          {t('openGenes')}
        </a>
      </div>
    </div>
  );
}
