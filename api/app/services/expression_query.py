"""Expression profile query for cucurbit genes (9 species, unified schema).

Wraps the per-species parsed parquet files produced by
High_confidence_structure/cucurbit_expression/parse_all_multi.py into a
single service that auto-detects species from gene ID prefix.

Returned dicts are designed for both:
  - the Agent tool (search_gene_expression)
  - the REST endpoint (GET /api/expression/gene)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.config import settings


# Directory mapping: species dir name -> (UI label, common name)
SPECIES_META: dict[str, dict[str, str]] = {
    "cucumber_v3":     {"label": "Cucumber (Chinese Long) v3",   "common": "Cucumber"},
    "melon_v4":        {"label": "Melon (DHL92) v4",             "common": "Melon"},
    "watermelon_v2.5": {"label": "Watermelon (97103) v2.5",      "common": "Watermelon"},
    "cmoschata_v2":    {"label": "C. moschata (Rifu) v2",        "common": "Pumpkin (C. moschata)"},
    "cpepo_v4":        {"label": "C. pepo (MU-CU-16) v4.1",      "common": "Pumpkin (C. pepo)"},
    "bittergourd_v2":  {"label": "Bitter gourd (OHB3-1) v2",    "common": "BitterGourd"},
    "bottlebottle_v1": {"label": "Bottle gourd (USVL1VR-Ls) v1","common": "BottleGourd"},
    "spongegourd":     {"label": "Sponge gourd (cylindrica) v1","common": "SpongeGourd"},
    "waxgourd_v1":     {"label": "Wax gourd (B227) v1",         "common": "WaxGourd"},
}

# gene ID prefix -> species dir (order matters: longer prefixes first)
ID_PREFIX_TO_SPECIES: list[tuple[str, str]] = [
    ("CsaV3",  "cucumber_v3"),
    ("MELO3C", "melon_v4"),
    ("Cla97",  "watermelon_v2.5"),
    ("RifuC",  "cmoschata_v2"),
    ("CmoCh",  "cmoschata_v2"),
    ("Cp4.1",  "cpepo_v4"),
    ("Moc",    "bittergourd_v2"),
    ("Lsi",    "bottlebottle_v1"),
    ("Spg",    "spongegourd"),
    ("Bhi",    "waxgourd_v1"),
]

# UI common name -> species dir (for explicit species selection from front-end dropdown)
UI_TO_SPECIES_DIR: dict[str, str] = {
    meta["common"]: sp_dir for sp_dir, meta in SPECIES_META.items()
}

# Reliability tiers based on sample count (from your spec)
# >=200 ★★★ / 100-199 ★★ / 50-99 ★ / <50 ○
SAMPLE_RELIABILITY_TIERS = [
    (200, "★★★", "reliable for both tissue profile and co-expression"),
    (100, "★★",  "tissue profile reliable; co-expression reasonable"),
    (50,  "★",   "tissue profile reliable; co-expression only as weak reference"),
    (0,   "○",   "sample count too low; only tissue profile meaningful, co-expression unreliable"),
]

# Per-species known statistics (from your data summary table)
# Used for the overview endpoint so we don't need to scan parquet headers each time.
SPECIES_STATS_CACHE: dict[str, dict[str, Any]] = {
    "cucumber_v3":     {"genes": 24267,  "samples": 523, "projects": 88, "tissues": 20, "rows": 12691641},
    "melon_v4":        {"genes": 28299,  "samples": 362, "projects": 40, "tissues": 18, "rows": 10244238},
    "watermelon_v2.5": {"genes": 21917,  "samples": 297, "projects": 47, "tissues": 15, "rows": 6509349},
    "cmoschata_v2":    {"genes": 26498,  "samples": 62,  "projects": 15, "tissues": 8,  "rows": 1642876},
    "cpepo_v4":        {"genes": 27868,  "samples": 94,  "projects": 11, "tissues": 9,  "rows": 2619592},
    "bittergourd_v2":  {"genes": 41016,  "samples": 30,  "projects": 4,  "tissues": 7,  "rows": 1230480},
    "bottlebottle_v1": {"genes": 22234,  "samples": 40,  "projects": 5,  "tissues": 6,  "rows": 889360},
    "spongegourd":     {"genes": 31661,  "samples": 21,  "projects": 8,  "tissues": 9,  "rows": 664881},
    "waxgourd_v1":     {"genes": 27467,  "samples": 28,  "projects": 4,  "tissues": 3,  "rows": 769076},
}


def _expression_base() -> Path:
    return settings.expression_dir


def auto_detect_species_dir(gene_id: str) -> Optional[str]:
    """Detect species dir from gene ID prefix. Returns None if unrecognized."""
    gid = gene_id.strip()
    for prefix, sp_dir in ID_PREFIX_TO_SPECIES:
        if gid.startswith(prefix):
            return sp_dir
    return None


# 表达库 → (UI 物种名, 表达矩阵所用当前版 ID 前缀)。有映射表的物种才做桥接。
_DIR_TO_MAP_TABLE = {
    "cucumber_v3": ("Cucumber", "CsaV3_"),
    "cmoschata_v2": ("Pumpkin (C. moschata)", "RifuC"),
    "watermelon_v2.5": ("Watermelon", "Cla97"),
    "melon_v4": ("Melon", "MELO3C"),
}


def bridge_gene_version(gene_id: str, sp_dir: str) -> Optional[str]:
    """Map an older gene ID to the expression-canonical ID via the species
    version-mapping table (e.g. moschata CmoCh20G011670 → RifuC20G011080).
    Returns None when no bridge is needed/possible."""
    entry = _DIR_TO_MAP_TABLE.get(sp_dir)
    if not entry:
        return None
    ui_species, canonical_prefix = entry
    from app.config import settings
    map_path = (settings.global_map_config or {}).get(ui_species)
    if not map_path or not os.path.exists(map_path):
        return None
    try:
        df_m = pd.read_csv(map_path, sep="\t", dtype=str)
    except Exception:
        return None
    mask = df_m.astype(str).apply(lambda c: c.str.lower() == gene_id.lower())
    if not mask.any().any():
        return None
    row = df_m[mask.any(axis=1)].iloc[0]
    meta_keys = ("mapping", "pep_seq", "sequence", "e_value", "bit", "coord", "confidence", "identity", "coverage", "method")
    cands = [str(v).strip() for v in row.values if str(v).strip()]
    for c in cands:
        if c.lower() == gene_id.lower():
            continue
        if c.lower().startswith(meta_keys):
            continue
        if c.lower().startswith(canonical_prefix.lower()):
            return c
    return None


def resolve_species_dir(gene_id: str, ui_species: str = "") -> Optional[str]:
    """Resolve species dir, preferring explicit UI selection over auto-detect."""
    if ui_species and ui_species in UI_TO_SPECIES_DIR:
        return UI_TO_SPECIES_DIR[ui_species]
    return auto_detect_species_dir(gene_id)


def _reliability_tier(n_samples: int) -> tuple[str, str]:
    """Return (stars, description) for a sample count."""
    for threshold, stars, desc in SAMPLE_RELIABILITY_TIERS:
        if n_samples >= threshold:
            return stars, desc
    return ("○", "no data")


def _tidy_path(sp_dir: str) -> Path:
    return _expression_base() / sp_dir / "parsed" / "expression_tidy.parquet"


def _gene_stats_path(sp_dir: str) -> Path:
    return _expression_base() / sp_dir / "parsed" / "gene_stats.tsv"


def _tissue_matrix_path(sp_dir: str) -> Path:
    return _expression_base() / sp_dir / "parsed" / "tissue_mean_matrix.tsv"


def _data_available(sp_dir: str) -> bool:
    return _tidy_path(sp_dir).exists()


def overview() -> dict[str, Any]:
    """Return the 9-species overview (for the Expression landing page table)."""
    species_rows: list[dict[str, Any]] = []
    total_genes = total_samples = total_projects = total_rows = 0
    for sp_dir, meta in SPECIES_META.items():
        stats = SPECIES_STATS_CACHE.get(sp_dir, {})
        n_samples = stats.get("samples", 0)
        stars, _ = _reliability_tier(n_samples)
        row = {
            "species_dir": sp_dir,
            "label": meta["label"],
            "common": meta["common"],
            "genes": stats.get("genes", 0),
            "samples": n_samples,
            "projects": stats.get("projects", 0),
            "tissues": stats.get("tissues", 0),
            "rows": stats.get("rows", 0),
            "reliability": stars,
            "data_available": _data_available(sp_dir),
        }
        species_rows.append(row)
        total_genes += row["genes"]
        total_samples += row["samples"]
        total_projects += row["projects"]
        total_rows += row["rows"]

    return {
        "status": "success",
        "total": {
            "species": len(species_rows),
            "genes": total_genes,
            "samples": total_samples,
            "projects": total_projects,
            "rows": total_rows,
        },
        "species": species_rows,
    }


def query_gene_expression(
    gene_id: str,
    ui_species: str = "",
    tissue_filter: str = "",
    top_samples: int = 15,
) -> dict[str, Any]:
    """Query expression profile for one gene across all samples/tissues.

    Reads:
      - gene_stats.tsv  -> fast path for stats summary (tau, top_tissue)
      - expression_tidy.parquet (filtered to gene_id) -> per-sample + per-tissue breakdown

    Returns dict suitable for both Agent tool and REST endpoint.
    """
    gid = (gene_id or "").strip()
    if not gid:
        return {"status": "invalid", "message": "gene_id is required"}

    sp_dir = resolve_species_dir(gid, ui_species)
    if not sp_dir:
        return {
            "status": "unknown_species",
            "message": (
                f"Cannot recognize species from gene ID '{gid}'. "
                "Supported prefixes: CsaV3 / MELO3C / Cla97 / RifuC / CmoCh / "
                "Cp4.1 / Moc / Lsi / Spg / Bhi"
            ),
            "supported_species": [m["common"] for m in SPECIES_META.values()],
        }

    tidy = _tidy_path(sp_dir)
    if not tidy.exists():
        return {
            "status": "no_data",
            "message": f"Expression data not parsed yet for {sp_dir}",
            "species_dir": sp_dir,
        }

    # 0) Version bridge: older assembly IDs (CmoCh…/Csa3G…-style) are not in
    # the expression matrix — map to the canonical ID via the version table,
    # exactly like the gene master DB does.
    resolved_from = None
    try:
        probe = pd.read_parquet(tidy, columns=["gene_id"], filters=[("gene_id", "==", gid)])
    except Exception:
        probe = None
    if probe is None or len(probe) == 0:
        bridged = bridge_gene_version(gid, sp_dir)
        if bridged and bridged.lower() != gid.lower():
            resolved_from = gid
            gid = bridged

    # 1) Fast stats from gene_stats.tsv (avoid full parquet scan)
    stats_summary = _load_gene_stats(sp_dir, gid)

    # 2) Per-sample rows from parquet (pushdown filter -> ~instant)
    try:
        df = pd.read_parquet(tidy, filters=[("gene_id", "==", gid)])
    except Exception as exc:
        return {"status": "error", "message": f"parquet read failed: {exc}"}

    if len(df) == 0:
        # Try to suggest similar gene IDs
        all_genes = pd.read_parquet(tidy, columns=["gene_id"])["gene_id"].unique()
        cands = [g for g in all_genes if gid.upper() in str(g).upper()][:10]
        return {
            "status": "not_found",
            "gene_id": gid,
            "species_dir": sp_dir,
            "message": f"Gene '{gid}' not found in {SPECIES_META[sp_dir]['label']}",
            "suggestions": cands,
        }

    n_samples = len(df)
    n_projects = int(df["project"].nunique()) if "project" in df.columns else 0
    fpkm_mean = float(df["FPKM"].mean())
    fpkm_max = float(df["FPKM"].max())

    # Per-tissue aggregation
    tissue_profile: list[dict[str, Any]] = []
    if "tissue" in df.columns:
        tiss = (
            df.groupby("tissue")["FPKM"]
            .agg(["mean", "max", "count"])
            .round(2)
            .sort_values("mean", ascending=False)
            .reset_index()
        )
        for _, r in tiss.iterrows():
            tissue_profile.append({
                "tissue": str(r["tissue"]),
                "mean": float(r["mean"]),
                "max": float(r["max"]),
                "count": int(r["count"]),
            })

    # Filtered subset (by tissue if requested)
    sub = df
    if tissue_filter and "tissue" in df.columns:
        sub = df[df["tissue"].astype(str).str.lower() == tissue_filter.lower()]

    # Top high-expression samples
    sub_sorted = sub.sort_values("FPKM", ascending=False).head(max(0, min(top_samples, 100)))
    sample_cols = ["sample_id", "FPKM", "tissue", "condition", "description", "project", "project_desc"]
    available_cols = [c for c in sample_cols if c in sub_sorted.columns]
    top_samples_list = []
    for _, r in sub_sorted[available_cols].iterrows():
        top_samples_list.append({
            "sample_id": str(r.get("sample_id", "")),
            "fpkm": float(r.get("FPKM", 0)),
            "tissue": str(r.get("tissue", "")) if "tissue" in r else "",
            "condition": str(r.get("condition", "")) if "condition" in r else "",
            "description": str(r.get("description", "")) if "description" in r else "",
            "project": str(r.get("project", "")) if "project" in r else "",
        })

    # Condition distribution (what treatments this gene was measured under)
    condition_dist: list[dict[str, Any]] = []
    if "condition" in df.columns:
        cond = df["condition"].fillna("unknown").astype(str).value_counts().head(10)
        for cond_name, cnt in cond.items():
            condition_dist.append({"condition": cond_name, "count": int(cnt)})

    stars, _ = _reliability_tier(n_samples)

    return {
        "status": "success",
        "gene_id": gid,
        "resolved_from": resolved_from,
        "species_dir": sp_dir,
        "species_label": SPECIES_META[sp_dir]["label"],
        "species_common": SPECIES_META[sp_dir]["common"],
        "n_samples": n_samples,
        "n_projects": n_projects,
        "n_tissues": len(tissue_profile),
        "mean_fpkm": round(fpkm_mean, 2),
        "max_fpkm": round(fpkm_max, 2),
        "tau_specificity": stats_summary.get("tau"),
        "top_tissue": stats_summary.get("top_tissue") or (tissue_profile[0]["tissue"] if tissue_profile else ""),
        "top_tissue_fpkm": stats_summary.get("top_tissue_fpkm"),
        "reliability": stars,
        "tissue_profile": tissue_profile,
        "top_samples": top_samples_list,
        "condition_distribution": condition_dist,
    }


def _load_gene_stats(sp_dir: str, gene_id: str) -> dict[str, Any]:
    """Fast stats lookup from gene_stats.tsv (tau, top_tissue). Empty dict on miss."""
    path = _gene_stats_path(sp_dir)
    if not path.exists():
        return {}
    try:
        # Read with dtype=str to avoid type coercion surprises, filter manually
        df = pd.read_csv(path, sep="\t", dtype=str)
        row = df[df["gene_id"] == gene_id]
        if row.empty:
            return {}
        r = row.iloc[0]
        out: dict[str, Any] = {}
        if "tau_specificity" in r and pd.notna(r["tau_specificity"]):
            try:
                out["tau"] = float(r["tau_specificity"])
            except (ValueError, TypeError):
                pass
        if "top_tissue" in r and pd.notna(r["top_tissue"]):
            out["top_tissue"] = str(r["top_tissue"])
        if "top_tissue_FPKM" in r and pd.notna(r["top_tissue_FPKM"]):
            try:
                out["top_tissue_fpkm"] = float(r["top_tissue_FPKM"])
            except (ValueError, TypeError):
                pass
        return out
    except Exception:
        return {}


def get_tissue_matrix(gene_id: str, ui_species: str = "") -> dict[str, Any]:
    """Return the gene × tissue mean FPKM row (for heatmap/bar chart on front-end)."""
    gid = (gene_id or "").strip()
    if not gid:
        return {"status": "invalid", "message": "gene_id is required"}

    sp_dir = resolve_species_dir(gid, ui_species)
    if not sp_dir:
        return {"status": "unknown_species", "message": f"Cannot recognize species for '{gid}'"}

    path = _tissue_matrix_path(sp_dir)
    if not path.exists():
        return {"status": "no_data", "message": f"tissue_mean_matrix.tsv missing for {sp_dir}"}

    try:
        df = pd.read_csv(path, sep="\t", dtype=str)
        row = df[df["gene_id"] == gene_id]
        if row.empty:
            return {"status": "not_found", "gene_id": gid, "message": "gene not in tissue matrix"}
        r = row.iloc[0].to_dict()
        # gene_id + each tissue -> float
        tissues: dict[str, float] = {}
        for k, v in r.items():
            if k == "gene_id":
                continue
            try:
                tissues[k] = float(v)
            except (ValueError, TypeError):
                continue
        # sorted desc
        sorted_tissues = sorted(tissues.items(), key=lambda kv: kv[1], reverse=True)
        return {
            "status": "success",
            "gene_id": gid,
            "species_dir": sp_dir,
            "species_label": SPECIES_META[sp_dir]["label"],
            "tissues": [{"tissue": t, "mean_fpkm": v} for t, v in sorted_tissues],
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def agent_tool_search_expression(gene_id: str, species: str = "", tissue: str = "") -> str:
    """Adapter for the Agent tool `search_gene_expression`. Returns JSON string."""
    result = query_gene_expression(gene_id, ui_species=species, tissue_filter=tissue)
    return json.dumps(result, ensure_ascii=False)
