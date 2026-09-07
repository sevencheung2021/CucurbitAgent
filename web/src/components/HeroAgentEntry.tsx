'use client';

import { useTranslations } from 'next-intl';
import { useRouter } from '@/i18n/routing';
import { SendIcon } from '@/components/ui/icons';

/**
 * Compact one-line teaser that matches CucurbitAgent's composer look.
 * Click / Enter / Send → jump to /agent (optionally with ?q=).
 */
export default function HeroAgentEntry() {
  const router = useRouter();
  const t = useTranslations('home');

  function go(q?: string) {
    const query = (q || '').trim();
    router.push(query ? `/agent?q=${encodeURIComponent(query)}` : '/agent');
  }

  return (
    <button
      type="button"
      onClick={() => go()}
      className="group w-full text-left rounded-xl border border-[#e2e8f0] bg-white/95 px-3 py-2.5 shadow-[0_4px_14px_rgba(51,65,85,0.06)] hover:border-[#5EEAD4] hover:shadow-[0_6px_18px_rgba(51,65,85,0.1)] transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[#475569] focus-visible:ring-offset-2"
      aria-label={t('agentTeaser')}
    >
      <div className="flex items-center gap-3">
        <span className="flex-1 min-w-0 text-sm text-[#94A3B8] truncate">
          {t('agentTeaser')}
        </span>
        <span className="shrink-0 h-9 w-9 rounded-lg bg-[#475569] text-white flex items-center justify-center group-hover:bg-[#334155]">
          <SendIcon className="size-4" aria-hidden />
        </span>
      </div>
    </button>
  );
}
