import { CheckIcon, RefreshCwIcon } from '@/components/ui/icons';
import { useTranslations } from 'next-intl';

export default function GeneAnnotation({ data }: { data: any }) {
  const t = useTranslations('genes');
  const mapping = data.version_mapping || {};
  const mappingText = Object.entries(mapping)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' | ');

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-[#DFF5E8] border border-[#C7EED6] px-5 py-4 text-sm text-[#334155] flex items-start gap-2">
        <CheckIcon className="size-4 shrink-0 mt-[2px]" />
        <span>Successfully resolved. Showing data for: <code>{data.gene_id}</code></span>
      </div>
      {mappingText && (
        <div className="rounded-lg bg-[#EAF4FF] border border-[#D7EAFE] px-5 py-4 text-sm text-[#1F4E79] flex items-start gap-2">
          <RefreshCwIcon className="size-4 shrink-0 mt-[2px]" />
          <span><b>{t('versionHistory')}:</b> {mappingText}</span>
        </div>
      )}
      <div className="rounded-lg bg-[#EAF4FF] px-5 py-5 text-sm text-[#1F2937]">
        <b>{t('functionDesc')}:</b> {data.basic_info?.function || 'N/A'}
      </div>
      <div className="text-base">
        <b>{t('locationLabel')}:</b>{' '}
        <code className="text-[#334155]">{data.basic_info?.chr}</code> :{' '}
        <code className="text-[#334155]">{data.basic_info?.start}</code> -{' '}
        <code className="text-[#334155]">{data.basic_info?.end}</code>{' '}
        (Strand: <code>{data.basic_info?.strand}</code>)
      </div>
    </div>
  );
}
