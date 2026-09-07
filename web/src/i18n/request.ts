import { getRequestConfig } from 'next-intl/server';
import { routing } from './routing';

/** 深合并：base（英文）作为兜底，locale 覆盖其上。
 *  长尾语言可渐进翻译——缺的键回退英文，页面永不缺字。（与 MendelSel 相同策略） */
function deepMerge(base: Record<string, unknown>, over: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...base };
  for (const k of Object.keys(over)) {
    const b = base[k];
    const o = over[k];
    if (b && o && typeof b === 'object' && typeof o === 'object' && !Array.isArray(b) && !Array.isArray(o)) {
      out[k] = deepMerge(b as Record<string, unknown>, o as Record<string, unknown>);
    } else {
      out[k] = o;
    }
  }
  return out;
}

export default getRequestConfig(async ({ requestLocale }) => {
  // This typically corresponds to the `[locale]` segment
  let locale = await requestLocale;

  // Ensure that a valid locale is used
  if (!locale || !routing.locales.includes(locale as any)) {
    locale = routing.defaultLocale;
  }

  const en = (await import(`../../messages/en.json`)).default as Record<string, unknown>;
  let messages = en;
  if (locale !== 'en') {
    const loc = (await import(`../../messages/${locale}.json`)).default as Record<string, unknown>;
    messages = deepMerge(en, loc);
  }

  return { locale, messages };
});
