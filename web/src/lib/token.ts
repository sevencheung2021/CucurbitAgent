/**
 * localStorage key for the auth bearer token.
 *
 * Lives in its own directive-free module so BOTH `lib/auth.ts` ('use client')
 * and `lib/api.ts` (also imported from server components) can share it.
 */
export const TOKEN_KEY = 'cuagent_auth_token';

import { locales } from '@/i18n/config';

/**
 * Current URL's locale prefix (e.g. "/zh"), or '' for the default (en).
 * Used so hard navigations (401 → /login) keep the user's language.
 */
export function currentLocalePrefix(): string {
  if (typeof window === 'undefined') return '';
  const first = window.location.pathname.split('/')[1] || '';
  return locales.includes(first as any) && first !== 'en' ? `/${first}` : '';
}
