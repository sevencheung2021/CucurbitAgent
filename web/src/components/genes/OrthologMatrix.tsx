const CUC = ['Cucumber', 'Melon', 'Watermelon', 'Pumpkin Moschata', 'Pumpkin Pepo', 'BitterGourd', 'BottleGourd', 'SpongeGourd', 'WaxGourd'];
const MODEL = ['Arabidopsis', 'Maize', 'Rice', 'Tomato'];
import { NetworkIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

export default function OrthologMatrix({ matrix }: { matrix?: any }) {
  const t = useTranslations('genes');
  if (!matrix?.columns?.length) return null;
  const groups = [
    ['🥒 Cucurbitaceae', matrix.columns.filter((c: string) => CUC.includes(c))],
    ['🌾 Model Crops', matrix.columns.filter((c: string) => MODEL.includes(c))],
  ] as const;
  const found = matrix.columns.filter((c: string) => Object.values(matrix.rows).some((row: any) => row[matrix.columns.indexOf(c)] !== '—'));
  const missing = matrix.columns.filter((c: string) => !found.includes(c));

  return (
    <section className="mt-10">
      <h2 className="mb-4 text-3xl font-extrabold text-[#0f172a] inline-flex items-center gap-3">
        <NetworkIcon className="size-7 text-[#475569]" /> Plant Orthologs
      </h2>
      <p className="mb-6 text-sm text-[#64748B]">Each column is one other species (excluding the query species); rows show the best homolog hit. Gray cells (—) mean no homolog passed the filter (identity ≥ 40%, coverage ≥ 50%).</p>
      {groups.map(([title, cols]) => cols.length ? <MatrixTable key={title} title={title} cols={cols as string[]} matrix={matrix} /> : null)}
      <div className="mt-6 rounded-lg bg-[#EAF4FF] px-5 py-4 text-[#1F4E79]">
        {t('foundInPre')} <b>{found.length}/{matrix.columns.length}</b> {t('foundInPost', { missing: missing.length ? missing.join(', ') : t('none') })}
      </div>
    </section>
  );
}

function MatrixTable({ title, cols, matrix }: { title: string; cols: string[]; matrix: any }) {
  const indexes = cols.map((c) => matrix.columns.indexOf(c));
  return (
    <div className="mb-8">
      <h3 className="mb-3 text-lg font-bold">{title}</h3>
      <div className="overflow-x-auto rounded-lg border border-[#E2E8F0] bg-white">
        <table className="min-w-full text-sm">
          <thead><tr><th className="p-3" />{cols.map((c) => <th key={c} className="p-3 text-left font-normal text-[#64748B]">{c}</th>)}</tr></thead>
          <tbody>
            {Object.entries(matrix.rows).map(([rowName, vals]: any) => (
              <tr key={rowName} className="border-t border-[#E2E8F0]"><td className="p-3 font-medium text-[#64748B]">{rowName}</td>{indexes.map((idx) => <td key={idx} className={`p-3 ${vals[idx] === '—' ? 'bg-[#f4f6f7] text-[#95a5a6]' : ''}`}>{vals[idx]}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
