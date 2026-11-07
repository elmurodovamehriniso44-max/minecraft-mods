"""Yengil qidiruv: qisman moslik, kalit so'z va imlo xatolariga chidamlilik."""
import re
from difflib import SequenceMatcher
from typing import List, Optional

from database import queries as q
from utils.helpers import compat_state

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> List[str]:
    return _WORD.findall((text or "").lower())


def _token_sim(qt: str, tokens: List[str]) -> float:
    """So'rov so'zining token'lar ro'yxatiga o'xshashligi (0..1)."""
    best = 0.0
    for t in tokens:
        if t == qt:
            return 1.0
        if len(qt) >= 2 and t.startswith(qt):
            best = max(best, 0.9)
        elif len(qt) >= 3 and qt in t:
            best = max(best, 0.8)
        elif len(qt) >= 3 and abs(len(t) - len(qt)) <= 3:
            ratio = SequenceMatcher(None, qt, t).ratio()
            if ratio >= 0.72:
                best = max(best, ratio * 0.85)
    return best


def _in_description(qt: str, desc_tokens: List[str]) -> bool:
    """Tavsifda aniq yoki prefiks bo'yicha moslik (fuzzy emas — tezlik uchun)."""
    for t in desc_tokens:
        if t == qt or (len(qt) >= 3 and t.startswith(qt)):
            return True
    return False


async def search(
    query: str,
    category_id: Optional[int] = None,
    version: Optional[str] = None,
    limit: int = 200,
) -> List[int]:
    """Mos kelgan mod ID'larini ball bo'yicha saralab qaytaradi."""
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    q_norm = " ".join(q_tokens)

    scored = []
    for row in await q.search_index():
        if category_id and row["category_id"] != category_id:
            continue
        if version and compat_state(row["versions"], version) != "ok":
            continue

        name_tokens = _tokens(row["name"])
        name_norm = " ".join(name_tokens)
        meta_tokens = _tokens(f"{row['author']} {row['category_name']}")
        desc_tokens = _tokens(row["description"])

        total = 0.0
        for qt in q_tokens:
            s_name = _token_sim(qt, name_tokens)
            s_meta = _token_sim(qt, meta_tokens) * 0.6
            s_desc = 0.5 if _in_description(qt, desc_tokens) else 0.0
            total += max(s_name, s_meta, s_desc)
        avg = total / len(q_tokens)
        if avg < 0.5:
            continue

        score = avg * 100
        if q_norm == name_norm:
            score += 100
        elif name_norm.startswith(q_norm):
            score += 50
        elif q_norm in name_norm:
            score += 40
        score += min(row["downloads"], 1000) / 1000
        scored.append((score, row["id"]))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [mod_id for _, mod_id in scored[:limit]]
