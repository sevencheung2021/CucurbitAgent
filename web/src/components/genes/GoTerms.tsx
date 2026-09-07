import { BarChart3Icon } from '@/components/ui/icons';

const blocks = [
  ['biological_process', 'Biological Process', '#27ae60'],
  ['molecular_function', 'Molecular Function', '#2980b9'],
  ['cellular_component', 'Cellular Component', '#f39c12'],
] as const;

function parseGo(term: string) {
  const match = term.match(/(GO:\d+)/);
  return { label: term.replace(/\s*\((GO:\d+)\)/, ''), go: match?.[1] };
}

export default function GoTerms({ terms }: { terms?: Record<string, string[]> }) {
  if (!terms) return null;
  return (
    <section className="mt-8 rounded-lg border border-[#e0e0e0] bg-white p-5">
      <h3 className="mb-4 text-base font-bold text-[#2c3e50] inline-flex items-center gap-2">
        <BarChart3Icon className="size-5 text-[#0D9488]" /> InterPro GO terms
      </h3>
      <div className="grid gap-5 md:grid-cols-3">
        {blocks.map(([key, title, color]) => (
          <div key={key} className="rounded-md bg-[#fdfefe] p-3" style={{ borderLeft: `4px solid ${color}` }}>
            <div className="mb-2 text-sm font-bold" style={{ color }}>{title}</div>
            <div className="space-y-1 text-sm leading-relaxed text-[#444]">
              {(terms[key] || []).length ? terms[key].map((term, i) => {
                const { label, go } = parseGo(term);
                return (
                  <div key={`${term}-${i}`}>• {' '}
                    {label && label !== go ? <span>{label} </span> : null}
                    {go ? <a className="text-[#2980b9] underline" href={`http://amigo.geneontology.org/amigo/term/${go}`} target="_blank" rel="noreferrer">{go}</a> : term}
                  </div>
                );
              }) : <span className="text-[#bdc3c7]">None</span>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
