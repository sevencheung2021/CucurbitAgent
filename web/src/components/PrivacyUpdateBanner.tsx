'use client';

import { useTranslations } from 'next-intl';

import { Link } from '@/i18n/routing';
import { useEffect, useState } from 'react';
import { apiUrl } from '@/lib/api';
import { authHeaders, useAuth } from '@/lib/auth';

/**
 * Non-blocking privacy-policy re-consent banner.
 *
 * On mount (when signed in) it asks the server for the current policy version
 * and the user's last-accepted version. If they differ — i.e. the policy was
 * updated after the user last consented — it shows a slim, dismissible banner.
 * Clicking "Agree" records fresh consent via POST /api/auth/consent; clicking
 * "Review" opens the policy page; closing just hides the banner (non-forcing).
 *
 * Migration note: users who registered before this feature shipped have
 * privacy_version === null, which is treated as "stale" so they get prompted
 * once on next login — that is intentional and legally safer than assuming
 * consent.
 */

type BannerState = 'hidden' | 'visible' | 'agreeing' | 'done';

export default function PrivacyUpdateBanner() {
  const t = useTranslations('banner');
  const { user, isSignedIn, ready } = useAuth();
  const [state, setState] = useState<BannerState>('hidden');
  const [serverVersion, setServerVersion] = useState<string>('');
  const [dismissed, setDismissed] = useState(false);

  // Respect a prior dismissal stored this session, so a user who postponed
  // isn't nagged on every page navigation within the same session.
  useEffect(() => {
    try {
      if (sessionStorage.getItem('cuagent_privacy_banner_dismissed') === '1') {
        setDismissed(true);
      }
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!ready || !isSignedIn || !user || dismissed) return;
    let cancelled = false;

    (async () => {
      try {
        const res = await fetch(apiUrl('/api/auth/me'), { headers: authHeaders() });
        if (!res.ok) return;
        const data = await res.json();
        const current = data?.current_privacy_version || '';
        const mine = data?.user?.privacy_version || '';
        if (!cancelled && current && current !== mine) {
          setServerVersion(current);
          setState('visible');
        }
      } catch {
        /* network error — silently skip; will retry next session */
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [ready, isSignedIn, user, dismissed]);

  async function agree() {
    setState('agreeing');
    try {
      const res = await fetch(apiUrl('/api/auth/consent'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ privacy_version: serverVersion || undefined }),
      });
      if (!res.ok) throw new Error('consent failed');
      // Refresh the locally cached user so the version matches and the banner
      // doesn't reappear until the next real policy bump.
      const data = await res.json();
      const cached = JSON.parse(localStorage.getItem('cuagent_auth_user') || '{}');
      cached.privacy_consented_at = data.privacy_consented_at;
      cached.privacy_version = data.privacy_version || serverVersion;
      localStorage.setItem('cuagent_auth_user', JSON.stringify(cached));
      window.dispatchEvent(new Event('cuagent-auth-changed'));
      setState('done');
      setDismissed(true);
    } catch {
      setState('visible'); // let them retry
    }
  }

  function dismiss() {
    setDismissed(true);
    setState('hidden');
  }

  if (state === 'hidden' || state === 'done' || dismissed) return null;

  return (
    <div
      role="region"
      aria-label="Privacy policy update notice"
      className="sticky top-0 z-[60] border-b border-[#e2e8f0] bg-[#f8fafc] px-4 py-2 text-xs text-slate-700 shadow-sm"
    >
      <div className="mx-auto flex max-w-content flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="font-semibold text-[#334155]">{t('privacyUpdated')}</span>
        <span className="hidden sm:inline text-slate-600">
          We&apos;ve revised our Privacy Policy. Please review and agree to continue.
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/privacy"
            className="rounded-md border border-[#475569] px-2.5 py-1 text-[11px] font-semibold text-[#475569] hover:bg-white"
          >
            Review
          </Link>
          <button
            type="button"
            onClick={agree}
            disabled={state === 'agreeing'}
            className="rounded-md bg-[#475569] px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-[#334155] disabled:opacity-60"
          >
            {state === 'agreeing' ? 'Saving…' : 'I agree'}
          </button>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss"
            className="rounded p-1 text-slate-400 hover:bg-white hover:text-slate-600"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
              <path
                fillRule="evenodd"
                d="M4.3 4.3a1 1 0 011.4 0L10 8.58l4.3-4.3a1 1 0 111.4 1.42L11.42 10l4.3 4.3a1 1 0 01-1.42 1.4L10 11.42l-4.3 4.3a1 1 0 01-1.4-1.42L8.58 10 4.3 5.7a1 1 0 010-1.4z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
