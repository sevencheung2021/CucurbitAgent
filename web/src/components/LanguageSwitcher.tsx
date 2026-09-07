'use client';

import { useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from '@/i18n/routing';
import { localeFlags, localeNames, locales, type Locale } from '@/i18n/config';

/** 语言菜单（参考 MendelSel LanguageSwitcher，适配 CucurbitAgent 导航样式）。 */
export default function LanguageSwitcher() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const locale = useLocale() as Locale;
  const t = useTranslations('nav');
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  function switchLocale(next: Locale) {
    // 保留当前 query（如 ?gene=CsaV3_1G000010），切语言不丢深链接参数。
    // 直接读 window.location.search（事件处理器内，客户端专用），
    // 避免 useSearchParams 触发静态页的 Suspense 边界要求。
    const qs = typeof window !== 'undefined' ? window.location.search : '';
    router.replace(
      { pathname, search: qs } as any,
      { locale: next },
    );
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 pb-3 text-sm font-semibold text-slate-500 hover:text-[#0D9488] transition-colors"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={t('language')}
        title={t('language')}
      >
        <span className="text-base leading-none" aria-hidden>
          🌐
        </span>
        <span className="hidden lg:inline">{localeNames[locale]}</span>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={t('language')}
          className="absolute right-0 z-50 mt-1 max-h-[70vh] w-[220px] overflow-y-auto rounded-xl border border-slate-200 bg-white py-1.5 shadow-[0_8px_28px_rgba(15,23,42,0.12)]"
        >
          {locales.map((l) => (
            <button
              key={l}
              type="button"
              role="option"
              aria-selected={l === locale}
              onClick={() => switchLocale(l)}
              className={`flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm transition-colors ${
                l === locale
                  ? 'bg-[#F0FDFA] font-semibold text-[#0F766E]'
                  : 'text-slate-700 hover:bg-slate-50'
              }`}
            >
              <span className="text-base" aria-hidden>
                {localeFlags[l]}
              </span>
              <span className="truncate">{localeNames[l]}</span>
              {l === locale && (
                <span className="ml-auto text-[#0D9488]" aria-hidden>
                  ✓
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
