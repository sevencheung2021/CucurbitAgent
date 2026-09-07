#!/usr/bin/env python3
"""Re-export all_sites_json from all_sites TXT with a new score threshold.

Existing website JSON was generated with score > 0.6. Lowering the API filter
alone does not change the UI, because residue annotations are already baked
into the JSON files. Re-run this script after changing SCORE_THRESHOLD.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURES = ROOT / "data" / "science" / "structures"

SITE_DIRS = [
    "cucu_v3_pdb_site",
    "melon_pdb_site",
    "pumpkin_moschata_pdb_site",
    "pumpkin_pepo_pdb_site",
    "bittergourd_pdb_site",
    "bottlegourd_pdb_site",
    "waxgourd_pdb_site",
    "spongegourd_pdb_site",
]

SKIP_TYPES = {"HEM"}
DEFAULT_THRESHOLD = 0.5


def txt_to_json(txt_path: Path, threshold: float) -> dict[str, str]:
    processed: dict[str, str] = {}
    try:
        lines = txt_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return processed
    if not lines:
        return processed
    header = lines[0].strip().split()
    for line in lines[1:]:
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        res_no = parts[0]
        active: list[str] = []
        for i in range(2, min(len(header), len(parts))):
            try:
                score = float(parts[i])
            except ValueError:
                continue
            if score <= threshold:
                continue
            c_name = header[i].replace("_binding", "").replace("_Binding", "")
            if c_name.upper() in SKIP_TYPES:
                continue
            active.append(f"{c_name}: {score:.2f}")
        if active:
            processed[res_no] = " | ".join(active)
    return processed


def reprocess_dir(site_dir: Path, threshold: float) -> int:
    txt_dir = site_dir / "all_sites"
    out_dir = site_dir / "all_sites_json"
    if not txt_dir.is_dir():
        print(f"skip (no all_sites): {site_dir.name}")
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for txt_path in txt_dir.glob("*.txt"):
        data = txt_to_json(txt_path, threshold)
        (out_dir / f"{txt_path.stem}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        n += 1
        if n % 5000 == 0:
            print(f"  {site_dir.name}: {n}...")
    print(f"✓ {site_dir.name}: {n} JSON files (threshold > {threshold}, skip {sorted(SKIP_TYPES)})")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--only", nargs="*", help="Optional subset of site dir names")
    args = ap.parse_args()
    dirs = args.only or SITE_DIRS
    total = 0
    for name in dirs:
        total += reprocess_dir(STRUCTURES / name, args.threshold)
    print(f"Done. Total {total} files.")


if __name__ == "__main__":
    main()
