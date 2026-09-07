import json
import os
import urllib.parse
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import settings
from app.services.action_logger import ActionTimer
from app.services.genome_catalog import SPECIES_DIRS, SPECIES_GPSITE_CSV, SPECIES_SITE_DIRS
from app.services.legacy_core import tool_search_protein_structure
from app.services.rate_limit import client_ip, enforce_download_rate_limit

router = APIRouter(prefix="/api/proteins", tags=["proteins"])

# Cache coverage scans (large PDB dirs); refresh every 10 minutes.
_COVERAGE_CACHE: dict = {"ts": 0.0, "payload": None}
_COVERAGE_TTL_SEC = 600.0


def resolve_pdb_path(tdir: Path, gene_id: str) -> Optional[Path]:
    """Prefer exact / prefix PDB filenames; avoid loose substring matches.

    Order:
      1. ``{gene_id}.pdb``
      2. stem == gene_id or stem startswith ``gene_id_`` / ``gene_id.``
      3. unique substring match (only if exactly one file contains gene_id)
    """
    gid = (gene_id or "").strip()
    if not gid or not tdir.exists():
        return None
    exact = tdir / f"{gid}.pdb"
    if exact.is_file():
        return exact

    prefix_hits: list[Path] = []
    substr_hits: list[Path] = []
    for name in os.listdir(tdir):
        if not name.endswith(".pdb"):
            continue
        path = tdir / name
        if not path.is_file():
            continue
        stem = name[:-4]
        if stem == gid or stem.startswith(gid + "_") or stem.startswith(gid + "."):
            prefix_hits.append(path)
        elif gid in name:
            substr_hits.append(path)
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    if len(prefix_hits) > 1:
        # Deterministic: shortest stem wins (usually the canonical file)
        return sorted(prefix_hits, key=lambda p: (len(p.name), p.name))[0]
    if len(substr_hits) == 1:
        return substr_hits[0]
    return None


def _count_suffix(dir_path: Path, suffix: str) -> int:
    if not dir_path.is_dir():
        return 0
    return sum(1 for name in os.listdir(dir_path) if name.endswith(suffix))


def site_root_for(species: str) -> Optional[Path]:
    rel = SPECIES_SITE_DIRS.get(species)
    if not rel:
        return None
    root = settings.web_structure_dir / rel
    return root if root.is_dir() else None


def residue_sites_dir_for(species: str) -> Optional[Path]:
    root = site_root_for(species)
    if root is None:
        return None
    json_dir = root / "all_sites_json"
    return json_dir if json_dir.is_dir() else None


def gpsite_csv_for(species: str) -> Optional[Path]:
    root = site_root_for(species)
    if root is None:
        return None
    name = SPECIES_GPSITE_CSV.get(species, "GPSite_summary.csv")
    path = root / name
    return path if path.is_file() else None


def _build_species_coverage() -> dict:
    details = []
    ready = []
    with_sites = []
    for species, pdb_rel in SPECIES_DIRS.items():
        pdb_dir = settings.web_structure_dir / pdb_rel
        site_rel = SPECIES_SITE_DIRS.get(species, "")
        sites_dir = residue_sites_dir_for(species)
        n_pdb = _count_suffix(pdb_dir, ".pdb")
        n_site = _count_suffix(sites_dir, ".json") if sites_dir else 0
        is_ready = n_pdb > 0
        has_sites = n_site > 0
        if is_ready:
            ready.append(species)
        if has_sites:
            with_sites.append(species)
        details.append({
            "species": species,
            "pdb_dir": pdb_rel,
            "site_dir": site_rel or "",
            "n_pdb": n_pdb,
            "n_site_json": n_site,
            "ready": is_ready,
            "has_sites": has_sites,
        })
    return {
        "species": list(SPECIES_DIRS.keys()),
        "ready": ready,
        "with_sites": with_sites,
        "details": details,
    }


@router.get("/species")
def protein_species():
    now = time.time()
    cached = _COVERAGE_CACHE.get("payload")
    if cached is not None and (now - float(_COVERAGE_CACHE["ts"])) < _COVERAGE_TTL_SEC:
        return cached
    payload = _build_species_coverage()
    _COVERAGE_CACHE["ts"] = now
    _COVERAGE_CACHE["payload"] = payload
    return payload


@router.get("/search")
def protein_search(species: str = Query(...), gene_id: str = Query(...), request: Request = None):
    ip = client_ip(request) if request is not None else None
    session_id = request.headers.get("X-Session-Id") if request is not None else None
    with ActionTimer(module="protein", action="search", gene_id=gene_id,
                     species=species, query_text=gene_id, ip=ip, session_id=session_id):
        raw = tool_search_protein_structure(gene_id=gene_id, species=species)
        data = json.loads(raw)
        if data.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=data.get("message", "Not found"))

        sp_dir = SPECIES_DIRS.get(species, "cucumber_pdb")
        tdir = settings.web_structure_dir / sp_dir
        # 工具已把老版本 ID（CmoCh…/Csa3G…）桥接成当前版（data.gene_id）——
        # PDB 文件按当前版命名，路由侧也必须用桥接后的 ID 找文件，
        # 否则 pdb_url 为空、前端显示 "No structure data available"。
        canonical_id = data.get("gene_id", gene_id)
        pdb_path = resolve_pdb_path(tdir, canonical_id) or resolve_pdb_path(tdir, gene_id)
        data["pdb_url"] = (
            f"/api/proteins/pdb?species={species}&gene_id={urllib.parse.quote(canonical_id)}"
            if pdb_path else None
        )

        exact_id = data.get("gene_id", gene_id)
        sites_dir = residue_sites_dir_for(species)
        if sites_dir is not None:
            site_json = sites_dir / f"{exact_id}.json"
            if not site_json.is_file():
                # Cucumber PDB stems sometimes omit transcript suffix (.1)
                alt = list(sites_dir.glob(f"{exact_id}*.json"))
                if len(alt) == 1:
                    site_json = alt[0]
            if site_json.is_file():
                with open(site_json, "r", encoding="utf-8") as jf:
                    raw_sites = json.load(jf)
                aa_map = _pdb_residue_map(pdb_path) if pdb_path else {}
                data["residue_sites"] = _normalize_residue_sites(raw_sites, exact_id, aa_map)

        return data


# PDB 三字母 -> 单字母氨基酸映射 (标准 20 种)
_PDB_AA_3TO1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    # 常见修饰/非标准残基
    "MSE": "M", "SEC": "U", "PYL": "O",
}


def _pdb_residue_map(pdb_path) -> dict:
    """
    扫一遍 PDB 文件，构建 {resno(int): 单字母氨基酸} 映射。

    只读 ATOM 行 (跳过 HETATM)，按残基序号去重 (同一个 resno 的所有原子
    残基代号必然相同，取第一次出现的即可)。PDB 文件一般几百 KB，全量扫
    一次约 10-30ms，对请求延迟影响可忽略。
    """
    if not pdb_path or not os.path.exists(pdb_path):
        return {}
    out = {}
    try:
        with open(pdb_path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.startswith("ATOM"):
                    continue
                # 标准 PDB 列: 1-6 记录名, 13-16 原子名, 18-20 残基三字母,
                # 22 位链 ID, 23-26 残基序号。注意列是 1-indexed。
                if len(line) < 27:
                    continue
                res3 = line[17:20].strip().upper()
                try:
                    resno = int(line[22:26].strip())
                except ValueError:
                    continue
                if resno in out:
                    continue
                aa1 = _PDB_AA_3TO1.get(res3)
                if aa1:
                    out[resno] = aa1
    except Exception:
        pass
    return out


def _normalize_residue_sites(raw, gene_id: str, aa_map: dict = None) -> list:
    """
    把原始 GPSite JSON 转成前端可消费的标准化数组。

    原始格式 (dict):
        {"87": "RNA: 0.83 | Peptide: 0.60", "95": "Protein: 0.76", ...}
    标准化后 (list):
        [
            {"resno": 87, "resname": "Y", "site_type": "RNA",     "confidence": 0.83},
            {"resno": 87, "resname": "Y", "site_type": "Peptide", "confidence": 0.83},
            ...
        ]
    """
    if not isinstance(raw, dict):
        return []
    if aa_map is None:
        aa_map = {}
    import re as _re
    out = []
    pattern = _re.compile(r"([A-Za-z]+):\s*([\d.]+)")
    for resno_key, val in raw.items():
        try:
            resno = int(resno_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(val, str):
            continue
        aa = aa_map.get(resno, "")
        for m in pattern.finditer(val):
            site_type = m.group(1).strip()
            # HEM is rarely prioritized in plant functional genomics UIs.
            if site_type.upper() == "HEM":
                continue
            try:
                conf = round(float(m.group(2)), 3)
            except ValueError:
                continue
            if conf <= 0.5:
                continue
            out.append({
                "resno": resno,
                "resname": aa,
                "site_type": site_type,
                "confidence": conf,
            })
    return out


@router.get("/pdb")
def get_pdb(species: str = Query(..., max_length=64), gene_id: str = Query(..., max_length=128),
            request: Request = None):
    if request is not None:
        enforce_download_rate_limit(request)
    sp_dir = SPECIES_DIRS.get(species, "cucumber_pdb")
    tdir = settings.web_structure_dir / sp_dir
    if not tdir.exists():
        raise HTTPException(status_code=404, detail="Species directory not found")
    path = resolve_pdb_path(tdir, gene_id)
    if path is None:
        # 老版本 ID → 当前版 ID 桥接后重试（PDB 文件按当前版命名）
        from app.services.legacy_core import _bridge_protein_gene_id, _transcript_id_from_master
        bridged = _bridge_protein_gene_id(gene_id, species)
        if bridged:
            path = resolve_pdb_path(tdir, bridged)
    if path is None:
        # WaxGourd 等：PDB 按转录本 ID 命名 — 主库别名再试
        from app.services.legacy_core import _transcript_id_from_master
        tx = _transcript_id_from_master(gene_id, species)
        if tx:
            path = resolve_pdb_path(tdir, tx)
    if path is None:
        raise HTTPException(status_code=404, detail="PDB not found")
    return FileResponse(
        path,
        media_type="chemical/x-pdb",
        filename=path.name,
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )
