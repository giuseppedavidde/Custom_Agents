"""
Knowledge Loader: bridge tra i progetti e la nuova LLM_Wiki/Trading_Wiki.

Carica intere categorie (directory) dalla wiki, mantenendo backward compatibility
con le chiavi legacy usate da opencode_debate.py e ibkr_trading.py.
Supporta anche il caricamento delle skills (framework da libro) come knowledge aggiuntiva.
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional

WIKI_BASE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "LLM_Wiki", "Trading_Wiki", "wiki")
)

SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"

CATEGORIES = [
    "trading",
    "scalping_trading",
    "trading_options",
    "crypto_trading",
]

# Slug di skills considerate "core" e caricate di default con load_all_knowledge_with_skills()
DEFAULT_SKILL_SLUGS: list[str] = [
    "wyckoff-2-0",
    "volume-price-analysis",
    "volume-profile",
    "trades-about-to-happen",
    "trading-against-the-crowd",
    "price-action-volman",
    "crypto-technical-analysis",
    "crypto-crash-course",
    "options-playbook",
    "options-course-workbook",
    "options-crash-course",
]


def _compress(text: str) -> str:
    """Rimuove righe vuote multiple e markdown visivo per risparmiare token."""
    text = re.sub(r"\n\s*\n", "\n", text)
    text = re.sub(r"\*\*|\*|---", "", text)
    return text.strip()


def load_category(category: str) -> str:
    """Load all .md files from a wiki category directory, merged into one string.

    Args:
        category: Name of the category directory (e.g. 'trading', 'scalping_trading').

    Returns:
        Concatenated content of all .md files in the category, compressed.
        Empty string if the directory does not exist.
    """
    cat_dir = os.path.join(WIKI_BASE, category)
    if not os.path.isdir(cat_dir):
        return ""

    parts: list[str] = []
    for fname in sorted(os.listdir(cat_dir)):
        if fname.endswith(".md"):
            fpath = os.path.join(cat_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                parts.append(_compress(content))
            except FileNotFoundError:
                continue

    return "\n\n".join(parts)


def _strip_yaml(text: str) -> str:
    """Strip YAML frontmatter (---...--- or +++...+++) from start of file."""
    return re.sub(r"^(---|\+\+\+)[\s\S]*?^(---|\+\+\+)\s*\n?", "", text)


def load_skill_frameworks(slug: str) -> str:
    """Load the Core Frameworks section from a skill's SKILL.md.

    Returns empty string if the skill or frameworks section is not found.
    """
    skill_file = SKILLS_DIR / slug / "SKILL.md"
    if not skill_file.exists():
        return ""
    content = skill_file.read_text(encoding="utf-8", errors="replace")
    content = _strip_yaml(content)
    match = re.search(
        r"^## Core Frameworks.*?(?=^## )",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return _compress(match.group(0))
    return _compress(content[:3000])


def load_skills_knowledge(slugs: Optional[list[str]] = None) -> Dict[str, str]:
    """Load frameworks from multiple skills into a dict keyed by slug.

    Args:
        slugs: List of skill slugs. If None, loads DEFAULT_SKILL_SLUGS.

    Returns:
        Dict of {slug: frameworks_text} for each successfully loaded skill.
    """
    if slugs is None:
        slugs = DEFAULT_SKILL_SLUGS
    result: dict[str, str] = {}
    for slug in slugs:
        fw = load_skill_frameworks(slug)
        if fw:
            result[slug] = fw
    return result


def load_all_knowledge() -> Dict[str, str]:
    """Load ALL wiki categories into a dict keyed by domain.

    Returns:
        Dict with keys:
            "trading"           -> tutto trading/ (Wyckoff, VPA, Volume Profile, Order Flow)
            "scalping_trading"   -> tutto scalping_trading/ (Volman)
            "trading_options"    -> tutto trading_options/ (Fontanills, Overby)
            "crypto_trading"     -> tutto crypto_trading/
            "vpa" (backward)     -> trading + scalping_trading (merge)
            "options" (backward) -> trading_options
    """
    trading = load_category("trading")
    scalping = load_category("scalping_trading")
    options_cat = load_category("trading_options")
    crypto = load_category("crypto_trading")

    return {
        "trading": trading,
        "scalping_trading": scalping,
        "trading_options": options_cat,
        "crypto_trading": crypto,
        # Backward compat (usato da opencode_debate.py, ibkr_trading.py)
        "vpa": (trading + "\n\n" + scalping).strip(),
        "options": options_cat,
    }


def load_all_knowledge_with_skills(
    wiki_override: Optional[dict[str, str]] = None,
    skill_slugs: Optional[list[str]] = None,
) -> Dict[str, str]:
    """Load wiki categories + skill frameworks in one merged dict.

    Same keys as load_all_knowledge() plus a "skills" key containing
    the Core Frameworks of each requested skill.

    Args:
        wiki_override: Optional pre-loaded wiki dict (from load_all_knowledge()).
                       If None, loads fresh.
        skill_slugs: Which skills to include. If None, uses DEFAULT_SKILL_SLUGS.

    Returns:
        Dict with all wiki keys + "skills" key.
    """
    knowledge = wiki_override if wiki_override is not None else load_all_knowledge()
    skills = load_skills_knowledge(skill_slugs)
    if skills:
        knowledge["skills"] = "\n\n─── SKILL FRAMEWORKS ───\n\n" + "\n\n".join(
            f"### {slug}\n{fw}" for slug, fw in skills.items()
        )
    return knowledge
