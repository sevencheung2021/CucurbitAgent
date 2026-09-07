"""
Query parsing and rewrite for literature hybrid search (Week 2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Locus IDs (CsaV3_1G000080) OR gene symbols with digits (MYB60, CsMYB60, WRKY33).
# Trailing alnum after the digit group is optional so "MYB60" matches.
GENE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:"
    r"[A-Za-z][A-Za-z0-9]*(?:[Vv]\d+(?:\.\d+)?)?[_\.][A-Za-z0-9][A-Za-z0-9_.]{3,}"
    r"|"
    r"[A-Za-z]{2,}\d+[A-Za-z0-9_.-]*"
    r")"
    r"(?![A-Za-z0-9_])"
)

# Family names without a required digit (WRKY, MYB, NAC…) — common in Chinese
# questions like "WRKY在黄瓜中的功能" where Python \b fails (CJK is \w).
GENE_FAMILY_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:Cs|Cl|Cm|Cmo|Cpe)?"
    r"(?:WRKY|MYB|NACRE|bHLH|BHLH|ERF|bZIP|BZIP|APRR|NAC|MADS|STAYGREEN|SGR)"
    r"\d*"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

# Cucumber / cucurbit locus IDs as printed in papers (V1/V2/V3, Gy14 Csa5M…).
LOCUS_ID_RE = re.compile(
    r"\b(?:"
    r"CsaV3_\d+G\d+(?:\.\d+)?|"
    r"Csa\d+[MG]\d+(?:\.\d+)?|"
    r"Csa\d{5,}(?:\.\d+)?"
    r")\b",
    re.IGNORECASE,
)

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "with", "by",
    "what", "when", "where", "which", "who", "why", "how", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "about", "tell", "me", "please", "gene", "genes", "paper", "papers",
    "literature", "research", "study", "studies", "related", "function", "role",
    # Conversational filler — AND-ing these with the gene name zeros FTS hits.
    "i", "we", "you", "my", "our", "your", "their", "them", "these", "those",
    "this", "that", "want", "wanted", "find", "finding", "search", "searching",
    "look", "looking", "know", "knowing", "show", "give", "get", "list",
    "summarize", "summary", "describe", "explain", "recent", "recently",
    "also", "more", "some", "any", "all", "info", "information", "question",
    "can", "could", "would", "should", "from", "into", "over", "under",
    "using", "use", "used", "include", "including", "regarding", "concerning",
    "based", "respectively", "publication", "publications", "journal", "pubmed",
    # Chinese conversational / question filler
    "我", "我们", "你", "您", "想", "知道", "了解", "请问", "请", "帮", "帮忙",
    "一下", "什么", "哪些", "怎么", "如何", "关于", "有关", "查", "查找", "检索",
    "告诉", "介绍", "说说", "讲讲", "一下", "这个", "那个", "以及", "还有",
    "功能", "作用", "角色", "文献", "论文", "研究", "基因",
    "对应", "编号", "locus", "id",
}

SPECIES_ALIASES: dict[str, list[str]] = {
    "cucumber": [
        "cucumber", "cucumis sativus", "cucumis",
        "黄瓜", "青瓜",
    ],
    "watermelon": [
        "watermelon", "citrullus lanatus", "citrullus",
        "西瓜",
    ],
    "melon": [
        "melon", "cucumis melo",
        "甜瓜", "哈密瓜", "香瓜",
    ],
    "pumpkin": [
        "pumpkin", "cucurbita pepo", "cucurbita moschata", "cucurbita",
        "南瓜",
    ],
    "squash": [
        "squash", "cucurbita",
        "西葫芦", "笋瓜",
    ],
    "bitter gourd": [
        "bitter gourd", "bittergourd", "momordica charantia", "momordica",
        "苦瓜",
    ],
    "bottle gourd": [
        "bottle gourd", "bottlegourd", "lagenaria",
        "葫芦", "瓠瓜",
    ],
    "wax gourd": [
        "wax gourd", "waxgourd", "benincasa",
        "冬瓜",
    ],
    "sponge gourd": [
        "sponge gourd", "spongegourd", "luffa",
        "丝瓜",
    ],
    # Umbrella "cucurbit(s)" — papers.species stores binomials; filtering on
    # these aliases drops real hits. Cleared in parse_literature_query.
    "gourd": ["gourd", "cucurbitaceae", "cucurbit", "葫芦科", "瓜类"],
}


@dataclass
class ParsedLiteratureQuery:
    raw: str
    rewritten: str
    gene_ids: list[str] = field(default_factory=list)
    core_terms: list[str] = field(default_factory=list)
    species_key: Optional[str] = None
    species_terms: list[str] = field(default_factory=list)
    fts_match: str = ""


def _tokenize(text: str) -> list[str]:
    """Split mixed Chinese/English so 'WRKY在黄瓜' → ['WRKY', '在', '黄瓜'].

    A single [A-Za-z0-9一-鿿]+ class would glue the whole Chinese sentence into
    one FTS token and miss every paper.
    """
    return re.findall(r"[A-Za-z][A-Za-z0-9_\-.]*|[0-9]+|[一-鿿]+", text or "")


def _extract_gene_tokens(text: str) -> list[str]:
    found: list[str] = []
    for m in GENE_ID_RE.finditer(text or ""):
        found.append(m.group(0))
    for m in GENE_FAMILY_RE.finditer(text or ""):
        found.append(m.group(0))
    # Preserve order, case-insensitive dedupe (keep first spelling).
    out: list[str] = []
    seen: set[str] = set()
    for tok in found:
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tok)
    return out


def detect_species(text: str) -> tuple[Optional[str], list[str]]:
    lower = text.lower()
    # Prefer longer aliases first within each species; scan specific crops
    # before the umbrella "gourd" key (dict order in Py3.7+).
    for key, aliases in SPECIES_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if alias.lower() in lower or alias in text:
                return key, aliases
    return None, []


def build_fts_match(gene_ids: list[str], core_terms: list[str], fallback_tokens: list[str]) -> str:
    """Build FTS5 MATCH expression.

    Gene / symbol tokens are OR'd (any hit is enough). Remaining biology terms
    are AND'd as a secondary clause and OR'd with the gene clause — never
    AND'd *with* the gene name, otherwise chatty multi-word questions zero out.
    """
    gene_parts = [f'"{gid}"' for gid in gene_ids if gid]
    terms = [t for t in core_terms if len(t) > 1]

    clauses: list[str] = []
    if gene_parts:
        clauses.append(gene_parts[0] if len(gene_parts) == 1 else f"({' OR '.join(gene_parts)})")

    if terms:
        if len(terms) == 1:
            term_clause = f'"{terms[0]}"'
        else:
            term_clause = "(" + " AND ".join(f'"{t}"' for t in terms[:6]) + ")"
        clauses.append(term_clause)
    elif not clauses and fallback_tokens:
        or_part = " OR ".join(f'"{t}"' for t in fallback_tokens[:8] if len(t) > 1)
        if or_part:
            clauses.append(or_part)

    if not clauses:
        return ""
    if len(clauses) == 1:
        return clauses[0]
    return " OR ".join(clauses)


def parse_literature_query(raw: str) -> ParsedLiteratureQuery:
    text = (raw or "").strip()
    gene_ids = _extract_gene_tokens(text)
    species_key, species_terms = detect_species(text)

    # Umbrella cucurbits/gourd: corpus is already cucurbit-scoped; binomial
    # species fields won't match "cucurbit". Keep key for rewrite hints only.
    if species_key == "gourd":
        species_terms = []

    tokens = _tokenize(text)
    lowered_gene = {g.lower() for g in gene_ids}
    # English aliases used for species-term stripping; Chinese aliases too.
    species_alias_lower = {a.lower() for a in species_terms}

    filtered: list[str] = []
    for tok in tokens:
        tl = tok.lower()
        if tl in STOPWORDS or tok in STOPWORDS or len(tok) <= 1:
            continue
        if tl in lowered_gene:
            continue
        if species_alias_lower and (
            tl in species_alias_lower
            or any(tl in a or a in tl for a in species_alias_lower if len(a) >= 2)
        ):
            continue
        if tok in {"葫芦科", "瓜类", "cucurbit", "cucurbits", "cucurbitaceae", "gourd"}:
            continue
        # Drop lone Chinese particles / short noise left after split
        if re.fullmatch(r"[一-鿿]+", tok) and tok in {
            "在", "中", "的", "了", "吗", "呢", "吧", "啊", "和", "与", "及", "等",
            "其", "它们", "它们的",
        }:
            continue
        filtered.append(tok)

    core_terms = list(dict.fromkeys(filtered))
    # Chinese has no spaces: leftover CJK blobs like "我想知道" / "在黄瓜中的功能"
    # poison FTS if AND'd. When we already have a gene/family symbol, drop
    # pure-CJK core terms — species is carried via species_key/filter instead.
    if gene_ids:
        core_terms = [t for t in core_terms if not re.fullmatch(r"[一-鿿]+", t)]
    fts_match = build_fts_match(gene_ids, core_terms, tokens)
    rewritten_parts = list(gene_ids) + core_terms
    if species_key and species_key != "gourd":
        # Prefer English species name for vector channel.
        rewritten_parts.append(species_key)
    rewritten = " ".join(dict.fromkeys(rewritten_parts)) or text

    return ParsedLiteratureQuery(
        raw=text,
        rewritten=rewritten,
        gene_ids=gene_ids,
        core_terms=core_terms,
        species_key=species_key,
        species_terms=species_terms,
        fts_match=fts_match,
    )


def normalize_cucumber_locus(gene_id: str) -> str:
    """Strip transcript suffix and map Gy14/9930 V2 ``Csa5M156180`` → ``Csa5G156180``."""
    gid = (gene_id or "").strip()
    gid = re.sub(r"\.\d+$", "", gid)
    gid = re.sub(r"^(Csa\d+)M(\d+)$", r"\1G\2", gid, flags=re.IGNORECASE)
    if re.match(r"^Csa\d+G\d+$", gid, re.IGNORECASE):
        return _canonical_csa_g(gid)
    if re.match(r"^CsaV3_\d+G\d+$", gid, re.IGNORECASE):
        return _canonical_csav3(gid)
    if re.match(r"^Csa\d{5,}$", gid, re.IGNORECASE):
        return "Csa" + gid[3:]
    return gid


def _canonical_csa_g(gid: str) -> str:
    m = re.match(r"^Csa(\d+)G(\d+)$", gid, re.IGNORECASE)
    if not m:
        return gid
    return f"Csa{m.group(1)}G{m.group(2)}"


def _canonical_csav3(gid: str) -> str:
    m = re.match(r"^CsaV3_(\d+)G(\d+)$", gid, re.IGNORECASE)
    if not m:
        return gid
    return f"CsaV3_{m.group(1)}G{m.group(2)}"


def extract_locus_ids(text: str) -> list[str]:
    if not text:
        return []
    found = [m.group(0) for m in LOCUS_ID_RE.finditer(text)]
    out: list[str] = []
    seen: set[str] = set()
    for gid in found:
        key = gid.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(gid)
    return out


def extract_locus_ids_linked_to_names(text: str, gene_names: list[str]) -> list[str]:
    """Locus IDs that sit near a gene symbol (e.g. ``CsSGR (Csa5G156180)``)."""
    if not text:
        return []
    names = [n for n in gene_names if n and len(n) >= 3]
    name_re = re.compile(
        r"(?:CsSGR|STAY[- ]?GREEN|"
        + ("|".join(re.escape(n) for n in names) if names else "CsSGR")
        + r")",
        re.IGNORECASE,
    )
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for m in name_re.finditer(text):
        after = text[m.end() : m.end() + 100]
        before = text[max(0, m.start() - 40) : m.start()]
        for gm in LOCUS_ID_RE.finditer(after):
            gid = gm.group(0)
            key = gid.lower()
            if key in seen:
                continue
            seen.add(key)
            scored.append((gm.start(), gid))
        for gm in LOCUS_ID_RE.finditer(before):
            gid = gm.group(0)
            key = gid.lower()
            if key in seen:
                continue
            seen.add(key)
            scored.append((1000 + (40 - gm.start()), gid))
    scored.sort(key=lambda x: x[0])
    return [gid for _, gid in scored]


def rewrite_for_retrieval(raw: str, llm_expand: Optional[str] = None) -> ParsedLiteratureQuery:
    """Rule-based rewrite; optional llm_expand string merged for vector channel."""
    parsed = parse_literature_query(raw)
    if llm_expand and llm_expand.strip():
        extra = parse_literature_query(llm_expand.strip())
        merged_terms = list(dict.fromkeys(parsed.core_terms + extra.core_terms))
        parsed.core_terms = merged_terms[:8]
        parsed.rewritten = " ".join(
            dict.fromkeys(
                parsed.gene_ids
                + parsed.core_terms
                + ([parsed.species_key] if parsed.species_key and parsed.species_key != "gourd" else [])
            )
        ) or parsed.raw
        parsed.fts_match = build_fts_match(parsed.gene_ids, parsed.core_terms, _tokenize(parsed.raw))
    return parsed
