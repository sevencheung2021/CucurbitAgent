/**
 * Shared species lists — single source of truth for genes / expression /
 * proteins pages. Backend uses the same English display names as dict keys,
 * so keep the spelling byte-identical when editing.
 */

/** All species the gene/expression databases cover. */
export const SPECIES: string[] = [
  'Cucumber', 'Watermelon', 'Melon',
  'Pumpkin (C. moschata)', 'Pumpkin (C. pepo)',
  'BitterGourd', 'BottleGourd', 'WaxGourd', 'SpongeGourd',
];

/** Species with a curated SNP / InDel variant index (Natural Variants tab). */
export const VARIANT_SPECIES = new Set<string>([
  'Cucumber',
  'Watermelon',
  'Melon',
  'Pumpkin (C. pepo)',
  'Pumpkin (C. moschata)',
]);

/**
 * Read `?gene=` / `?gene_id=` (+ optional `?species=`) from the current URL.
 * Used by genes / expression / proteins pages so ChatPanel "Open in …"
 * deep links land on an executed search instead of the landing page.
 *
 * Mount-time only — the pages that link here are on other routes, so the
 * target page always mounts fresh.
 */
export function readGeneDeepLink(): { geneId: string; species: string } {
  if (typeof window === 'undefined') return { geneId: '', species: '' };
  const params = new URLSearchParams(window.location.search);
  const geneId = (params.get('gene') || params.get('gene_id') || '').trim();
  const species = (params.get('species') || '').trim();
  return { geneId, species };
}
