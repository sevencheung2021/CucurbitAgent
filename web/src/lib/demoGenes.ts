/**
 * Curated demo genes shared by Genes / Expression / Protein landings.
 * Keep in sync: each entry should resolve with useful content on Genes
 * (GO + Pfam + variants when indexed); Expression / Protein use the same IDs.
 */
export type DemoGene = {
  species: string;
  geneId: string;
  /** Short label shown after the ID, e.g. "C. pepo" */
  label: string;
};

export const DEMO_GENES: DemoGene[] = [
  { species: 'Cucumber', geneId: 'CsaV3_1G000080', label: 'Cucumber' },
  { species: 'Melon', geneId: 'MELO3C008442', label: 'Melon' },
  { species: 'Watermelon', geneId: 'Cla97C03G062540', label: 'Watermelon' },
  { species: 'Pumpkin (C. pepo)', geneId: 'Cp4.1LG09g07700', label: 'C. pepo' },
  { species: 'Pumpkin (C. moschata)', geneId: 'RifuC08G006150', label: 'C. moschata' },
];
