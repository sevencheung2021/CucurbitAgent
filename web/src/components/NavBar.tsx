'use client';

import { useEffect, useState, type ComponentType, type SVGProps } from 'react';
import { useTranslations } from 'next-intl';
import { Link, usePathname } from '@/i18n/routing';
import { useAuth } from '@/lib/auth';
import NavUserMenu from '@/components/NavUserMenu';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import {
  HomeIcon,
  BotIcon,
  DnaIcon,
  BarChart3Icon,
  MicroscopeIcon,
  BookOpenIcon,
  DownloadIcon,
  MessageSquareIcon,
  MenuIcon,
  CloseIcon,
} from '@/components/ui/icons';

type NavItem = {
  href: string;
  labelKey: 'home' | 'agent' | 'genes' | 'expression' | 'proteins' | 'literatures' | 'genomes' | 'feedback';
  Icon: ComponentType<SVGProps<SVGSVGElement> & { title?: string }>;
};

const NAV: NavItem[] = [
  { href: '/', labelKey: 'home', Icon: HomeIcon },
  { href: '/agent', labelKey: 'agent', Icon: BotIcon },
  { href: '/genes', labelKey: 'genes', Icon: DnaIcon },
  { href: '/expression', labelKey: 'expression', Icon: BarChart3Icon },
  { href: '/proteins', labelKey: 'proteins', Icon: MicroscopeIcon },
  { href: '/literatures', labelKey: 'literatures', Icon: BookOpenIcon },
  { href: '/genomes', labelKey: 'genomes', Icon: DownloadIcon },
  { href: '/feedback', labelKey: 'feedback', Icon: MessageSquareIcon },
];

export default function NavBar() {
  const pathname = usePathname() || '/';
  const isHome = pathname === '/';
  const t = useTranslations('nav');
  const { user, isSignedIn, ready } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Lock body scroll while the mobile drawer is open.
  useEffect(() => {
    if (!drawerOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [drawerOpen]);

  // Close drawer on route change.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  return (
    <nav className="max-w-content mx-auto px-4 pt-3 border-b-2 border-[#E2E8F0]">
      {/* Desktop: horizontal nav row */}
      <ul className="hidden md:flex flex-wrap items-end justify-between gap-x-2 gap-y-1">
        {NAV.map((item) => {
          const active = isActive(item.href);
          const { Icon } = item;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={`group flex items-center gap-1.5 pb-3 text-base font-extrabold whitespace-nowrap border-b-4 transition-colors ${
                  active
                    ? 'text-[#334155] border-[#475569]'
                    : 'text-slate-500 border-transparent hover:text-[#475569] hover:border-[#e2e8f0]'
                }`}
              >
                <Icon
                  className={`size-4 transition-colors ${
                    active
                      ? 'text-[#475569]'
                      : 'text-slate-400 group-hover:text-[#475569]'
                  }`}
                />
                {t(item.labelKey)}
              </Link>
            </li>
          );
        })}

        <LanguageSwitcher />

        {/* Logged-in: avatar menu on every page. Logged-out Sign in/Register: home only. */}
        {ready && isSignedIn && user ? (
          <li className="shrink-0 list-none">
            <NavUserMenu user={user} />
          </li>
        ) : isHome ? (
          <li className="pb-3 shrink-0">
            {!ready ? (
              <div className="h-8 w-28" aria-hidden />
            ) : (
              <div className="flex flex-col items-end gap-0.5">
                <div className="flex items-center gap-2">
                  <Link
                    href="/login"
                    className="text-sm font-semibold text-[#475569] hover:underline"
                  >
                    {t('signIn')}
                  </Link>
                  <Link
                    href="/register"
                    className="rounded-md bg-[#475569] px-2.5 py-1 text-xs font-semibold text-white hover:bg-[#334155]"
                  >
                    {t('register')}
                  </Link>
                </div>
                <p className="text-[10px] leading-none text-slate-500">
                  {t('signInHint')}
                </p>
              </div>
            )}
          </li>
        ) : null}
      </ul>

      {/* Mobile: logo row + hamburger */}
      <div className="md:hidden flex items-center justify-between pb-2">
        <Link
          href="/"
          className="flex items-center gap-2 text-[#334155] font-extrabold text-lg"
          aria-label="CucurbitAgent home"
        >
          <BotIcon className="size-6 text-[#475569]" />
          CucurbitAgent
        </Link>

        <div className="flex items-center gap-2">
          {ready && isSignedIn && user ? (
            <NavUserMenu user={user} />
          ) : isHome && ready ? (
            <Link
              href="/login"
              className="text-sm font-semibold text-[#475569] hover:underline"
            >
              {t('signIn')}
            </Link>
          ) : null}

          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label={t('menu')}
            aria-expanded={drawerOpen}
            aria-controls="mobile-nav-drawer"
            className="inline-flex items-center justify-center size-9 rounded-lg border border-[#E2E8F0] bg-white text-slate-600 hover:bg-slate-50 hover:text-[#475569] transition-colors"
          >
            <MenuIcon className="size-5" />
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div
          className="md:hidden fixed inset-0 z-50"
          role="dialog"
          aria-modal="true"
          aria-label={t('menu')}
        >
          {/* Backdrop */}
          <button
            type="button"
            aria-label={t('menu')}
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px]"
            tabIndex={-1}
          />

          {/* Panel — slides in from the right */}
          <div
            id="mobile-nav-drawer"
            className="absolute right-0 top-0 h-full w-[280px] max-w-[80vw] bg-white shadow-xl flex flex-col"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#E2E8F0]">
              <span className="flex items-center gap-2 font-extrabold text-[#334155]">
                <BotIcon className="size-5 text-[#475569]" />
                {t('menu')}
              </span>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label={t('menu')}
                className="inline-flex items-center justify-center size-9 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              >
                <CloseIcon className="size-5" />
              </button>
            </div>

            <ul className="flex-1 overflow-y-auto py-2">
              {NAV.map((item) => {
                const active = isActive(item.href);
                const { Icon } = item;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? 'page' : undefined}
                      className={`flex items-center gap-3 px-4 py-3 text-base font-semibold border-l-4 transition-colors ${
                        active
                          ? 'text-[#334155] bg-[#f8fafc] border-[#475569]'
                          : 'text-slate-700 border-transparent hover:bg-slate-50 hover:text-[#475569]'
                      }`}
                    >
                      <Icon
                        className={`size-5 ${
                          active ? 'text-[#475569]' : 'text-slate-400'
                        }`}
                      />
                      {t(item.labelKey)}
                    </Link>
                  </li>
                );
              })}
            </ul>

            {/* Language + auth actions inside drawer */}
            <div className="border-t border-[#E2E8F0] p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  {t('language')}
                </span>
                <div className="pb-0">
                  <MobileLanguageSwitcher />
                </div>
              </div>
              {(!ready || !isSignedIn) && (
                <div className="space-y-2 pt-1">
                  {!ready ? (
                    <div className="h-10 rounded-lg bg-slate-100 animate-pulse" />
                  ) : (
                    <>
                      <Link
                        href="/login"
                        className="block w-full text-center rounded-lg border border-[#475569] px-4 py-2.5 text-sm font-semibold text-[#475569] hover:bg-[#f8fafc] transition-colors"
                      >
                        {t('signIn')}
                      </Link>
                      <Link
                        href="/register"
                        className="block w-full text-center rounded-lg bg-[#475569] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#334155] transition-colors"
                      >
                        {t('register')}
                      </Link>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}

/** 抽屉里用的紧凑版：只显示国旗+当前语言名（点击弹同样的下拉）。 */
function MobileLanguageSwitcher() {
  return (
    <div className="[&>button]:pb-0.5">
      <LanguageSwitcher />
    </div>
  );
}
