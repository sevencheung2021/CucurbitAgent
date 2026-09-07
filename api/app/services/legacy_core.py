"""
Business logic ported from v28_cucurbit_web_agent.py (no Streamlit).
"""
import os
import gzip
import json
import re
import time
import hashlib
import math
import sqlite3
import textwrap
import threading
import queue as queue_module
import pandas as pd
import requests
from typing import Optional
from functools import lru_cache

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    chromadb = None

from app.config import settings
from app.services.llm_text_sanitize import (
    answer_is_insufficient,
    sanitize_assistant_text,
)

DATA_ROOT = settings.data_root

GLOBAL_SEARCH_CONFIG = settings.global_search_config
GLOBAL_MAP_CONFIG = settings.global_map_config
SPECIES_GFF3 = settings.species_gff3
SPECIES_GO_GAF = settings.species_go_gaf
SPECIES_PFAM_DOMAINS = settings.species_pfam_domains
HOMOLOGY_DB_V2 = str(settings.homology_db)
VARIANT_INDEX_DB = str(settings.variant_index_db)
CHROMA_DB_PATH_V2 = str(settings.chroma_db_path)
LITERATURE_DB_V2 = str(settings.literature_db_path)
EMBED_MODEL_NAME = settings.embed_model_name

ZHIPU_API_KEY = settings.zhipu_api_key
ZHIPU_BASE_URL = settings.zhipu_base_url
# ──────────────────────────────────────────────────────────────────
# 模型角色分配 (2026-07-09 用户决定: 全切 glm-4.5-air, 统一一条链路)
#
#   DECISION_MODEL      — 用于 Agent loop 的工具决策 (function calling)
#                        和 Guard / query rephrase。要求"快", 因为最多 4 轮循环 +
#                        2 次辅助调用, 用 glm-5.1 累计耗时 60-120s。
#                        glm-4.5-air 快 5 倍, 工具选择质量足够。
#
#   FINAL_ANSWER_MODEL  — 用于基于工具结果做最终流式总结。原默认 glm-5.1
#                        (质量强但慢), 但用户反馈首字延迟 5-15s 体验差, 80%
#                        的日常查询(单基因/文献/结构) glm-4.5-air 已足够。
#                        改成统一 glm-4.5-air: 简单、快、好调试, 无 fallback。
#                        若复杂综合题答得浅, 可临时改回 glm-5.1。
#
#   注意: 如果发现 glm-4.5-air 决策老是选错工具, 把 CUAGENT_DECISION_MODEL
#   改回 glm-5.1 即可 (会慢但更稳)。
# ──────────────────────────────────────────────────────────────────
# 模型角色分配 (2026-07-21)
#   DECISION_MODEL / FINAL_ANSWER_MODEL — Agent 决策与长总结
#   FAST_PATH_MODEL — 四模块快路径卡片总结（文献/基因/表达/蛋白）
# glm-4.5-flash 在智谱侧偶发排队 60-90s（用户体感“一直转圈”）；
# 快路径默认改用更稳的 glm-4-flash（TTFB 通常 <1s）。可用环境变量覆盖。
# ──────────────────────────────────────────────────────────────────
DECISION_MODEL = os.getenv("CUAGENT_DECISION_MODEL", "glm-4.5-flash")
FINAL_ANSWER_MODEL = os.getenv("CUAGENT_ANSWER_MODEL", "glm-4.5-flash")
FAST_PATH_MODEL = os.getenv("CUAGENT_FAST_PATH_MODEL", "glm-4-flash")
FINAL_ANSWER_MAX_TOKENS = int(os.getenv("CUAGENT_ANSWER_MAX_TOKENS", "2048"))

# 兼容别名: 老代码可能还在用 ZHIPU_MODEL 这个名字。保留但不用于决策。
ZHIPU_MODEL = settings.zhipu_model


def _agent_status(status_container, msg):
    if status_container is None:
        return
    if hasattr(status_container, "write"):
        status_container.write(msg)
    elif callable(status_container):
        status_container(msg)


CUCURBIT_ORTHOLOG_SPECIES = [
    "Cucumber", "Melon", "Watermelon", "Pumpkin_Moschata", "Pumpkin_Pepo",
    "BitterGourd", "BottleGourd", "SpongeGourd", "WaxGourd",
]
MODEL_CROP_SPECIES = ["Arabidopsis", "Maize", "Rice_T2T", "Tomato"]
ALL_ORTHOLOG_SPECIES = CUCURBIT_ORTHOLOG_SPECIES + MODEL_CROP_SPECIES


UI_TO_DB_SPECIES = {
    "Watermelon": "Watermelon",
    "Cucumber": "Cucumber",
    "Melon": "Melon",
    "Pumpkin (C. moschata)": "Pumpkin_Moschata",
    "Pumpkin (C. pepo)": "Pumpkin_Pepo",
    "BitterGourd": "BitterGourd",
    "BottleGourd": "BottleGourd",
    "WaxGourd": "WaxGourd",
    "SpongeGourd": "SpongeGourd",
}



def format_homology_species_display(db_species: str) -> str:
    if db_species == "Rice_T2T":
        return "Rice"
    return db_species.replace("_", " ")


_TX_SUFFIX = re.compile(r"\.\d+$")


_STAYGREEN_NAME_RE = re.compile(r"\b(?:CsSGR|STAY[- ]?GREEN)\b", re.IGNORECASE)


def _sanitize_literature_query(query: str) -> str:
    """Drop pasted locus IDs from CsSGR/STAYGREEN queries to avoid confirmation bias."""
    from app.services.literature_query import LOCUS_ID_RE

    q = (query or "").strip()
    if not q:
        return q
    if _STAYGREEN_NAME_RE.search(q):
        q = LOCUS_ID_RE.sub(" ", q)
        q = re.sub(r"\s{2,}", " ", q).strip()
    return q


def _lookup_cucumber_version_ids(gene_id: str) -> Optional[dict]:
    """Map a literature locus (V1/V2/V3, including Csa5M…) to V1/V2/V3 IDs."""
    from app.services.literature_query import normalize_cucumber_locus

    gid = normalize_cucumber_locus(gene_id)
    map_path = GLOBAL_MAP_CONFIG.get("Cucumber")
    if not map_path or not os.path.exists(map_path):
        return None
    df_m = load_db(map_path)
    if df_m is None:
        return None
    candidates = list(dict.fromkeys([gene_id, gid, f"{gid}.1"]))
    for cand in candidates:
        if not cand:
            continue
        m_mask = df_m.astype(str).apply(lambda col: col.str.lower() == cand.lower())
        if not m_mask.any().any():
            continue
        row = df_m[m_mask.any(axis=1)].iloc[0]
        v3 = str(row.get("V3_ID") or "").strip()
        v2 = str(row.get("V2_ID") or "").strip()
        v1 = str(row.get("V1_ID") or "").strip()
        na = {"", "-", "n/a", "nan", "none"}
        return {
            "query_id": gene_id,
            "normalized_id": gid,
            "v1": v1 if v1.lower() not in na else None,
            "v2": v2 if v2.lower() not in na else None,
            "v3": v3 if v3.lower() not in na else None,
        }
    return None


# 通用缩写/非基因词黑名单：不参与"基因符号邻近 locus"匹配
_NON_GENE_TOKENS = {
    "RNA", "DNA", "UV", "GO", "SNP", "QTL", "PCR", "ABA", "IAA", "GA", "ET",
    "SA", "JA", "ROS", "DEG", "DEGS", "TF", "KO", "OE", "WT", "BL", "V1",
    "V2", "V3", "V25", "CHINESE", "CHINESELONG", "DHL", "T2T", "FPKM",
    "ESMFOLD", "NCBI", "PMCID", "HTTP", "HTTPS", "DOI", "PDf", "PDF",
}


def _strict_gene_symbols(q: str):
    """Gene-symbol-like tokens only: ≥2 uppercase letters, len≥3, not an
    acronym in the blocklist (CsCHS/CHS/F3H/MGT2/STAYGREEN pass;
    chalcone/synthase/cucumber fail)."""
    out = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", q):
        letters = re.sub(r"[^A-Za-z]", "", tok)
        if len(letters) < 3:
            continue
        upper = sum(1 for c in letters if c.isupper())
        if upper < 2:
            continue
        if tok.upper() in _NON_GENE_TOKENS:
            continue
        out.append(tok)
    return list(dict.fromkeys(out))


# 各物种基因 ID 格式（用于"用户问题已带 ID → 直接走基因模块"的路由判定）
_SPECIES_LOCUS_RE = re.compile(
    r"""(?<![A-Za-z0-9_.])(?:          # 词首边界（不匹配更长 token 的一部分）
        CsaV3_\d+G\d+                 # Cucumber V3
      | Csa\d+G\d+(?:\.\d+)?        # Cucumber V2（含转录本 .1）
      | Csa\d+M\d+                   # Cucumber V2 Gy14/9930 M 式
      | Csa\d{5,}                     # Cucumber V1
      | MELO3C\d+                     # Melon v4
      | MELO\d{6,}                    # Melon 旧版
      | Cla97C\d+G\d+                # Watermelon 97103
      | Cla\d{7,}                     # Watermelon 旧版
      | RifuC\d+G\d+                 # Pumpkin moschata (Rifu v2)
      | Cmo\w{3,}\d+                 # Pumpkin moschata 旧版
      | Cp\d(?:\.\d+)?LG\w+\d+    # Pumpkin pepo (Cp4.1LG…)
      | Moctig\w+\d+                 # BitterGourd
      | Lsi\d+G\d+                   # BottleGourd
      | Bhi\d+G\d+                   # WaxGourd
      | Bhi\d+M\d+                   # WaxGourd 旧版
      | Spg\d{5,}                     # SpongeLuffa
    )(?![A-Za-z0-9])""",
    re.VERBOSE,
)


_LOCUS_PREFIX_TO_SPECIES = [
    ("csa", "Cucumber"),
    ("cla", "Watermelon"),
    ("melo", "Melon"),
    ("rifu", "Pumpkin (C. moschata)"),
    ("cmo", "Pumpkin (C. moschata)"),
    ("cp", "Pumpkin (C. pepo)"),
    ("moctig", "BitterGourd"),
    ("lsi", "BottleGourd"),
    ("bhi", "WaxGourd"),
    ("spg", "SpongeGourd"),
]


def _species_from_gene_id(gene_id: str) -> str:
    """Best-effort species detection from the locus ID prefix.

    The agent LLM often omits ``species`` when the question carries an ID;
    the old default ("Cucumber") meant watermelon/melon IDs were looked up
    against the cucumber DB only → bogus "not found" (CucuBench Q3, 2026-08-19).
    """
    gl = (gene_id or "").strip().lower()
    if not gl:
        return ""
    for prefix, sp in _LOCUS_PREFIX_TO_SPECIES:
        if gl.startswith(prefix):
            return sp if sp in GLOBAL_SEARCH_CONFIG else ""
    return ""


def detect_user_locus_ids(text: str) -> list:
    """Locus IDs typed by the user in their question, any cucurbit species."""
    if not text:
        return []
    return list(dict.fromkeys(m.group(0) for m in _SPECIES_LOCUS_RE.finditer(text)))


def _symbol_variants(symbols):
    """CsCHS → also match bare CHS: papers write "chalcone synthase (CHS)
    (Csa3G600020.1)" without the species prefix. Core = tail after the last
    species-prefix chunk (Cs/Cm/Cl…)."""
    variants = list(symbols)
    for s in symbols:
        m = re.match(r"^(?:[A-Z][a-z])+([A-Z][A-Za-z0-9]{2,})$", s)
        core = m.group(1) if m else None
        if core and core.upper() not in _NON_GENE_TOKENS and core not in variants:
            variants.append(core)
    return variants


def gene_id_base(gene_id: str) -> str:
    """Strip transcript suffix (.1) only — pepo IDs contain a mid-dot (Cp4.1LG…)."""
    return _TX_SUFFIX.sub("", (gene_id or "").strip())


def fetch_plant_orthologs(query_species: str, gene_id: str):
    """Best-hit orthologs per species from Homology Engine V2."""
    if not os.path.exists(HOMOLOGY_DB_V2):
        return None
    query_species_db = UI_TO_DB_SPECIES.get(query_species, query_species)
    clean_id = gene_id_base(gene_id)
    try:
        conn = sqlite3.connect(HOMOLOGY_DB_V2)
        df_homo = pd.read_sql_query(
            "SELECT subject_species, subject_gene, identity, qcover, evalue "
            "FROM homolog_pairs WHERE query_species = ? AND query_gene = ?",
            conn,
            params=(query_species_db, clean_id),
        )
        conn.close()
        if df_homo.empty:
            return None
        df_homo = df_homo.sort_values(by=["identity", "qcover"], ascending=[False, False])
        return df_homo.drop_duplicates(subset=["subject_species"])
    except Exception:
        return None


def get_query_species_db(query_species: str) -> str:
    return UI_TO_DB_SPECIES.get(query_species, query_species)


def ortholog_target_species(query_species: str) -> list:
    """All ortholog species except the query species itself."""
    query_db = get_query_species_db(query_species)
    return [sp for sp in ALL_ORTHOLOG_SPECIES if sp != query_db]


def build_ortholog_matrix(df_homo: pd.DataFrame, query_species: str = None) -> pd.DataFrame:
    """Species-as-columns matrix: one glance shows hits vs missing (—)."""
    hit_map = {str(row["subject_species"]): row for _, row in df_homo.iterrows()}
    target_species = ortholog_target_species(query_species) if query_species else ALL_ORTHOLOG_SPECIES
    columns, gene_row, id_row, cov_row, eval_row = [], [], [], [], []

    for sp in target_species:
        columns.append(format_homology_species_display(sp))
        if sp in hit_map:
            r = hit_map[sp]
            gene_row.append(str(r["subject_gene"]))
            id_row.append(f"{r['identity']:.1f}%")
            cov_row.append(f"{min(100.0, float(r['qcover'])):.1f}%")
            eval_row.append(str(r["evalue"]))
        else:
            gene_row.append("—")
            id_row.append("—")
            cov_row.append("—")
            eval_row.append("—")

    return pd.DataFrame(
        [gene_row, id_row, cov_row, eval_row],
        index=["Ortholog Gene ID", "Identity", "Coverage", "E-value"],
        columns=columns,
    )


def split_ortholog_matrix(matrix_df: pd.DataFrame, query_species: str = None):
    """Split full matrix into cucurbit block + model-crop block for cleaner layout."""
    query_db = get_query_species_db(query_species) if query_species else None
    cuc_cols = [
        format_homology_species_display(sp)
        for sp in CUCURBIT_ORTHOLOG_SPECIES
        if sp != query_db
    ]
    model_cols = [format_homology_species_display(sp) for sp in MODEL_CROP_SPECIES]
    return matrix_df[cuc_cols], matrix_df[model_cols]


def style_ortholog_matrix(matrix_df: pd.DataFrame):
    """Gray out missing cells so gaps are visually obvious."""
    def _highlight_missing(val):
        if val == "—":
            return "background-color: #f4f6f7; color: #95a5a6;"
        return ""

    return matrix_df.style.applymap(_highlight_missing)


def _sequence_available(seq: str) -> bool:
    return bool(seq) and str(seq).strip() not in ("N/A", "nan", "")


def classify_variant_impact(region: str, consequence: str) -> str:
    region = str(region or "")
    cons = str(consequence or "").lower()
    if region == "CDS":
        if "synonymous" in cons or "同义" in cons:
            return "cds_synonymous"
        if "missense" in cons or "错义" in cons:
            return "cds_missense"
        if "nonsense" in cons or "无义" in cons or "stop" in cons:
            return "cds_nonsense"
        return "cds_other"
    if region in ("Intron/UTR", "Intron", "UTR", "5'-UTR", "3'-UTR"):
        return "non_cds"
    if region == "Intergenic":
        return "intergenic"
    return "other"


def fetch_gene_variants(species: str, gene_id: str):
    if not os.path.exists(VARIANT_INDEX_DB):
        return None
    clean_id = gene_id_base(gene_id)
    try:
        conn = sqlite3.connect(VARIANT_INDEX_DB)
        df = pd.read_sql_query(
            "SELECT chr, pos, ref, alt, region, consequence, aa_change, description, impact_class "
            "FROM gene_variants WHERE species = ? AND gene_id = ? ORDER BY pos",
            conn,
            params=(species, clean_id),
        )
        conn.close()
        return df if not df.empty else None
    except Exception:
        return None


def summarize_variants(df: pd.DataFrame) -> dict:
    counts = df["impact_class"].value_counts().to_dict()
    cds_total = sum(counts.get(k, 0) for k in ("cds_synonymous", "cds_missense", "cds_nonsense", "cds_other"))
    return {
        "total": len(df),
        "cds_total": cds_total,
        "non_cds": counts.get("non_cds", 0) + counts.get("other", 0),
        "synonymous": counts.get("cds_synonymous", 0),
        "missense": counts.get("cds_missense", 0),
        "nonsense": counts.get("cds_nonsense", 0),
        "protein_altering": counts.get("cds_missense", 0) + counts.get("cds_nonsense", 0) + counts.get("cds_other", 0),
    }


def english_only_variant_label(text: str) -> str:
    """Strip Chinese parenthetical suffixes, e.g. 'Missense (错义)' -> 'Missense'.

    Also normalizes pandas NaN / placeholder values to a clean empty string so
    they don't leak into LLM context as the literal string "nan".
    """
    if text is None:
        return ""
    text_str = str(text).strip()
    if not text_str or text_str in ("-", "nan", "NaN", "N/A", "None"):
        return ""
    return re.sub(r"\s*\([^)]*\)\s*", "", text_str).strip()


# Languages we explicitly support for the final-answer reply. Anything outside
# this set falls back to English (rare languages: glm-4.5-air quality is poor,
# and the user can always re-ask in English). Keep this list small and stable
# — adding a language here is a deliberate UX decision, not a freebie.
_SUPPORTED_REPLY_LANGS = {
    "zh": "Chinese", "en": "English", "es": "Spanish", "fr": "French",
    "de": "German", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese",
    "ru": "Russian", "it": "Italian", "ar": "Arabic",
}


def detect_user_language(text: str) -> str:
    """Return a stable ISO 639-1 language code for the user's message.

    Detection order (each layer is a fast, deterministic gate before the next):
      1. Japanese — hiragana/katakana. MUST run before the Chinese check
         because Japanese shares CJK ideographs with Chinese; the presence of
         kana is the reliable Japanese tell. (Pure-kanji Japanese is rare in
         user queries and will be caught by langdetect below.)
      2. Chinese — CJK Unified Ideographs range. Deterministic, 0ms. This
         catches mixed text like "CsaV3_3G027830基因功能" that langdetect
         misclassifies (it says "vi" for that exact string).
      3. Korean — Hangul range. Deterministic, 0ms. Done before the short-
         input fast-path because Hangul syllables aren't counted as "letters"
         by the Latin-only regex below, so a Korean query would be wrongly
         treated as a short bare-ID input.
      4. Short / noisy input fast-path — fewer than 8 Latin letters means
         it's almost certainly a bare gene ID (e.g. "CsaV3_3G027830"), which
         langdetect misclassifies (returns "hu"). Treat as English.
      5. langdetect — for everything else (Spanish, French, German, etc.).
         DetectorFactory.seed=0 makes results deterministic across runs.

    Returns "en" on any failure (safe fallback: English always retrieves well
    against the English-only knowledge base).
    """
    # Layer 1: Japanese (hiragana / katakana) — before Chinese check.
    if re.search(r"[ぁ-ゖァ-ヾ]", text):
        return "ja"
    # Layer 2: Chinese (CJK Unified Ideographs).
    if re.search(r"[一-鿿]", text):
        return "zh"
    # Layer 3: Korean (Hangul Syllables).
    if re.search(r"[가-힣]", text):
        return "ko"
    # Layer 4: short input fast-path. Count Latin letters (incl. accented);
    # ignore digits/punctuation/gene-ID separators.
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", text)
    if len(letters) < 8:
        return "en"
    # Layer 5: langdetect (Spanish, French, German, Portuguese, ...).
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0  # reproducible results
        return detect(text)
    except Exception:
        return "en"


def format_variant_display_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Ref→Alt"] = out["ref"].astype(str) + "→" + out["alt"].astype(str)
    out["consequence"] = out["consequence"].apply(english_only_variant_label)
    out.rename(
        columns={
            "chr": "Chr",
            "pos": "Pos",
            "region": "Region",
            "consequence": "Consequence",
            "aa_change": "AA Change",
        },
        inplace=True,
    )
    return out


def style_variant_table(df: pd.DataFrame):
    colors = {
        "cds_synonymous": "background-color: #eafaf1",
        "cds_missense": "background-color: #fdf2e9",
        "cds_nonsense": "background-color: #fadbd8",
        "non_cds": "background-color: #ebf5fb",
    }

    def _row_style(row):
        return [colors.get(row.get("impact_class", ""), "")] * len(row)

    if "impact_class" in df.columns:
        return df.drop(columns=["impact_class"]).style.apply(_row_style, axis=1)
    return df


def load_db(path):
    if not path or not os.path.exists(path): return None
    try: return pd.read_csv(path, sep='\t').fillna("N/A")
    except: return None

def calculate_avg_plddt(pdb_string):
    plddt_scores = []
    for line in pdb_string.split('\n'):
        if line.startswith('ATOM') and line[12:16].strip() == 'CA':
            try:
                bfactor = float(line[60:66].strip())
                plddt_scores.append(bfactor)
            except ValueError: continue
    if not plddt_scores: return 0.0
    avg_score_plddt = sum(plddt_scores) / len(plddt_scores)
    if 0 < avg_score_plddt <= 1.0: avg_score_plddt = avg_score_plddt * 100
    return avg_score_plddt


def get_chroma_collection():
    """Cached Chroma collection (see literature_rag)."""
    from app.services import literature_rag

    return literature_rag.get_chroma_collection()


# =========================================
# Tool Implementation: search_literatureDB  → literature_rag.hybrid_search
# =========================================
def tool_search_literatureDB(query: str) -> str:
    """HYBRID local literature retrieval via unified literature_rag service.

    Returns reranked chunks + paper summaries. The outer agent synthesizes
    the final answer from chunks (cited-answer generation inside the tool
    was tried but made things slower on glm-4.5-air — see _generate_cited_answer
    docstring for the postmortem; it's kept for a future faster model).
    """
    from app.services import literature_rag

    q = _sanitize_literature_query(query)
    result = literature_rag.search_for_agent(q)
    try:
        from app.services.literature_query import (
            extract_locus_ids,
            extract_locus_ids_linked_to_names,
            normalize_cucumber_locus,
            parse_literature_query,
        )

        chunks = result.get("chunks") if isinstance(result, dict) else None
        parsed = parse_literature_query(q)
        # ── Locus candidate scoring (v2) ─────────────────────────────────────
        # Old bug: every English word in the query acted as a "gene name", and
        # the FIRST locus found near any word became literature_locus. A plain
        # word like "synthase" linked an unrelated ID (MGT2/CsaV3_7G006660)
        # from a review chunk while the paper abstract holding the true ID
        # (Csa3G600020.1) was never scanned. Fix: (a) scan returned paper
        # ABSTRACTS + titles (highest trust), (b) only gene-symbol-like tokens
        # (CsCHS/CHS/F3H — ≥2 uppercase letters) drive "linked" extraction,
        # (c) score candidates instead of first-come.
        strict_symbols = list(parsed.gene_ids) or _strict_gene_symbols(q)
        link_names = _symbol_variants(strict_symbols)
        # Score by NORMALIZED id (Csa3G600020.1 == Csa3G600020) so transcript
        # suffixes don't split the vote; keep the most display-worthy raw form.
        scores: dict = {}
        best_form: dict = {}

        def _add(gid: str, pts: float) -> None:
            key = normalize_cucumber_locus(gid).lower()
            if key not in scores:
                scores[key] = 0.0
                best_form[key] = gid
            scores[key] += pts

        def _add_linked(text: str, base: float) -> None:
            # The linked extractor returns distance-sorted ids — closer to the
            # symbol = more points (table chunks list many unrelated ids).
            linked = extract_locus_ids_linked_to_names(text, link_names)
            for rank, gid in enumerate(linked):
                _add(gid, base + max(0, 4 - rank) * 0.5)

        # (a) abstracts/titles of the retrieved papers — top trust source
        papers = result.get("papers") if isinstance(result, dict) else None
        if isinstance(papers, list):
            for pidx, p in enumerate(papers):
                if not isinstance(p, dict):
                    continue
                abs_text = f"{p.get('title') or ''} {p.get('abstract') or ''}"
                if not abs_text.strip():
                    continue
                rank_pts = max(0.0, 6.0 - pidx)  # earlier paper = better
                for gid in extract_locus_ids(abs_text):
                    _add(gid, 4.0 + rank_pts)
                if link_names:
                    _add_linked(abs_text, 10.0)

        # (b/c) chunks: symbol-linked IDs beat incidental IDs
        if isinstance(chunks, list):
            for ch in chunks:
                if not isinstance(ch, dict):
                    continue
                chunk_text = ch.get("chunk_text") or ""
                if link_names:
                    _add_linked(chunk_text, 6.0)
                for gid in extract_locus_ids(chunk_text):
                    _add(gid, 1.0)

        if scores:
            ranked_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
            primary = best_form[ranked_keys[0]]
            norm = normalize_cucumber_locus(primary)
            ranked = [best_form[k] for k in ranked_keys]
            same = [g for g in ranked if normalize_cucumber_locus(g) == norm]
            result["evidence_gene_ids"] = same or [primary]
            # Expose a few alternates so the agent can retry when the primary
            # turns out inconsistent with the literature context.
            result["evidence_gene_id_candidates"] = ranked[:5]
            result["literature_locus"] = primary
            mapping = _lookup_cucumber_version_ids(primary)
            if mapping:
                result["version_mapping"] = mapping
    except Exception:
        pass
    return json.dumps(result, ensure_ascii=False)


# =========================================
# AGENT TOOL DEFINITIONS (Function Calling)
# =========================================

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_gene_by_name",
            "description": (
                "Find gene IDs by FUNCTION NAME or annotation description in the species "
                "master databases (e.g. name='chalcone synthase', species='Melon' → "
                "MELO3C014767). Use when the question names a gene function/symbol but NO "
                "locus ID — especially for non-cucumber species ('melon chalcone synthase', "
                "'watermelon receptor kinase'). Returns matching gene IDs with descriptions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Function name, e.g. 'chalcone synthase'",
                    },
                    "species": {
                        "type": "string",
                        "description": "Target species (optional; scans all when empty)",
                        "default": "",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_gene_comprehensive",
            "description": "Retrieve COMPLETE gene information including: gene structure (exons/introns from GFF3), GO terms (Biological Process/Molecular Function/Cellular Component), Pfam protein domains, natural variants (SNP/InDel with consequence), CDS and protein sequences, plant orthologs (cucurbit species plus Arabidopsis, Maize, Rice, Tomato), and wild relative synteny orthologs. Use this when the user asks about gene function, structure, annotation, or wants full details about a gene.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gene_id": {
                        "type": "string",
                        "description": "Gene ID, e.g. 'CsaV3_1G000080'"
                    },
                    "species": {
                        "type": "string",
                        "description": "Target species (default: auto-detect from gene ID prefix)",
                        "default": "Cucumber"
                    }
                },
                "required": ["gene_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_gene_expression",
            "description": "Retrieve tissue-level expression profile, tau tissue-specificity index, sample/project stats, condition breakdown, and top co-expressed genes (Pearson correlation) from RNA-seq data. Use this when the user asks about expression pattern, tissue specificity, where a gene is highly expressed, or co-expression / functional partners.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gene_id": {
                        "type": "string",
                        "description": "Gene ID, e.g. 'CsaV3_3G027830'"
                    },
                    "species": {
                        "type": "string",
                        "description": "Target species (default: auto-detect from gene ID prefix)",
                        "default": "Cucumber"
                    }
                },
                "required": ["gene_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_literatureDB",
            "description": "Search the local curated cucurbit literature database (20000+ papers) using hybrid keyword (FTS5 on PDF chunks) and semantic vector retrieval. Returns chunk_text evidence plus paper metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords, e.g. 'watermelon flesh color carotenoid' or 'fusarium wilt resistance'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_protein_structure",
            "description": "Retrieve 3D protein structure prediction (ESMFold PDB), pLDDT confidence score, and AI-predicted functional binding sites (GPSite). Use this when the user asks about protein structure, 3D visualization, folding confidence, or binding sites.",
            "parameters": {
                "type": "object",
                "properties": {
                    "gene_id": {
                        "type": "string",
                        "description": "Gene ID, e.g. 'CsaV3_1G000080'"
                    },
                    "species": {
                        "type": "string",
                        "description": "Target species (default: Cucumber)",
                        "default": "Cucumber"
                    }
                },
                "required": ["gene_id"]
            }
        }
    }
]


# =========================================
# Tool Implementation: search_gene_database
# =========================================
def tool_search_gene_database(gene_id: str, species: str = "") -> str:
    """Search local cucurbit master databases for gene info."""
    results = []
    search_targets = {}
    if species and species in GLOBAL_SEARCH_CONFIG:
        search_targets = {species: GLOBAL_SEARCH_CONFIG[species]}
    else:
        search_targets = GLOBAL_SEARCH_CONFIG

    for sp, path in search_targets.items():
        df = load_db(path)
        if df is None:
            continue
        match = df[df.iloc[:, 0].astype(str).str.lower() == gene_id.lower()]
        if not match.empty:
            row = match.iloc[0]
            func_desc_raw = row.get('Gene_Description', '')
            if pd.isna(func_desc_raw) or str(func_desc_raw).strip() in ["-", "N/A", "nan", "NaN", ""]:
                func_desc = "Not provided"
            else:
                func_desc = str(func_desc_raw).strip()

            info = {
                "gene_id": str(row.iloc[0]),
                "species": sp,
                "function": func_desc,
                "chr": str(row.get('Chr', 'N/A')),
                "start": str(row.get('Start', 'N/A')),
                "end": str(row.get('End', 'N/A')),
                "strand": str(row.get('Strand', 'N/A')),
            }

            # Check version mapping
            map_path = GLOBAL_MAP_CONFIG.get(sp)
            if map_path and os.path.exists(map_path):
                df_m = load_db(map_path)
                if df_m is not None:
                    m_mask = df_m.astype(str).apply(lambda col: col.str.lower() == gene_id.lower())
                    if m_mask.any().any():
                        mapped_df = df_m[m_mask.any(axis=1)]
                        if not mapped_df.empty:
                            row_dict = mapped_df.iloc[0].to_dict()
                            ignore_keys = ["V2_Confidence", "V2_Coord_Overlap", "V1_Confidence", "V1_Coord_Overlap", "Method"]
                            mapping = {k: str(v) for k, v in row_dict.items()
                                       if str(v).strip() not in ["-", "N/A", "nan", "NaN"] and k not in ignore_keys}
                            info["version_mapping"] = mapping

            results.append(info)
            break

    if not results:
        return json.dumps({"status": "not_found", "message": f"Gene '{gene_id}' not found in any local database."}, ensure_ascii=False)
    return json.dumps({"status": "success", "results": results}, ensure_ascii=False)


# =========================================
# Tool Implementation: search_gene_comprehensive
# =========================================
@lru_cache(maxsize=256)
def _bridge_moschata_ids(gene_id: str, prefer_v1: bool = True) -> tuple:
    """Pumpkin (C. moschata) ID bridging.

    The master DB stores v2 IDs (RifuC..), but the GFF3/GO files only contain
    v1 IDs (CmoCh..). Look up the mapping table and return all candidate IDs
    (in v1 space when ``prefer_v1`` is True, otherwise the original v2 id).
    """
    map_path = settings.pumpkin_moschata_mapping
    if not os.path.exists(map_path):
        return (gene_id,)
    try:
        df_m = load_db(map_path)
        if df_m is None:
            return (gene_id,)
        mask = df_m.astype(str).apply(lambda col: col.str.lower() == gene_id.lower())
        if not mask.any().any():
            return (gene_id,)
        row = df_m[mask.any(axis=1)].iloc[0]
        v1_id = str(row.get("V1_ID", "")).strip()
        v2_id = str(row.get("V2_ID", "")).strip()
        candidates = []
        if prefer_v1:
            if v1_id and v1_id not in ("-", "N/A", "nan", "NaN"):
                candidates.append(v1_id)
            if v2_id and v2_id not in ("-", "N/A", "nan", "NaN"):
                candidates.append(v2_id)
        else:
            if v2_id and v2_id not in ("-", "N/A", "nan", "NaN"):
                candidates.append(v2_id)
            if v1_id and v1_id not in ("-", "N/A", "nan", "NaN"):
                candidates.append(v1_id)
        return tuple(candidates) if candidates else (gene_id,)
    except Exception:
        return (gene_id,)


def _summarize_gene_info(result: dict) -> str:
    """Turn the structured gene-comprehensive blob into a concise paragraph.

    Mirrors the search_RAG_db architecture change: the outer agent used to
    spend 25-35s re-interpreting the GO/Pfam/variant/ortholog structure each
    turn. By emitting a ready-made summary here, the agent only does light
    integration. Uses glm-4.5-air (same provider as the agent, no extra deps).
    """
    if not result or result.get("status") != "success":
        return ""
    if not ZHIPU_API_KEY:
        return ""

    # Strip the heavy sequence payloads before sending to the LLM — they bloat
    # the prompt without helping the summary.
    slim = {k: v for k, v in result.items() if k not in ("protein_sequence", "cds_sequence")}
    try:
        client = OpenAI(api_key=ZHIPU_API_KEY, base_url=ZHIPU_BASE_URL)
        resp = client.chat.completions.create(
            model=DECISION_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a plant genomics curator. Read the structured gene record "
                        "(JSON) and write a concise, scientifically accurate summary paragraph "
                        "for a researcher. Cover: basic info (location/strand), function, GO "
                        "annotations, Pfam domains, notable variants, and orthologs. Keep it "
                        "under 200 words. Do NOT list raw IDs exhaustively — synthesize. "
                        "Reply in English regardless of input language."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Gene record (JSON):\n{json.dumps(slim, ensure_ascii=False)[:3500]}",
                },
            ],
            temperature=0.2,
            max_tokens=400,
            extra_body=settings.llm_extra_body,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or ""
    except Exception as exc:
        print(f"Gene summary generation failed: {exc}")
        return ""


def tool_search_gene_by_name(name: str, species: str = "") -> str:
    """Find gene IDs by FUNCTION NAME against the master annotation
    Gene_Description column (e.g. 'chalcone synthase' in Melon → MELO3C014767…).

    Deterministic complement to the literature tool for name-based questions,
    especially non-cucumber species where literature chunks often lack IDs.
    """
    q = (name or "").strip()
    if len(q) < 3:
        return json.dumps({"status": "invalid", "message": "name too short"}, ensure_ascii=False)
    detected = _species_from_gene_id(q)  # 空（name 不是 ID）
    target = species if species in GLOBAL_SEARCH_CONFIG else (detected or "")
    ordered_species = ([target] if target else []) + [sp for sp in GLOBAL_SEARCH_CONFIG if sp != target]
    hits = []
    try:
        for sp in ordered_species:
            df = load_db(GLOBAL_SEARCH_CONFIG[sp])
            if df is None or "Gene_Description" not in df.columns:
                continue
            mask = df["Gene_Description"].astype(str).str.contains(q, case=False, na=False)
            for _, r in df[mask].head(6).iterrows():
                hits.append({
                    "gene_id": str(r.iloc[0]),
                    "species": sp,
                    "description": str(r.get("Gene_Description", ""))[:120],
                    "protein_len": str(r.get("Protein_Seq_Len", "")),
                })
            if target and hits:
                break  # 指定了物种：该物种的命中足够
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
    if not hits:
        return json.dumps({
            "status": "not_found",
            "message": f"No gene annotated with '{q}' in any species master database.",
        }, ensure_ascii=False)
    return json.dumps({
        "status": "success",
        "query": q,
        "count": len(hits),
        "genes": hits,
        "note": (
            "Multiple hits may be gene-family members. To pick the primary one, "
            "resolve the same name in cucumber, then use the cucumber gene's "
            "plant_orthologs entry for this species (highest identity)."
        ),
    }, ensure_ascii=False)


def tool_search_gene_comprehensive(gene_id: str, species: str = "Cucumber") -> str:
    """Get complete gene info: structure, GO, Pfam, variants, sequences, orthologs."""
    result = {"status": "not_found", "gene_id": gene_id}

    # 1. Find gene in master database — species detected from the ID prefix
    # gets FIRST priority (the LLM often omits species), then the caller's
    # species, then everything else.
    search_targets = {}
    for cand in [
        _species_from_gene_id(gene_id),
        species if species in GLOBAL_SEARCH_CONFIG else "",
    ] + list(GLOBAL_SEARCH_CONFIG):
        if cand and cand in GLOBAL_SEARCH_CONFIG and cand not in search_targets:
            search_targets[cand] = GLOBAL_SEARCH_CONFIG[cand]
    found_sp, found_row, latest_id = None, None, gene_id

    for sp, path in search_targets.items():
        df = load_db(path)
        if df is None: continue
        # Direct match
        match = df[df.iloc[:, 0].astype(str).str.lower() == gene_id.lower()]
        if match.empty:
            # Try version mapping
            map_path = GLOBAL_MAP_CONFIG.get(sp)
            if map_path and os.path.exists(map_path):
                df_m = load_db(map_path)
                if df_m is not None:
                    m_mask = df_m.astype(str).apply(lambda col: col.str.lower() == gene_id.lower())
                    if m_mask.any().any():
                        mapped_df = df_m[m_mask.any(axis=1)]
                        candidate_ids = [str(v).strip() for v in mapped_df.iloc[0].values if str(v).strip() not in ["-","N/A","nan","NaN"]]
                        match = df[df.iloc[:,0].astype(str).str.lower().isin([x.lower() for x in candidate_ids])]
        if not match.empty:
            found_sp = sp
            found_row = match.iloc[0]
            latest_id = str(found_row.iloc[0])
            break

    if found_row is None:
        return json.dumps({"status": "not_found", "message": f"Gene '{gene_id}' not found in any database."}, ensure_ascii=False)

    # Basic info
    func_desc_raw = found_row.get('Gene_Description', '')
    func_desc = "Not provided" if pd.isna(func_desc_raw) or str(func_desc_raw).strip() in ["-","N/A","nan","NaN",""] else str(func_desc_raw).strip()

    result = {
        "status": "success",
        "gene_id": latest_id,
        "species": found_sp,
        "basic_info": {
            "chr": str(found_row.get('Chr', 'N/A')),
            "start": str(found_row.get('Start', 'N/A')),
            "end": str(found_row.get('End', 'N/A')),
            "strand": str(found_row.get('Strand', 'N/A')),
            "function": func_desc
        }
    }

    # 2. Version mapping
    map_path = GLOBAL_MAP_CONFIG.get(found_sp)
    if map_path and os.path.exists(map_path):
        df_m = load_db(map_path)
        if df_m is not None:
            m_mask = df_m.astype(str).apply(lambda col: col.str.lower() == gene_id.lower())
            if not m_mask.any().any():
                m_mask = df_m.astype(str).apply(lambda col: col.str.lower() == latest_id.lower())
            if m_mask.any().any():
                mapped_df = df_m[m_mask.any(axis=1)]
                if not mapped_df.empty:
                    ignore_keys = ["V2_Confidence", "V2_Coord_Overlap", "V1_Confidence", "V1_Coord_Overlap", "Method"]
                    result["version_mapping"] = {k: str(v) for k, v in mapped_df.iloc[0].to_dict().items()
                                                  if str(v).strip() not in ["-","N/A","nan","NaN"] and k not in ignore_keys}

    # 3. Gene structure (GFF3) - all 9 species
    gff_path = SPECIES_GFF3.get(found_sp)
    if gff_path and os.path.exists(gff_path):
        # Pumpkin (C. moschata): master DB uses v2 IDs (RifuC..), but the GFF3
        # only has v1 IDs (CmoCh..). Bridge via the v1<->v2 mapping table so we
        # look up the correct GFF3 entry.
        gff_query_ids = [latest_id]
        if found_sp == "Pumpkin (C. moschata)":
            gff_query_ids = _bridge_moschata_ids(latest_id, prefer_v1=True)

        exons = []
        g_start, g_end, strand = None, None, None
        try:
            with gzip.open(gff_path, "rt", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#"): continue
                    if not any(qid in line for qid in gff_query_ids): continue
                    parts = line.strip().split("\t")
                    if len(parts) < 9: continue
                    if parts[2] == "gene":
                        g_start, g_end = int(parts[3]), int(parts[4])
                        strand = parts[6]
                    elif parts[2] == "CDS":
                        exons.append([int(parts[3]), int(parts[4])])
        except Exception:
            pass
        if exons:
            exons.sort(key=lambda x: x[0])
            result["gene_structure"] = {
                "gene_start": g_start, "gene_end": g_end, "strand": strand,
                "gene_length_bp": g_end - g_start + 1 if g_start and g_end else 0,
                "cds_exons": exons,
                "num_exons": len(exons),
                "total_cds_bp": sum(e[1]-e[0]+1 for e in exons)
            }

    # 4. GO terms (GAF) - all 9 species
    go_path = SPECIES_GO_GAF.get(found_sp)
    if go_path and os.path.exists(go_path):
        go_query_ids = [latest_id]
        if found_sp == "Pumpkin (C. moschata)":
            go_query_ids = _bridge_moschata_ids(latest_id, prefer_v1=True)

        bp_list, mf_list, cc_list = [], [], []
        try:
            with gzip.open(go_path, "rt", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("!"): continue
                    if not any(qid in line for qid in go_query_ids): continue
                    parts = line.strip().split("\t")
                    if len(parts) >= 9 and any(parts[i] == qid for i in (1, 2) for qid in go_query_ids):
                        go_id = parts[4]
                        aspect = parts[8]
                        term_name = parts[9] if len(parts) > 9 and parts[9] not in [parts[1], parts[2]] else ""
                        entry = f"{term_name} ({go_id})" if term_name else go_id
                        if aspect == 'P' and entry not in bp_list: bp_list.append(entry)
                        elif aspect == 'F' and entry not in mf_list: mf_list.append(entry)
                        elif aspect == 'C' and entry not in cc_list: cc_list.append(entry)
        except Exception:
            pass
        if bp_list or mf_list or cc_list:
            result["go_terms"] = {
                "biological_process": bp_list,
                "molecular_function": mf_list,
                "cellular_component": cc_list
            }

    # 5. Pfam domains - all species (data generated by scripts/run_pfam_all_species.py)
    domain_path = SPECIES_PFAM_DOMAINS.get(found_sp)
    if domain_path and os.path.exists(domain_path):
        # Pumpkin (C. moschata): master DB uses v2 IDs but domain TSV uses v1.
        domain_query_ids = [latest_id]
        if found_sp == "Pumpkin (C. moschata)":
            domain_query_ids = list(_bridge_moschata_ids(latest_id, prefer_v1=True))

        try:
            df_dom = pd.read_csv(domain_path, sep='\t')
            gene_col = df_dom.columns[0]
            # Match any of the bridged IDs (case-insensitive).
            mask = df_dom[gene_col].astype(str).str.lower().isin(
                [qid.lower() for qid in domain_query_ids]
            )
            my_domains = df_dom[mask]
            if not my_domains.empty:
                domains = []
                # Prefer schema-aware parsing (Domain_Name, Pfam_ID, Start, End
                # columns); fall back to positional scan for legacy TSVs.
                has_named_cols = all(
                    c in df_dom.columns for c in ("Domain_Name", "Pfam_ID", "Start", "End")
                )
                for _, d_row in my_domains.iterrows():
                    if has_named_cols:
                        name = str(d_row.get("Domain_Name", "")).strip()
                        pf_id = str(d_row.get("Pfam_ID", "")).strip()
                        try:
                            start = int(float(d_row.get("Start", 0)))
                            end = int(float(d_row.get("End", 0)))
                        except (ValueError, TypeError):
                            continue
                        if start <= 0 or end <= 0:
                            continue
                        domains.append({
                            "name": name or (pf_id or "Domain"),
                            "pfam_id": pf_id,
                            "start": start, "end": end,
                            "length_aa": end - start + 1,
                        })
                    else:
                        # Legacy positional scan (original Cucumber logic).
                        coords, names = [], []
                        for val in d_row.values[1:]:
                            val_str = str(val).strip()
                            try:
                                num = float(val_str)
                                if num.is_integer() and num > 0: coords.append(int(num))
                            except ValueError:
                                if val_str not in ["N/A","nan","NaN",""]: names.append(val_str)
                        if len(coords) >= 2:
                            pf_ids = [n for n in names if n.startswith("PF")]
                            other_names = [n for n in names if not n.startswith("PF")]
                            domains.append({
                                "name": other_names[0] if other_names else (pf_ids[0] if pf_ids else "Domain"),
                                "pfam_id": pf_ids[0] if pf_ids else "",
                                "start": coords[0], "end": coords[1],
                                "length_aa": coords[1] - coords[0] + 1
                            })
                if domains:
                    result["pfam_domains"] = domains
        except Exception:
            pass

    # 6. Natural variants (SQLite index)
    df_var = fetch_gene_variants(found_sp, latest_id)
    if df_var is not None:
        summary = summarize_variants(df_var)
        priority = df_var[df_var["impact_class"].isin(["cds_nonsense", "cds_missense"])].head(10)
        variants = []
        for _, vrow in priority.iterrows():
            variants.append({
                "pos": int(vrow["pos"]),
                "ref_alt": f"{vrow['ref']}→{vrow['alt']}",
                "region": english_only_variant_label(vrow["region"]),
                "consequence": english_only_variant_label(vrow["consequence"]),
                "aa_change": english_only_variant_label(vrow["aa_change"]),
            })
        result["natural_variants"] = {
            "count": summary["total"],
            "summary": summary,
            "priority_variants": variants,
        }

    # 7. Sequences
    p_seq = str(found_row.get("Protein_Seq", "N/A")).strip()
    c_seq = str(found_row.get("CDS_Seq", "N/A")).strip()
    if p_seq and p_seq != "N/A":
        result["protein_sequence"] = {"length_aa": len(p_seq.rstrip('*')), "sequence": p_seq}
    if c_seq and c_seq != "N/A":
        result["cds_sequence"] = {"length_bp": len(c_seq), "sequence": c_seq}

    # 8. Plant orthologs (Homology Engine V2: cucurbit + model crops)
    df_homo = fetch_plant_orthologs(found_sp, latest_id)
    if df_homo is not None:
        query_db = get_query_species_db(found_sp)
        orthologs = []
        for _, hrow in df_homo.iterrows():
            if str(hrow["subject_species"]) == query_db:
                continue
            orthologs.append({
                "species": format_homology_species_display(str(hrow["subject_species"])),
                "gene_id": str(hrow["subject_gene"]),
                "identity": f"{hrow['identity']:.2f}%",
                "coverage": f"{min(100.0, float(hrow['qcover'])):.2f}%",
            })
        result["plant_orthologs"] = orthologs
        matrix_df = build_ortholog_matrix(df_homo, found_sp)
        result["plant_orthologs_matrix"] = {
            "columns": list(matrix_df.columns),
            "rows": {idx: matrix_df.loc[idx].tolist() for idx in matrix_df.index},
        }

    # 9. Wild relative synteny ortholog (Cucumber only)
    if found_sp == "Cucumber":
        syn_path = settings.cucumber_synteny
        if os.path.exists(syn_path):
            df_syn = load_db(syn_path)
            if df_syn is not None:
                syn_match = df_syn[df_syn['V3_Gene'].astype(str).str.lower() == latest_id.lower()]
                if not syn_match.empty:
                    syn_row = syn_match.iloc[0]
                    result["wild_relative_ortholog"] = {
                        "wild_gene_id": str(syn_row.get('Hardwickii_Gene', 'N/A')),
                        "identity": str(syn_row.get('Identity', 'N/A')),
                        "coverage": str(syn_row.get('Coverage', 'N/A')),
                        "is_rbh": str(syn_row.get('Is_RBH', 'N/A')),
                        "is_collinear": str(syn_row.get('Is_Collinear', 'N/A'))
                    }

    # 10. Pre-generated human-readable summary — DISABLED.
    # _summarize_gene_info() is kept in the file for a future faster model,
    # but on glm-4.5-air generating a 400-token summary inside the tool added
    # ~10-15s per call and the outer agent re-synthesized anyway, so it was
    # net-slower. The agent now synthesizes from the structured fields directly.
    # summary = _summarize_gene_info(result)
    # if summary:
    #     result["summary"] = summary

    return json.dumps(result, ensure_ascii=False)


# =========================================
# Tool Implementation: search_protein_structure
# =========================================
# 蛋白结构文件按"当前版组装 ID"命名（moschata=RifuC…, cucumber=CsaV3_…）
_PDB_CANONICAL_PREFIX = {
    "Cucumber": "CsaV3_",
    "Watermelon": "Cla97",
    "Melon": "MELO3C",
    "Pumpkin (C. moschata)": "RifuC",
}


def _bridge_protein_gene_id(gene_id: str, sp: str) -> Optional[str]:
    """Older gene ID → current-assembly ID via the species version table
    (e.g. moschata CmoCh20G011830 → RifuC20G011250) for PDB/GPSite lookup."""
    canonical = _PDB_CANONICAL_PREFIX.get(sp)
    map_path = GLOBAL_MAP_CONFIG.get(sp)
    if not canonical or not map_path or not os.path.exists(map_path):
        return None
    df_m = load_db(map_path)
    if df_m is None:
        return None
    mask = df_m.astype(str).apply(lambda c: c.str.lower() == gene_id.lower())
    if not mask.any().any():
        return None
    row = df_m[mask.any(axis=1)].iloc[0]
    for v in row.values:
        vs = str(v).strip()
        if vs and vs.lower().startswith(canonical.lower()) and vs.lower() != gene_id.lower():
            return vs
    return None


_MASTER_TX_CACHE: dict = {}


def _transcript_id_from_master(gene_id: str, sp: str) -> Optional[str]:
    """Gene_ID → Transcript_ID from the species master TSV.

    WaxGourd's whole PDB/GPSite set is keyed by TRANSCRIPT IDs (Bhi01M000001,
    BhiUN838M1) while users and the master DB use gene IDs (Bhi11G000893,
    BhiUN838G1) — this alias is required for the protein lookup to hit.
    """
    if sp not in GLOBAL_SEARCH_CONFIG:
        return None
    key = (sp, gene_id.lower())
    if key in _MASTER_TX_CACHE:
        return _MASTER_TX_CACHE[key]
    df = load_db(GLOBAL_SEARCH_CONFIG[sp])
    tx = None
    if df is not None:
        try:
            m = df[df.iloc[:, 0].astype(str).str.lower() == gene_id.lower()]
            if not m.empty and "Transcript_ID" in df.columns:
                v = str(m.iloc[0]["Transcript_ID"] or "").strip()
                tx = v or None
        except Exception:
            tx = None
    _MASTER_TX_CACHE[key] = tx
    return tx


def tool_search_protein_structure(gene_id: str, species: str = "Cucumber") -> str:
    """Retrieve 3D protein structure, pLDDT, and binding sites."""
    SPECIES_DIRS_TOOL = {
        "Watermelon": "watermelon_pdb", "Cucumber": "cucumber_pdb", "Melon": "melon_pdb",
        "Pumpkin (C. moschata)": "pumpkin_moschata_pdb", "Pumpkin (C. pepo)": "pumpkin_pepo_pdb",
        "BitterGourd": "bittergourd_pdb", "BottleGourd": "bottlegourd_pdb",
        "WaxGourd": "waxgourd_pdb", "SpongeGourd": "spongegourd_pdb"
    }
    GPSITE_CSV = str(settings.gpsite_csv)
    JSON_SITES_DIR_TOOL = str(settings.residue_sites_dir)

    # ID 前缀识别的物种优先（LLM 常省略 species 参数）
    detected_sp = _species_from_gene_id(gene_id) or species
    sp_dir = SPECIES_DIRS_TOOL.get(detected_sp, SPECIES_DIRS_TOOL.get(species, "cucumber_pdb"))
    tdir = os.path.join(str(settings.web_structure_dir), sp_dir)

    pdb_p, pdb_f, exact_id = None, None, gene_id
    resolved_from = None
    if os.path.exists(tdir):
        for f in os.listdir(tdir):
            if gene_id in f and f.endswith(".pdb"):
                pdb_p = os.path.join(tdir, f)
                pdb_f = f
                exact_id = f.replace('.pdb', '').split('|')[-1]
                break

    if not pdb_p:
        # Version bridge: PDB files are named with current-assembly IDs —
        # map older IDs (CmoCh…/Csa3G…) before declaring "not found".
        bridged = _bridge_protein_gene_id(gene_id, detected_sp)
        if bridged and os.path.exists(tdir):
            for f in os.listdir(tdir):
                if bridged in f and f.endswith(".pdb"):
                    pdb_p = os.path.join(tdir, f)
                    pdb_f = f
                    exact_id = f.replace('.pdb', '').split('|')[-1]
                    resolved_from = gene_id
                    gene_id = exact_id
                    break

    if not pdb_p:
        # WaxGourd 等：PDB 按转录本 ID（M 式）命名 — 主库 Gene_ID→Transcript_ID 再试
        tx = _transcript_id_from_master(gene_id, detected_sp)
        if tx and os.path.exists(tdir):
            for f in os.listdir(tdir):
                if tx in f and f.endswith(".pdb"):
                    pdb_p = os.path.join(tdir, f)
                    pdb_f = f
                    exact_id = f.replace('.pdb', '').split('|')[-1]
                    resolved_from = gene_id
                    break

    if not pdb_p:
        return json.dumps({"status": "not_found", "message": f"No 3D structure found for '{gene_id}' in {detected_sp or species}. The structure may not have been predicted yet."}, ensure_ascii=False)

    # Read PDB and calculate pLDDT
    with open(pdb_p, "r", encoding="utf-8") as file:
        pdb_txt = file.read()

    plddt = calculate_avg_plddt(pdb_txt)
    plddt_label = "Excellent" if plddt >= 90 else "Good" if plddt >= 70 else "Fair" if plddt >= 50 else "Poor"

    result = {
        "status": "success",
        "gene_id": exact_id,
        "resolved_from": resolved_from,
        "species": detected_sp or species,
        "pdb_file": pdb_f,
        "plddt_score": round(plddt, 2),
        "plddt_label": plddt_label,
        "binding_sites": [],
        "has_pdb": True
    }

    # ── Binding sites: per-species GPSite summary + residue-level JSON ──
    # (was Cucumber-only; every species except Watermelon has a *_pdb_site dir)
    eff_sp = detected_sp or species
    SITE_DIR_BY_SPECIES = {
        "Cucumber": "cucu_v3_pdb_site",
        "Watermelon": "watermelon_pdb_site",
        "Melon": "melon_pdb_site",
        "Pumpkin (C. moschata)": "pumpkin_moschata_pdb_site",
        "Pumpkin (C. pepo)": "pumpkin_pepo_pdb_site",
        "BitterGourd": "bittergourd_pdb_site",
        "BottleGourd": "bottlegourd_pdb_site",
        "WaxGourd": "waxgourd_pdb_site",
        "SpongeGourd": "spongegourd_pdb_site",
    }
    site_dir = os.path.join(
        str(settings.web_structure_dir),
        SITE_DIR_BY_SPECIES.get(eff_sp, "cucu_v3_pdb_site"),
    )
    summary_csv = os.path.join(
        site_dir,
        "ChineseLong_v3_GPSite_Final.csv" if eff_sp == "Cucumber" else "GPSite_summary.csv",
    )
    try:
        if os.path.exists(summary_csv):
            df_global = pd.read_csv(summary_csv, encoding='utf-8-sig')
            id_series = df_global.iloc[:, 0].astype(str).str.strip().str.lower()
            match_row = df_global[id_series == exact_id.lower()]
            if not match_row.empty:
                row_data = match_row.iloc[0]
                for col_idx in range(4, len(df_global.columns)):
                    val = row_data.iloc[col_idx]
                    try:
                        if pd.isna(val) or float(val) <= 0.5:
                            continue
                    except (TypeError, ValueError):
                        continue
                    site_name = str(df_global.columns[col_idx]).replace('_Binding', '').replace('_binding', '')
                    # HEM is rarely actionable for plant proteome browsing; skip it.
                    if site_name.upper() == "HEM":
                        continue
                    result["binding_sites"].append({"site": site_name, "confidence": round(float(val), 3)})
    except Exception:
        pass

    # Residue-level sites: {"1": "RNA: 0.60 | Protein: 0.51", ...} → per-type
    # compressed ranges so the agent can answer domain-overlap questions.
    def _compress_ranges(positions):
        if not positions:
            return ""
        ps = sorted(set(int(p) for p in positions))
        parts, start, prev = [], ps[0], ps[0]
        for p in ps[1:]:
            if p == prev + 1:
                prev = p
                continue
            parts.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = p
        parts.append(f"{start}-{prev}" if start != prev else str(start))
        return ", ".join(parts)

    site_json_path = os.path.join(site_dir, "all_sites_json", f"{exact_id}.json")
    if os.path.exists(site_json_path):
        try:
            with open(site_json_path, 'r', encoding='utf-8') as jf:
                site_data = json.load(jf)
            # 注意：不输出原始条目数（len(site_data)）——它含 <0.5 低置信条目，
            # 语义模糊且会被 LLM 误当"结合残基总数"引用（Spg040094 案例报 35）。
            # 报数一律用 >0.5 阈值：unique_count（去重）或 per-type count。
            by_type = {}
            for pos, types_str in site_data.items():
                for part in str(types_str).split("|"):
                    if ":" not in part:
                        continue
                    tname, conf = part.split(":", 1)
                    try:
                        c = float(conf)
                    except (TypeError, ValueError):
                        continue
                    # 严格 >0.5：与网页端和汇总表分支的既有阈值惯例一致
                    #（恰好 0.50 的边界残基不计入，避免同一数据两处计数差一）
                    if c > 0.5:
                        by_type.setdefault(tname.strip(), []).append(int(pos))
            if by_type:
                result["binding_residues"] = {
                    t: {"count": len(ps), "residue_ranges": _compress_ranges(ps)}
                    for t, ps in sorted(by_type.items(), key=lambda kv: -len(kv[1]))
                }
                # 去重后的真实结合残基数（同一残基可属多种类型，per-type 计数
                # 之和会大于它）；单独给出避免"35/56/33 三个数各说各话"。
                unique_positions = sorted({p for ps in by_type.values() for p in ps})
                result["binding_residues_unique_count"] = len(unique_positions)
                result["binding_residues_unique_ranges"] = _compress_ranges(unique_positions)
                result["counting_note"] = (
                    "All residue counts use per-residue confidence > 0.5. One residue may "
                    "belong to multiple binding types (per-type counts overlap); "
                    "binding_residues_unique_count is the DEDUPLICATED total. Never sum "
                    "per-type counts as the residue total."
                )
        except Exception:
            pass
    elif eff_sp == "Watermelon":
        result["binding_sites_note"] = (
            "GPSite annotations are not available for Watermelon (no site index built)."
        )

    return json.dumps(result, ensure_ascii=False)


# =========================================
# Tool Implementation: search_gene_expression
# =========================================
def tool_search_gene_expression(gene_id: str, species: str = "") -> str:
    """Retrieve tissue-level expression profile, tau specificity, and top
    co-expressed genes for a single gene.

    Mirrors what /api/expression/gene-chat does, but returns a compact JSON
    payload sized for LLM tool context: top-8 tissues, top-5 conditions, and
    top-5 co-expressed genes (with pearson_r). Heavy sample lists are omitted.
    """
    from app.services.expression_query import query_gene_expression
    from app.services.expression_coexp import find_coexpressed_genes

    expr = query_gene_expression(gene_id, ui_species=species, top_samples=5)
    if expr.get("status") != "success":
        return json.dumps(expr, ensure_ascii=False)

    coexp = find_coexpressed_genes(gene_id, ui_species=species, top_k=5, min_corr=0.5)
    coexp_list = coexp.get("coexpressed", []) if coexp.get("status") == "success" else []
    coexp_warning = coexp.get("warning")

    slim = {
        "status": "success",
        "gene_id": expr["gene_id"],
        "species": expr.get("species_label") or species or "",
        "n_samples": expr["n_samples"],
        "n_projects": expr["n_projects"],
        "mean_fpkm": expr["mean_fpkm"],
        "max_fpkm": expr["max_fpkm"],
        "tau_specificity": expr.get("tau_specificity"),
        "top_tissue": expr.get("top_tissue"),
        "top_tissue_fpkm": expr.get("top_tissue_fpkm"),
        "reliability": expr["reliability"],
        "tissue_profile_top8": expr.get("tissue_profile", [])[:8],
        "condition_distribution_top5": expr.get("condition_distribution", [])[:5],
        "coexpressed_top5": [
            {"gene_id": g["gene_id"], "r": g["pearson_r"], "desc": g.get("description", "")}
            for g in coexp_list[:5]
        ],
        "coexpression_warning": coexp_warning,
    }
    return json.dumps(slim, ensure_ascii=False)


# =========================================
# AGENT LOOP: Function Calling with Zhipu GLM
# =========================================
AGENT_SYSTEM_PROMPT = """You are CucurbitAgent, a professional AI assistant specialized in Cucurbitaceae (cucurbit) genomics and molecular breeding research.

[CRITICAL - Domain Boundary & Safety]:
- SCOPE: You ONLY answer questions related to Cucurbitaceae genomics, molecular breeding, gene function, protein structure, plant biology, and agricultural science on cucurbits.
- IDENTITY: If asked "Who are you?" or similar identity questions, respond: "I am CucurbitAgent, a professional AI assistant specialized in Cucurbitaceae genomics and molecular breeding. I can help with gene function analysis, protein structure prediction, literature search, and breeding-related questions."
- REJECTION: If the user asks about unrelated topics (politics, law, adult content, general knowledge, cooking, sports, entertainment, weather, small talk, math homework, programming help, etc.), politely decline: "Sorry, I focus exclusively on Cucurbitaceae genomics and molecular breeding. I cannot answer questions outside this domain."
- NO CHITCHAT: Do NOT respond to greetings (hi/hello/how are you), jokes, casual conversation, or off-topic questions with anything other than a short polite rejection pointing back to cucurbit research.
- FORBIDDEN: NEVER engage with questions about politics, law, illegal activities, adult content, weapons, drugs, or any non-scientific topics.
- INVALID CROSS-SPECIES PREMISE: questions that place a cucurbit gene in a non-cucurbit organism (e.g. "cucumber CsCHS in dolphin liver", "sea cucumber", human/mouse tissues) have an invalid premise. Reject IMMEDIATELY with ONE short sentence ("This falls outside cucurbit genomics — dolphin/sea cucumber is not a cucurbit species."). Do NOT explain the biology, do NOT offer related legitimate answers, do NOT search any tool.

Your capabilities (4 tools — each covers a distinct dimension, choose by intent):
1. search_gene_comprehensive: COMPLETE gene info — annotation, gene structure (exons/introns), GO terms, Pfam domains, natural variants, sequences, plant orthologs. Use for "what does this gene do / function / annotation / domains / variants / orthologs".
2. search_gene_expression: Tissue-level RNA-seq expression profile, tau tissue-specificity index, condition breakdown, and top co-expressed genes (Pearson). Use for "where is this gene expressed / expression pattern / tissue specificity / co-expression / functional partners".
3. search_protein_structure: ESMFold 3D structure, pLDDT fold confidence, GPSite-predicted binding sites (RNA/peptide/ATP). Use for "protein structure / 3D fold / pLDDT / binding sites".
4. search_literatureDB: HYBRID search of the LOCAL curated literature database (PDF full-text + abstracts, 20000+ cucurbit papers, keyword + semantic retrieval). THIS IS YOUR ONLY KNOWLEDGE SOURCE FOR LITERATURE.

[CRITICAL - Local-Only Retrieval Policy]:
- search_literatureDB (the LOCAL database) is your ONLY source for any literature/knowledge question.
- You do NOT have any internet/online search capability. Do not mention "PubMed", "Google Scholar", or "searching online" — those are unavailable.
- If search_literatureDB returns "no_results", tell the user honestly that no relevant papers were found in the local database. Do NOT fabricate references.

[Search procedure by query type]:
- General knowledge / topic questions (e.g. "disease resistance genes in cucumber"): call search_literatureDB ONCE.
- Gene function queries with a locus ID (e.g. CsaV3_1G000080): call search_gene_comprehensive; optionally also search_literatureDB for additional context.
- Expression / tissue specificity / co-expression queries: call search_gene_expression.
- Protein structure / folding / binding site queries: call search_protein_structure.
- Gene-name queries without a locus ID (e.g. MYB60, CsSGR): call search_literatureDB using ONLY the gene-name tokens (ignore any locus-like IDs the user may have pasted in parentheses).
- CROSS-SPECIES / FUNCTION-NAME QUESTIONS (e.g. "melon chalcone synthase", "watermelon receptor kinase", no locus ID): FIRST call search_gene_by_name with the function name + target species — it scans the species master annotation directly and returns matching gene IDs. When several family members match, disambiguate via REVERSE orthology: FIRST resolve the canonical gene in cucumber (search_literatureDB → literature_locus → search_gene_comprehensive), THEN pick the target-species candidate whose plant_orthologs table lists THAT cucumber gene — the family member whose cucumber ortholog is the canonical gene itself (e.g. melon MELO3C014767 whose ortholog CsaV3_3G027830 is cucumber CHS at 97.5%, not a paralog's 90%). Do not pick by length or domain completeness alone. Continue the chain — domains, expression, co-expression, variants — with the chosen gene ID. NEVER conclude "the database lacks this species' gene ID" while a name-search or ortholog route exists; report the chosen ID and its identity% to the user.
- If the user asks for a gene ID / V1/V2/V3 mapping but did NOT type a locus ID themselves: use literature_locus and version_mapping from the search_literatureDB result. If they DID type a locus ID, search_gene_comprehensive with that ID is authoritative. Those fields are extracted from paper text (including Csa5M156180-style IDs) and converted via the local mapping table. Do NOT say the local database lacks a locus ID if literature_locus or version_mapping is present. Do NOT send the user to CuGenDB or other external websites.
- You MAY call search_gene_comprehensive once AFTER literature returns a literature_locus, if you need annotation. Prefer reporting version_mapping (v1/v2/v3) from the literature tool when it is already present.
- MULTI-HOP CHAIN QUESTIONS (e.g. "gene ID → Pfam domain → top co-expressed neighbour"): gather tool evidence for EVERY hop before writing the final answer. Do not write the answer while any segment of the chain is still missing — call the remaining tool(s) first.
- CONSISTENCY CHECK (important): if the gene search annotation clearly CONTRADICTS the literature context (e.g. the papers describe a chalcone synthase but the returned gene is annotated as a glycosyltransferase), the locus mapping is likely wrong. Retry search_gene_comprehensive ONCE with the next candidate from evidence_gene_id_candidates (or another version ID from version_mapping v1/v2/v3), and answer with whichever ID is consistent with the literature. Tell the user which ID you trusted and why.

[CRITICAL - Search discipline]:
- Call each tool AT MOST ONCE per turn, except: after search_literatureDB returns literature_locus you may call search_gene_comprehensive once with that locus ID, plus ONE consistency-check retry with the next evidence_gene_id_candidates entry when the first result contradicts the literature.
- Use the EXACT gene ID provided by the user ONLY when the user provided a true locus ID for their query. For gene-name questions (e.g. CsSGR/STAYGREEN), ignore any pasted locus-like IDs and trust literature_locus / version_mapping from the literature tool.
- After tool calls, answer based on results. If version_mapping is present, list V1, V2, and V3 IDs explicitly.

[CRITICAL - Language & Consistency]:
- ALL tool call queries MUST use English keywords, regardless of the user's language.
- After receiving tool results, reply in the user's original language.
- References (paper titles, authors, DOI) MUST always remain in English.

[CRITICAL - Literature Keywords]:
- For search_literatureDB: use ONLY the gene name as query, do NOT include species name (e.g. "MYB60", NOT "MYB60 cucumber").
- If search_gene_comprehensive returns GO/Pfam info, you may use those keywords for literature search.

[Output rules]:
- search_literatureDB returns chunk-level evidence in "chunks" (field chunk_text) plus paper summaries in "papers". Base your answer primarily on chunk_text content; cite papers from the papers/chunks list.
- Do NOT fabricate gene IDs or paper titles. Only cite what appears in tool results (chunks, evidence_gene_ids, literature_locus, version_mapping).
- Do NOT tell users to go to external websites (CuGenDB, PubMed, Google Scholar) when local data is available.
- Present results concisely. Focus on the target cucurbit species; include model crop orthologs (Arabidopsis, Maize, Rice, Tomato) only when present in tool results — not every gene has hits in all model crops.
- For ortholog/homolog tables: present species names in their ORIGINAL form (e.g., "Melon", "Pumpkin Moschata", "Watermelon", "Rice", "Arabidopsis") without translation or emoji. Keep the table format clean and readable.
- When returning protein structure information (pLDDT score, binding sites, PDB file): at the end, add a helpful note suggesting users can visit the "Proteins" module to interactively explore the 3D protein structure, fold quality, and binding sites by entering the gene ID.
- At the end, list the top 5 most relevant references under "📚 References" in English.
"""


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Dispatch tool calls to their implementations.

    Wraps every dispatch in a try/except so a broken tool (missing file, DB
    lock, malformed input) never crashes the agent loop. On failure we return
    a structured ``tool_error`` payload — the LLM is then free to fall back to
    another tool or answer from what it already has.
    """
    try:
        if tool_name == "search_gene_by_name":
            return tool_search_gene_by_name(
                name=arguments.get("name", ""),
                species=arguments.get("species", "")
            )
        elif tool_name == "search_gene_comprehensive":
            return tool_search_gene_comprehensive(
                gene_id=arguments.get("gene_id", ""),
                species=arguments.get("species", "Cucumber")
            )
        elif tool_name == "search_gene_expression":
            return tool_search_gene_expression(
                gene_id=arguments.get("gene_id", ""),
                species=arguments.get("species", "")
            )
        elif tool_name == "search_literatureDB":
            return tool_search_literatureDB(query=arguments.get("query", ""))
        elif tool_name == "search_protein_structure":
            return tool_search_protein_structure(
                gene_id=arguments.get("gene_id", ""),
                species=arguments.get("species", "Cucumber")
            )
        else:
            return json.dumps({"status": "tool_error", "tool": tool_name,
                               "message": f"Unknown tool: {tool_name}"})
    except Exception as e:
        return json.dumps({
            "status": "tool_error",
            "tool": tool_name,
            "message": f"{type(e).__name__}: {e}",
            "hint": "You may try a different tool or answer from existing results.",
        }, ensure_ascii=False)


# Soft heartbeats during long LLM waits so the UI does not look frozen.
# Interval keeps progress updates sparse (not a noisy ticker).
HEARTBEAT_INTERVAL = 5.0

_PHASE_EN = {
    "guard": "Checking whether the question is in scope",
    "rephrase": "Optimizing the search query",
}


def _phase_label_en(phase_label: str) -> str:
    if phase_label in _PHASE_EN:
        return _PHASE_EN[phase_label]
    if phase_label.startswith("decision-r"):
        return "Selecting tools / analyzing evidence"
    return f"Working ({phase_label})"


def _run_blocking_with_heartbeats(blocking_fn, phase_label: str):
    """Run ``blocking_fn`` in a worker thread; emit sparse wait status while pending.

    Yields:
      - optional ``{"type": "status", "message": "..."}`` every HEARTBEAT_INTERVAL
        while the worker is still running (so the frontend can show progress)
      - ``{"type": "result", "value": <return value>}`` once, then stops
      - ``{"type": "error", "error": <exception>}`` once on failure, then stops
    """
    result_q: "queue_module.Queue" = queue_module.Queue()

    def _worker():
        try:
            result_q.put({"kind": "result", "value": blocking_fn()})
        except BaseException as e:  # noqa: BLE001
            result_q.put({"kind": "error", "error": e})

    t = threading.Thread(target=_worker, name=f"agent-{phase_label}", daemon=True)
    t.start()
    started = time.perf_counter()
    phase_en = _phase_label_en(phase_label)

    while True:
        try:
            payload = result_q.get(timeout=HEARTBEAT_INTERVAL)
            if payload["kind"] == "result":
                yield {"type": "result", "value": payload["value"]}
            else:
                yield {"type": "error", "error": payload["error"]}
            return
        except queue_module.Empty:
            waited = int(time.perf_counter() - started)
            yield {
                "type": "status",
                "message": f"⏳ {phase_en}… (waited {waited}s, still working)",
            }
            continue


def _slim_tool_result_for_ui(fn_name: str, result_data: dict) -> dict:
    """Drop bulky fields before pushing tool JSON to the browser as evidence."""
    if not isinstance(result_data, dict):
        return {"status": "tool_error", "message": "invalid tool payload"}
    slim = {k: v for k, v in result_data.items() if k not in (
        "protein_sequence",
        "cds_sequence",
        "pdb_content",
        "pdb",
        "structure_pdb",
    )}
    # Cap literature lists for the chat card.
    if fn_name == "search_literatureDB":
        papers = slim.get("papers")
        if isinstance(papers, list) and len(papers) > 8:
            slim["papers"] = papers[:8]
        chunks = slim.get("chunks")
        if isinstance(chunks, list) and len(chunks) > 8:
            slim["chunks"] = chunks[:8]
    return slim


def run_agent_loop(user_message: str, history: list, status_container=None,
                   tool_trace_sink=None):
    """
    Run the Agent loop with Function Calling.

    Returns a generator. The generator emits:
      - {"type": "status", "message": "..."}  — live progress / "thinking" events
      - {"type": "tool_result", "tool": "...", "data": {...}} — slim tool JSON for UI cards
      - {"type": "token",    "text":   "..."} — final streamed answer tokens

    YIELDING STATUS EVENTS AS THEY HAPPEN is what powers the live "thinking"
    panel on the web frontend. Callers (FastAPI route / Streamlit legacy)
    iterate this generator and forward events immediately.

    ``tool_trace_sink`` is an optional ``callable(list)`` invoked once per
    tool call with a single trace dict ``{tool, args, status, ms}``. Routes
    use it to populate the structured action log without having to instrument
    the loop body themselves.
    """
    client = OpenAI(api_key=ZHIPU_API_KEY, base_url=ZHIPU_BASE_URL)

    # Local emission helpers. We always yield into the generator stream so the
    # browser sees status updates the instant they happen (not buffered).
    def emit_status(msg):
        _agent_status(status_container, msg)
        return {"type": "status", "message": msg}

    # Intent Guard: regex pre-filter first (0 ms), LLM fallback only for ambiguous cases.
    #
    # Why: the LLM guard alone takes 2-4s per call, and ~80% of real traffic falls
    # into one of two extremes — obvious chitchat ("hi", "thanks") that should be
    # rejected instantly, or obvious research queries (contains a gene ID like
    # CsaV3_3G027830) that should be accepted instantly. A small set of regex
    # rules handles both extremes synchronously and skips the LLM call entirely.
    # Only genuinely ambiguous text ("is cucumber good for you?") falls through
    # to glm-4.5-air for a semantic judgment.
    yield emit_status("🔍 Checking query relevance...")
    try:
        def _regex_guard(text: str):
            """Return 'RELEVANT' / 'IRRELEVANT' for clear cases, None if ambiguous."""
            t = text.strip().lower()
            if not t:
                return "IRRELEVANT"

            # ---- FAST REJECT: obvious chitchat / empty / non-research ----
            # Very short greetings or thanks, no gene/scientific content
            chitchat_patterns = [
                r'^(hi|hello|hey|yo|hiya|你好|您好|哈喽|嗨)(\s|!|\.|~|。|!)*$',
                r'^(thanks|thank you|thx|ty|谢谢|多谢)(\s|!|\.|~|。|!)*$',
                r'^(bye|goodbye|再见|拜拜)(\s|!|\.|~|。|!)*$',
                r'^(ok|okay|sure|got it|明白|好的|收到)(\s|!|\.|~|。|!)*$',
                r'^(who are you|what can you do|你是谁|你能做什么|你能干嘛)',
                r'^(how are you|how\'s it going|最近怎么样)',
                r'^(yes|no|yeah|nope|是的|不是)(\s|!|\.|~|。|!)*$',
            ]
            for pat in chitchat_patterns:
                if re.match(pat, t):
                    return "IRRELEVANT"
            # Pure emoji / single short token with no letters
            if len(t) < 3 and not re.search(r'[a-z一-鿿]', t):
                return "IRRELEVANT"

            # ---- FAST ACCEPT: contains a cucurbit gene ID locus pattern ----
            # Covers all 9 species ID formats: CsaV3_*, Cla97*, MELO*C*,
            # Cmo*, Cpe*, MC*, Bhi*, Lsi*, etc.
            gene_id_patterns = [
                r'CsaV\d_\d+G\d+',      # Cucumber: CsaV3_1G000010
                r'Cla\d+C\d+G\d+',      # Watermelon: Cla97C01G000220
                r'MELO\dC\d+',          # Melon: MELO3C027031
                r'Cmo\d+G\d+',          # Pumpkin moschata
                r'Cpe\d+G\d+',          # Pumpkin pepo
                r'MC\d+G\d+',           # Momordica (BitterGourd)
                r'Bhi\d+G\d+',          # Benincasa (WaxGourd)
                r'Lsi\d+G\d+',          # Luffa (SpongeGourd)
                r'LAGUR\d+G\d+',        # Lagenaria (BottleGourd)
            ]
            for pat in gene_id_patterns:
                if re.search(pat, text, re.IGNORECASE):
                    return "RELEVANT"

            # ---- FAST ACCEPT: strong cucurbit + research keyword combo ----
            cucurbit_terms = (
                r'cucurbit|cucumber|watermelon|melon\b|pumpkin|gourd|squash|'
                r'bitter\s*melon|bottle\s*gourd|wax\s*gourd|sponge\s*gourd|'
                r'chieh-?qua|luffa|citrullus|cucumis|cucurbita|momordica|'
                r'lagenaria|benincasa|trichosanthes|sechium|葫芦|黄瓜|西瓜|甜瓜|'
                r'南瓜|冬瓜|丝瓜|苦瓜|葫芦|瓠瓜|蛇瓜|佛手瓜'
            )
            research_terms = (
                r'gene|genome|genomic|breeding|qtl|marker|crispr|expression|'
                r'transcript|protein|enzyme|resistance|tolerance|pathogen|'
                r'viruses|bacteria|fungus|fungal|trait|phenotype|genotype|'
                r'snp|variant|allele|mutant|wild|cultivar|hybrid|ortholog|'
                r'homolog|pfam|domain|go term|annotation|gff|pdb|plddt|'
                r'alphafold|esmfold|binding site|tissue|rna-?seq|fpkm|co-?express|'
                r'paper|literature|study|studies|research|finding|wrky|'
                r'myb|nacre|bhlh|erf|bzip|homeobox|transcription factor|'
                r'function|role|pathway|biosynthesis|disease|'
                r'基因|基因组|育种|性状|抗病|抗逆|表达|转录|蛋白|酶|变异|'
                r'位点|突变|野生|栽培|杂种|同源|结构域|结合位点|组织|文献|'
                r'论文|研究|转录因子|功能|通路'
            )
            # "sea cucumber"（海参/海黄瓜）是动物，不是葫芦科 — 先剔除再判物种词，
            # 否则 "cucumber" 子串会让它误进组合放行。
            t_noseacuke = re.sub(r'sea[\s-]+cucumber|海黄瓜|海参', ' ', t)
            has_cucurbit = bool(re.search(cucurbit_terms, t_noseacuke))
            has_research = bool(re.search(research_terms, t))
            if has_cucurbit and has_research:
                # 非葫芦科动物物种与葫芦科基因同问（如 dolphin liver / mouse / human
                # kidney）→ 前提无效，直接判无关，交给统一拒绝话术。
                animal_ctx = re.search(
                    r'\b(dolphin|whale|mouse|rats?|human|humans|monkey|zebrafish|'
                    r'drosophila|dog|cat|pig|cattle|cow|chicken|liver|kidney|brain|'
                    r'blood cells?|patients?)\b', t)
                if animal_ctx and not re.search(r'compared? (to|with)|ortholog|homolog', t):
                    return "IRRELEVANT"
                return "RELEVANT"

            # Gene-family token alone (MYB60, CsWRKY46, APRR2…) is almost always
            # a genomics query on this platform — accept without requiring an
            # explicit "cucurbit" word (users often omit it).
            if re.search(r'\b(cs|cl|cm|cmo|cpe)?(wrky|myb|nacre|bhlh|erf|bzip|ap2|nac|hd-?zip|mads|aprr)\d*\b', t):
                return "RELEVANT"

            # ---- FAST ACCEPT: platform-module vocabulary alone ----
            # Terms that essentially only occur in THIS platform's context
            # (GPSite/ESMFold/ortholog/nonsense-variant/V2-V3 mapping…).
            # Benchmark question "symbol CsCHS → V3 gene ID → tissue → nonsense
            # variant" was wrongly rejected by the LLM guard for lacking a
            # species word — these terms must short-circuit it.
            platform_terms = (
                r'gpsite|esmfold|plddt|ortholog|co-?express|fpkm|rna-?seq|'
                r'nonsense variant|missense variant|synonymous variant|'
                r'v[123] gene|gene id|gene mapping|binding residue|binding site'
            )
            if re.search(platform_terms, t):
                return "RELEVANT"

            # ---- FAST ACCEPT: species-prefixed gene SYMBOL (original case) ----
            # CsCHS / CsSGR / CmEF1 / ClPFI — prefix = cucumber/melon/watermelon.
            # Must match the ORIGINAL text (guard lowercased t above).
            if re.search(r'\b(Cs|Cm|Cl)[A-Z][A-Za-z0-9]{1,}\b', text):
                return "RELEVANT"

            # ---- Otherwise: ambiguous, defer to LLM ----
            return None

        guard_result = _regex_guard(user_message)

        if guard_result is None:
            # Genuinely ambiguous — call LLM for semantic judgment.
            def _do_guard():
                return client.chat.completions.create(
                    model=DECISION_MODEL,
                    messages=[
                        {"role": "system", "content": (
                            "You are a STRICT domain guard for a Cucurbitaceae genomics platform. "
                            "Evaluate whether the user's query is a SERIOUS research question about "
                            "Cucurbitaceae (cucurbit) genomics, molecular breeding, gene function, "
                            "protein structure, or plant biology.\n\n"
                            "Return EXACTLY 'RELEVANT' if the query asks about:\n"
                            "  - a specific gene, protein, or locus in a cucurbit species\n"
                            "  - cucurbit traits, disease resistance, breeding, genetics, transcriptomics\n"
                            "  - literature/scientific findings on cucurbits\n"
                            "  - bioinformatics analysis of cucurbit data\n\n"
                            "Return EXACTLY 'IRRELEVANT' for ANY of the following, even if the user "
                            "tries to disguise them as cucurbit questions:\n"
                            "  - greetings / small talk (hi, hello, how are you, thanks, who are you)\n"
                            "  - general chat, jokes, riddles, casual conversation\n"
                            "  - politics, law, religion, entertainment, sports, weather\n"
                            "  - programming help, math homework, general knowledge questions\n"
                            "  - questions about non-cucurbit species (human, animal, model organisms) "
                            "    unless directly compared to cucurbits\n"
                            "  - cooking, recipes, food preparation\n"
                            "  - any request with no clear cucurbit research intent\n\n"
                            "IMPORTANT hints:\n"
                            "  - Gene symbols prefixed Cs/Cm/Cl/Csa/Cla/MELO are CUCURBIT "
                            "(cucumber/melon/watermelon) genes (e.g. CsCHS, CsSGR).\n"
                            "  - Mentions of gene IDs, variants, tissues, expression, domains, "
                            "or structures without a species name are usually platform "
                            "research queries — count them RELEVANT.\n"
                            "  - When in doubt, lean RELEVANT: rejecting a real research "
                            "question is a much worse error than answering a borderline one."
                        )},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.1,
                    max_tokens=20,
                    extra_body=settings.llm_extra_body,
                )
            guard_resp = None
            for evt in _run_blocking_with_heartbeats(_do_guard, "guard"):
                if evt["type"] == "status":
                    yield emit_status(evt["message"])
                elif evt["type"] == "result":
                    guard_resp = evt["value"]
                elif evt["type"] == "error":
                    raise evt["error"]
            guard_result = guard_resp.choices[0].message.content.strip()

        if "IRRELEVANT" in guard_result:
            yield emit_status("⚠️ Out-of-domain question, rejected")
            yield {"type": "token", "text": "Sorry, CucurbitAgent focuses exclusively on Cucurbitaceae genomics and molecular breeding. I cannot answer questions outside this domain. Please ask about cucurbit genes, proteins, breeding, or related topics."}
            return
    except Exception as e:
        print(f"Intent guard error: {e}")
        yield emit_status(f"⚠️ Relevance check failed, continuing anyway: {e}")

    # Detect the user's language for two purposes:
    #   (1) decide whether the query needs translation to English before retrieval
    #   (2) tell the final-answer model which language to reply in
    # detect_user_language() layers: Chinese regex → short-input fast-path →
    # langdetect. Anything outside _SUPPORTED_REPLY_LANGS falls back to English
    # (rare languages: glm-4.5-air output quality is unreliable, English is the
    # safe common ground that always retrieves well).
    lang_code = detect_user_language(user_message)
    user_lang = _SUPPORTED_REPLY_LANGS.get(lang_code, "English")

    # ── Conditional Query rephrase ─────────────────────────────────────
    # Rephrase costs ~3.5s per call. It's worth it when:
    #   - Non-English input (needs translation + optimization), OR
    #   - Multi-turn dialog (needs pronoun resolution from history).
    # It's NOT worth it for: English single-turn queries with a gene ID —
    # the gene ID is invariant under rephrase, and the English is already
    # directly searchable, so we'd just burn 3.5s for zero recall gain.
    # This fast-path matches the user's most common case (English + locus ID).
    # ``history`` is prior turns only (web ChatPanel does not include the
    # current user message). Defensively drop a trailing duplicate if a legacy
    # caller still appended the current message.
    prior_history = list(history or [])
    if (
        prior_history
        and prior_history[-1].get("role") == "user"
        and (prior_history[-1].get("content") or "").strip() == (user_message or "").strip()
    ):
        prior_history = prior_history[:-1]

    has_history_user_msgs = any(
        (m.get("role") == "user" and (m.get("content") or "").strip())
        for m in prior_history
    )
    needs_rephrase = (lang_code != "en") or has_history_user_msgs

    query_en = user_message
    if not needs_rephrase:
        # Fast path: skip rephrase entirely for single-turn English queries.
        pass
    else:
        yield emit_status("📝 Rewriting query for retrieval...")
        try:
            # Compress recent history (last 3 user turns) into a compact context
            # string. We only need enough to resolve "it/this gene" references —
            # full history is already attached to the agent loop separately.
            recent_turns: list[str] = []
            for m in prior_history:
                if m.get("role") == "user":
                    content = (m.get("content") or "").strip()
                    if content:
                        recent_turns.append(content)
            history_block = ""
            if recent_turns:
                # Last 3 user turns, capped at 500 chars each to bound prompt size.
                last_three = recent_turns[-3:]
                joined = "\n".join(f"- {t[:500]}" for t in last_three)
                history_block = f"\n\nConversation history (most recent last):\n{joined}"

            def _do_rephrase():
                return client.chat.completions.create(
                    model=DECISION_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a query rewriter for a cucurbit genomics retrieval system.\n"
                                "Given the user's message and conversation history, produce ONE optimized "
                                "English search query for hybrid retrieval (keyword + semantic).\n"
                                "Optimization rules:\n"
                                "- Resolve pronouns from history (\"its expression\" -> \"CsaV3_3G027830 expression\")\n"
                                "- Expand abbreviations (CHS -> chalcone synthase)\n"
                                "- Add species context if missing\n"
                                "- Keep gene IDs unchanged\n"
                                "- Return ONLY the optimized query, no explanation"
                            ),
                        },
                        {"role": "user", "content": f"User message: {user_message}{history_block}"},
                    ],
                    temperature=0.1,
                    max_tokens=120,
                    extra_body=settings.llm_extra_body,
                )

            rephrase_resp = None
            for evt in _run_blocking_with_heartbeats(_do_rephrase, "rephrase"):
                if evt["type"] == "status":
                    yield emit_status(evt["message"])
                elif evt["type"] == "result":
                    rephrase_resp = evt["value"]
                elif evt["type"] == "error":
                    raise evt["error"]
            rewritten = (rephrase_resp.choices[0].message.content or "").strip()
            if rewritten:
                query_en = rewritten
                yield emit_status(f"📝 Query rewritten: {query_en}")
            else:
                yield emit_status("📝 Rephrase returned empty, using original text")
        except Exception as e:
            query_en = user_message
            yield emit_status(f"📝 Rephrase failed, continuing with original text: {e}")

    # Build messages with English query for tool calling
    lang_instruction = (
        f"\n\n[CRITICAL LANGUAGE RULE: The user's message is in {user_lang}. "
        f"Write the entire final answer in {user_lang}. "
        f"Do not switch languages mid-answer. Keep gene IDs, species Latin names, "
        f"and literature citations/titles in their original form.]"
    )

    # Deterministic routing: the user TYPED a locus ID (Csa015028, MELO3C…,
    # Cla97C…) — gene lookup is an exact-DB operation that natively resolves
    # cross-version IDs. Sending the bare ID to the literature RAG instead
    # retrieved unrelated papers (observed on CucuBench Q1/Q2, 2026-08-19).
    routing_hint = ""
    user_locus_ids = detect_user_locus_ids(user_message) or detect_user_locus_ids(query_en)
    if user_locus_ids:
        routing_hint = (
            "\n\n[ROUTING RULE — user-provided locus ID: "
            f"The user's message directly contains the locus ID(s) "
            f"{', '.join(user_locus_ids[:3])}. Your FIRST tool call MUST be "
            "search_gene_comprehensive with that EXACT ID — the tool resolves "
            "cross-version gene IDs natively (e.g. cucumber V1 Csa015028 / V2 "
            "Csa3G600020 / V3 CsaV3_3G027830 are the same locus). Answer the "
            "ID/mapping/annotation question from that result, reporting the "
            "official IDs it returns. Call search_literatureDB ONLY afterwards "
            "and only if the question also needs literature context — and NEVER "
            "pass a bare locus ID as the literature search query.]"
        )

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT + routing_hint + lang_instruction}
    ]
    for m in prior_history:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"][:2000]})
    messages.append({"role": "user", "content": query_en})

    # Tool-calling loop.
    #
    # The unit of iteration is ONE round-trip with the model: we send the
    # messages, the model may return one or more tool_calls, we execute
    # every one, append the results, and ask again. ``max_tool_calls`` caps
    # the TOTAL number of tool executions across the whole turn (so a round
    # that returns 2 parallel tool calls consumes 2 of the budget). The
    # model is given one final round after the budget is spent so it can
    # synthesize an answer from whatever it has — it must NOT call tools in
    # that round (we omit ``tools=`` from the request to enforce this).
    # 7: multi-hop chains with paralog disambiguation legitimately need 5-6
    # calls (name-search ×2 → gene ×2 candidates → disambiguation → expression);
    # 5 still cut off the final hop mid-answer (CucuBench watermelon CHS, 2026-08-19).
    max_tool_calls = int(os.getenv("CUAGENT_MAX_TOOL_CALLS", "7"))
    tool_calls_made = 0

    while True:
        can_call_tools = tool_calls_made < max_tool_calls
        kwargs = dict(
            model=DECISION_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=4096,
            extra_body=settings.llm_extra_body,
        )
        if can_call_tools:
            kwargs["tools"] = AGENT_TOOLS

        response = None
        for evt in _run_blocking_with_heartbeats(
            lambda: client.chat.completions.create(**kwargs),
            f"decision-r{tool_calls_made}",
        ):
            if evt["type"] == "status":
                yield emit_status(evt["message"])
            elif evt["type"] == "result":
                response = evt["value"]
            elif evt["type"] == "error":
                raise evt["error"]

        choice = response.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            break

        if not can_call_tools:
            # Model tried to call more tools after the budget was spent.
            # Refuse the call and force it to answer with current context.
            messages.append({
                "role": "system",
                "content": (
                    "Tool budget exhausted. Write the FINAL answer NOW using the evidence "
                    "already collected. If a requested segment of the chain is missing, say "
                    "explicitly which part could not be retrieved — do NOT announce planned "
                    "tool calls or write 'let me check…'."
                ),
            })
            break

        # Persist the assistant turn, but scrub any DSML tool-call markup that
        # DeepSeek / GLM occasionally dumps into ``content`` alongside structured
        # tool_calls — otherwise it poisons history and can resurface later.
        dumped = msg.model_dump()
        if isinstance(dumped.get("content"), str) and dumped["content"]:
            dumped["content"] = sanitize_assistant_text(dumped["content"]) or None
        messages.append(dumped)

        for tool_call in msg.tool_calls:
            if tool_calls_made >= max_tool_calls:
                # Budget exhausted mid-batch (model returned more parallel
                # tool_calls than remaining slots). Refuse the rest so the
                # model synthesizes from what it already has.
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps({
                        "status": "tool_error",
                        "message": "Tool budget exhausted; answer with existing results.",
                    }),
                })
                continue

            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            # Display concise tool call summary in st.status
            if fn_name == "search_gene_comprehensive":
                yield emit_status(f"🔧 Calling search_gene_comprehensive(gene_id='{fn_args.get('gene_id', '')}') — fetching full gene info")
            elif fn_name == "search_gene_expression":
                yield emit_status(f"🔧 Calling search_gene_expression(gene_id='{fn_args.get('gene_id', '')}') — fetching expression profile")
            elif fn_name == "search_literatureDB":
                yield emit_status(f"🔧 Calling search_literatureDB(query='{fn_args.get('query', '')}')")
            elif fn_name == "search_protein_structure":
                yield emit_status(f"🔧 Calling search_protein_structure(gene_id='{fn_args.get('gene_id', '')}') — fetching protein structure")

            tool_call_start = time.perf_counter()
            tool_result = execute_tool(fn_name, fn_args)
            tool_call_ms = int((time.perf_counter() - tool_call_start) * 1000)
            tool_calls_made += 1

            # Show concise result summary
            try:
                result_data = json.loads(tool_result)
                result_status = result_data.get("status", "unknown")
                if result_data.get("status") == "success":
                    if fn_name == "search_gene_comprehensive":
                        parts = []
                        if "gene_structure" in result_data: parts.append("gene structure")
                        if "go_terms" in result_data: parts.append("GO annotations")
                        if "pfam_domains" in result_data: parts.append("Pfam domains")
                        if "natural_variants" in result_data:
                            nv = result_data["natural_variants"]
                            s = nv.get("summary", {})
                            parts.append(f"{nv.get('count', 0)} variants (CDS {s.get('cds_total', '?')})")
                        if "plant_orthologs" in result_data: parts.append("orthologs")
                        yield emit_status(f"✅ Loaded: {', '.join(parts) if parts else 'basic info'}")
                    elif fn_name == "search_gene_expression":
                        mean_f = result_data.get("mean_fpkm", "?")
                        top_t = result_data.get("top_tissue", "?")
                        tau = result_data.get("tau_specificity")
                        n_coexp = len(result_data.get("coexpressed_top5", []))
                        tau_str = f", tau={tau}" if tau is not None else ""
                        yield emit_status(f"✅ Expression: mean FPKM {mean_f}, top tissue '{top_t}'{tau_str}, {n_coexp} co-expressed genes")
                    elif fn_name == "search_protein_structure":
                        plddt = result_data.get("plddt_score", "N/A")
                        label = result_data.get("plddt_label", "")
                        sites = result_data.get("binding_sites", [])
                        yield emit_status(f"✅ Protein structure: pLDDT={plddt} ({label}), {len(sites)} binding sites")
                    elif fn_name == "search_literatureDB":
                        kc = result_data.get("keyword_count", 0)
                        sc = result_data.get("semantic_count", 0)
                        chunks_n = len(result_data.get("chunks", []))
                        yield emit_status(f"✅ Literature search: {chunks_n} chunks (keyword {kc}, semantic {sc})")
                    else:
                        count = result_data.get("count", len(result_data.get("results", result_data.get("papers", []))))
                        yield emit_status(f"✅ Retrieved {count} results")
                elif result_data.get("status") == "not_found":
                    yield emit_status(f"⚠️ No matching records found")
                elif result_data.get("status") == "no_results":
                    yield emit_status(f"⚠️ No relevant literature found")
                elif result_data.get("status") == "tool_error":
                    yield emit_status(f"❌ Tool error: {result_data.get('message', 'unknown')}")
                else:
                    yield emit_status(f"❌ {result_data.get('message', 'Tool error')}")

                # Push slim evidence payload to the UI (DataCards).
                yield {
                    "type": "tool_result",
                    "tool": fn_name,
                    "data": _slim_tool_result_for_ui(fn_name, result_data),
                }
            except Exception:
                result_status = "parse_failed"
                yield emit_status(f"✅ Tool returned result")

            if tool_trace_sink is not None:
                try:
                    tool_trace_sink({
                        "tool": fn_name,
                        "args": fn_args,
                        "status": result_status,
                        "ms": tool_call_ms,
                    })
                except Exception:
                    pass

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result
            })

    # Final answer.
    #
    # DeepSeek (and peers) sometimes ignore "no tools" and emit another tool
    # call as plain text (DSML / "Now let me search…"). We buffer the first
    # attempt, sanitize it, and if nothing usable remains, force one rewrite
    # that must answer from the tool results already in ``messages``.
    yield emit_status("✍️ Writing answer…")

    def _collect_final_stream(msgs) -> str:
        resp = client.chat.completions.create(
            model=FINAL_ANSWER_MODEL,
            messages=msgs,
            temperature=0.2,
            max_tokens=FINAL_ANSWER_MAX_TOKENS,
            stream=True,
            extra_body=settings.llm_extra_body,
        )
        parts: list[str] = []
        for chunk in resp:
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        return "".join(parts)

    raw_answer = _collect_final_stream(messages)
    safe_answer = sanitize_assistant_text(raw_answer)

    if answer_is_insufficient(safe_answer):
        yield emit_status(
            "✍️ Model tried another tool call in text — rewriting from collected evidence…"
        )
        rewrite_messages = list(messages) + [
            {
                "role": "user",
                "content": (
                    "Do NOT call any tools and do NOT output tool-call markup. "
                    "Using only the tool results already in this conversation, "
                    "write the complete final answer to the user's question now. "
                    "Cover gene function (or note if annotation is missing), "
                    "expression if available, and related literature if available."
                ),
            }
        ]
        raw_answer = _collect_final_stream(rewrite_messages)
        safe_answer = sanitize_assistant_text(raw_answer)

    if not safe_answer:
        safe_answer = (
            "I gathered local database evidence (see the cards above) but could not "
            "produce a full written summary. Please retry, or open the linked module "
            "pages for the structured records."
        )

    # Yield in small chunks so the UI still feels streamed.
    step = 48
    for i in range(0, len(safe_answer), step):
        yield {"type": "token", "text": safe_answer[i : i + step]}
