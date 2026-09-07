'use client';

import { useState } from 'react';

/** Table cell text: 2-line clamp by default, click to expand full content. */
export default function ExpandableText({
  text,
  className = '',
}: {
  text?: string | null;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const value = (text || '').trim();

  if (!value) {
    return <span className={className}>—</span>;
  }

  const needsToggle = value.length > 72;

  return (
    <div className={`min-w-[220px] max-w-[520px] ${className}`}>
      <div
        className={`text-slate-600 break-words whitespace-normal ${
          open || !needsToggle ? '' : 'line-clamp-2'
        }`}
      >
        {value}
      </div>
      {needsToggle && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-0.5 text-[10px] font-medium text-[#475569] hover:text-[#B01A75] hover:underline"
        >
          {open ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  );
}
