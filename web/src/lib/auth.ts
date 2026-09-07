'use client';

import { useCallback, useEffect, useState } from 'react';

import { TOKEN_KEY, currentLocalePrefix } from '@/lib/token';

const USER_KEY = 'cuagent_auth_user';

export type AuthUser = {
  id: number;
  email: string;
  role: string;
  // Privacy consent trail. May be absent for users registered before this
  // feature shipped — treated by the UI as "needs to consent".
  privacy_consented_at?: string | null;
  privacy_version?: string | null;
};

export const AUTH_ROLES = [
  'Researcher / Professor',
  'Associate Researcher / Associate Professor',
  'Assistant Researcher / Assistant Professor',
  'Postdoctoral researcher',
  'Student',
  'Research technician',
  'Other',
] as const;

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthUser>;
    // Corrupt / partial sessions (e.g. {} after a failed write) must not
    // reach NavUserMenu — email.split would throw and blank the whole app.
    if (
      typeof parsed?.id !== 'number' ||
      typeof parsed?.email !== 'string' ||
      !parsed.email.trim()
    ) {
      return null;
    }
    return parsed as AuthUser;
  } catch {
    return null;
  }
}

export function setAuthSession(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event('cuagent-auth-changed'));
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event('cuagent-auth-changed'));
}

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getAuthToken();
  const headers: Record<string, string> = { ...extra };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

/**
 * Validate a `?next=` redirect target from the URL before navigating to it.
 *
 * Blocks open-redirect vectors: protocol-relative `//evil.com` AND the
 * backslash form `/\evil.com` (browsers normalize `\` → `/`, so it becomes
 * `//evil.com` after the startsWith('/') check passes).
 */
export function safeNextPath(next: string | null | undefined, fallback = '/agent'): string {
  if (!next) return fallback;
  if (!next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return fallback;
  if (/(?:^|[/\\])(?:\d{1,3}(?:\.\d{1,3}){3}|localhost)(?::\d+)?(?:[/?#]|$)/i.test(next)) {
    return fallback;
  }
  return next;
}

export function redirectToLogin(nextPath?: string) {
  if (typeof window === 'undefined') return;
  const next = nextPath || window.location.pathname + window.location.search;
  const q = next && next !== '/login' && next !== '/register'
    ? `?next=${encodeURIComponent(next)}`
    : '';
  window.location.href = `${currentLocalePrefix()}/login${q}`;
}

/** Parse FastAPI error body into a readable string. */
export async function readApiError(res: Response, fallback = 'Request failed'): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text);
    if (typeof j.detail === 'string') return j.detail;
    if (Array.isArray(j.detail)) {
      return j.detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ');
    }
  } catch {
    /* ignore */
  }
  return text || fallback;
}

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(() => {
    setUser(getStoredUser());
    setReady(true);
  }, []);

  useEffect(() => {
    refresh();
    const onChange = () => refresh();
    window.addEventListener('cuagent-auth-changed', onChange);
    window.addEventListener('storage', onChange);
    return () => {
      window.removeEventListener('cuagent-auth-changed', onChange);
      window.removeEventListener('storage', onChange);
    };
  }, [refresh]);

  return { user, ready, isSignedIn: Boolean(user && getAuthToken()) };
}
