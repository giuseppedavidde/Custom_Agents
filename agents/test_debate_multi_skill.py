"""
Offline test for debate_multi_skill — verifies skill loading, prompt construction,
round iteration, and record saving without requiring an LLM.

Usage: python -m agents.test_debate_multi_skill
"""
import json
import sys

from .opencode_debate import (
    OpencodeDebate,
    DebateRound,
    DebateRecordMulti,
    DebateHistoryMulti,
    SLUG_TO_NAME,
)
from .skill_loader import load_skills, extract_frameworks


# ── Mock agent that returns deterministic text ──
class _MockAgent:
    def __init__(self):
        self.round_count = 0

    def stream_prompt(self, prompt: str):
        self.round_count += 1
        signal = "LONG" if self.round_count % 2 == 0 else "WAIT"
        confidence = min(70 + self.round_count * 5, 99)
        yield json.dumps({
            "signal": signal,
            "confidence": confidence,
            "setup": f"Mock analysis from round {self.round_count}",
            "analysis": f"This is a mock analysis for round {self.round_count}",
            "key_levels": {"support": 180, "resistance": 185},
        })


class _MockConfig:
    model: str = "test-model"
    temperature: float = 0.3
    max_tokens: int = 500
    system_prompt: str = "System prompt"


def _make_mock_debate() -> OpencodeDebate:
    debate = OpencodeDebate.__new__(OpencodeDebate)
    debate.agent = _MockAgent()  # type: ignore[assignment]
    debate.knowledge = {"test": "knowledge"}
    debate.config = _MockConfig()  # type: ignore[assignment]
    debate._first_round_done = False
    return debate


def test_skill_loading():
    slugs = [
        "wyckoff-2-0", "volume-price-analysis", "volume-profile",
        "trades-about-to-happen", "price-action-volman",
    ]
    skills = load_skills(slugs)
    assert len(skills) == len(slugs)
    for slug, content in skills.items():
        assert len(content) > 1000, f"{slug}: {len(content)} chars"
        fw = extract_frameworks(content)
        assert len(fw) > 200, f"{slug} frameworks: {len(fw)} chars"
    print(f"  ✓ Loaded {len(skills)}/{len(slugs)} skills with frameworks")


def test_framework_extraction():
    skills = load_skills(["wyckoff-2-0", "options-playbook"])
    fw = extract_frameworks(skills.get("wyckoff-2-0", ""))
    assert len(fw) > 500 and "Wyckoff" in fw
    fw = extract_frameworks(skills.get("options-playbook", ""))
    assert len(fw) > 500
    print(f"  ✓ Wyckoff and Options frameworks extracted correctly")


def test_slug_to_name_mapping():
    known = [
        "wyckoff-2-0", "volume-price-analysis", "volume-profile",
        "trades-about-to-happen", "trading-against-the-crowd",
        "price-action-volman", "options-playbook", "options-course-workbook",
        "options-crash-course", "crypto-technical-analysis", "crypto-crash-course",
    ]
    for slug in known:
        assert slug in SLUG_TO_NAME, f"Missing: {slug}"
    print(f"  ✓ All {len(known)} slugs in SLUG_TO_NAME")


def test_debate_multi_skill_mock():
    debate = _make_mock_debate()
    slugs = ["wyckoff-2-0", "volume-price-analysis"]
    full_text = "".join(debate.debate_multi_skill(
        ticker="AAPL", price=185.50,
        change=1.25, skill_slugs=slugs,
        trend="Bullish", adx=28.0, rsi=62.0,
        stoch_k=75.0, stoch_d=68.0,
        macd=0.45, macd_signal=0.32, macd_histogram=0.13,
        bb_position="Above Mid", bb_width=0.08, volume_ratio=1.3,
    ))

    for r in range(1, 5):
        assert f"Round {r}/4" in full_text, f"Missing Round {r}/4"
    assert "Analisi Tecnica Base" in full_text
    assert "Sintesi Finale" in full_text
    assert "Wyckoff" in full_text or "Wyckoff 2.0" in full_text
    assert "Volume Price Analysis" in full_text or "VPA" in full_text
    round_count = full_text.count("Round ")
    assert round_count >= 4, f"Found {round_count} rounds, expected >=4"
    print(f"  ✓ Mock debate produced {len(full_text)} chars with {round_count} round headers")


def test_multi_skill_record_saving():
    record = DebateRecordMulti(
        ticker="TSLA",
        skill_slugs=["wyckoff-2-0", "volume-price-analysis"],
        rounds=[
            DebateRound(name="Analisi Base", knowledge_used="none",
                        parsed_signal="WAIT", parsed_confidence=50.0),
            DebateRound(name="Wyckoff", knowledge_used="wyckoff-2-0",
                        parsed_signal="LONG", parsed_confidence=80.0),
            DebateRound(name="VPA", knowledge_used="volume-price-analysis",
                        parsed_signal="LONG", parsed_confidence=75.0),
            DebateRound(name="Sintesi Finale", knowledge_used="none",
                        parsed_signal="LONG", parsed_confidence=78.0),
        ],
        final_signal="LONG",
        final_confidence=78.0,
    )
    data = record.model_dump()
    assert data["ticker"] == "TSLA"
    assert len(data["rounds"]) == 4
    assert data["final_signal"] == "LONG"

    history = DebateHistoryMulti()
    history.add(record)
    latest = history.get_latest("TSLA")
    assert latest is not None and latest.final_signal == "LONG"
    print(f"  ✓ DebateRecordMulti serializes ({len(data['rounds'])} rounds), history stores/retrieves")


def run_all():
    failures = 0
    tests = [
        ("Skill Loading", test_skill_loading),
        ("Framework Extraction", test_framework_extraction),
        ("SLUG_TO_NAME Mapping", test_slug_to_name_mapping),
        ("Debate Multi-Skill (Mock)", test_debate_multi_skill_mock),
        ("Record Saving", test_multi_skill_record_saving),
    ]
    for name, fn in tests:
        try:
            fn()
            print(f"  [✓] {name}")
        except Exception as e:
            print(f"  [✗] {name}: {e}")
            failures += 1

    print(f"\n{'─' * 40}")
    print(f"Results: {len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(run_all())
