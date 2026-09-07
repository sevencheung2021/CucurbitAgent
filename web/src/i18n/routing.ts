import { defineRouting } from 'next-intl/routing';
import { createNavigation } from 'next-intl/navigation';

export const routing = defineRouting({
  // 与 MendelSel 相同的 37 语言清单
  locales: [
    'en', 'zh', 'hi', 'es', 'ar', 'fr', 'bn', 'pt', 'ru', 'ur',
    'id', 'sw', 'de', 'ja', 'tr', 'vi', 'ko', 'ta', 'it', 'fa',
    'ha', 'fil', 'ms', 'th', 'pl', 'uk', 'uz', 'nl', 'ro', 'el',
    'kk', 'sv', 'ug', 'cs', 'bg', 'tib', 'mn',
  ],

  // CucurbitAgent 面向国际研究者：默认英文，无前缀（现有 URL 全部保持不变）
  defaultLocale: 'en',

  // 默认语言不加前缀；其他语言 /zh /ru …
  localePrefix: 'as-needed',
});

// 全站内部导航统一从这里 import Link/useRouter/usePathname（自动带语言前缀）
export const { Link, redirect, usePathname, useRouter } =
  createNavigation(routing);
