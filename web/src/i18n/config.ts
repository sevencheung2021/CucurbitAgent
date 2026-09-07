/**
 * i18n 配置 — 语言清单与 MendelSel 保持一致（37 种语言，按总使用人数降序）。
 * 顺序 = 语言菜单显示顺序（英语居首）。defaultLocale = 'en'（CucurbitAgent 面向国际研究者，
 * 现有 URL 无前缀即英文；其他语言加 /zh /ru 等前缀）。
 */
export const locales = [
  'en', 'zh', 'hi', 'es', 'ar', 'fr', 'bn', 'pt', 'ru', 'ur',
  'id', 'sw', 'de', 'ja', 'tr', 'vi', 'ko', 'ta', 'it', 'fa',
  'ha', 'fil', 'ms', 'th', 'pl', 'uk', 'uz', 'nl', 'ro', 'el',
  'kk', 'sv', 'ug', 'cs', 'bg', 'tib', 'mn',
] as const;
export const defaultLocale = 'en' as const;

export type Locale = (typeof locales)[number];

export const localeNames: Record<Locale, string> = {
  en: 'English',
  zh: '中文',
  hi: 'हिन्दी',
  es: 'Español',
  ar: 'العربية',
  fr: 'Français',
  bn: 'বাংলা',
  pt: 'Português',
  ru: 'Русский',
  ur: 'اردو',
  id: 'Indonesia',
  sw: 'Kiswahili',
  de: 'Deutsch',
  ja: '日本語',
  tr: 'Türkçe',
  vi: 'Tiếng Việt',
  ko: '한국어',
  ta: 'தமிழ்',
  it: 'Italiano',
  fa: 'فارسی',
  ha: 'Hausa',
  fil: 'Filipino',
  ms: 'Melayu',
  th: 'ไทย',
  pl: 'Polski',
  uk: 'Українська',
  uz: 'Oʻzbekcha',
  nl: 'Nederlands',
  ro: 'Română',
  el: 'Ελληνικά',
  kk: 'Қазақша',
  sv: 'Svenska',
  ug: 'ئۇيغۇرچە',
  cs: 'Čeština',
  bg: 'Български',
  tib: 'བོད་ཡིག',
  mn: 'Монгол',
};

export const localeFlags: Record<Locale, string> = {
  en: '🇺🇸',
  zh: '🇨🇳',
  hi: '🇮🇳',
  es: '🇪🇸',
  ar: '🇸🇦',
  fr: '🇫🇷',
  bn: '🇧🇩',
  pt: '🇧🇷',
  ru: '🇷🇺',
  ur: '🇵🇰',
  id: '🇮🇩',
  sw: '🇰🇪',
  de: '🇩🇪',
  ja: '🇯🇵',
  tr: '🇹🇷',
  vi: '🇻🇳',
  ko: '🇰🇷',
  ta: '🇱🇰',
  it: '🇮🇹',
  fa: '🇮🇷',
  ha: '🇳🇬',
  fil: '🇵🇭',
  ms: '🇲🇾',
  th: '🇹🇭',
  pl: '🇵🇱',
  uk: '🇺🇦',
  uz: '🇺🇿',
  nl: '🇳🇱',
  ro: '🇷🇴',
  el: '🇬🇷',
  kk: '🇰🇿',
  sv: '🇸🇪',
  ug: '🇨🇳',
  cs: '🇨🇿',
  bg: '🇧🇬',
  tib: '🇨🇳',
  mn: '🇲🇳',
};

// RTL 语言（阿拉伯字母系统）：阿拉伯语、乌尔都语、波斯语、维语
export const rtlLocales: Locale[] = ['ar', 'ur', 'fa', 'ug'];

export function isRTL(locale: Locale): boolean {
  return rtlLocales.includes(locale);
}

export function getNativeLocaleName(locale: Locale): string {
  return localeNames[locale];
}
