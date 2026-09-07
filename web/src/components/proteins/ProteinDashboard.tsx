import { BotIcon } from '@/components/ui/icons';

export default function ProteinDashboard({ data }: { data: any }) {
  const score = Number(data.plddt_score || 0);
  const color = score >= 90 ? '#117a65' : score >= 70 ? '#2980b9' : score >= 50 ? '#f39c12' : '#c0392b';
  return (
    <div className="grid gap-5 md:grid-cols-[1fr_2fr] mb-6">
      <div className="rounded-xl bg-white p-5 text-center shadow border-t-[5px]" style={{ borderTopColor: color }}>
        <div className="text-sm font-bold text-[#7f8c8d]">Prediction Confidence</div>
        <div className="my-2 text-4xl font-black" style={{ color }}>{score.toFixed(2)}</div>
        <div className="text-base font-bold" style={{ color }}>{data.plddt_label}</div>
      </div>
      <div className="rounded-xl bg-white p-5 shadow border-t-[5px] border-[#1abc9c] flex flex-col justify-center">
        <div className="mb-4 text-sm font-bold text-[#117a65] inline-flex items-center gap-2">
          <BotIcon className="size-4" /> AI Global Functional Summary
        </div>
        <div className="text-lg leading-relaxed text-[#2c3e50]">
          {data.binding_sites?.length ? data.binding_sites.map((s: any) => <b key={s.site} className="mr-3">{s.site} Binding Protein</b>) : <span className="text-[#bdc3c7]">No specific binding detected.</span>}
        </div>
      </div>
    </div>
  );
}
