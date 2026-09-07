# Science data layout

The CucurbitAgent knowledge base lives under one root directory
(`CUAGENT_DATA_ROOT`, default `data/science/` — excluded from git because the
full build is ~100 GB). The platform resolves every module database relative
to this root, so you can rebuild as much or as little as you need.

```
science/
├── genes/
│   ├── Database_Outputs/          per-species master tables + variant TSVs
│   │                              (gene models, CDS/protein sequences, Pfam,
│   │                              GO, cross-version ID maps, orthologs)
│   └── ...                        per-species raw/intermediate files
├── expression/                    per-species FPKM matrices + gene_stats
├── structures/                    ESMFold PDB files per species
│                                  (pLDDT in the B-factor field)
├── literature/
│   ├── Cucurbit_Papers_v4.db      papers + abstracts + chunks (SQLite)
│   └── chroma_cucurbit_db_v4/     bge-m3 vector index (ChromaDB)
└── downloads/                     per-gene downloadable bundles
```

## What is included in this repository

- `cucurbench/cucubench_prompts_v23.json` — the 50-item CucurbitBench set
  (eight capability axes, nine cucurbit species, locked 2026-08-25).
- `examples/Arabidopsis_to_Cucumber_V3.tsv` — a small cross-species ortholog table
  illustrating the gene-table format.

## Public sources of each layer

| Layer | Source |
|---|---|
| Genome assemblies & annotations | CuGenDB, NCBI, Phytozome, species consortium releases (see the manuscript's Methods for the full citation list per assembly) |
| Natural variants | whole-genome resequencing and GBS accessions cited per species in the manuscript |
| Protein structures | ESMFold predictions computed by us (Lin et al., 2023) |
| Binding sites | GPSite predictions computed by us (Yuan et al., 2024) |
| RNA-seq expression | public SRA runs re-quantified to FPKM |
| Literature corpus | PubMed, filtered by the pipeline described in the manuscript |

Rebuild helpers included under `../scripts/`: `fetch_pubmed_range.py`
(corpus ingestion), `run_pfam_all_species.py` (domain annotation),
`reprocess_gpsite_json.py` (binding-site post-processing).

Snapshots of the exact data used in the manuscript are archived by version
and will be linked here upon publication.
