import os
from .ai_provider import AIProvider
import json
from typing import List, Dict, Any, Optional


class TraderAgent:
    def __init__(self, provider_type="gemini", model_name=None):
        self.ai = AIProvider(provider_type=provider_type, model_name=model_name)
        self.knowledge = self._load_knowledge()
        # Backward-compat alias used by suggest_option_strategy prompt
        self.knowledge_base = self.knowledge.get("options", "")

    @staticmethod
    def _load_kb_file(filename: str) -> str:
        """Load and lossless-compress a single knowledge markdown file."""
        import re

        kb_path = os.path.join(os.path.dirname(__file__), "knowledge", filename)
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Compressione lossless: rimuove righe vuote multiple e markdown visivo
                content = re.sub(r"\n\s*\n", "\n", content)
                content = re.sub(r"\*\*|\*|---", "", content)
                return content.strip()
        except FileNotFoundError:
            return ""

    def _load_knowledge(self) -> dict:
        """Load all knowledge bases into a dict keyed by domain."""
        return {
            "options": self._load_kb_file("fontanills_options_knowledge.md"),
            "vpa": self._load_kb_file("coulling_volman_knowledge.md"),
        }

    def suggest_option_strategy(
        self,
        ticker: str,
        analysis: dict,
        expirations: List[str],
        strikes: List[float],
        underlying_price: float,
        time_horizon: str = "monthly",
        greeks_table: Optional[List[Dict]] = None,
        iv: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ask the AI to suggest optimal option strategies based on technical analysis
        AND pre-calculated Black-Scholes Greeks.

        Args:
            analysis: dict from detect_patterns() with indicators
            greeks_table: list of dicts from option_utils.compute_greeks_table()
                          Each dict: {strike, expiry, dte, call: {price, delta, gamma, theta, vega}, put: {...}}
            time_horizon: "weekly", "monthly", or "quarterly"

        Returns a list of strategy dicts with 'legs' array and real Greeks per leg.
        """
        trend = analysis.get("trend", "Unknown")
        rsi = analysis.get("rsi", "N/A")
        patterns = ", ".join(analysis.get("patterns", [])) or "None"
        hv = iv or analysis.get("hist_volatility")

        # Build compact indicator section (one line each)
        ind = [f"Price:{underlying_price:.2f} Trend:{trend} RSI:{rsi}"]
        emas = []
        if analysis.get("ema_20"):
            emas.append(f"20={analysis['ema_20']:.2f}")
        if analysis.get("ema_50"):
            emas.append(f"50={analysis['ema_50']:.2f}")
        if analysis.get("ema_200"):
            emas.append(f"200={analysis['ema_200']:.2f}")
        if emas:
            ind.append(f"EMA:{'/'.join(emas)}")
        if analysis.get("vwap"):
            ind.append(f"VWAP:{analysis['vwap']:.2f}")
        if analysis.get("macd") is not None:
            ind.append(
                f"MACD:{analysis['macd']:.4f}/Sig:{analysis.get('macd_signal','')}/H:{analysis.get('macd_histogram','')}"
            )
        if analysis.get("bb_upper"):
            ind.append(
                f"BB:{analysis['bb_lower']:.2f}-{analysis['bb_upper']:.2f}(w={analysis.get('bb_width','')})"
            )
        if hv:
            ind.append(f"HV:{hv*100:.1f}%")
        if analysis.get("volume_ratio"):
            ind.append(f"Vol:{analysis['volume_ratio']}x")
        if patterns != "None":
            ind.append(f"Pat:{patterns}")
        indicators_text = " | ".join(ind)

        # Filter strikes near ATM (±10% to reduce rows)
        atm_range = underlying_price * 0.10
        nearby_strikes = sorted(
            [s for s in strikes if abs(s - underlying_price) <= atm_range]
        )
        if len(nearby_strikes) < 4:
            nearby_strikes = sorted(strikes[:20])

        # Filter expirations based on actual time difference from today
        import datetime

        today_date = datetime.date.today()

        def get_days_to_exp(exp_str):
            try:
                exp_date = datetime.datetime.strptime(exp_str, "%Y%m%d").date()
                return (exp_date - today_date).days
            except:
                return 0

        # Target days for each horizon
        horizon_targets = {
            "weekly": 7,
            "monthly": 30,
            "quarterly": 90,
        }
        target_days = horizon_targets.get(time_horizon, 30)

        # Sort ALL available expirations by how close they are to the target date
        sorted_exps = sorted(
            expirations, key=lambda x: abs(get_days_to_exp(x) - target_days)
        )

        # Take the top 3 closest expirations to give the AI options around that timeframe
        limited_exps = sorted(sorted_exps[:3])

        horizon_label = {
            "weekly": "1-2wk",
            "monthly": "1-2mo",
            "quarterly": "3-6mo",
        }.get(time_horizon, "1-2mo")

        # Build compact CSV Greeks table (no padding, short headers)
        greeks_text = ""
        if greeks_table:
            # Filtro per inviare all'LLM solo i dati delle opzioni selezionate (risparmio drastico di token)
            nearby_strikes_set = set(float(s) for s in nearby_strikes)
            limited_exps_set = set(str(e) for e in limited_exps)

            greeks_lines = ["K,D,CΔ,CΘ,C$,PΔ,PΘ,P$,V"]
            for row in greeks_table:
                if (
                    float(row["strike"]) not in nearby_strikes_set
                    or str(row["expiry"]) not in limited_exps_set
                ):
                    continue
                c, p = row["call"], row["put"]
                greeks_lines.append(
                    f"{row['strike']},{row['dte']},"
                    f"{c['delta']:+.2f},{c['theta']:+.3f},{c['price']:.2f},"
                    f"{p['delta']:+.2f},{p['theta']:+.3f},{p['price']:.2f},{c['vega']:.3f}"
                )
            greeks_text = "\n".join(greeks_lines)

        import datetime

        today_str = datetime.date.today().strftime("%Y-%m-%d")

        prompt = f"""Sei un trader di opzioni istituzionale.
I tuoi principi chiave sono basati su questa knowledge base teorica:

CONOSCENZA TEORICA (Regole di Trading e Adjustments):
{self.knowledge_base}

DATI DI MERCATO REALI (Modello Black-Scholes):
DATA ODIERNA: {today_str} (Usa questa data per calcolare i giorni a scadenza. Le scadenze sono nel formato YYYYMMDD. Esempio oggi e' 2026-02-20, la scadenza 20260223 e' a 3 giorni, non 4 mesi)
{ticker}: {indicators_text}
Horizon (Categoria): {horizon_label}
SCADENZA ESATTA DA UTILIZZARE (OBBLIGATORIO): {','.join(limited_exps)}
Strikes: {','.join(str(s) for s in nearby_strikes)}
"""
        if greeks_text:
            prompt += f"""Greeks(IV={((hv or 0.30)*100):.1f}%,r=5%):
{greeks_text}
"""
        prompt += """Rules: 3 strategies, ALL legs specified, use ONLY listed strikes and the EXACT EXPIRATION DATE provided above. Do not invent dates.
ATTENZIONE ALLA MATEMATICA: Devi agire come una calcolatrice rigorosa. Quando sommi o sottrai decimali (es. 24.5 + 0.18), fallo passo dopo passo per evitare allucinazioni (il risultato è 24.68, non 26.30).  NON INVENTARE MAI LA MATEMATICA.
Respond ONLY valid JSON:
{"strategies":[{"name":"...","direction":"BULLISH/BEARISH/NEUTRAL","legs":[{"action":"BUY/SELL","quantity":1,"strike":0.0,"right":"C/P","expiry":"YYYYMMDD"}],"rationale":"cite real indicators+greeks and ESPLICITARE LA VOLATILITA (IBKR IV) ASSUNTA NEL PRICING (mostrata in Greeks(IV=...)) come possibile fonte di discrepanza dal mercato reale","max_profit":"$X","max_loss":"$X","breakeven":"X.XX","calculations":"Mostra i calcoli matematici espliciti, SCRITTI PASSO PER PASSO COME UN'EQUAZIONE VERIFICATA PUNTUALMENTE (es: 24.50 + 0.18 = 24.68) per profitto massimo, perdita massima e punti di pareggio","probability":65}]}"""

        try:
            model = self.ai.get_model(json_mode=True)
            response = model.generate_content(prompt)
            text = response.text.strip()

            # Clean potential markdown code fences
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            data = json.loads(text)
            strategies = data.get("strategies", [])

            # Build a quick lookup for Greeks
            greeks_lookup = {}
            if greeks_table:
                for row in greeks_table:
                    greeks_lookup[(row["strike"], row["expiry"])] = row

            # Convert available data to sets for fast lookup (Restricting to the subset provided to LLM)
            valid_strikes_set = set(float(s) for s in nearby_strikes)
            valid_exps_set = set(limited_exps)
            sorted_strikes = sorted(valid_strikes_set)

            # Validate and enrich each strategy
            valid = []
            for s in strategies[:3]:
                if not isinstance(s, dict) or "name" not in s or "legs" not in s:
                    continue
                valid_legs = []
                for leg in s.get("legs", []):
                    if not isinstance(leg, dict):
                        continue
                    if all(k in leg for k in ("action", "strike", "right", "expiry")):
                        leg["action"] = str(leg["action"]).upper()
                        leg["right"] = str(leg["right"]).upper()
                        leg.setdefault("quantity", 1)
                        if leg["right"] not in ("C", "P"):
                            leg["right"] = "C"
                        if leg["action"] not in ("BUY", "SELL"):
                            leg["action"] = "BUY"

                        # ── STRICT VALIDATION ──────────────────────────
                        # Snap strike to nearest valid IBKR strike
                        try:
                            leg_strike = float(leg["strike"])
                        except (ValueError, TypeError):
                            leg_strike = 0.0

                        if leg_strike not in valid_strikes_set and valid_strikes_set:
                            nearest = min(
                                sorted_strikes, key=lambda x: abs(x - leg_strike)
                            )
                            print(
                                f"⚠️ Strike {leg_strike} not in IBKR chain → snapped to {nearest}"
                            )
                            leg["strike"] = nearest
                            leg["strike_corrected"] = True
                        else:
                            leg["strike"] = leg_strike

                        # Snap expiry to nearest valid IBKR expiry
                        leg_exp = str(leg["expiry"]).strip()
                        if leg_exp not in valid_exps_set and valid_exps_set:
                            try:
                                # Try to parse as int to find nearest, fallback to first if invalid
                                exp_int = int(leg_exp)
                                nearest_exp = min(
                                    limited_exps, key=lambda x: abs(int(x) - exp_int)
                                )
                            except (ValueError, TypeError):
                                nearest_exp = limited_exps[0]

                            print(
                                f"⚠️ Expiry {leg_exp} not in IBKR chain → snapped to {nearest_exp}"
                            )
                            leg["expiry"] = nearest_exp
                            leg["expiry_corrected"] = True

                        # Attach REAL calculated Greeks to each leg
                        key = (leg["strike"], leg["expiry"])
                        if key in greeks_lookup:
                            side = "call" if leg["right"] == "C" else "put"
                            leg["greeks"] = greeks_lookup[key][side]
                            leg["dte"] = greeks_lookup[key]["dte"]

                        valid_legs.append(leg)

                if not valid_legs:
                    continue

                s["legs"] = valid_legs

                # ── STRICT MATH CALCULATOR ─────────────────────────
                # We calculate P/L locally rather than trusting AI arithmetic
                try:
                    net_cost = 0.0
                    for leg in valid_legs:
                        # Find price from greeks mapped earlier or fallback to 0
                        leg_price = leg.get("greeks", {}).get("price", 0.0)
                        if leg["action"] == "BUY":
                            net_cost += leg_price * leg["quantity"]
                        else:
                            net_cost -= leg_price * leg["quantity"]

                    net_cost = round(net_cost, 2)
                    is_credit = net_cost < 0
                    abs_cost = abs(net_cost)
                    premium = round(abs_cost * 100, 2)

                    # Very basic spread logic: assumed 1x1 vertical spread for breakeven/max risk
                    if (
                        len(valid_legs) == 2
                        and valid_legs[0]["quantity"] == 1
                        and valid_legs[1]["quantity"] == 1
                    ):
                        strike1 = valid_legs[0]["strike"]
                        strike2 = valid_legs[1]["strike"]
                        width = abs(strike1 - strike2)
                        max_risk = (
                            premium
                            if not is_credit
                            else round((width * 100) - premium, 2)
                        )
                        max_reward = (
                            premium if is_credit else round((width * 100) - premium, 2)
                        )

                        # Approximated Breakeven for standard verticals
                        is_call = valid_legs[0]["right"] == "C"
                        if is_call:  # Bull Call / Bear Call
                            lower_strike = min(strike1, strike2)
                            be = (
                                lower_strike + abs_cost
                                if not is_credit
                                else lower_strike + abs_cost
                            )
                        else:  # Bull Put / Bear Put
                            higher_strike = max(strike1, strike2)
                            be = (
                                higher_strike - abs_cost
                                if not is_credit
                                else higher_strike - abs_cost
                            )

                        calc_text = (
                            f"Python Math Engine:\n"
                            f"Net Premium: ${premium} ({'Credit' if is_credit else 'Debit'} di {abs_cost} * 100)\n"
                            f"Max Risk: ${max_risk}\n"
                            f"Max Reward: ${max_reward}\n"
                            f"Breakeven (Approx): {round(be, 2)}\n"
                        )
                        s["max_profit"] = f"${max_reward}"
                        s["max_loss"] = f"${max_risk}"
                        s["breakeven"] = str(round(be, 2))
                        s["calculations"] = (
                            calc_text
                            + "\n(AI Rationale: "
                            + str(s.get("calculations", ""))
                            + ")"
                        )
                    else:
                        # Single leg or complex
                        if len(valid_legs) == 1:
                            leg = valid_legs[0]
                            max_risk = (
                                premium if leg["action"] == "BUY" else "Unlimited"
                            )
                            be = (
                                leg["strike"] + abs_cost
                                if leg["right"] == "C"
                                else leg["strike"] - abs_cost
                            )
                            s["max_loss"] = f"${max_risk}"
                            s["breakeven"] = str(round(be, 2))
                            s["calculations"] = (
                                f"Python Math: Premium pagato ${premium}. Breakeven = {leg['strike']} {'+' if leg['right']=='C' else '-'} {abs_cost} = {round(be, 2)}\n\nAI: {s.get('calculations', '')}"
                            )
                except Exception as ex:
                    print(
                        f"⚠️ Local math overlay failed, falling back to AI texts. Err: {ex}"
                    )

                s.setdefault("direction", "NEUTRAL")
                s.setdefault("rationale", "")
                s.setdefault("max_profit", "N/A")
                s.setdefault("max_loss", "N/A")
                s.setdefault("breakeven", "N/A")
                s.setdefault("calculations", "")
                s.setdefault("probability", 50)
                valid.append(s)

            return valid

        except json.JSONDecodeError as e:
            print(f"⚠️ AI returned invalid JSON for option strategy: {e}")
            try:
                print(f"   Raw response: {response.text[:500]}")
            except Exception:
                pass
            return []
        except Exception as e:
            print(f"❌ Error suggesting option strategy: {e}")
            return []

    def analyze_market(self, ticker, timeframe, active_analysis):
        """
        Generates an analysis prompt and queries the AI.

        Args:
            ticker (str): Ticker symbol.
            timeframe (str): Timeframe used.
            active_analysis (dict): Dictionary from technical_analysis.detect_patterns.

        Returns:
            str: The AI's response.
        """

        # Construct the Prompt
        # We need to make sure values are strings or formatted numbers
        price = active_analysis.get("current_price", "N/A")
        rsi = active_analysis.get("rsi", "N/A")
        trend = active_analysis.get("trend", "Unknown")
        patterns = ", ".join(active_analysis.get("patterns", [])) or "None"

        # Inject Coulling/Volman VPA knowledge for market analysis context
        vpa_knowledge = self.knowledge.get("vpa", "")
        vpa_section = ""
        if vpa_knowledge:
            vpa_section = f"""\nCONOSCENZA TEORICA (VPA & Price Action - Coulling/Volman):
{vpa_knowledge}
"""

        prompt = f"""Sei un trader esperto e analista quantitativo, specializzato in Volume Price Analysis (VPA) e Price Action.
I tuoi principi chiave sono basati su questa knowledge base teorica:
{vpa_section}
DATI DI MERCATO:
- Ticker: {ticker}
- Timeframe: {timeframe}
- Prezzo Attuale: {price}
- Trend Tecnico (EMA): {trend}
- RSI (14): {rsi}
- Pattern Rilevati: {patterns}

OBIETTIVO:
Analizza la situazione di mercato usando i principi di Volume Price Analysis (Anna Coulling) e i setup operativi a 5 minuti (Bob Volman).
Applica le anomalie prezzo-volume (Sforzo senza Risultato, Risultato senza Sforzo, Selling Climax, Stopping Volume, Divergenza Trend/Volume) ai dati forniti.
Identifica eventuali setup operativi Volman (Pattern Break, Pullback Reversal, Trade-for-Failure, etc.) se applicabili al timeframe.
Non inventare dati. Se i dati sono contrastanti, dillo.

FORMATO RISPOSTA RICHIESTO:
1. **Analisi VPA**: Valuta il rapporto prezzo-volume e identifica anomalie (max 3 righe).
2. **Setup Volman**: C'è un setup operativo riconoscibile? (Sì/No/Forse) — specifica quale.
3. **Direzione**: Long / Short / Wait
4. **Livelli Chiave**: Suggerisci Stop Loss (10 pip/tick standard) e Take Profit (20 pip/tick target) basati sui magneti di prezzo.
5. **Probabilità**: Dai una stima percentuale di successo (es. 60%).
"""

        try:
            # Send to AI
            # Using generate_content from AIProvider
            # We get a wrapped object with .text attribute
            response = self.ai.get_model().generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error gathering AI analysis: {e}"
