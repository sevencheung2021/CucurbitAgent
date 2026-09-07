import { DnaIcon } from '@/components/ui/icons';

export default function GeneStructure({ structure }: { structure?: any }) {
  if (!structure?.cds_exons?.length) return null;
  const start = Number(structure.gene_start || 0);
  const end = Number(structure.gene_end || 0);
  const len = Number(structure.gene_length_bp || (end - start + 1));

  return (
    <section className="mt-8">
      <h3 className="text-sm font-bold text-[#2c3e50] mb-2 inline-flex flex-wrap items-center gap-2">
        <DnaIcon className="size-4 text-[#475569]" />
        <span>V3 Gene Structure | Strand: {structure.strand || 'N/A'} | Length: {len.toLocaleString()} bp</span>
      </h3>
      <div className="relative h-[35px] w-full rounded border border-[#d5dbdb] bg-[#f8f9fa] overflow-hidden">
        <div className="absolute left-0 top-1/2 h-[2px] w-full -translate-y-1/2 bg-[#7f8c8d]" />
        {structure.cds_exons.map((exon: [number, number], idx: number) => {
          const left = ((exon[0] - start) / len) * 100;
          const width = ((exon[1] - exon[0] + 1) / len) * 100;
          return (
            <div
              key={`${exon[0]}-${exon[1]}-${idx}`}
              title={`CDS ${idx + 1}: ${exon[0]}-${exon[1]} (${exon[1] - exon[0] + 1} bp)`}
              className="absolute top-[20%] h-[60%] rounded bg-[#2980b9] shadow"
              style={{ left: `${left}%`, width: `${Math.max(width, 1)}%` }}
            />
          );
        })}
      </div>
      <div className="mt-2 flex justify-end gap-4 text-xs text-[#555]">
        <span className="inline-flex items-center gap-1"><span className="h-3.5 w-3.5 rounded-sm bg-[#2980b9]" /> CDS</span>
        <span className="inline-flex items-center gap-1"><span className="h-[2px] w-6 bg-[#7f8c8d]" /> Intron/UTR</span>
      </div>
    </section>
  );
}
