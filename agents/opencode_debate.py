"""Modulo OpencodeDebate: orchestratore dibattito multi-round tra analisi base e knowledge skills."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterator, Optional

from pydantic import BaseModel, Field

from .opencode_agent import OpencodeAgent, OpencodeConfig, load_all_knowledge
from .skill_loader import load_skills, extract_frameworks


class DebateRound(BaseModel):
    """Un singolo round del debate."""

    name: str
    knowledge_used: str = "none"
    prompt: str = ""
    result: str = ""
    parsed_signal: Optional[str] = None
    parsed_confidence: Optional[float] = None


class DebateRecord(BaseModel):
    """Record completo di un debate legacy a 3 round."""

    timestamp: datetime = Field(default_factory=datetime.now)
    ticker: str
    analysis_type: str = "technical"
    round1: DebateRound
    round2: DebateRound
    synthesis: DebateRound
    final_signal: str = "WAIT"
    final_confidence: float = 0.0


class DebateRecordMulti(BaseModel):
    """Record per debate multi-skill con N round (base + skills + sintesi)."""

    timestamp: datetime = Field(default_factory=datetime.now)
    ticker: str
    analysis_type: str = "multi-skill"
    skill_slugs: list[str] = []
    rounds: list[DebateRound] = []
    final_signal: str = "WAIT"
    final_confidence: float = 0.0


class DebateHistory(BaseModel):
    """Storico dei debate legacy (3 round) salvati in sessione."""

    records: list[DebateRecord] = []

    def add(self, record: DebateRecord) -> None:
        self.records.append(record)

    def get_latest(self, ticker: str) -> Optional[DebateRecord]:
        for rec in reversed(self.records):
            if rec.ticker.upper() == ticker.upper():
                return rec
        return None

    def get_all_for_ticker(self, ticker: str) -> list[DebateRecord]:
        return [
            rec for rec in self.records if rec.ticker.upper() == ticker.upper()
        ]


class DebateHistoryMulti(BaseModel):
    """Storico dei debate multi-skill (N round) salvati in sessione."""

    records: list[DebateRecordMulti] = []

    def add(self, record: DebateRecordMulti) -> None:
        self.records.append(record)

    def get_latest(self, ticker: str) -> Optional[DebateRecordMulti]:
        for rec in reversed(self.records):
            if rec.ticker.upper() == ticker.upper():
                return rec
        return None


ROUND1_SYSTEM = """Sei un analista tecnico indipendente e obiettivo.
Analizza il ticker basandoti ESCLUSIVAMENTE sui dati numerici forniti,
senza applicare nessuna specifica scuola di trading o framework teorico.
Concentrati sui numeri e sulle evidenze oggettive."""

ROUND2_VPA_SYSTEM = """Sei un trader esperto specializzato in Volume Price Analysis (VPA) e Price Action.
Applica le conoscenze teoriche fornite per interpretare i dati di mercato.
Identifica anomalie prezzo-volume e setup operativi riconoscibili."""

ROUND2_OPTIONS_SYSTEM = """Sei un trader di opzioni istituzionale.
Applica le conoscenze teoriche fornite per analizzare le strategie.
Usa il framework Direction, Duration, Magnitude per valutare i setup."""

ROUND3_SYSTEM = """Sei un senior trader supervisore con anni di esperienza sui mercati.
Il tuo compito e' confrontare due analisi indipendenti per lo stesso ticker,
identificare convergenze e divergenze, e produrre una sintesi obiettiva.
Non hai nessun pregiudizio verso nessuna delle due scuole di pensiero."""

ROUND_SKILL_SYSTEM = """Sei un trader specializzato nel framework "{skill_name}".
Applica le conoscenze teoriche fornite per interpretare i dati di mercato.
Usa i concetti, le regole e i setup del framework nella tua analisi.
Identifica pattern, anomalie e setup operativi riconoscibili secondo questo framework."""

ROUND_FINAL_SYSTEM = """Sei un senior trader supervisore con esperienza su tutti i framework di trading.
Il tuo compito e' confrontare TUTTE le analisi indipendenti per lo stesso ticker,
ciascuna basata su un diverso framework di trading.
Identifica convergenze (punti in cui piu' framework concordano) e divergenze.
Risolvi i conflitti usando il principio che la convergenza tra framework e' piu' affidabile di un singolo framework.
Produci un verdetto unico e sintetico."""

SLUG_TO_NAME = {
    "wyckoff-2-0": "Wyckoff 2.0 — Structures, Volume Profile & Order Flow",
    "volume-price-analysis": "Volume Price Analysis (VPA) — Coulling",
    "volume-profile": "Volume Profile — The Insider's Guide",
    "trades-about-to-happen": "Trades About to Happen — Weis Wave",
    "trading-against-the-crowd": "Trading Against the Crowd — Sentiment Analysis",
    "price-action-volman": "Price Action (5-min) — Bob Volman",
    "options-playbook": "Options Playbook — Brian Overby",
    "options-course-workbook": "Options Course Workbook — Fontanills",
    "options-crash-course": "Options Crash Course",
    "crypto-technical-analysis": "Crypto Technical Analysis",
    "crypto-crash-course": "Crypto Crash Course",
}


def _fmt(val: Any, decimals: int = 2) -> str:
    """Format a numeric value or return 'N/A'."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


def _guess_signal(text: str) -> dict[str, Any]:
    """Extract signal and confidence from text heuristically."""
    signal = "WAIT"
    confidence = 0.0

    text_upper = text.upper()

    try:
        data = json.loads(text) if isinstance(text, str) else text
        if isinstance(data, dict):
            for key in ("signal", "action", "final_signal"):
                if key in data:
                    val = str(data[key]).upper()
                    if val in ("LONG", "SHORT", "WAIT"):
                        signal = val
                        break
            for key in ("confidence", "final_confidence"):
                if key in data:
                    try:
                        confidence = float(data[key])
                    except (ValueError, TypeError):
                        pass
                    break

    except (json.JSONDecodeError, TypeError):
        pass

    if signal == "WAIT":
        if "LONG" in text_upper and "SHORT" not in text_upper:
            signal = "LONG"
        elif "SHORT" in text_upper and "LONG" not in text_upper:
            signal = "SHORT"

    if confidence == 0.0:
        matches = re.findall(r'confidence["\s:]+(\d+(?:\.\d+)?)', text, re.IGNORECASE)
        if matches:
            try:
                confidence = float(matches[0])
            except (ValueError, TypeError):
                pass

    return {"signal": signal, "confidence": min(confidence, 100.0)}


class OpencodeDebate:
    """Orchestratore di debate a 3 round tra analisi base e knowledge-based."""

    def __init__(self, config: OpencodeConfig) -> None:
        self.agent = OpencodeAgent(config)
        self.knowledge = load_all_knowledge()

    def _make_prompt_round1(
        self,
        ticker: str,
        price: float,
        change: Optional[float] = None,
        trend: str = "Unknown",
        adx: Optional[float] = None,
        rsi: Optional[float] = None,
        stoch_k: Optional[float] = None,
        stoch_d: Optional[float] = None,
        williams_r: Optional[float] = None,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        macd_histogram: Optional[float] = None,
        bb_position: str = "N/A",
        bb_width: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        volume_signal: str = "N/A",
        patterns: Optional[list[str]] = None,
        holders_text: Optional[str] = None,
        financials_text: Optional[str] = None,
    ) -> str:
        """Round 1: prompt senza knowledge, solo dati."""
        change_str = f" ({change:+.2f}%)" if change is not None else ""
        patterns_str = ", ".join(patterns) if patterns else "Nessuno"

        prompt = f"""{ROUND1_SYSTEM}

DATI NUMERICI {ticker}:
- Prezzo: {price}{change_str}
- Trend: {trend} (ADX: {_fmt(adx)})
- RSI(14): {_fmt(rsi)}
- Stocastico: {_fmt(stoch_k)}/{_fmt(stoch_d)}
- Williams %R: {_fmt(williams_r)}
- MACD: {_fmt(macd, 4)} / Signal: {_fmt(macd_signal, 4)} / Hist: {_fmt(macd_histogram, 4)}
- Bollinger: posizione={bb_position}, larghezza={_fmt(bb_width)}
- Volume: {_fmt(volume_ratio)}x ({volume_signal})
- Pattern: {patterns_str}
"""
        if holders_text:
            prompt += f"\nAZIONARIATO:\n{holders_text}\n"
        if financials_text:
            prompt += f"\nFINANZIARI:\n{financials_text}\n"

        prompt += """
Analizza e produci un report in formato JSON:
{"signal": "LONG/SHORT/WAIT", "confidence": 0-100, "analysis": "...", "key_levels": {"support": X, "resistance": Y}}
"""
        return prompt

    def _make_prompt_round2_vpa(
        self,
        ticker: str,
        price: float,
        change: Optional[float] = None,
        trend: str = "Unknown",
        adx: Optional[float] = None,
        rsi: Optional[float] = None,
        stoch_k: Optional[float] = None,
        stoch_d: Optional[float] = None,
        williams_r: Optional[float] = None,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        macd_histogram: Optional[float] = None,
        bb_position: str = "N/A",
        bb_width: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        volume_signal: str = "N/A",
        patterns: Optional[list[str]] = None,
        holders_text: Optional[str] = None,
        financials_text: Optional[str] = None,
    ) -> str:
        """Round 2: prompt con knowledge VPA Coulling/Volman."""
        vpa_knowledge = self.knowledge.get("vpa", "")
        change_str = f" ({change:+.2f}%)" if change is not None else ""
        patterns_str = ", ".join(patterns) if patterns else "Nessuno"

        prompt = f"""{ROUND2_VPA_SYSTEM}

CONOSCENZA TEORICA (VPA & Price Action - Coulling/Volman):
{vpa_knowledge}

DATI DI MERCATO {ticker}:
- Prezzo: {price}{change_str}
- Trend: {trend} (ADX: {_fmt(adx)})
- RSI(14): {_fmt(rsi)}
- Stocastico: {_fmt(stoch_k)}/{_fmt(stoch_d)}
- Williams %R: {_fmt(williams_r)}
- MACD: {_fmt(macd, 4)} / Signal: {_fmt(macd_signal, 4)} / Hist: {_fmt(macd_histogram, 4)}
- Bollinger: posizione={bb_position}, larghezza={_fmt(bb_width)}
- Volume: {_fmt(volume_ratio)}x ({volume_signal})
- Pattern: {patterns_str}
"""
        if holders_text:
            prompt += f"\nAZIONARIATO:\n{holders_text}\n"
        if financials_text:
            prompt += f"\nFINANZIARI:\n{financials_text}\n"

        prompt += """
Applica le anomalie prezzo-volume (Sforzo senza Risultato, Risultato senza Sforzo,
Selling Climax, Stopping Volume, Divergenza, Sumo Candle) ai dati forniti.
Identifica eventuali setup operativi di Volman (Break, Pullback, Range Break, etc.).
Valuta i livelli magnete psicologici (00/50).

Produci un report in formato JSON:
{"signal": "LONG/SHORT/WAIT", "confidence": 0-100, "vpa_anomalies": [...], "volman_setup": "...", "analysis": "..."}
"""
        return prompt

    def _make_prompt_round2_options(
        self,
        ticker: str,
        price: float,
        change: Optional[float] = None,
        trend: str = "Unknown",
        adx: Optional[float] = None,
        rsi: Optional[float] = None,
        stoch_k: Optional[float] = None,
        stoch_d: Optional[float] = None,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        macd_histogram: Optional[float] = None,
        bb_position: str = "N/A",
        bb_width: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        iv: Optional[float] = None,
        greeks_summary: Optional[str] = None,
        expirations: Optional[list[str]] = None,
        strikes: Optional[list[float]] = None,
        geopolitics_context: Optional[str] = None,
        holders_text: Optional[str] = None,
        financials_text: Optional[str] = None,
    ) -> str:
        """Round 2: prompt con knowledge Options Fontanills."""
        options_knowledge = self.knowledge.get("options", "")
        change_str = f" ({change:+.2f}%)" if change is not None else ""
        exps_str = ", ".join(expirations) if expirations else "N/A"
        strikes_str = ", ".join(str(s) for s in (strikes or []))

        prompt = f"""{ROUND2_OPTIONS_SYSTEM}

CONOSCENZA TEORICA (Options Trading - Fontanills):
{options_knowledge}

DATI DI MERCATO {ticker}:
- Prezzo: {price}{change_str}
- Trend: {trend} (ADX: {_fmt(adx)})
- RSI(14): {_fmt(rsi)}
- Stocastico: {_fmt(stoch_k)}/{_fmt(stoch_d)}
- MACD: {_fmt(macd, 4)} / Signal: {_fmt(macd_signal, 4)} / Hist: {_fmt(macd_histogram, 4)}
- Bollinger: posizione={bb_position}, larghezza={_fmt(bb_width)}
- Volume: {_fmt(volume_ratio)}x
- IV: {_fmt(iv, 1)}%
- Scadenze disponibili: {exps_str}
- Strikes: {strikes_str}
"""
        if greeks_summary:
            prompt += f"\nGREEKS TABLE:\n{greeks_summary}\n"
        if geopolitics_context:
            prompt += f"\nCONTESTO GEOPOLITICO:\n{geopolitics_context}\n"
        if holders_text:
            prompt += f"\nAZIONARIATO:\n{holders_text}\n"
        if financials_text:
            prompt += f"\nFINANZIARI:\n{financials_text}\n"

        prompt += """
Usa il framework Direction, Duration, Magnitude per valutare i possibili setup.
Considera le regole delle greche (Delta, Gamma, Theta, Vega) e il contesto di volatilita'.

Produci un report in formato JSON:
{"signal": "LONG/SHORT/WAIT", "confidence": 0-100, "strategy": "...", "analysis": "..."}
"""
        return prompt

    def _make_prompt_round3(
        self,
        ticker: str,
        round1_text: str,
        round2_text: str,
        analysis_type: str = "VPA",
    ) -> str:
        """Round 3: giudice neutrale, confronta R1 e R2."""
        prompt = f"""{ROUND3_SYSTEM}

Confronta le due analisi indipendenti per {ticker}:

── ANALISI 1 (Tecnica Base - senza framework teorico) ──
{round1_text[:2000]}

── ANALISI 2 ({analysis_type} - con knowledge specializzata) ──
{round2_text[:2000]}

Confrontale oggettivamente:
1. PUNTI DI CONVERGENZA: dove concordano? (alta confidenza)
2. PUNTI DI DIVERGENZA: dove discordano? (risolvi il conflitto)
3. SINTESI FINALE: risolvi le divergenze e produci un verdetto unico

Produci un report in formato JSON:
{{"final_signal": "LONG/SHORT/WAIT", "confidence": 0-100, "convergences": [...], "divergences": [...], "resolution": "...", "synthesis": "..."}}
"""
        return prompt

    def debate_technical_analysis(
        self,
        ticker: str,
        price: float,
        change: Optional[float] = None,
        trend: str = "Unknown",
        adx: Optional[float] = None,
        rsi: Optional[float] = None,
        stoch_k: Optional[float] = None,
        stoch_d: Optional[float] = None,
        williams_r: Optional[float] = None,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        macd_histogram: Optional[float] = None,
        bb_position: str = "N/A",
        bb_width: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        volume_signal: str = "N/A",
        patterns: Optional[list[str]] = None,
        holders_text: Optional[str] = None,
        financials_text: Optional[str] = None,
    ) -> Iterator[str]:
        """Esegue debate 3 round per analisi tecnica (knowledge VPA)."""
        kw = dict(
            ticker=ticker,
            price=price,
            change=change,
            trend=trend,
            adx=adx,
            rsi=rsi,
            stoch_k=stoch_k,
            stoch_d=stoch_d,
            williams_r=williams_r,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            bb_position=bb_position,
            bb_width=bb_width,
            volume_ratio=volume_ratio,
            volume_signal=volume_signal,
            patterns=patterns,
            holders_text=holders_text,
            financials_text=financials_text,
        )

        yield "## 📊 Round 1/3: Analisi Tecnica Base\n"
        r1_prompt = self._make_prompt_round1(**kw)
        r1_text = ""
        for chunk in self.agent.stream_prompt(r1_prompt):
            r1_text += chunk
            yield chunk
        
        if not r1_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per il Round 1. Verificare i log o la connessione.*"

        yield "\n\n---\n\n## 📈 Round 2/3: Analisi VPA (Coulling/Volman)\n"
        r2_prompt = self._make_prompt_round2_vpa(**kw)
        r2_text = ""
        for chunk in self.agent.stream_prompt(r2_prompt):
            r2_text += chunk
            yield chunk
            
        if not r2_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per il Round 2. Verificare i log o la connessione.*"

        yield "\n\n---\n\n## 🏆 Round 3/3: Sintesi Finale\n"
        r3_prompt = self._make_prompt_round3(ticker, r1_text, r2_text, "VPA")
        r3_text = ""
        for chunk in self.agent.stream_prompt(r3_prompt):
            r3_text += chunk
            yield chunk
            
        if not r3_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per la Sintesi Finale.*"

        self._save_debate_record(
            ticker=ticker,
            analysis_type="technical",
            r1_text=r1_text,
            r2_text=r2_text,
            r3_text=r3_text,
            r1_prompt=r1_prompt,
            r2_prompt=r2_prompt,
            r3_prompt=r3_prompt,
        )

    def debate_option_strategy(
        self,
        ticker: str,
        price: float,
        change: Optional[float] = None,
        trend: str = "Unknown",
        adx: Optional[float] = None,
        rsi: Optional[float] = None,
        stoch_k: Optional[float] = None,
        stoch_d: Optional[float] = None,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        macd_histogram: Optional[float] = None,
        bb_position: str = "N/A",
        bb_width: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        iv: Optional[float] = None,
        greeks_summary: Optional[str] = None,
        expirations: Optional[list[str]] = None,
        strikes: Optional[list[float]] = None,
        geopolitics_context: Optional[str] = None,
        holders_text: Optional[str] = None,
        financials_text: Optional[str] = None,
    ) -> Iterator[str]:
        """Esegue debate 3 round per strategie opzioni (knowledge Fontanills)."""
        kw = dict(
            ticker=ticker,
            price=price,
            change=change,
            trend=trend,
            adx=adx,
            rsi=rsi,
            stoch_k=stoch_k,
            stoch_d=stoch_d,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            bb_position=bb_position,
            bb_width=bb_width,
            volume_ratio=volume_ratio,
        )

        yield "## 📊 Round 1/3: Analisi Base\n"
        r1_prompt = self._make_prompt_round1(**kw)
        r1_text = ""
        for chunk in self.agent.stream_prompt(r1_prompt):
            r1_text += chunk
            yield chunk

        if not r1_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per il Round 1.*"

        yield "\n\n---\n\n## 📈 Round 2/3: Analisi Options (Fontanills)\n"
        r2_kw = dict(
            ticker=ticker,
            price=price,
            change=change,
            trend=trend,
            adx=adx,
            rsi=rsi,
            stoch_k=stoch_k,
            stoch_d=stoch_d,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            bb_position=bb_position,
            bb_width=bb_width,
            volume_ratio=volume_ratio,
            iv=iv,
            greeks_summary=greeks_summary,
            expirations=expirations,
            strikes=strikes,
            geopolitics_context=geopolitics_context,
            holders_text=holders_text,
            financials_text=financials_text,
        )
        r2_prompt = self._make_prompt_round2_options(**r2_kw)
        r2_text = ""
        for chunk in self.agent.stream_prompt(r2_prompt):
            r2_text += chunk
            yield chunk

        if not r2_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per il Round 2.*"

        yield "\n\n---\n\n## 🏆 Round 3/3: Sintesi Finale\n"
        r3_prompt = self._make_prompt_round3(ticker, r1_text, r2_text, "Options")
        r3_text = ""
        for chunk in self.agent.stream_prompt(r3_prompt):
            r3_text += chunk
            yield chunk

        if not r3_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per la Sintesi Finale.*"

        self._save_debate_record(
            ticker=ticker,
            analysis_type="options",
            r1_text=r1_text,
            r2_text=r2_text,
            r3_text=r3_text,
            r1_prompt=r1_prompt,
            r2_prompt=r2_prompt,
            r3_prompt=r3_prompt,
        )

    def debate_multi_skill(
        self,
        ticker: str,
        price: float,
        skill_slugs: Optional[list[str]] = None,
        change: Optional[float] = None,
        trend: str = "Unknown",
        adx: Optional[float] = None,
        rsi: Optional[float] = None,
        stoch_k: Optional[float] = None,
        stoch_d: Optional[float] = None,
        williams_r: Optional[float] = None,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        macd_histogram: Optional[float] = None,
        bb_position: str = "N/A",
        bb_width: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        volume_signal: str = "N/A",
        patterns: Optional[list[str]] = None,
        holders_text: Optional[str] = None,
        financials_text: Optional[str] = None,
    ) -> Iterator[str]:
        """Debate multi-skill: R1 base + RN skill rounds + Final synthesis.

        Carica le skills specificate, esegue un round per ognuna,
        poi produce una sintesi finale che confronta tutte le prospettive.
        """
        if not skill_slugs:
            yield from self.debate_technical_analysis(
                ticker=ticker, price=price, change=change,
                trend=trend, adx=adx, rsi=rsi,
                stoch_k=stoch_k, stoch_d=stoch_d,
                williams_r=williams_r, macd=macd,
                macd_signal=macd_signal, macd_histogram=macd_histogram,
                bb_position=bb_position, bb_width=bb_width,
                volume_ratio=volume_ratio, volume_signal=volume_signal,
                patterns=patterns, holders_text=holders_text,
                financials_text=financials_text,
            )
            return

        skills_content = load_skills(skill_slugs)
        if not skills_content:
            yield "⚠️ Nessuna skill disponibile. Uso analisi standard.\n\n"
            yield from self.debate_technical_analysis(
                ticker=ticker, price=price, change=change,
                trend=trend, adx=adx, rsi=rsi,
                stoch_k=stoch_k, stoch_d=stoch_d,
                williams_r=williams_r, macd=macd,
                macd_signal=macd_signal, macd_histogram=macd_histogram,
                bb_position=bb_position, bb_width=bb_width,
                volume_ratio=volume_ratio, volume_signal=volume_signal,
                patterns=patterns, holders_text=holders_text,
                financials_text=financials_text,
            )
            return

        kw = dict(
            ticker=ticker, price=price, change=change,
            trend=trend, adx=adx, rsi=rsi,
            stoch_k=stoch_k, stoch_d=stoch_d,
            williams_r=williams_r, macd=macd,
            macd_signal=macd_signal, macd_histogram=macd_histogram,
            bb_position=bb_position, bb_width=bb_width,
            volume_ratio=volume_ratio, volume_signal=volume_signal,
            patterns=patterns,
            holders_text=holders_text, financials_text=financials_text,
        )

        change_str = f" ({change:+.2f}%)" if change is not None else ""
        patterns_str = ", ".join(patterns) if patterns else "Nessuno"

        n_skills = len(skills_content)
        total_rounds = 1 + n_skills + 1  # R1 + Rn skills + Final

        # ── R1: Base analysis (no knowledge) ──
        yield f"## 📊 Round 1/{total_rounds}: Analisi Tecnica Base\n\n"
        r1_prompt = self._make_prompt_round1(**kw)
        r1_text = ""
        for chunk in self.agent.stream_prompt(r1_prompt):
            r1_text += chunk
            yield chunk
        if not r1_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per il Round 1.*"

        # ── R2..RN: Skill-based rounds ──
        skill_texts: dict[str, str] = {}
        for i, (slug, sk_content) in enumerate(skills_content.items(), start=2):
            skill_name = slug.replace("-", " ").title()
            frameworks = extract_frameworks(sk_content)
            yield f"\n\n---\n\n## 📈 Round {i}/{total_rounds}: {skill_name}\n\n"
            yield f"> Framework: {SLUG_TO_NAME.get(slug, skill_name)}\n\n"

            system = ROUND_SKILL_SYSTEM.format(skill_name=skill_name)
            prompt = f"""{system}

CONOSCENZA TEORICA ({skill_name}):
{frameworks}

DATI DI MERCATO {ticker}:
- Prezzo: {price}{change_str}
- Trend: {trend} (ADX: {_fmt(adx)})
- RSI(14): {_fmt(rsi)}
- Stocastico: {_fmt(stoch_k)}/{_fmt(stoch_d)}
- Williams %R: {_fmt(williams_r)}
- MACD: {_fmt(macd, 4)} / Signal: {_fmt(macd_signal, 4)} / Hist: {_fmt(macd_histogram, 4)}
- Bollinger: posizione={bb_position}, larghezza={_fmt(bb_width)}
- Volume: {_fmt(volume_ratio)}x ({volume_signal})
- Pattern: {patterns_str}
"""
            if holders_text:
                prompt += f"\nAZIONARIATO:\n{holders_text}\n"
            if financials_text:
                prompt += f"\nFINANZIARI:\n{financials_text}\n"

            prompt += """
Applica i concetti del framework ai dati forniti.
Identifica setup operativi, pattern, anomalie o conferme.
Produci un report in formato JSON:
{"signal": "LONG/SHORT/WAIT", "confidence": 0-100, "setup": "...", "analysis": "...", "key_levels": {"support": X, "resistance": Y}}
"""
            skill_text = ""
            for chunk in self.agent.stream_prompt(prompt):
                skill_text += chunk
                yield chunk
            if not skill_text.strip():
                yield "\n> ⚠️ *Nessun output ricevuto.*"
            skill_texts[slug] = skill_text

        # ── Final round: Synthesis ──
        yield f"\n\n---\n\n## 🏆 Round {total_rounds}/{total_rounds}: Sintesi Finale\n\n"

        final_prompt = f"""{ROUND_FINAL_SYSTEM}

Confronta TUTTE le analisi indipendenti per {ticker}:

── ANALISI BASE (senza framework) ──
{r1_text[:2000]}

"""
        for slug, sk_text in skill_texts.items():
            skill_name = slug.replace("-", " ").title()
            final_prompt += f"── ANALISI {skill_name} ──\n{sk_text[:2000]}\n\n"

        final_prompt += """
Confronta oggettivamente TUTTE le analisi:

1. PUNTI DI CONVERGENZA: dove concordano? (massima confidenza)
2. PUNTI DI DIVERGENZA: dove discordano? (risolvi il conflitto)
3. PESO: dai piu' peso ai punti in cui piu' framework convergono
4. SINTESI FINALE: verdetto unico che integra tutte le prospettive

Produci un report in formato JSON:
{"final_signal": "LONG/SHORT/WAIT", "confidence": 0-100, "convergences": [...], "divergences": [...], "resolution": "...", "synthesis": "..."}
"""
        final_text = ""
        for chunk in self.agent.stream_prompt(final_prompt):
            final_text += chunk
            yield chunk
        if not final_text.strip():
            yield "\n> ⚠️ *Nessun output ricevuto per la Sintesi Finale.*"

        # Save multi-skill record with all N rounds preserved
        r3_signal = _guess_signal(final_text)
        all_rounds: list[DebateRound] = [
            DebateRound(
                name="Analisi Base",
                knowledge_used="none",
                prompt=r1_prompt,
                result=r1_text,
                parsed_signal=_guess_signal(r1_text)["signal"],
                parsed_confidence=_guess_signal(r1_text)["confidence"],
            ),
        ]
        for slug, sk_text in skill_texts.items():
            skill_name = SLUG_TO_NAME.get(slug, slug.replace("-", " ").title())
            all_rounds.append(DebateRound(
                name=skill_name,
                knowledge_used=slug,
                prompt="",
                result=sk_text,
                parsed_signal=_guess_signal(sk_text)["signal"],
                parsed_confidence=_guess_signal(sk_text)["confidence"],
            ))
        all_rounds.append(DebateRound(
            name="Sintesi Finale",
            knowledge_used="none",
            prompt=final_prompt,
            result=final_text,
            parsed_signal=r3_signal["signal"],
            parsed_confidence=r3_signal["confidence"],
        ))
        record = DebateRecordMulti(
            ticker=ticker.upper(),
            analysis_type="multi-skill",
            skill_slugs=list(skill_texts.keys()),
            rounds=all_rounds,
            final_signal=r3_signal["signal"],
            final_confidence=r3_signal["confidence"],
        )
        try:
            import streamlit as st  # type: ignore[import-untyped]
            if "debate_history_multi" not in st.session_state:
                st.session_state.debate_history_multi = DebateHistoryMulti()
            st.session_state.debate_history_multi.add(record)
        except ImportError:
            pass

    def _save_debate_record(
        self,
        ticker: str,
        analysis_type: str,
        r1_text: str,
        r2_text: str,
        r3_text: str,
        r1_prompt: str,
        r2_prompt: str,
        r3_prompt: str,
    ) -> None:
        """Salva il record del debate in session state Streamlit."""
        r1_signal = _guess_signal(r1_text)
        r2_signal = _guess_signal(r2_text)
        r3_signal = _guess_signal(r3_text)

        record = DebateRecord(
            ticker=ticker.upper(),
            analysis_type=analysis_type,
            round1=DebateRound(
                name="Analisi Base",
                knowledge_used="none",
                prompt=r1_prompt,
                result=r1_text,
                parsed_signal=r1_signal["signal"],
                parsed_confidence=r1_signal["confidence"],
            ),
            round2=DebateRound(
                name="Analisi VPA" if analysis_type == "technical" else "Analisi Options",
                knowledge_used="vpa" if analysis_type == "technical" else "options",
                prompt=r2_prompt,
                result=r2_text,
                parsed_signal=r2_signal["signal"],
                parsed_confidence=r2_signal["confidence"],
            ),
            synthesis=DebateRound(
                name="Sintesi Finale",
                knowledge_used="none",
                prompt=r3_prompt,
                result=r3_text,
                parsed_signal=r3_signal["signal"],
                parsed_confidence=r3_signal["confidence"],
            ),
            final_signal=r3_signal["signal"],
            final_confidence=r3_signal["confidence"],
        )

        try:
            import streamlit as st

            if "debate_history" not in st.session_state:
                st.session_state.debate_history = DebateHistory()
            st.session_state.debate_history.add(record)
        except ImportError:
            pass

    @staticmethod
    def render_debate_history_ui() -> None:
        """Render storico debate in Streamlit (legacy + multi-skill)."""
        try:
            import streamlit as st
        except ImportError:
            return

        # ── Legacy 3-round history ──
        history: Optional[DebateHistory] = st.session_state.get("debate_history")
        history_multi: Optional[DebateHistoryMulti] = st.session_state.get("debate_history_multi")

        if (not history or not history.records) and (not history_multi or not history_multi.records):
            return

        with st.expander("📜 Storico Debate", expanded=False):
            total = (len(history.records) if history else 0) + (len(history_multi.records) if history_multi else 0)
            st.caption(f"Totale: {total} debate")

            if history and history.records:
                with st.popover(f"🎯 Legacy ({len(history.records)}):", use_container_width=True):
                    for rec in reversed(history.records[-20:]):
                        r = rec
                        c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1])
                        c1.markdown(f"**{r.ticker}**")
                        c2.markdown(r.analysis_type)
                        c3.markdown(f"`{r.final_signal}`")
                        c4.markdown(f"{r.final_confidence:.0f}%")

            if history_multi and history_multi.records:
                with st.popover(f"🧪 Multi-Skill ({len(history_multi.records)}):", use_container_width=True):
                    for rec in reversed(history_multi.records[-20:]):
                        r = rec
                        skills_str = ", ".join(s[:12] for s in r.skill_slugs)
                        c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1])
                        c1.markdown(f"**{r.ticker}**")
                        c2.markdown(skills_str)
                        c3.markdown(f"`{r.final_signal}`")
                        c4.markdown(f"{r.final_confidence:.0f}%")

                        with st.popover(f"Dettaglio {r.ticker}", use_container_width=True):
                            for i, round_ in enumerate(r.rounds):
                                st.subheader(f"Round {i+1}: {round_.name}")
                                c = round_.parsed_confidence
                                conf_str = f"{c:.0f}%" if c is not None else "N/A"
                                st.caption(f"Segnale: {round_.parsed_signal} | Conf: {conf_str}")
                                if round_.result:
                                    st.text(round_.result[:400])

    @staticmethod
    def render_streamlit_sidebar() -> Optional[OpencodeConfig]:
        """Render config sidebar delegating to OpencodeAgent."""
        return OpencodeAgent.render_streamlit_sidebar()
