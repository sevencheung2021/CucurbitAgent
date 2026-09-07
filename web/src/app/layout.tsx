import type { ReactNode } from 'react';

type Props = { children: ReactNode };

// Root layout — 最小透传（html/body 由 [locale]/layout.tsx 渲染，
// 这样 <html lang dir> 才能跟随当前语言）。与 MendelSel 相同结构。
export default function RootLayout({ children }: Props) {
  return children;
}
