import Image from 'next/image';
import HeroAgentEntry from '@/components/HeroAgentEntry';

export default function Hero({
  title,
  subtitle,
  imageSrc,
}: {
  title: string;
  subtitle: string;
  imageSrc: string;
}) {
  // Localized titles carry their own line break (e.g. "欢迎来到\nCucurbitAgent");
  // only prettify the legacy English one-line form.
  const displayTitle = title.includes('\n')
    ? title
    : title.includes('Welcome to')
      ? 'Welcome to\nCucurbitAgent'
      : title;

  return (
    <section className="max-w-content mx-auto px-4 my-8 flex flex-col lg:flex-row lg:items-end gap-8 lg:gap-10">
      <div className="flex-1 flex flex-col justify-end min-w-0 lg:max-w-[48%]">
        <h1 className="text-4xl lg:text-5xl font-extrabold text-teal-brand leading-tight mb-4 whitespace-pre-line">
          {displayTitle}
        </h1>
        <p className="text-slate-muted text-lg leading-relaxed mb-5">{subtitle}</p>
        <HeroAgentEntry />
      </div>

      <div className="flex-1 flex justify-end min-w-0">
        <Image
          src={imageSrc}
          alt="Cucurbit"
          width={480}
          height={320}
          className="rounded-xl max-h-72 w-auto object-contain"
          priority
        />
      </div>
    </section>
  );
}
