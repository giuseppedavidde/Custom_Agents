"""
Skill Loader: carica skills OpenCode generate da book-to-skill-bridge.

Se una skill non esiste ancora, la genera automaticamente (lazy generation)
cercando il PDF corrispondente in LLM_Wiki/Trading_Wiki/raw/.

Utilizzo:
    from skill_loader import load_skills, get_available_slugs
    content = load_skills(["wyckoff-2-0", "volume-price-analysis"])
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"
TRADING_WIKI = (
    Path.home() / "Progetti" / "Github" / "LLM_Wiki" / "Trading_Wiki"
)

# Mapping slug → path to PDF inside Trading_Wiki
SLUG_TO_PDF: dict[str, str | None] = {
    "wyckoff-2-0": "raw/trading/Wyckoff 2.0",
    "volume-price-analysis": "raw/trading/A Complete Guide To Volume Price Analysis",
    "volume-profile": "raw/trading/VOLUME PROFILE",
    "trades-about-to-happen": "raw/trading/Trades About to Happen",
    "trading-against-the-crowd": "raw/trading/Trading Against the Crowd",
    "price-action-volman": "raw/scalping-trading/Understanding Price Action",
    "options-playbook": "raw/options/The Options Playbook",
    "options-course-workbook": "raw/options/The Options Course Workbook",
    "options-crash-course": "raw/options/Options Trading Crash Course",
    "crypto-technical-analysis": "raw/crypto/Crypto Technical Analysis",
    "crypto-crash-course": "raw/crypto/The Crypto Crash Course",
}


def _find_pdf(partial_path: str) -> Optional[Path]:
    """Find the actual PDF file matching a partial path."""
    base = TRADING_WIKI / partial_path
    if base.is_file():
        return base
    pattern = base.name + "*"
    pdf_dir = base.parent
    if not pdf_dir.exists():
        return None
    for f in sorted(pdf_dir.glob(f"{base.name}*.pdf")):
        return f
    for f in sorted(pdf_dir.glob(f"{base.name}*")):
        return f
    return None


def load_skill(slug: str) -> Optional[str]:
    """Load a single skill's SKILL.md content.

    If the skill does not exist, attempt lazy generation via book-to-skill-bridge.
    Returns None only if the skill truly cannot be found or generated.
    """
    skill_dir = SKILLS_DIR / slug
    skill_file = skill_dir / "SKILL.md"

    if skill_file.exists():
        return skill_file.read_text(encoding="utf-8", errors="replace")

    # Lazy generation
    pdf_path = _find_pdf(SLUG_TO_PDF.get(slug, "")) if slug in SLUG_TO_PDF else None
    if not pdf_path:
        # Try scanning raw/ directories for a matching PDF
        raw_dir = TRADING_WIKI / "raw"
        if raw_dir.exists():
            for topic_dir in raw_dir.iterdir():
                if topic_dir.is_dir():
                    for f in topic_dir.iterdir():
                        if f.suffix.lower() == ".pdf" and slug in f.stem.lower():
                            pdf_path = f
                            break
    if not pdf_path or not pdf_path.exists():
        return None

    print(f"[skill_loader] Generating skill '{slug}' from {pdf_path.name}...", file=sys.stderr)
    try:
        result = subprocess.run(
            [
                "opencode", "run",
                f"/book-to-skill-bridge {pdf_path} {slug}",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            print(f"[skill_loader] Generation failed: {result.stderr[:200]}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"[skill_loader] Exception during generation: {e}", file=sys.stderr)
        return None

    # Retry load
    if skill_file.exists():
        return skill_file.read_text(encoding="utf-8", errors="replace")
    return None


def load_skills(slugs: list[str]) -> dict[str, str]:
    """Load multiple skills. Returns {slug: content} for each successfully loaded skill.

    If a slug is not found and cannot be generated, it is omitted from the result.
    """
    result = {}
    for slug in slugs:
        content = load_skill(slug)
        if content:
            result[slug] = content
        else:
            print(f"[skill_loader] WARNING: Skill '{slug}' not available", file=sys.stderr)
    return result


def get_available_slugs() -> list[str]:
    """Return list of all installed skill slugs in ~/.config/opencode/skills/."""
    if not SKILLS_DIR.exists():
        return []
    slugs = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            slugs.append(d.name)
    return slugs


def _strip_yaml(text: str) -> str:
    """Strip YAML frontmatter (---...--- or +++...+++) from start of file."""
    return re.sub(r"^(---|\+\+\+)[\s\S]*?^(---|\+\+\+)\s*\n?", "", text)


def extract_frameworks(skill_md: str) -> str:
    """Extract the Core Frameworks section from a skill's SKILL.md.

    Returns the first ~2000 tokens of the frameworks section, or the full content
    if no frameworks section is found.
    """
    cleaned = _strip_yaml(skill_md)
    match = re.search(
        r"^## Core Frameworks.*?(?=\n## |\Z)",
        cleaned,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(0).strip()

    # Fallback: first 3000 chars (after stripping YAML)
    return cleaned[:3000].strip()


if __name__ == "__main__":
    # Test: load all known skills
    import pprint
    slugs = [
        "wyckoff-2-0", "volume-price-analysis", "volume-profile",
        "trades-about-to-happen", "trading-against-the-crowd",
        "price-action-volman", "options-playbook", "options-course-workbook",
        "options-crash-course", "crypto-technical-analysis", "crypto-crash-course",
    ]
    result = load_skills(slugs)
    print(f"Loaded {len(result)}/{len(slugs)} skills:")
    for slug, content in result.items():
        print(f"  {slug}: {len(content)} chars")
