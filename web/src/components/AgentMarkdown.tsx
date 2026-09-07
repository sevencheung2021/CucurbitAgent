'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Props = {
  content: string;
  className?: string;
};

/** Fullwidth / lookalike pipes → ASCII. */
function normalizePipes(text: string): string {
  return text.replace(/[\uFF5C\u2223\u2502\uFFE8]/g, '|');
}

/**
 * Strip leaked GLM/DeepSeek DSML tool-call markup from assistant text.
 *
 * Handles `<|DSML|…>` and `<||DSML||…>` (single / double pipes). Kept
 * deliberately simple — no nested quantifiers — to avoid runtime RegExp
 * failures in the browser. Backend sanitizes too; this is defense-in-depth.
 *
 * Never throws: on any failure returns the original text.
 */
export function stripDsmlMarkup(text: string): string {
  try {
    if (text == null) return '';
    if (typeof text !== 'string') text = String(text);
    if (!text) return text;

    let cleaned = normalizePipes(text);
    if (!/DSML/i.test(cleaned)) {
      return stripNarration(cleaned).trim();
    }

    // Closed blocks (tool_calls / invoke / parameter), allow 1+ pipes.
    cleaned = cleaned.replace(
      /<\s*\|+\s*DSML\s*\|+\s*tool_calls\s*>[\s\S]*?<\s*\/\s*\|+\s*DSML\s*\|+\s*tool_calls\s*>/gi,
      '',
    );
    cleaned = cleaned.replace(
      /<\s*\|+\s*DSML\s*\|+\s*invoke\b[^>]*>[\s\S]*?<\s*\/\s*\|+\s*DSML\s*\|+\s*invoke\s*>/gi,
      '',
    );
    cleaned = cleaned.replace(
      /<\s*\|+\s*DSML\s*\|+\s*parameter\b[^>]*>[\s\S]*?<\s*\/\s*\|+\s*DSML\s*\|+\s*parameter\s*>/gi,
      '',
    );

    // Unclosed opener — cut from here so payload cannot leak.
    const start = cleaned.search(/<\s*\|+\s*DSML\b/i);
    if (start >= 0) {
      cleaned = cleaned.slice(0, start);
    } else {
      // Orphan tags only.
      cleaned = cleaned.replace(/<\s*\/?\s*\|+\s*DSML\b[^>]*>/gi, '');
      if (/\bDSML\b/i.test(cleaned)) {
        cleaned = cleaned
          .split('\n')
          .filter(
            (line) =>
              !(/\bDSML\b/i.test(line) && /\b(tool_calls|invoke|parameter)\b/i.test(line)),
          )
          .join('\n');
      }
    }

    return stripNarration(cleaned).replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  } catch {
    // Never crash the chat UI over a sanitizer bug.
    return typeof text === 'string' ? text : '';
  }
}

function stripNarration(cleaned: string): string {
  cleaned = cleaned.replace(
    /(?:^|\n)\s*(?:Now\s+)?(?:Let\s+me|I'll|I\s+will|I\s+am\s+going\s+to)\s+(?:also\s+)?(?:search|check|call|look\s+up|query|fetch|retrieve|use|try|run|invoke|ask)\b[^\n]*/gi,
    '',
  );
  cleaned = cleaned.replace(
    /(?:^|\n)\s*(?:让我|我来|我再|接下来(?:我)?(?:将|会)?)\s*(?:也)?(?:搜索|查询|检索|调用|查一下|看一下|获取)[^\n]*/g,
    '',
  );
  return cleaned;
}

export default function AgentMarkdown({ content, className = '' }: Props) {
  let safe = '';
  try {
    safe = stripDsmlMarkup(content || '');
  } catch {
    safe = typeof content === 'string' ? content : '';
  }
  if (!safe.trim()) return null;

  return (
    <div className={`agent-markdown text-sm leading-relaxed text-[#2c3e50] ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="mb-3 mt-4 text-xl font-bold text-[#1a252f] first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-4 text-lg font-bold text-[#1a252f] first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-2 mt-3 text-base font-semibold text-[#1a252f] first:mt-0">{children}</h3>
          ),
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-[#1a252f]">{children}</strong>,
          em: ({ children }) => <em className="italic text-[#475569]">{children}</em>,
          hr: () => <hr className="my-4 border-[#E2E8F0]" />,
          blockquote: ({ children }) => (
            <blockquote className="mb-3 border-l-4 border-[#0d9488] bg-[#F0FDFA] px-3 py-2 text-[#0f766e] last:mb-0">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="font-medium text-[#2980b9] underline decoration-[#2980b9]/40 underline-offset-2 hover:decoration-[#2980b9]"
            >
              {children}
            </a>
          ),
          code: ({ className: codeClass, children }) => {
            const isBlock = Boolean(codeClass);
            if (isBlock) {
              return (
                <pre className="mb-3 overflow-x-auto rounded-lg bg-[#1e293b] p-3 text-xs text-[#e2e8f0] last:mb-0">
                  <code>{children}</code>
                </pre>
              );
            }
            return (
              <code className="rounded bg-[#E2E8F0] px-1.5 py-0.5 font-mono text-[0.85em] text-[#1a252f]">
                {children}
              </code>
            );
          },
          table: ({ children }) => (
            <div className="mb-3 overflow-x-auto rounded-lg border border-[#E2E8F0] last:mb-0">
              <table className="w-full min-w-[280px] border-collapse text-left text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-[#F8FAFC] text-[#64748B]">{children}</thead>,
          tbody: ({ children }) => <tbody className="divide-y divide-[#E2E8F0] bg-white">{children}</tbody>,
          tr: ({ children }) => <tr>{children}</tr>,
          th: ({ children }) => <th className="px-3 py-2 font-semibold">{children}</th>,
          td: ({ children }) => <td className="px-3 py-2 align-top text-[#475569]">{children}</td>,
        }}
      >
        {safe}
      </ReactMarkdown>
    </div>
  );
}
