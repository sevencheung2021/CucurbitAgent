'use client';
import { SendIcon } from '@/components/ui/icons';

export default function AgentComposer({
  value,
  onChange,
  onSend,
  disabled,
  placeholder = 'Ask me about CsaV3_1G000010?',
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  return (
    <div className="rounded-[18px] border border-[#e2e8f0] bg-white/95 p-4 shadow-[0_8px_24px_rgba(51,65,85,0.08)]">
      <textarea
        className="w-full h-28 resize-none border-0 outline-none text-sm text-[#334155] placeholder:text-[#94A3B8] bg-transparent"
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Enter sends; Shift+Enter inserts a newline. Matches the behavior
          // users expect from ChatGPT / WeChat / Slack.
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSend();
          }
        }}
      />
      <div className="border-t border-[#E2E8F0] pt-3 flex flex-wrap items-center gap-3">
        <div className="ml-auto hidden sm:block" />
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="h-10 w-10 rounded-xl bg-[#475569] text-white font-bold flex items-center justify-center hover:bg-[#334155] transition-colors disabled:opacity-40"
          title="Send"
          aria-label="Send message"
        >
          <SendIcon className="size-4" />
        </button>
      </div>
    </div>
  );
}
