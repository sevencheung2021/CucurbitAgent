import { notFound } from 'next/navigation';

/** Catch-all：未匹配的路径在 [locale] 内触发本地化的 404 页。 */
export default function CatchAllPage() {
  notFound();
}
