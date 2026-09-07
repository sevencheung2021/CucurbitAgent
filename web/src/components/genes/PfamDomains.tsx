import { PuzzleIcon } from '@/components/ui/icons';

const colors = ['#9b59b6', '#e67e22', '#1abc9c', '#e74c3c', '#34495e', '#f1c40f', '#2980b9', '#27ae60'];

type Domain = { name: string; pfam_id?: string; start: number; end: number; length_aa?: number };

export default function PfamDomains({ domains, proteinLength }: { domains?: Domain[]; proteinLength?: number }) {
  if (!domains?.length || !proteinLength) return null;
  const sorted = [...domains].sort((a, b) => a.start - b.start);
  const tracks: number[] = [];
  const placed = sorted.map((d) => {
    let track = tracks.findIndex((end) => d.start > end + 2);
    if (track === -1) { track = tracks.length; tracks.push(d.end); }
    else tracks[track] = d.end;
    return { ...d, track };
  });
  const height = Math.max(70, tracks.length * 38 + 26);

  return (
    <section className="mt-8">
      <h3 className="mb-2 text-sm font-bold text-[#8e44ad] inline-flex flex-wrap items-center gap-2">
        <PuzzleIcon className="size-4" />
        <span>Protein Domain Architecture (Pfam) | Length: {proteinLength} aa</span>
      </h3>
      <div className="relative w-full rounded border border-[#d5dbdb] bg-[#f8f9fa] overflow-hidden" style={{ height }}>
        <div className="absolute left-0 top-[25px] h-1 w-full bg-[#bdc3c7]" />
        {placed.map((d, i) => {
          const left = (d.start / proteinLength) * 100;
          const width = ((d.end - d.start + 1) / proteinLength) * 100;
          const color = colors[i % colors.length];
          const label = `${d.name}${d.pfam_id ? ` (${d.pfam_id})` : ''}`;
          return (
            <div key={`${d.name}-${d.start}-${i}`} className="absolute z-10 flex h-7 items-center justify-center overflow-hidden whitespace-nowrap rounded-lg px-1 text-[11px] font-bold text-white shadow" title={`${label}: ${d.start}-${d.end}`} style={{ left: `${left}%`, width: `${Math.max(width, 7)}%`, top: 10 + d.track * 35, background: color }}>
              {d.name} {d.pfam_id ? <a className="ml-1 underline" href={`https://www.ebi.ac.uk/interpro/entry/pfam/${d.pfam_id}/`} target="_blank" rel="noreferrer">{d.pfam_id}</a> : null}
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap justify-end gap-4 text-xs text-[#555]">
        {placed.map((d, i) => (
          <span key={`${d.name}-legend-${i}`} className="inline-flex items-center gap-1">
            <span className="h-3.5 w-3.5 rounded-full" style={{ background: colors[i % colors.length] }} />
            {d.name} {d.pfam_id ? <a className="text-[#2980b9] underline" href={`https://www.ebi.ac.uk/interpro/entry/pfam/${d.pfam_id}/`} target="_blank" rel="noreferrer">{d.pfam_id}</a> : null}
          </span>
        ))}
      </div>
    </section>
  );
}
