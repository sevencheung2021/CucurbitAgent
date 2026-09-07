'use client';

import { useLocale, useTranslations } from 'next-intl';
import { Link, usePathname } from '@/i18n/routing';
import { useAuth } from '@/lib/auth';
import { BotIcon } from '@/components/ui/icons';

/**
 * Gate for AI Q&A / summary features.
 * - Signed in → render children
 * - Signed out → show email sign-in prompt (database search stays available elsewhere)
 */
export default function AiSignInGate({
  children,
  feature = 'AI Q&A',
  compact = false,
}: {
  children: React.ReactNode;
  /** Short name shown in the prompt, e.g. "Paper Chat", "AI Summary" */
  feature?: string;
  /** Tighter padding for inline panels */
  compact?: boolean;
}) {
  const { ready, isSignedIn } = useAuth();
  const pathname = usePathname();
  const locale = useLocale();
  const t = useTranslations('auth');
  // intl usePathname 不带语言前缀 — 登录后要回到同一语言，next 里补上 /zh 等前缀
  const next = encodeURIComponent(
    locale === 'en' || !pathname ? (pathname || '/') : `/${locale}${pathname}`,
  );

  if (!ready) {
    return (
      <div
        className={`rounded-lg border border-[#E2E8F0] bg-slate-50 ${
          compact ? 'px-3 py-4' : 'px-4 py-6'
        } animate-pulse`}
        aria-hidden
      >
        <div className="mx-auto h-4 w-48 rounded bg-slate-200" />
      </div>
    );
  }

  if (isSignedIn) return <>{children}</>;

  return (
    <div
      className={`rounded-lg border border-amber-200 bg-amber-50/80 text-center ${
        compact ? 'px-3 py-4' : 'px-5 py-6'
      }`}
      role="status"
    >
      <div className="mx-auto mb-2 flex size-9 items-center justify-center rounded-full bg-white border border-amber-200">
        <BotIcon className="size-4 text-[#0D9488]" />
      </div>
      <p className="text-sm font-semibold text-slate-800">
        {t('gateTitle', { feature })}
      </p>
      <p className="mt-1 text-xs text-slate-600 max-w-md mx-auto">
        {t('gateDesc')}
      </p>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        <Link
          href={`/login?next=${next}`}
          className="inline-flex items-center rounded-lg bg-[#0D9488] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0F766E] transition-colors"
        >
          {t('gateSignIn')}
        </Link>
        <Link
          href={`/register?next=${next}`}
          className="inline-flex items-center rounded-lg border border-[#0D9488] px-4 py-2 text-sm font-semibold text-[#0D9488] hover:bg-white transition-colors"
        >
          {t('gateRegister')}
        </Link>
      </div>
    </div>
  );
}
