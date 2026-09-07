'use client';

import { useTranslations } from 'next-intl';
import { useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useState } from 'react';
import { apiUrl } from '@/lib/api';
import { readApiError, safeNextPath, setAuthSession } from '@/lib/auth';
import { Link } from '@/i18n/routing';

function LoginForm() {
  const search = useSearchParams();
  const next = search.get('next') || '/agent';
  const t = useTranslations('auth');

  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
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
        body: JSON.stringify({ email: email.trim(), purpose: 'login' }),
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
          purpose: 'login',
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
      <h1 className="text-2xl font-bold text-[#0F766E]">{t('loginTitle')}</h1>
      <p className="mt-2 text-sm text-slate-600">{t('loginDesc')}</p>

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
          {error && <p className="text-sm text-red-600">{error}</p>}
          {info && <p className="text-sm text-teal-700">{info}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-[#0D9488] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0F766E] disabled:opacity-60"
          >
            {busy ? t('sending') : t('sendCode')}
          </button>
        </form>
      ) : (
        <form onSubmit={verify} className="mt-6 space-y-4">
          <p className="text-sm text-slate-600">
            {t('codeSentTo')} <span className="font-semibold">{email}</span>
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
            className="w-full rounded-lg bg-[#0D9488] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0F766E] disabled:opacity-60"
          >
            {busy ? t('signingIn') : t('verifyLogin')}
          </button>
          <button
            type="button"
            className="w-full text-sm text-slate-500 underline"
            onClick={() => { setStep('form'); setCode(''); setError(''); }}
          >
            {t('useDifferentEmail')}
          </button>
        </form>
      )}

      <p className="mt-6 text-center text-sm text-slate-600">
        {t('newHere')}{' '}
        <Link href={`/register?next=${encodeURIComponent(next)}`} className="font-semibold text-[#0D9488]">
          {t('createAccount')}
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="p-10 text-center text-sm text-slate-500">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
