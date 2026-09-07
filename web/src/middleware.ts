import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import createIntlMiddleware from 'next-intl/middleware';
import { routing } from './i18n/routing';

/**
 * 三件事：
 * 1. 堆叠路径修复（原 CucurbitAgent middleware）：
 *    Host:port segments in the path (e.g. /8.1.2.3:3000/genes) happen when a
 *    scheme-less "8.1.2.3:3000/..." string is resolved as a relative URL.
 *    Fix at the edge with a 308 so the App Router never hydrates a stacked URL.
 * 2. 静态文件（路径以扩展名结尾，如 /icon.png /robots.txt）直接放行，
 *    不进 intl 路由。注意：不能在 matcher 里用 `.*\\..*` 排除带点路径——
 *    那会把 IP 形式的堆叠路径也排除掉（点号），所以放这里判断。
 * 3. next-intl locale 路由（/zh /ru 前缀，默认 en 无前缀）。
 */
const HOST_SEG = /^(?:\d{1,3}(?:\.\d{1,3}){3}|localhost)(?::\d+)?$/i;

const intlMiddleware = createIntlMiddleware(routing);

export function middleware(request: NextRequest) {
  const parts = request.nextUrl.pathname.split('/').filter(Boolean);

  // 1. stacked host:port path → 308 to the clean path
  if (parts.some((p) => HOST_SEG.test(p))) {
    while (parts.length && HOST_SEG.test(parts[0])) {
      parts.shift();
    }
    const url = request.nextUrl.clone();
    url.pathname = parts.length ? `/${parts.join('/')}` : '/';
    return NextResponse.redirect(url, 308);
  }

  // 2. file-like path (ends with an extension) → skip locale routing
  if (/\.[^/]+$/.test(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  // 3. locale routing
  return intlMiddleware(request);
}

export const config = {
  // Skip Next internals, static asset dirs, and the API proxy
  matcher: ['/((?!api|_next/static|_next/image|vendor/|assets/|favicon\\.ico).*)'],
};
