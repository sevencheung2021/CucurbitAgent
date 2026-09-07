"""Co-expression analysis for cucurbit genes (Pearson correlation on gene × sample matrix).

Wraps coexp.py logic into an importable service. Returns top N co-expressed genes
with correlation coefficient and functional description.

Reliability tiers (from your spec):
  ★★★ >=200 samples: reliable
  ★★  100-199: reasonable
  ★   50-99: weak reference only
  ○   <50: unreliable — caller should warn
"""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.config import settings
from app.services.expression_query import (
    SPECIES_META,
    SAMPLE_RELIABILITY_TIERS,
    resolve_species_dir,
    _reliability_tier,
)


# Per-species gene description files (relative to settings.data_root / genes).
# Used to attach functional annotations to co-expressed gene hits.
def _desc_files() -> dict[str, str]:
    g = settings.data_root / "genes"
    return {
        "cucumber_v3": str(g / "Cucumber" / "Cucumber_v3" / "ChineseLong_gene_description_v3.txt.gz"),
        "melon_v4": str(g / "Melon" / "Melon_v4.0" / "DHL92_gene_description_v4.txt.gz"),
        "watermelon_v2.5": str(g / "Watermelon" / "Watermelon_v2.5" / "97103_AHRD_v2.5.txt.gz"),
        "cmoschata_v2": str(
            g / "Pumpkin_Squash" / "Cucurbita_moschata" / "v2" / "Cmoschata_Rifu_v2.gff3.gz"
        ),
        "cpepo_v4": str(
            g / "Pumpkin_Squash" / "Cucurbita_pepo" / "MU-CU-16" / "Cpepo_gene_description_v4.1.txt.gz"
        ),
        "bittergourd_v2": str(g / "BitterGourd" / "OHB3-1" / "OHB3-1_gene_description_v2.txt.gz"),
        "bottlebottle_v1": str(
            g / "BottleGourd" / "USVL1VR-Ls" / "USVL1VR-Ls_gene_description_v1.txt.gz"
        ),
        "spongegourd": str(
            g / "SpongeGourd" / "L_cylindrica" / "L_cylindrica_gene_description.txt.gz"
        ),
        "waxgourd_v1": str(g / "WaxGourd" / "WG_gene_description.txt.gz"),
    }


DESC_FILES: dict[str, str] = _desc_files()


def _expression_base() -> Path:
    return settings.expression_dir


def _matrix_path(sp_dir: str) -> Path:
    return _expression_base() / sp_dir / "parsed" / "gene_x_sample.parquet"


def _matrix_available(sp_dir: str) -> bool:
    return _matrix_path(sp_dir).exists()


def _load_desc_map(sp_dir: str, candidate_gene_ids: list[str]) -> dict[str, str]:
    """Load functional description only for candidate genes (saves memory)."""
    path = DESC_FILES.get(sp_dir)
    if not path or not Path(path).exists():
        return {}
    desc_map: dict[str, str] = {}
    cand = set(candidate_gene_ids)
    try:
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    g = parts[0].split(".")[0]
                    if g in cand:
                        desc_map[g] = parts[1][:60]
    except Exception:
        pass
    return desc_map


def find_coexpressed_genes(
    gene_id: str,
    ui_species: str = "",
    top_k: int = 20,
    min_corr: float = 0.5,
) -> dict[str, Any]:
    """Find top-N Pearson-correlated genes for a query gene.

    Returns dict with status, reliability tier, optional warning for low-sample
    species, and the ranked co-expression list.

    Per your spec decision: low-sample species (<50 samples) are ALLOWED but a
    strong warning is attached so users know results may be noise.
    """
    gid = (gene_id or "").strip()
    if not gid:
        return {"status": "invalid", "message": "gene_id is required"}

    # Clamp parameters
    top_k = max(1, min(int(top_k or 20), 200))
    min_corr = max(0.0, min(float(min_corr or 0.0), 1.0))

    sp_dir = resolve_species_dir(gid, ui_species)
    if not sp_dir:
        return {
            "status": "unknown_species",
            "message": f"Cannot recognize species from gene ID '{gid}'",
        }

    matrix_path = _matrix_path(sp_dir)
    if not matrix_path.exists():
        return {
            "status": "no_data",
            "message": f"gene_x_sample.parquet missing for {sp_dir}",
            "species_dir": sp_dir,
        }

    try:
        df = pd.read_parquet(matrix_path).set_index("gene_id")
    except Exception as exc:
        return {"status": "error", "message": f"parquet read failed: {exc}"}

    n_samples = df.shape[1]
    stars, tier_desc = _reliability_tier(n_samples)

    # Build warning for low-reliability species
    warning: Optional[str] = None
    if n_samples < 50:
        warning = (
            f"⚠️ {SPECIES_META[sp_dir]['label']} has only {n_samples} samples. "
            "Co-expression results are likely dominated by noise and should be "
            "interpreted as weak hints only. Consider validating top hits via "
            "functional annotation or orthology."
        )
    elif n_samples < 100:
        warning = (
            f"⚠️ {SPECIES_META[sp_dir]['label']} has {n_samples} samples. "
            "Co-expression is usable for strongly related genes but may miss "
            "weaker associations."
        )

    if gid not in df.index:
        # Version bridge first (CmoCh…/older IDs → canonical matrix ID);
        # fall back to similar-ID suggestions when no mapping exists.
        from app.services.expression_query import bridge_gene_version
        bridged = bridge_gene_version(gid, sp_dir)
        if bridged and bridged in df.index:
            gid = bridged
        else:
            cands = [g for g in df.index if gid.upper() in str(g).upper()][:10]
            return {
                "status": "not_found",
                "gene_id": gid,
                "species_dir": sp_dir,
                "message": f"Gene '{gid}' not in co-expression matrix",
                "suggestions": cands,
            }

    target = df.loc[gid].values.astype(np.float32)

    # Vectorized Pearson correlation across all genes
    x = df.values.astype(np.float32)
    t_centered = target - target.mean()
    t_norm = np.sqrt((t_centered ** 2).sum()) + 1e-9
    x_mean = x.mean(axis=1, keepdims=True)
    x_centered = x - x_mean
    x_norm = np.sqrt((x_centered ** 2).sum(axis=1)) + 1e-9
    corrs = (x_centered @ t_centered) / (x_norm * t_norm)

    res = pd.DataFrame({"gene_id": df.index, "pearson_r": corrs.round(4)})
    res = res[res["gene_id"] != gid]
    res["abs_r"] = res["pearson_r"].abs()
    res = res[res["abs_r"] >= min_corr]
    res = res.sort_values("abs_r", ascending=False).head(top_k).reset_index(drop=True)

    if res.empty:
        return {
            "status": "no_results",
            "gene_id": gid,
            "species_dir": sp_dir,
            "species_label": SPECIES_META[sp_dir]["label"],
            "n_samples": n_samples,
            "reliability": stars,
            "warning": warning,
            "min_corr": min_corr,
            "message": f"No genes with |r| >= {min_corr} (try lowering --min_corr)",
            "coexpressed": [],
        }

    # Attach descriptions only for the returned top-K
    desc_map = _load_desc_map(sp_dir, res["gene_id"].tolist())

    coexp_list: list[dict[str, Any]] = []
    for _, r in res.iterrows():
        gid_hit = str(r["gene_id"])
        coexp_list.append({
            "gene_id": gid_hit,
            "pearson_r": float(r["pearson_r"]),
            "abs_r": float(r["abs_r"]),
            "description": desc_map.get(gid_hit, ""),
        })

    return {
        "status": "success",
        "gene_id": gid,
        "species_dir": sp_dir,
        "species_label": SPECIES_META[sp_dir]["label"],
        "species_common": SPECIES_META[sp_dir]["common"],
        "n_samples": n_samples,
        "reliability": stars,
        "reliability_desc": tier_desc,
        "warning": warning,
        "min_corr": min_corr,
        "top_k": top_k,
        "count": len(coexp_list),
        "coexpressed": coexp_list,
    }


def agent_tool_search_coexpression(
    gene_id: str,
    species: str = "",
    top_k: int = 20,
    min_corr: float = 0.5,
) -> str:
    """Adapter for the Agent tool `search_coexpression`. Returns JSON string."""
    result = find_coexpressed_genes(gene_id, ui_species=species, top_k=top_k, min_corr=min_corr)
    return json.dumps(result, ensure_ascii=False)
