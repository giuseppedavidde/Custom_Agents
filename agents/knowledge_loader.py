"""
Knowledge Loader: bridge tra i progetti e la nuova LLM_Wiki/Trading_Wiki.

Carica intere categorie (directory) dalla wiki, mantenendo backward compatibility
con le chiavi legacy usate da opencode_debate.py e ibkr_trading.py.
"""

import os
import re
from typing import Dict

WIKI_BASE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "LLM_Wiki", "Trading_Wiki", "wiki")
)

CATEGORIES = [
    "trading",
    "scalping_trading",
    "trading_options",
    "crypto_trading",
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
