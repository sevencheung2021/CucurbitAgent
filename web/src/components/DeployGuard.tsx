'use client';

import { useEffect } from 'react';

/**
 * After redeploy, an open tab may hold a stale Next BUILD_ID. Soft navigation
 * then fails to load /_next chunks. Hard-reload once when that happens.
 *
 * Stacked host:port paths are handled by middleware (308) + a sync head script
 * — do NOT location.replace them here; that raced with the App Router and
 * caused endless address-bar flashing.
 */
export default function DeployGuard() {
  useEffect(() => {
    const KEY = 'cuagent_deploy_reload_at';
    const WINDOW_MS = 15_000;

    const reloadOnce = (reason: string) => {
      try {
        const last = Number(sessionStorage.getItem(KEY) || '0');
        if (Date.now() - last < WINDOW_MS) return;
        // Session-wide cap: if the site is genuinely broken (not just a stale
        // BUILD_ID), stop reloading after 3 tries instead of looping forever.
        const count = Number(sessionStorage.getItem(`${KEY}_count`) || '0');
        if (count >= 3) return;
        sessionStorage.setItem(KEY, String(Date.now()));
        sessionStorage.setItem(`${KEY}_count`, String(count + 1));
      } catch {
        /* private mode */
      }
      // eslint-disable-next-line no-console
      console.warn('[DeployGuard] hard reload:', reason);
      window.location.reload();
    };

    const looksStale = (msg: string) =>
      /Loading chunk \d+|ChunkLoadError|Failed to fetch RSC payload|fetchServerResponse|\/_next\/static\//i.test(
        msg,
      );

    const onError = (event: ErrorEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'SCRIPT' || target.tagName === 'LINK')) {
        const src =
          (target as HTMLScriptElement).src ||
          (target as HTMLLinkElement).href ||
          '';
        if (src.includes('/_next/static/')) {
          reloadOnce(`asset ${src}`);
          return;
        }
      }
      const msg = String(event.message || event.error || '');
      if (looksStale(msg)) reloadOnce(msg.slice(0, 120));
    };

    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const msg =
        typeof reason === 'string'
          ? reason
          : String(reason?.message || reason || '');
      if (looksStale(msg)) reloadOnce(msg.slice(0, 120));
    };

    window.addEventListener('error', onError, true);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError, true);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);

  return null;
}
