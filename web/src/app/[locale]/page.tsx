import { setRequestLocale } from 'next-intl/server';
import Hero from '@/components/Hero';
import About from '@/components/About';
import LatestLiterature from '@/components/LatestLiterature';
import ExternalResources from '@/components/ExternalResources';
import CiteUs from '@/components/CiteUs';
import Footer from '@/components/Footer';
import { fetchHomeContent, fetchLiteraturePapers } from '@/lib/api';
import { locales } from '@/i18n/config';

export const dynamic = 'force-dynamic';

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const [content, lit] = await Promise.all([
    fetchHomeContent(locale),
    fetchLiteraturePapers('', 1).catch(() => ({ papers: [] })),
  ]);
  const latestPapers = (lit?.papers || []).slice(0, 3);

  return (
    <>
      <Hero
        title={content.hero.title}
        subtitle={content.hero.subtitle}
        imageSrc="/assets/watermelon_1.png"
      />
      <About title={content.about.title} paragraphs={content.about.paragraphs} />
      <LatestLiterature papers={latestPapers} />
      <ExternalResources
        title={content.externalResources.title}
        items={content.externalResources.items}
      />
      <CiteUs content={content.citeUs} />
      <Footer
        institution={content.footer.institution}
        contact={content.footer.contact}
        affiliations={content.footer.affiliations}
        copyright={content.footer.copyright}
      />
    </>
  );
}
