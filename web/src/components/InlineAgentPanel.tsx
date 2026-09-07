'use client';

import { useState, useEffect, useRef, type ReactNode } from 'react';
import AgentMarkdown from '@/components/AgentMarkdown';
import { BotIcon, CheckIcon } from '@/components/ui/icons';
import type { AgentStreamHandlers } from '@/lib/api';

type Props = {
  title?: string;
  message: string;
  runKey?: string | number;
  runner: (handlers: AgentStreamHandlers) => Promise<void>;
  autoRun?: boolean;
  viewer?: ReactNode;
  extraActions?: ReactNode;
};

export default function InlineAgentPanel({
  title = 'CucurbitAgent',
  message,
  runKey,
  runner,
  autoRun = false,
  viewer,
  extraActions,
}: Props) {
  const [statuses, setStatuses] = useState<string[]>([]);
  const [answer, setAnswer] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const startedRef = useRef<string | number | undefined>(undefined);

  const run = async () => {
    setStatuses([]);
    setAnswer('');
    setError('');
    setLoading(true);
    try {
      await runner({
        onStatus: (m) => setStatuses((prev) => [...prev, m]),
        onToken: (t) => setAnswer((prev) => prev + t),
        onError: (m) => setError(m),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!autoRun) return;
    if (runKey === undefined || runKey === null) return;
    if (startedRef.current === runKey) return;
    startedRef.current = runKey;
    run();
  }, [autoRun, runKey]);

  const hasContent = statuses.length > 0 || answer !== '' || error !== '';

  return (
    <div className="rounded-xl border border-[#E2E8F0] bg-white shadow-sm overflow-hidden">
      {title && (
        <div className="px-4 py-2.5 border-b border-[#E2E8F0] bg-gradient-to-r from-teal-accent/10 to-transparent flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BotIcon className="size-5 text-[#475569]" />
            <span className="text-sm font-semibold text-slate-800">{title}</span>
          </div>
          {extraActions}
        </div>
      )}
      <div className="p-4 space-y-3">
        <div className="text-sm text-slate-600 bg-slate-50 rounded-lg px-3 py-2">
          <span className="text-xs text-slate-400 mr-2">Q:</span>
          {message}
        </div>

        {loading && !answer && (
          <div className="space-y-2">
            {statuses.length === 0 ? (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span className="inline-block w-1.5 h-1.5 bg-teal-600 rounded-full animate-pulse" />
                <span>Thinking...</span>
              </div>
            ) : (
              <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 space-y-1.5">
                {statuses.map((s, i) => {
                  const isLast = i === statuses.length - 1;
                  const isProgress = s.includes('✅') || s.includes('🔧') || s.includes('✍️');
                  return (
                    <div
                      key={i}
                      className={`flex items-center gap-2 text-xs ${
                        isLast && isProgress ? 'text-slate-800 font-medium' : 'text-slate-500'
                      }`}
                    >
                      {isLast && isProgress ? (
                        <span className="inline-block w-1.5 h-1.5 bg-teal-600 rounded-full animate-pulse" />
                      ) : (
                        <span className="inline-block w-1.5 h-1.5 opacity-0" />
                      )}
                      <span>{s}</span>
                    </div>
                  );
                })}
                <div className="flex items-center gap-2 pt-1 text-xs text-slate-400">
                  <span className="inline-block w-1.5 h-1.5 bg-slate-300 rounded-full animate-pulse" />
                  <span>generating answer...</span>
                </div>
              </div>
            )}
          </div>
        )}

        {hasContent && (
          <div className="space-y-3">
            {answer && (
              <div className="rounded-lg bg-[#EAF4FF] border border-[#D7EAFE] px-5 py-4 text-sm leading-relaxed text-slate-800">
                <div className="text-xs mb-1 font-semibold" style={{ color: '#1F4E79' }}>
                  AI Summary
                </div>
                <AgentMarkdown content={answer} />
              </div>
            )}

            {error && (
              <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
          </div>
        )}

        {viewer && <div className="border-t border-slate-100 pt-3 mt-2">{viewer}</div>}
      </div>

      {!autoRun && (
        <div className="px-4 py-3 border-t border-[#E2E8F0] bg-slate-50/50 flex justify-end">
          <button
            onClick={run}
            disabled={loading}
            className="px-4 py-1.5 rounded-lg text-sm font-medium bg-teal-accent text-white hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Running...' : hasContent ? 'Re-run' : 'Run Chat'}
          </button>
        </div>
      )}
    </div>
  );
}
