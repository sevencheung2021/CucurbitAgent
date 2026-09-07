'use client';

import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useState } from 'react';
import { apiUrl } from '@/lib/api';
import {
  AUTH_ROLES,
  readApiError,
  safeNextPath,
  setAuthSession,
} from '@/lib/auth';
import { Link } from '@/i18n/routing';

function RegisterForm() {
  const search = useSearchParams();
  const next = search.get('next') || '/agent';
  const t = useTranslations('auth');

  const [email, setEmail] = useState('');
  const [role, setRole] = useState<string>(AUTH_ROLES[0]);
  const [code, setCode] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [step, setStep] = useState<'form' | 'code'>('form');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  async function requestCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    setInfo('');
    try {
      const res = await fetch(apiUrl('/api/auth/request-code'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), purpose: 'register' }),
      });
      if (!res.ok) throw new Error(await readApiError(res));
      const data = await res.json();
      setInfo(data.message || 'Verification code sent.');
      setStep('code');
    } catch (err: any) {
      setError(err?.message || 'Failed to send code');
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await fetch(apiUrl('/api/auth/verify'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          code: code.trim(),
          purpose: 'register',
          role,
          agreed,
        }),
      });
      if (!res.ok) throw new Error(await readApiError(res));
      const data = await res.json();
      setAuthSession(data.token, data.user);
      window.location.replace(safeNextPath(next));
    } catch (err: any) {
      setError(err?.message || 'Verification failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-10">
      <h1 className="text-2xl font-bold text-[#334155]">{t('registerTitle')}</h1>
      <p className="mt-2 text-sm text-slate-600">{t('registerDesc')}</p>

      {step === 'form' ? (
        <form onSubmit={requestCode} className="mt-6 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-semibold text-slate-700">{t('email')}</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="you@institution.edu"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-semibold text-slate-700">{t('role')}</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white"
            >
              {AUTH_ROLES.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {info && <p className="text-sm text-teal-700">{info}</p>}

          {/* Privacy consent — required at registration (PIPL/CSL). */}
          <label className="flex items-start gap-2 text-xs leading-snug text-slate-600">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-[#475569] focus:ring-[#475569]"
              required
            />
            <span>
              I have read and agree to the{' '}
              <Link
                href="/privacy"
                target="_blank"
                rel="noopener"
                className="font-semibold text-[#475569] underline"
              >
                Privacy Policy
              </Link>{' '}
              and{' '}
              <Link
                href="/terms"
                target="_blank"
                rel="noopener"
                className="font-semibold text-[#475569] underline"
              >
                Terms of Use
              </Link>
              .
            </span>
          </label>

          <button
            type="submit"
            disabled={busy || !agreed}
            className="w-full rounded-lg bg-[#475569] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#334155] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? t('sending') : t('sendCode')}
          </button>
        </form>
      ) : (
        <form onSubmit={verify} className="mt-6 space-y-4">
          <p className="text-sm text-slate-600">
            {t('codeSentTo')} <span className="font-semibold">{email}</span>. {t('role')}:{' '}
            <span className="font-semibold">{role}</span>
          </p>
          <div>
            <label className="mb-1 block text-sm font-semibold text-slate-700">{t('code')}</label>
            <input
              inputMode="numeric"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm tracking-widest"
              placeholder={t('codePlaceholder')}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {info && <p className="text-sm text-teal-700">{info}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-[#475569] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#334155] disabled:opacity-60"
          >
            {busy ? t('verifying') : t('verifyRegister')}
          </button>
          <button
            type="button"
            className="w-full text-sm text-slate-500 underline"
            onClick={() => { setStep('form'); setCode(''); setError(''); }}
          >
            {t('changeEmailRole')}
          </button>
        </form>
      )}

      <p className="mt-6 text-center text-sm text-slate-600">
        {t('haveAccount')}{' '}
        <Link href={`/login?next=${encodeURIComponent(next)}`} className="font-semibold text-[#475569]">
          {t('gateSignIn')}
        </Link>
      </p>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="p-10 text-center text-sm text-slate-500">Loading…</div>}>
      <RegisterForm />
    </Suspense>
  );
}
