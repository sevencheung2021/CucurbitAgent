#!/usr/bin/env python3
"""Batch-run Pfam HMM search for all 9 cucurbit species.

Reuses the Cucumber Pfam-A.hmm database (already hmmpressed) and the same
pipeline as ``Cucumber/Cucumber_v3/get_v3_pep_domain.py``:

    1. zcat pep.fa.gz -> temp pep.fa
    2. hmmsearch --domtblout raw.txt Pfam-A.hmm pep.fa
    3. parse domtblout -> <Species>_Domains.tsv  (E-value <= 1e-5)

Output schema (identical to Cucumber_V3_Domains.tsv so the backend can read it
with the same parser):

    Gene_ID  Domain_Name  Pfam_ID  Start  End  E_value  Description

Usage:
    python3 scripts/run_pfam_all_species.py            # all species
    python3 scripts/run_pfam_all_species.py Watermelon  # subset by name
    python3 scripts/run_pfam_all_species.py --jobs 4    # limit parallelism
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# ==========================================
# Configuration
# ==========================================
_PLATFORM = Path(__file__).resolve().parents[1]
_SCI = Path(os.getenv("CUAGENT_DATA_ROOT", str(_PLATFORM / "data" / "science")))
GENOMES_ROOT = Path(os.getenv("CUAGENT_GENOMES_ROOT", str(_SCI / "genes")))
PFAM_HMM = GENOMES_ROOT / "Cucumber" / "Cucumber_v3" / "Pfam-A.hmm"
PFAM_H3F = GENOMES_ROOT / "Cucumber" / "Cucumber_v3" / "Pfam-A.hmm.h3f"

# Threshold: domain-level E-value must be <= this to be kept.
EVALUE_THRESHOLD = 1e-5


@dataclass
class SpeciesJob:
    key: str            # short identifier used in filenames / logs
    display: str        # master-DB display name (matches config.py keys)
    pep_gz: Path        # input protein FASTA (gzipped)
    out_tsv: Path       # output <Key>_Domains.tsv
    out_raw: Path       # intermediate hmmsearch domtblout


# Per-species definition. ``pep_gz`` paths verified earlier in the conversation.
SPECIES: list[SpeciesJob] = [
    SpeciesJob(
        key="Watermelon_V2.5",
        display="Watermelon",
        pep_gz=GENOMES_ROOT / "Watermelon" / "Watermelon_v2.5" / "97103_pep_v2.5.fa.gz",
        out_tsv=GENOMES_ROOT / "Watermelon" / "Watermelon_v2.5" / "Watermelon_V2.5_Domains.tsv",
        out_raw=GENOMES_ROOT / "Watermelon" / "Watermelon_v2.5" / "Watermelon_V2.5_Pfam_Raw.txt",
    ),
    SpeciesJob(
        key="Melon_V4",
        display="Melon",
        pep_gz=GENOMES_ROOT / "Melon" / "Melon_v4.0" / "DHL92_pep_v4.fa.gz",
        out_tsv=GENOMES_ROOT / "Melon" / "Melon_v4.0" / "Melon_V4_Domains.tsv",
        out_raw=GENOMES_ROOT / "Melon" / "Melon_v4.0" / "Melon_V4_Pfam_Raw.txt",
    ),
    SpeciesJob(
        key="Pumpkin_Moschata_V1",
        display="Pumpkin (C. moschata)",
        pep_gz=GENOMES_ROOT / "Pumpkin_Squash" / "Cucurbita_moschata" / "v1" / "Cmoschata_pep_v1.fa.gz",
        out_tsv=GENOMES_ROOT / "Pumpkin_Squash" / "Cucurbita_moschata" / "v1" / "Cmoschata_V1_Domains.tsv",
        out_raw=GENOMES_ROOT / "Pumpkin_Squash" / "Cucurbita_moschata" / "v1" / "Cmoschata_V1_Pfam_Raw.txt",
    ),
    SpeciesJob(
        key="Pumpkin_Pepo_V4.1",
        display="Pumpkin (C. pepo)",
        pep_gz=GENOMES_ROOT / "Pumpkin_Squash" / "Cucurbita_pepo" / "MU-CU-16" / "Cpepo_pep_v4.1.fa.gz",
        out_tsv=GENOMES_ROOT / "Pumpkin_Squash" / "Cucurbita_pepo" / "MU-CU-16" / "Cpepo_V4.1_Domains.tsv",
        out_raw=GENOMES_ROOT / "Pumpkin_Squash" / "Cucurbita_pepo" / "MU-CU-16" / "Cpepo_V4.1_Pfam_Raw.txt",
    ),
    SpeciesJob(
        key="BitterGourd_V2",
        display="BitterGourd",
        pep_gz=GENOMES_ROOT / "BitterGourd" / "OHB3-1" / "OHB3-1_pep_v2.fa.gz",
        out_tsv=GENOMES_ROOT / "BitterGourd" / "OHB3-1" / "BitterGourd_V2_Domains.tsv",
        out_raw=GENOMES_ROOT / "BitterGourd" / "OHB3-1" / "BitterGourd_V2_Pfam_Raw.txt",
    ),
    SpeciesJob(
        key="BottleGourd_V1",
        display="BottleGourd",
        pep_gz=GENOMES_ROOT / "BottleGourd" / "USVL1VR-Ls" / "USVL1VR-Ls_pep_v1.fa.gz",
        out_tsv=GENOMES_ROOT / "BottleGourd" / "USVL1VR-Ls" / "BottleGourd_V1_Domains.tsv",
        out_raw=GENOMES_ROOT / "BottleGourd" / "USVL1VR-Ls" / "BottleGourd_V1_Pfam_Raw.txt",
    ),
    SpeciesJob(
        key="WaxGourd",
        display="WaxGourd",
        pep_gz=GENOMES_ROOT / "WaxGourd" / "WG_pep.fa.gz",
        out_tsv=GENOMES_ROOT / "WaxGourd" / "WG_Domains.tsv",
        out_raw=GENOMES_ROOT / "WaxGourd" / "WG_Pfam_Raw.txt",
    ),
    SpeciesJob(
        key="SpongeGourd",
        display="SpongeGourd",
        pep_gz=GENOMES_ROOT / "SpongeGourd" / "L_cylindrica" / "L_cylindrica_pep.fa.gz",
        out_tsv=GENOMES_ROOT / "SpongeGourd" / "L_cylindrica" / "SpongeGourd_Domains.tsv",
        out_raw=GENOMES_ROOT / "SpongeGourd" / "L_cylindrica" / "SpongeGourd_Pfam_Raw.txt",
    ),
]


def run_cmd(cmd: str) -> None:
    subprocess.run(cmd, shell=True, check=True)


def run_one_species(job: SpeciesJob, threads: int) -> tuple[str, str, int]:
    """Run Pfam for a single species. Returns (key, status_message, n_rows)."""
    key = job.key
    if not job.pep_gz.exists():
        return (key, f"MISSING pep file: {job.pep_gz}", 0)

    # Skip entirely if final TSV already exists (idempotent reruns).
    if job.out_tsv.exists():
        n = sum(1 for _ in open(job.out_tsv)) - 1
        return (key, f"SKIP (tsv exists, {n} rows)", max(n, 0))

    work_dir = job.pep_gz.parent
    temp_pep = work_dir / f"temp_{key}_pep.fa"

    try:
        # 1. Decompress protein FASTA.
        if not temp_pep.exists():
            run_cmd(f"zcat {job.pep_gz} > {temp_pep}")

        # 2. Run hmmsearch (only if raw output missing).
        if not job.out_raw.exists():
            cmd = (
                f"hmmsearch --cpu {threads} --domtblout {job.out_raw} "
                f"--noali {PFAM_HMM} {temp_pep} > /dev/null"
            )
            run_cmd(cmd)

        # 3. Parse domtblout -> TSV.
        n_rows = parse_domtblout(job.out_raw, job.out_tsv)

        # 4. Cleanup temp pep (large file).
        if temp_pep.exists():
            os.remove(temp_pep)

        return (key, f"DONE ({n_rows} domains)", n_rows)
    except subprocess.CalledProcessError as e:
        return (key, f"FAIL cmd={e.cmd} rc={e.returncode}", 0)
    except Exception as e:
        return (key, f"FAIL {type(e).__name__}: {e}", 0)


def parse_domtblout(raw_path: Path, out_path: Path) -> int:
    """Parse hmmsearch --domtblout into a UI-friendly TSV.

    Fields (1-indexed, hmmsearch domtblout format):
        1  target name      (gene / transcript id)
        3  query name       (Pfam short name, e.g. 03009_C)
        4  accession        (PFxxxxx.version)
       13  independent E-value (domain-level)
       20  env-from
       21  env-to
      23+ description of target (free text, may be empty)
    """
    parsed: list[str] = []
    with open(raw_path, "r") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 22:
                continue

            # Strip transcript suffix (CsaV3_1G000010.1 -> CsaV3_1G000010)
            gene_base = parts[0].rsplit(".", 1)[0]
            pfam_name = parts[3]
            pfam_acc = parts[4].split(".")[0]  # PFxxxxx.version -> PFxxxxx
            try:
                e_value = float(parts[12])
            except ValueError:
                continue

            start = parts[19]
            end = parts[20]
            description = " ".join(parts[22:]) if len(parts) > 22 else "-"

            if e_value <= EVALUE_THRESHOLD:
                parsed.append(
                    f"{gene_base}\t{pfam_name}\t{pfam_acc}\t{start}\t{end}\t{e_value}\t{description}"
                )

    with open(out_path, "w", encoding="utf-8") as out:
        out.write("Gene_ID\tDomain_Name\tPfam_ID\tStart\tEnd\tE_value\tDescription\n")
        out.write("\n".join(parsed))
        if parsed:
            out.write("\n")
    return len(parsed)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "species",
        nargs="*",
        help="Optional species display names to run (default: all). "
             "e.g. 'Watermelon' 'Melon'",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=len(SPECIES),
        help="Max number of species to run in parallel (default: all).",
    )
    ap.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Threads per hmmsearch invocation (default: 4).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if output TSV already exists.",
    )
    args = ap.parse_args()

    # Pre-flight checks.
    if not PFAM_HMM.exists():
        print(f"ERROR: Pfam HMM database not found at {PFAM_HMM}", file=sys.stderr)
        return 1
    if not PFAM_H3F.exists():
        print(f"ERROR: Pfam HMM not hmmpressed (.h3f missing). Run: hmmpress {PFAM_HMM}", file=sys.stderr)
        return 1

    # Filter species.
    if args.species:
        wanted = {s.lower() for s in args.species}
        jobs = [j for j in SPECIES if j.display.lower() in wanted or j.key.lower() in wanted]
        if not jobs:
            print(f"No species matched: {args.species}", file=sys.stderr)
            print(f"Available: {[j.display for j in SPECIES]}", file=sys.stderr)
            return 1
    else:
        jobs = list(SPECIES)

    # Handle --force: delete existing TSVs so they get re-run.
    if args.force:
        for j in jobs:
            for p in (j.out_tsv, j.out_raw):
                if p.exists():
                    p.unlink()

    print(f"=== Pfam batch run ===")
    print(f"  Species:    {[j.display for j in jobs]}")
    print(f"  Parallel:   {min(args.jobs, len(jobs))} at a time")
    print(f"  Threads each: {args.threads}")
    print(f"  E-value cutoff: {EVALUE_THRESHOLD}")
    print()

    n_ok, n_fail = 0, 0
    with ProcessPoolExecutor(max_workers=min(args.jobs, len(jobs))) as ex:
        futures = {ex.submit(run_one_species, j, args.threads): j for j in jobs}
        for fut in as_completed(futures):
            key, msg, n_rows = fut.result()
            tag = "OK  " if msg.startswith(("DONE", "SKIP")) else "FAIL"
            print(f"  [{tag}] {key:25} {msg}")
            if tag == "OK  ":
                n_ok += 1
            else:
                n_fail += 1

    print()
    print(f"=== Summary: {n_ok} ok, {n_fail} fail ===")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
