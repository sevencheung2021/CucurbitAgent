"""Lightweight intent helpers for chat routes (greetings / meta questions)."""
from __future__ import annotations

import re

_GREETING_RE = re.compile(
    r"^(你好|您好|嗨|哈喽|谢谢|感谢|早上好|下午好|晚上好|再见|"
    r"hi|hello|hey|thanks|thank\s*you|bye|goodbye)[\s.,，。!?？！]*$",
    re.IGNORECASE,
)

_META_RE = re.compile(
    r"(你能做什么|你会什么|你是谁|介绍一下你自己|功能介绍|"
    r"what\s+can\s+you\s+do|who\s+are\s+you|what\s+are\s+you|\bhelp\s+me\b)",
    re.IGNORECASE,
)

CAPABILITY_REPLY_EN = (
    "I'm CucurbitAgent, a research assistant for Cucurbitaceae genomics and molecular breeding "
    "(cucumber, watermelon, melon, and related species).\n\n"
    "I can help with:\n"
    "- Gene annotation: structure, GO, Pfam, natural variants, orthologs\n"
    "- Expression: tissue profiles, tau specificity, co-expression\n"
    "- Protein structure: ESMFold pLDDT and predicted binding sites\n"
    "- Local literature: hybrid search over ~20k curated cucurbit papers\n\n"
    "Ask a research question, e.g. "
    "\"What is the function, tissue expression, and related papers for CsaV3_3G027830?\"."
)

CAPABILITY_REPLY_ZH = (
    "我是 CucurbitAgent，面向葫芦科（黄瓜、西瓜、甜瓜等）基因组学与分子育种的研究助手。\n\n"
    "我可以帮你：\n"
    "- 基因注释：结构、GO、Pfam、自然变异、同源基因\n"
    "- 表达谱：组织表达、tau、共表达\n"
    "- 蛋白结构：ESMFold pLDDT、预测结合位点\n"
    "- 本地文献：约 2 万篇葫芦科论文的混合检索与引用回答\n\n"
    "请直接问科研问题，或点下方示例开始："
)

CAPABILITY_REPLY_KO = (
    "저는 CucurbitAgent입니다. 박과(오이, 수박, 멜론 등) 유전체학·분자육종 연구 도우미입니다.\n\n"
    "도와드릴 수 있는 것:\n"
    "- 유전자 주석: 구조, GO, Pfam, 변이, 오솔로그\n"
    "- 발현: 조직 발현, tau, 공발현\n"
    "- 단백질 구조: ESMFold pLDDT, 예측 결합 부위\n"
    "- 문헌: 약 2만 편 박과 논문 하이브리드 검색\n\n"
    "연구 질문을 입력하거나 아래 예시를 눌러 보세요:"
)


def is_chitchat_or_meta(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if _GREETING_RE.match(t):
        return True
    if _META_RE.search(t):
        return True
    return False


def capability_reply_for(text: str) -> str:
    """Return a capability blurb in the user's language; UI chrome stays English."""
    t = text or ""
    if re.search(r"[가-힣]", t):
        return CAPABILITY_REPLY_KO
    if re.search(r"[一-鿿]", t):
        return CAPABILITY_REPLY_ZH
    return CAPABILITY_REPLY_EN
