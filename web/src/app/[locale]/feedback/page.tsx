'use client';

import { useState } from 'react';
import { submitFeedback } from '@/lib/api';
import { useTranslations } from 'next-intl';
import { MessageSquareIcon } from '@/components/ui/icons';

const MAX_CHARS = 1000;



export default function FeedbackPage() {
  const t = useTranslations('feedback');
  const REPORT_ITEMS = [t('item1'), t('item2'), t('item3'), t('item4')];
  const [email, setEmail] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const remaining = MAX_CHARS - description.length;
  const canSubmit =
    Boolean(email.trim()) &&
    Boolean(description.trim()) &&
    description.length <= MAX_CHARS &&
    !submitting;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError('');
    setSubmitting(true);
    try {
      await submitFeedback(email.trim(), description.trim());
      setDone(true);
      setEmail('');
      setDescription('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit feedback');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      <div className="max-w-content mx-auto px-4 py-8">
        <h1 className="mb-4 text-4xl font-extrabold text-[#1a252f] inline-flex items-center gap-3">
          <MessageSquareIcon className="size-8 text-[#0D9488]" /> {t('title')}
        </h1>

        <div className="mb-8 rounded-lg border-l-4 border-[#0D9488] bg-[#F0FDFA] p-5 text-[#115E59]">
          <p className="mb-2 font-semibold text-[#0F766E]">{t('introTitle')}</p>
          <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            {REPORT_ITEMS.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-[#E2E8F0] bg-white p-6 shadow-sm md:p-8">
          <h2 className="mb-6 text-xl font-bold text-[#1a252f]">{t('formTitle')}</h2>

          {done ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-[#CCFBF1] bg-[#F0FDFA] px-4 py-3 text-sm text-[#0F766E]">
                {t('thanks')}
              </div>
              <button
                type="button"
                onClick={() => setDone(false)}
                className="rounded-lg bg-[#0D9488] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#0F766E] transition-colors"
              >
                {t('submitAnother')}
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-5">
              <div>
                <label htmlFor="feedback-email" className="mb-1.5 block text-sm font-semibold text-slate-700">
                  {t('email')}<span className="text-[#B01A75]">*</span>:
                </label>
                <input
                  id="feedback-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email"
                  className="w-full rounded-lg border border-[#CBD5E1] px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-[#0D9488] focus:outline-none focus:ring-1 focus:ring-[#0D9488]"
                />
              </div>

              <div>
                <label htmlFor="feedback-desc" className="mb-1.5 block text-sm font-semibold text-slate-700">
                  {t('description')}:
                </label>
                <div className="relative">
                  <textarea
                    id="feedback-desc"
                    required
                    value={description}
                    onChange={(e) => setDescription(e.target.value.slice(0, MAX_CHARS))}
                    placeholder={t('descPlaceholder', { max: MAX_CHARS })}
                    rows={8}
                    className="w-full resize-y rounded-lg border border-[#CBD5E1] px-3 py-2.5 pb-8 text-sm text-slate-800 placeholder:text-slate-400 focus:border-[#0D9488] focus:outline-none focus:ring-1 focus:ring-[#0D9488]"
                  />
                  <div className="pointer-events-none absolute bottom-2.5 right-3 text-xs text-slate-400">
                    {t('chars', { used: description.length, max: MAX_CHARS })}
                    {remaining < 50 && remaining >= 0 ? (
                      <span className="ml-1 text-amber-600">{t('left', { left: remaining })}</span>
                    ) : null}
                  </div>
                </div>
              </div>

              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={!canSubmit}
                className="rounded-lg bg-[#0D9488] px-6 py-2.5 text-sm font-semibold text-white hover:bg-[#0F766E] transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? t('submitting') : t('submit')}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
