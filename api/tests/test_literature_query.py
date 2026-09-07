"""Tests for literature query parsing (Week 2)."""
from app.services.literature_query import build_fts_match, parse_literature_query


def test_gene_id_and_species_parsed():
    p = parse_literature_query("What is MYB60 function in cucumber?")
    assert "MYB60" in p.gene_ids
    assert p.species_key == "cucumber"
    assert p.species_terms
    assert "MYB60" in p.fts_match


def test_chatty_myb60_query_does_not_and_filler():
    """Full-sentence chat must not FTS-AND conversational words with MYB60."""
    p = parse_literature_query(
        "I want to Find papers on MYB60 in cucurbits and know about their function"
    )
    assert "MYB60" in p.gene_ids
    assert "want" not in p.core_terms
    assert "know" not in p.core_terms
    assert "their" not in p.core_terms
    assert p.species_key == "gourd"
    assert p.species_terms == []
    assert p.fts_match == '"MYB60"' or p.fts_match.startswith('"MYB60"')


def test_chinese_wrky_cucumber_query():
    """Mixed ZH/EN must extract WRKY + cucumber, not one giant FTS token."""
    p = parse_literature_query("我想知道WRKY在黄瓜中的功能")
    assert any(g.upper() == "WRKY" for g in p.gene_ids)
    assert p.species_key == "cucumber"
    assert p.fts_match == '"WRKY"'
    assert "我想知道" not in p.core_terms
    assert "我想知道WRKY在黄瓜中的功能" not in p.fts_match

def test_fts_and_core_terms():
    p = parse_literature_query("cucumber disease resistance")
    assert p.species_key == "cucumber"
    assert "disease" in p.core_terms and "resistance" in p.core_terms
    assert " AND " in p.fts_match


def test_gene_id_in_fts():
    match = build_fts_match(["CsaV3_1G000080"], ["chlorophyll"], [])
    assert "CsaV3_1G000080" in match
    assert " OR " in match


def test_cssgr_parsed_as_gene_symbol():
    p = parse_literature_query("CsSGR 基因的对应 gene ID")
    assert any(g.upper() == "CSSGR" for g in p.gene_ids)
    assert "对应" not in p.core_terms
    assert '"CsSGR"' in p.fts_match or '"CSSGR"' in p.fts_match.upper()


def test_normalize_csa5m_to_csa5g():
    from app.services.literature_query import normalize_cucumber_locus

    assert normalize_cucumber_locus("Csa5M156180.1") == "Csa5G156180"
    assert normalize_cucumber_locus("Csa5G156180") == "Csa5G156180"


def test_extract_cssgr_linked_locus():
    from app.services.literature_query import extract_locus_ids_linked_to_names

    pan = "Staygreen (SGR) (Csa5M156180) is the candidate for cla"
    citing = "Wang et al. proposed the CsSGR gene (Csa5G156180), a key regulator"
    neighbors = "FAM63A-like (Csa5M156160) Agamous-like (Csa5M156170) Staygreen (SGR) (Csa5M156180)"
    assert "Csa5M156180" in extract_locus_ids_linked_to_names(pan, ["CsSGR"])
    assert "Csa5G156180" in extract_locus_ids_linked_to_names(citing, ["CsSGR"])
    linked = extract_locus_ids_linked_to_names(neighbors, ["CsSGR"])
    assert "Csa5M156180" in linked
    # Neighbor genes in the same interval must not outrank Staygreen when
    # the window is centered on Staygreen/CsSGR.
    assert linked[0] == "Csa5M156180"
