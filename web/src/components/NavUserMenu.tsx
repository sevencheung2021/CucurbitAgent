'use client';

import { useEffect, useRef, useState } from 'react';
import { apiUrl } from '@/lib/api';
import { clearAuthSession, getAuthToken, type AuthUser } from '@/lib/auth';

/** TODO(prod): add password / security settings when SMTP + password auth ship. */

function initialsFromEmail(email: string | null | undefined): string {
  const local = String(email || '')
    .split('@')[0]
    .trim();
  if (!local) return '?';
  const parts = local.split(/[._-]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

export default function NavUserMenu({ user }: { user: AuthUser }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
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

  async function copyId() {
    try {
      await navigator.clipboard.writeText(String(user.id));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  async function signOut() {
    const token = getAuthToken();
    try {
      if (token) {
        await fetch(apiUrl('/api/auth/logout'), {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch {
      /* ignore */
    }
    clearAuthSession();
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative pb-3 shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-full pl-0.5 pr-1 py-0.5 hover:bg-slate-50 transition-colors"
        aria-expanded={open}
        aria-haspopup="menu"
        title={user.email}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#475569] text-[11px] font-bold text-white select-none">
          {initialsFromEmail(user.email)}
        </span>
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-3.5 w-3.5 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1 w-[280px] rounded-xl border border-slate-200 bg-white py-2 shadow-[0_8px_28px_rgba(15,23,42,0.12)]"
        >
          <div className="px-4 py-2.5 border-b border-slate-100">
            <div className="text-sm font-semibold text-slate-900 truncate" title={user.email}>
              {user.email}
            </div>
            <div className="mt-1 text-[11px] text-slate-500 truncate" title={user.role}>
              {user.role}
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-slate-500">
              <span>Account ID: {user.id}</span>
              <button
                type="button"
                onClick={copyId}
                className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                title="Copy account ID"
                aria-label="Copy account ID"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
                  <path d="M7 3.5A1.5 1.5 0 018.5 2h6A1.5 1.5 0 0116 3.5v10a1.5 1.5 0 01-1.5 1.5h-6A1.5 1.5 0 017 13.5v-10z" />
                  <path d="M4.5 6A1.5 1.5 0 003 7.5v9A1.5 1.5 0 004.5 18h6a1.5 1.5 0 001.5-1.5V16H8.5A2.5 2.5 0 016 13.5V6H4.5z" />
                </svg>
              </button>
              {copied && <span className="text-[#475569]">Copied</span>}
            </div>
          </div>

          <div className="py-1">
            <div className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Account
            </div>
            <div className="px-4 py-1.5 text-sm text-slate-700">
              <div className="font-medium text-slate-800">Account info</div>
              <p className="mt-0.5 text-[11px] leading-snug text-slate-500">
                Signed in with email verification. Password settings will be available later.
              </p>
              {user.privacy_consented_at && (
                <p className="mt-1 text-[10px] leading-snug text-slate-400">
                  Privacy policy accepted {user.privacy_version ? `(${user.privacy_version})` : ''}.
                </p>
              )}
            </div>
            <a
              href="/privacy"
              className="flex items-center justify-between px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              <span>Privacy &amp; Terms</span>
              <span className="text-[10px] text-slate-400">{user.privacy_version || 'view'}</span>
            </a>
            <button
              type="button"
              role="menuitem"
              onClick={signOut}
              className="mt-1 flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50"
            >
              <svg
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                className="h-4 w-4 text-slate-500"
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12.5 6.5V5.2A1.2 1.2 0 0011.3 4H5.2A1.2 1.2 0 004 5.2v9.6A1.2 1.2 0 005.2 16h6.1a1.2 1.2 0 001.2-1.2v-1.3M8.5 10H16m0 0l-2.2-2.2M16 10l-2.2 2.2"
                />
              </svg>
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
