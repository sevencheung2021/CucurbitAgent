import json
import re
from pathlib import Path
from functools import lru_cache

from app.config import settings


def _content_path(name: str) -> Path:
    return settings.content_dir / name


@lru_cache(maxsize=8)
def _load_json_cached(name: str, mtime_ns: int) -> dict:
    path = _content_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Content file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json(name: str) -> dict:
    path = _content_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Content file not found: {path}")
    # Bust cache when home.json (etc.) is edited on disk — no API restart needed.
    mtime_ns = path.stat().st_mtime_ns
    return _load_json_cached(name, mtime_ns)


def _deep_merge(base: dict, over: dict) -> dict:
    """home.json (英文基准) 作为兜底，locale 文件覆盖其上。

    与前端 request.ts 的策略一致：长尾语言/缺译字段自动回退英文，
    页面永不缺内容。列表（如 about.paragraphs）整体替换。
    """
    out = dict(base)
    for k, v in over.items():
        b = base.get(k)
        if isinstance(b, dict) and isinstance(v, dict):
            out[k] = _deep_merge(b, v)
        else:
            out[k] = v
    return out


# 与前端 i18n/config.ts 的 37 locales 对齐（2-3 位小写字母；正则同时防路径穿越）
_LOCALE_RE = re.compile(r"^[a-z]{2,3}$")


def get_home_content(locale: str = "en") -> dict:
    """Locale-aware home content: home.json 之上深合并 home.<locale>.json。

    校验通过且文件存在才合并，否则一律返回英文基准（缺译自动回退）。
    """
    loc = (locale or "en").strip().lower()
    if loc == "en" or not _LOCALE_RE.match(loc):
        return load_json("home.json")
    base = load_json("home.json")
    localized = _content_path(f"home.{loc}.json")
    if not localized.exists():
        return base
    mtime_ns = localized.stat().st_mtime_ns
    over = _load_json_cached(f"home.{loc}.json", mtime_ns)
    return _deep_merge(base, over)
