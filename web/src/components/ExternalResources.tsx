import type { ExternalResource } from '@/lib/api';

/** Shorten long database names so the single-row grid stays compact. */
function displayName(name: string) {
  const n = (name || '').trim();
  if (/^Melon Information Resource(\s*\(MIR\))?$/i.test(n)) return 'MIR';
  if (/\(MIR\)\s*$/i.test(n) && /melon/i.test(n)) return 'MIR';
  if (/Cucurbit Genomics/i.test(n) || /CuGenDB/i.test(n)) return 'CuGenDB';
  if (/ESMFold/i.test(n)) return 'ESMFold';
  if (/AlphaFold/i.test(n)) return 'AlphaFold';
  if (/Ensembl Plants/i.test(n)) return 'Ensembl Plants';
  return n;
}

export default function ExternalResources({
  title,
  items,
}: {
  title: string;
  items: ExternalResource[];
}) {
  return (
    <section className="max-w-content mx-auto px-4 mb-8">
      <h3 className="text-teal-brand font-bold text-center text-lg mb-3">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        {items.map((item) => (
          <a
            key={item.url}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            title={`${item.name} — ${item.description}`}
            className="block bg-white border border-[#E2E8F0] rounded-lg px-2 py-2 hover:shadow-md hover:border-[#e2e8f0] transition-shadow no-underline min-w-0"
          >
            <div className="font-bold text-teal-brand text-xs leading-tight truncate">
              {displayName(item.name)}
            </div>
            <div className="text-slate-card text-[11px] mt-0.5 leading-snug line-clamp-2">
              {item.description}
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}
