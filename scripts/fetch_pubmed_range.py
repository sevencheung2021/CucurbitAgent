#!/usr/bin/env python3
"""PubMed 葫芦科文献抓取入库（按出版日期范围）。

链路: esearch/efetch → 物种校验 → 写 SQLite(papers + chunks_fts)
      → bge-m3 嵌入写 ChromaDB(cucurbit_papers) → 日志统计。

用法:
  python fetch_pubmed_range.py --yesterday
  python fetch_pubmed_range.py --from 2026-08-01 --to 2026-08-29

环境变量（.env 已由外层 shell source）:
  ENTREZ_EMAIL   — NCBI 联系邮箱（必需, 3 req/s 限额）
  CUAGENT_LITERATURE_DB / CUAGENT_CHROMA_DB — 由 api config 读取
"""
import argparse
import datetime as dt
import logging
import re
import sqlite3
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")          # 与 API 一致: 模型本地缓存, 不访问 HF
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import requests  # noqa: E402

# 项目环境（直接跑脚本也可: python scripts/fetch_pubmed_range.py）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from app.config import settings  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pubmed_fetch")

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EMAIL = getattr(settings, "entrez_email", "") or "cuagent@example.org"

# ── 葫芦科物种指纹（用于校验 + 抽取 species 字段）────────────────────
# 强命中：植物学双名/属名（拉丁词精确匹配，误报率极低）
BINOMIALS = {
    "cucumis sativus": "cucumis sativus", "cucumis melo": "cucumis melo",
    "citrullus lanatus": "citrullus lanatus", "citrullus colocynthis": "citrullus colocynthis",
    "cucurbita moschata": "cucurbita moschata", "cucurbita pepo": "cucurbita pepo",
    "cucurbita maxima": "cucurbita maxima", "cucurbita ficifolia": "cucurbita ficifolia",
    "lagenaria siceraria": "lagenaria siceraria", "luffa cylindrica": "luffa cylindrica",
    "luffa acutangula": "luffa acutangula", "benincasa hispida": "benincasa hispida",
    "momordica charantia": "momordica charantia", "momordica dioica": "momordica dioica",
    "trichosanthes cucumerina": "trichosanthes cucumerina",
    "trichosanthes kirilowii": "trichosanthes kirilowii",
    "sechium edule": "sechium edule", "coccinia grandis": "coccinia grandis",
    "telfairia occidentalis": "telfairia occidentalis",
    "cucumis anguria": "cucumis anguria", "cucumis metuliferus": "cucumis metuliferus",
    "cucurbitaceae": "cucurbitaceae",
}
GENERA = ["cucumis", "citrullus", "cucurbita", "lagenaria", "luffa",
          "benincasa", "momordica", "trichosanthes", "sechium",
          "telfairia", "coccinia", "cucurbitaceae"]
# 弱命中：普通作物名。安全性由"标题/关键词强命中 或 摘要≥3次"的门槛保证
# （"melon diet"、"pumpkin spice" 类零星提及到不了 3 次）
COMMON_NAMES = ["cucumber", "watermelon", "melon", "muskmelon", "cantaloupe", "honeydew",
                "pumpkin", "zucchini", "courgette", "chayote", "calabash",
                "bitter gourd", "bitter melon", "bottle gourd", "wax gourd",
                "sponge gourd", "ridge gourd", "snake gourd", "ivy gourd",
                "turban gourd", "loofah", "cushaw", "winter squash", "summer squash"]
# 普通作物名词径的语境要求：必须是"作物研究"词，不含 tissue/dna 等生医也用的泛词
PLANT_CONTEXT = re.compile(
    r"cultivar|variety|germplasm|graft|rootstock|seedling|breeding|horticult|"
    r"agronom|greenhouse|field trial|pathogen|virus|fungal disease|resistance|"
    r"transcriptome|genome|qtl|gene expression|photosynth|yield|harvest|"
    r"orchard|farm|irrigation|fertilizer", re.I)
BIOMED_DOMINANT = re.compile(
    r"anticancer|apopto|cytotox|tumor|hepatoprotect|splenic|in vivo mice|"
    r"nanoparticle|nanocomposite|nanoemulsion|drug delivery|pharmacokinet|"
    r"clinical trial|patients?\b|serum|plasma", re.I)
# cucurbit(≠uril) 词根：cucurbit/cucurbits/cucurbitaceous 是植物；cucurbituril 是超分子化学
# cucurbituril 常写作 Cucurbit[7]uril —— 归一化后是 "cucurbit 7 uril"，断言需容数字/空格
CU_CURBIT = re.compile(r"cucurbit(?![\s\d]*uril)", re.I)

# 目标刊（弱命中但领域相关时放宽收）
TARGET_JOURNALS = re.compile(
    r"plant sci|hortic|theor appl genet|genetics|breeding|phytopathol|"
    r"plant physiol|plant cell|front plant|bmbe|planta|molecular breeding|"
    r"crop|sci agr|postharvest|food chem", re.I)

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def esearch(d1: str, d2: str):
    term = ("(Cucurbitaceae[tiab] OR cucurbit*[tiab] OR Cucumis[tiab] OR Citrullus[tiab] "
            "OR Cucurbita[tiab] OR Lagenaria[tiab] OR Luffa[tiab] OR Benincasa[tiab] "
            "OR Momordica[tiab] OR Trichosanthes[tiab] OR cucumber[tiab] OR watermelon[tiab] "
            "OR melon[tiab] OR pumpkin[tiab] OR squash[tiab] OR gourd[tiab])")
    r = requests.get(f"{EUTILS}/esearch.fcgi", params={
        "db": "pubmed", "term": term, "retmax": 500, "retmode": "json",
        "datetype": "pdat", "mindate": d1.replace("-", "/"), "maxdate": d2.replace("-", "/"),
        "email": EMAIL,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["esearchresult"].get("idlist", [])


def efetch(pmids):
    """逐批取回独立 XML 文档列表（拼接会变成非法 XML）。"""
    out = []
    for i in range(0, len(pmids), 100):
        batch = pmids[i:i + 100]
        r = requests.get(f"{EUTILS}/efetch.fcgi", params={
            "db": "pubmed", "id": ",".join(batch), "retmode": "xml", "email": EMAIL,
        }, timeout=120)
        r.raise_for_status()
        out.append(r.text)
        time.sleep(0.4)  # NCBI 限额礼仪
    return out


def _txt(el, path):
    """取节点全文。必须用 itertext：PubMed 的标题/摘要常含嵌套标记
    （<sup>、<i>，如 "Development of a Novel <sup>13</sup>C-..."），
    只取 .text 会在标记处截断——曾因此截断标题导致物种校验误杀真葫芦科论文。"""
    n = el.find(path)
    if n is None:
        return ""
    return "".join(n.itertext()).strip()


def parse_articles(xml_docs):
    """逐批解析独立 XML 文档（拼接会非法）；坏批次跳过不致命。"""
    arts = []
    for xml_text in xml_docs:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            log.warning("    批次 XML 解析失败跳过: %s", e)
            continue
        for art in root.iter("PubmedArticle"):
            med = art.find(".//MedlineCitation")
            if med is None:
                continue
            pmid = _txt(med, "PMID")
            info = art.find(".//PubmedData/ArticleIdList")
            doi = ""
            if info is not None:
                for aid in info.findall("ArticleId"):
                    if aid.get("IdType") == "doi":
                        doi = (aid.text or "").strip()
            if not doi:
                doi = _txt(med, ".//ELocationID[@EIdType='doi']")
            title = _txt(med, ".//ArticleTitle")
            abstract = " ".join(
                "".join(t.itertext()).strip()
                for t in med.findall(".//Abstract/AbstractText")
                if "".join(t.itertext()).strip()
            )
            authors = "; ".join(
                f"{_txt(a, 'LastName')}, {_txt(a, 'ForeName')}"
                for a in med.findall(".//Author")[:8]
            )
            journal = _txt(med, ".//Journal/Title")
            kw = "; ".join("".join(k.itertext()).strip() for k in med.findall(".//Keyword"))
            y, m, d, disp, pd_ = "", 0, 0, "", None
            # 优先 ArticleDate(Electronic)：那是真实上线日。Journal/PubDate 是
            # 印刷期号 —— 预出版论文的期号常在未来（实测 8 月上线给了 Oct 31）。
            for ad in med.findall(".//ArticleDate"):
                if ad.get("DateType") in ("Electronic", "PubInPrint"):
                    _mv = _txt(ad, "Month").strip().lower()
                    _mn = MONTHS.get(_mv[:3], 0) or (int(_mv) if _mv.isdigit() and 1 <= int(_mv) <= 12 else 0)
                    ay, am, ad_ = _txt(ad, "Year")[:4], _mn, int(_txt(ad, "Day") or 15)
                    if ay.isdigit() and (am or 0):
                        y, m, d = ay, am, ad_ or 15
                        disp = f"{ay} {list(MONTHS)[am-1].title()} {d}".strip() if am else ay
                        break
            if not y.isdigit():
                for pth in (".//Journal/PubDate", ".//PubDate"):
                    pd_ = med.find(pth)
                    if pd_ is None:
                        continue
                    y = _txt(pd_, "Year")[:4]
                    m = MONTHS.get(_txt(pd_, "Month")[:3].lower(), 0)
                    d = int(_txt(pd_, "Day") or 0)
                    disp = _txt(pd_, "MedlineDate")
                    if y.isdigit():
                        break
            # 兜底：解析出的日期在未来（期号错位）→ 压到今天，绝不允许未来排序
            today = dt.date.today()
            try:
                if y.isdigit() and (int(y), m or 6, d or 15) > (today.year, today.month, today.day):
                    y, m, d = str(today.year), today.month, today.day
                    disp = f"{today.year} {list(MONTHS)[today.month-1].title()} {today.day}"
            except Exception:
                pass
            if not y.isdigit():
                m_ = re.search(r"(19|20)\d{2}", disp or "")
                y = m_.group(0) if m_ else "2026"
            if not disp and pd_ is not None:
                disp = (f"{y}" + (f" {_txt(pd_, 'Month')}" if m else "")
                        + (f" {d}" if d else "")).strip()
            pub_date_disp = re.sub(r"\s+", " ", disp)[:32]
            if not title or not abstract:
                continue
            arts.append(dict(pmid=pmid, doi=doi, title=title, abstract=abstract,
                             authors=authors, journal=journal, keywords=kw,
                             year=int(y), month=m, day=int(d or 15), pub_date=pub_date_disp))
    return arts


def _cucurbit_terms_in(text):
    """返回 (命中词列表, 出现次数)。词表=双名+属+普通作物名+cucurbit 词根。"""
    t = " " + re.sub(r"[^a-z\s-]", " ", unicodedata.normalize("NFKD", (text or "").lower())) + " "
    t = re.sub(r"\bsea\s+cucumbers?\b", " ", t)
    hits, count = [], 0
    def _word(w):
        return re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t)
    for k in BINOMIALS:
        if _word(k):
            count += len(re.findall(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t))
            if BINOMIALS[k] not in hits:
                hits.append(BINOMIALS[k])
    for g in GENERA:
        n = len(re.findall(rf"(?<![a-z]){g}(?![a-z])", t))
        if n:
            count += n
            if g not in hits:
                hits.append(g)
    for c in COMMON_NAMES:
        n = len(re.findall(rf"(?<![a-z]){re.escape(c)}(?![a-z])", t))
        if n:
            count += n
            if "cucurbitaceae" not in hits:
                hits.append("cucurbitaceae")
    if CU_CURBIT.search(t):
        count += len(CU_CURBIT.findall(t))
        if "cucurbitaceae" not in hits:
            hits.append("cucurbitaceae")
    return hits, count


def species_hits(title, keywords, abstract):
    """主题级判定：论文必须是『研究葫芦科』，而非『顺带提到葫芦科』。

    三档：
      A. 标题或关键词含葫芦科词 → 研究主题就是它，通过
      B. 摘要中葫芦科词出现 ≥3 次 → 实质研究作物（病毒防治/栽培试验类），
         通过（要求非 BIOMED_DOMINANT）
      C. 摘要零星提及 1-2 次 → 顺带比较/举例（如药理论文拿苦瓜做对照），
         拒绝——Nyctanthes arbor-tristis 案例正是这样混进来的
    返回命中物种列表（空=拒绝）。
    """
    # A. 标题/关键词强命中 → 研究主题就是葫芦科（或其化合物，如 cucurbitacin）。
    #    药理/食品方向的葫芦科论文合法（库里本有 biomed/chem/food 分类），
    #    BIOMED 词不否决这一档——曾误删 gac(Momordica) 膳食补充和 cucurbitacin 研究。
    strong_hits, _ = _cucurbit_terms_in(f"{title} {keywords or ''}")
    if strong_hits:
        all_hits, _ = _cucurbit_terms_in(f"{title} {keywords or ''} {abstract}")
        return (all_hits or strong_hits)[:5]
    # B/C 档（仅摘要提及）才受 BIOMED 词否决：药理论文拿苦瓜/葫芦素当对照药提一嘴
    if BIOMED_DOMINANT.search(f"{title} {abstract}"):
        return []
    hits, count = _cucurbit_terms_in(abstract or "")
    if count >= 3:
        return hits[:5]
    return []


def classify_subject(text: str) -> str:
    t = text.lower()
    if re.search(r"resistance|qtl|breeding|marker|transgeni|crispr|gene edit|genome|sequenc|gene expression|tf\b|transcription|mutant|locus|allele|inherit|hybrid|pollination|gynoecious|sex determination|mapping population", t):
        return "cgi"
    if re.search(r"graft|fertiliz|rootstock|yield|greenhouse|prun|cultivation|salinity|drought|stress tolerance|seedling", t):
        return "agri"
    if re.search(r"food|nutrit|postharvest|ripening|flavor|sugar|quality|storage|juice|processing", t):
        return "food"
    if re.search(r"antioxidant|bioactiv|extract|pharmacolog|anticancer|diabetes|anti-inflammatory|clinical", t):
        return "biomed"
    if re.search(r"compound|metabolit|protein purif|enzyme kinetics|chemistry|biosynthesis pathway", t):
        return "chem"
    return "other"


def quality_of(journal: str, abstract: str) -> float:
    q = 0.84
    if TARGET_JOURNALS.search(journal or ""):
        q += 0.05
    if len(abstract) > 800:
        q += 0.03
    if re.search(r"genom|transcriptom|sequenc", abstract.lower()):
        q += 0.02
    return round(min(q, 0.95), 2)


def chunk_text(text: str, size: int = 800):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= size:
        return [text] if text else []
    parts, step = [], int(size * 0.85)
    for i in range(0, len(text), step):
        parts.append(text[i:i + size])
        if i + size >= len(text):
            break
    return parts[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yesterday", action="store_true")
    ap.add_argument("--from", dest="d1")
    ap.add_argument("--to", dest="d2")
    args = ap.parse_args()
    if args.yesterday:
        d = dt.date.today() - dt.timedelta(days=1)
        args.d1 = args.d2 = d.isoformat()
    if not args.d1 or not args.d2:
        ap.error("--yesterday 或 --from/--to 必填")

    log.info("🚀 PubMed 抓取入库: %s → %s", args.d1, args.d2)
    pmids = esearch(args.d1, args.d2)
    log.info("    抓取 PubMed : %d", len(pmids))
    if not pmids:
        log.info("============================================================")
        return

    articles = parse_articles(efetch(pmids))

    db_path = Path(settings.literature_db_path)
    conn = sqlite3.connect(db_path)
    existing = {r[0] for r in conn.execute("SELECT paper_key FROM papers")}

    from chromadb.utils import embedding_functions
    import chromadb
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.embed_model_name, device="cpu")
    # anonymized_telemetry=False: 后台线程会让进程完成后挂起不退出（实测 kill -9 才退）
    col = chromadb.PersistentClient(
        path=str(settings.chroma_db_path),
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    ).get_collection(name="cucurbit_papers", embedding_function=ef)

    n_skip = n_rej = n_relax = n_new = n_chunks = 0
    for a in articles:
        key = f"doi:{a['doi']}" if a["doi"] else f"pmid:{a['pmid']}"
        if key in existing:
            n_skip += 1
            continue
        sp = species_hits(a["title"], a["keywords"], a["abstract"])
        if not sp:
            # 目标刊放宽也必须至少有 1 次葫芦科词——纯期刊名匹配曾放进零相关论文
            from fetch_pubmed_range import _cucurbit_terms_in
            _, cnt = _cucurbit_terms_in(f"{a['title']} {a['keywords']} {a['abstract']}")
            if TARGET_JOURNALS.search(a["journal"] or "") and cnt >= 1:
                n_relax += 1
                sp = ["cucurbitaceae"]
            else:
                n_rej += 1
                continue
        ym = a["year"] * 100 + (a["month"] or 6)
        real = ym * 100 + a["day"]
        chunks = chunk_text(f"{a['title']}. {a['abstract']}")
        conn.execute(
            "INSERT INTO papers (paper_key, doi, pmid, title, authors, journal, pub_date,"
            " pub_year, abstract, keywords, species, quality, has_pdf, n_chunks,"
            " sort_ym, subject, pub_date_display, pub_date_real)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)",
            (key, a["doi"], a["pmid"], a["title"], a["authors"], a["journal"],
             a["pub_date"], a["year"], a["abstract"], a["keywords"], ", ".join(sp),
             quality_of(a["journal"], a["abstract"]), len(chunks), ym,
             classify_subject(text), a["pub_date"], real))
        ids, docs, metas = [], [], []
        for ci, ch in enumerate(chunks):
            conn.execute(
                "INSERT INTO chunks_fts (chunk_text, title, keywords, paper_key, source, chunk_id)"
                " VALUES (?,?,?,?, 'abstract', ?)", (ch, a["title"], a["keywords"], key, ci))
            ids.append(f"{key}::abstract::{ci}")
            docs.append(ch)
            metas.append({"chunk_id": ci, "doi": a["doi"], "paper_key": key,
                          "quality": quality_of(a["journal"], a["abstract"]),
                          "source": "abstract", "species": sp[0],
                          "title": a["title"][:80], "year": a["year"]})
        if ids:
            col.add(ids=ids, documents=docs, metadatas=metas)
        existing.add(key)
        n_new += 1
        n_chunks += len(chunks)
        log.info("    + %s | %s", key, a["title"][:60])

    conn.commit()
    conn.close()
    log.info("    已存在跳过    : %d", n_skip)
    log.info("    物种校验剔除  : %d", n_rej)
    log.info("    目标刊放宽入库: %d", n_relax)
    log.info("    新增入库      : %d (%d chunks)", n_new, n_chunks)
    log.info("============================================================")


if __name__ == "__main__":
    main()
    import os
    os._exit(0)  # chroma/sentence-transformers 的后台线程会阻止解释器退出
