'use client';

import Image from 'next/image';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/routing';
import { useEffect, useState } from 'react';
import { fetchVisitStats, type VisitStats } from '@/lib/api';
import { GlobeIcon, TrendingUpIcon, MapPinIcon, PhoneIcon, MailIcon } from '@/components/ui/icons';

const TOP_N = 6;

export type FooterAffiliation = { name: string; detail: string };

function affiliationLine(item: FooterAffiliation) {
  const name = (item.name || '').trim();
  const detail = (item.detail || '').trim();
  if (!detail) return name;
  if (!name) return detail;
  return `${name}, ${detail}`;
}

export default function Footer({
  institution,
  contact,
  affiliations = [],
  copyright,
}: {
  institution: { cn: string; en: string };
  contact: { address: string; phone: string; email: string };
  affiliations?: FooterAffiliation[];
  copyright: string;
}) {
  const t = useTranslations('footer');
  const [stats, setStats] = useState<VisitStats | null>(null);

  useEffect(() => {
    fetchVisitStats().then(setStats).catch(() => setStats(null));
  }, []);

  // Split countries into China vs others (lat/lon are approximations, so
  // group by country name; "Unknown" / missing country rolls into "Other").
  const topCountries = (stats?.by_country || []).slice(0, TOP_N);

  return (
    <footer className="max-w-content mx-auto mt-6 px-5 pt-3 pb-2.5 text-black overflow-hidden bg-gradient-to-b from-[#f8fafc] to-[#ECFDF5] border border-[#f1f5f9] border-t-[3px] border-t-[#475569] rounded-t-[12px] shadow-[0_2px_10px_rgba(51,65,85,0.06)]">
      {/* Top: Global Reach | Institution (+ logo) | Contact */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 sm:gap-6 w-full">
        <section className="shrink-0 w-full sm:w-auto sm:max-w-[180px]">
          <div className="flex items-center gap-1.5 text-[13px] font-bold mb-1 leading-none text-black">
            <GlobeIcon className="size-3.5 text-[#475569]" />
            {t('globalReach')}
          </div>
          <div className="text-[12px] text-black leading-snug">
            {t('totalVisits')}{' '}
            <strong className="tabular-nums">
              {stats ? stats.total.toLocaleString() : '—'}
            </strong>
          </div>
          <div className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-600 leading-snug">
            <TrendingUpIcon className="size-3 text-[#475569]" />
            {t('today')}{' '}
            <strong className="text-slate-800 tabular-nums">
              {stats ? stats.today.toLocaleString() : '—'}
            </strong>
          </div>
          <ul className="mt-1 space-y-0.5 text-[11px] leading-snug text-slate-700">
            {stats === null && <li className="text-slate-400">{t('loading')}</li>}
            {stats && topCountries.length === 0 && (
              <li className="text-slate-400">{t('noData')}</li>
            )}
            {topCountries.map((row) => {
              const label =
                !row.country || /^unknown$/i.test(row.country.trim())
                  ? t('other')
                  : row.country;
              return (
                <li key={row.country} className="truncate">
                  <span className="font-medium text-slate-800">{label}</span>
                  <span className="text-slate-400"> · </span>
                  <span className="tabular-nums text-[#334155]">
                    {row.visits.toLocaleString()}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="shrink-0 w-full sm:w-auto sm:max-w-[320px] min-w-0">
          <div className="text-[13px] font-bold mb-1.5 leading-none text-black">
            {t('institution')}
          </div>
          <Image
            src="/assets/bvrc-logo.png"
            alt="Beijing Vegetable Research Center of BAAFS"
            width={3688}
            height={614}
            className="h-8 w-auto max-w-[200px] object-contain mb-1.5"
            priority
          />
          <div className="text-[12px] text-black leading-snug">{institution.cn}</div>
          <div className="text-[11px] mt-0.5 text-black/75 leading-snug">
            {institution.en}
          </div>
        </section>

        <section className="shrink-0 w-full sm:w-auto sm:max-w-[280px]">
          <div className="text-[13px] font-bold mb-1 leading-none text-black">
            {t('contact')}
          </div>
          <div className="space-y-0.5 text-[11px] leading-snug text-black">
            <div className="flex items-start gap-1.5">
              <MapPinIcon className="size-3.5 shrink-0 mt-[1px] text-[#475569]" />
              <span>{contact.address}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <PhoneIcon className="size-3.5 shrink-0 text-[#475569]" />
              <a href={`tel:${(contact.phone || '').replace(/-/g, '')}`}>
                {contact.phone || '—'}
              </a>
            </div>
            <div className="flex items-center gap-1.5">
              <MailIcon className="size-3.5 shrink-0 text-[#475569]" />
              <a href={`mailto:${contact.email || ''}`}>{contact.email || '—'}</a>
            </div>
          </div>
        </section>
      </div>

      {/* Affiliations: one unit per row */}
      {affiliations.length > 0 && (
        <section
          aria-label="Research affiliations"
          className="mt-2.5 pt-2 border-t border-[#e2e8f0]/60"
        >
          <div className="text-[12px] font-bold mb-1 leading-none text-black">
            {t('affiliations')}
          </div>
          <ol className="m-0 p-0 list-none grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-0.5">
            {affiliations.map((item, i) => (
              <li
                key={item.name}
                className="flex gap-1.5 text-[11px] leading-[1.35] text-slate-700 min-w-0"
              >
                <span className="shrink-0 tabular-nums font-semibold text-[#334155] w-3.5 text-right">
                  {i + 1}.
                </span>
                <span className="min-w-0">{affiliationLine(item)}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="text-center text-[10px] mt-2 text-black/70 space-x-3">
        <span>{copyright}</span>
        <span className="text-black/30">·</span>
        <Link href="/privacy" className="text-[#334155] hover:underline">
          {t('privacy')}
        </Link>
        <span className="text-black/30">·</span>
        <Link href="/terms" className="text-[#334155] hover:underline">
          {t('terms')}
        </Link>
      </div>
    </footer>
  );
}
