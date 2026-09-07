import '../globals.css';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, getTranslations, setRequestLocale } from 'next-intl/server';
import NavBar from '@/components/NavBar';
import PrivacyUpdateBanner from '@/components/PrivacyUpdateBanner';
import DeployGuard from '@/components/DeployGuard';
import { routing } from '@/i18n/routing';
import { isRTL, locales, type Locale } from '@/i18n/config';

type Props = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'metadata' });
  return { title: t('title'), description: t('description') };
}

/** Runs before paint / React — last-resort unwrap if middleware was bypassed. */
const STACK_FIX_SCRIPT = `(function(){try{var p=location.pathname,re=/^(?:\\d{1,3}(?:\\.\\d{1,3}){3}|localhost)(?::\\d+)?$/i,parts=p.split('/').filter(Boolean);if(!parts.some(function(s){return re.test(s)}))return;while(parts.length&&re.test(parts[0]))parts.shift();var n=parts.length?'/'+parts.join('/'):'/';if(n===p)return;location.replace(location.protocol+'//'+location.host+n+location.search+location.hash)}catch(e){}})();`;

export default async function LocaleLayout({ children, params }: Props) {
  const { locale } = await params;

  // 显式告知 next-intl 当前 locale（避免运行时读 headers）
  setRequestLocale(locale);

  if (!routing.locales.includes(locale as any)) {
    notFound();
  }

  const messages = await getMessages();
  const dir = isRTL(locale as Locale) ? 'rtl' : 'ltr';

  return (
    <NextIntlClientProvider messages={messages}>
      <html lang={locale} dir={dir}>
        <head>
          <script dangerouslySetInnerHTML={{ __html: STACK_FIX_SCRIPT }} />
        </head>
        <body>
          <DeployGuard />
          <PrivacyUpdateBanner />
          <NavBar />
          <main>{children}</main>
        </body>
      </html>
    </NextIntlClientProvider>
  );
}
