from .ai_provider import AIProvider
import json
from typing import List, Dict, Any, Optional


class TraderAgent:
    def __init__(self, provider_type="gemini", model_name=None):
        self.ai = AIProvider(provider_type=provider_type, model_name=model_name)

    def suggest_option_strategy(
        self,
        ticker: str,
        analysis: dict,
        expirations: List[str],
        strikes: List[float],
        underlying_price: float,
        time_horizon: str = "monthly",
        greeks_table: Optional[List[Dict]] = None,
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
        hv = analysis.get("hist_volatility")

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

        # Filter expirations by time horizon
        horizon_map = {"weekly": 1, "monthly": 2, "quarterly": 4}
        max_exps = horizon_map.get(time_horizon, 2)
        limited_exps = expirations[:max_exps]

        horizon_label = {
            "weekly": "1-2wk",
            "monthly": "1-2mo",
            "quarterly": "3-6mo",
        }.get(time_horizon, "1-2mo")

        # Build compact CSV Greeks table (no padding, short headers)
        greeks_text = ""
        if greeks_table:
            greeks_lines = ["K,D,CΔ,CΘ,C$,PΔ,PΘ,P$,V"]
            for row in greeks_table:
                c, p = row["call"], row["put"]
                greeks_lines.append(
                    f"{row['strike']},{row['dte']},"
                    f"{c['delta']:+.2f},{c['theta']:+.3f},{c['price']:.2f},"
                    f"{p['delta']:+.2f},{p['theta']:+.3f},{p['price']:.2f},{c['vega']:.3f}"
                )
            greeks_text = "\n".join(greeks_lines)

        prompt = f"""Option strategy advisor. Real data below, computed via Black-Scholes.

{ticker}: {indicators_text}
Horizon: {horizon_label}
Expirations: {','.join(limited_exps)}
Strikes: {','.join(str(s) for s in nearby_strikes)}
"""
        if greeks_text:
            prompt += f"""Greeks(HV={((hv or 0.30)*100):.0f}%,r=5%):
{greeks_text}
"""
        prompt += """Rules: 3 strategies, ALL legs specified, use ONLY listed strikes/expirations.
Respond ONLY valid JSON:
{"strategies":[{"name":"...","direction":"BULLISH/BEARISH/NEUTRAL","legs":[{"action":"BUY/SELL","quantity":1,"strike":0.0,"right":"C/P","expiry":"YYYYMMDD"}],"rationale":"cite real indicators+greeks","max_profit":"$X","max_loss":"$X","breakeven":"X.XX","probability":65}]}"""

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

            # Convert available data to sets for fast lookup
            valid_strikes_set = set(float(s) for s in strikes)
            valid_exps_set = set(expirations)
            sorted_strikes = sorted(valid_strikes_set)

            # Validate and enrich each strategy
            valid = []
            for s in strategies[:3]:
                if "name" not in s or "legs" not in s:
                    continue
                valid_legs = []
                for leg in s.get("legs", []):
                    if all(k in leg for k in ("action", "strike", "right", "expiry")):
                        leg["action"] = leg["action"].upper()
                        leg["right"] = leg["right"].upper()
                        leg.setdefault("quantity", 1)
                        if leg["right"] not in ("C", "P"):
                            leg["right"] = "C"
                        if leg["action"] not in ("BUY", "SELL"):
                            leg["action"] = "BUY"

                        # ── STRICT VALIDATION ──────────────────────────
                        # Snap strike to nearest valid IBKR strike
                        leg_strike = float(leg["strike"])
                        if leg_strike not in valid_strikes_set:
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
                        leg_exp = str(leg["expiry"])
                        if leg_exp not in valid_exps_set:
                            nearest_exp = min(
                                expirations, key=lambda x: abs(int(x) - int(leg_exp))
                            )
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
                s.setdefault("direction", "NEUTRAL")
                s.setdefault("rationale", "")
                s.setdefault("max_profit", "N/A")
                s.setdefault("max_loss", "N/A")
                s.setdefault("breakeven", "N/A")
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

        prompt = f"""
Sei un trader esperto e analista quantitativo. Analizza i seguenti dati tecnici per {ticker} sul timeframe {timeframe}:

DATI DI MERCATO:
- Prezzo Attuale: {price}
- Trend Tecnico (EMA): {trend}
- RSI (14): {rsi}
- Pattern Rilevati: {patterns}

OBIETTIVO:
Analizza la situazione di mercato basandoti SOLO su questi numeri e sulla tua conoscenza dei mercati finanziari.
Non inventare dati. Se i dati sono contrastanti, dillo.

FORMATO RISPOSTA RICHIESTO:
1. **Analisi Sintetica**: Spiega cosa suggeriscono gli indicatori (max 3 righe).
2. **Setup**: C'è un'opportunità di trading? (Sì/No/Forse)
3. **Direzione**: Long / Short / Wait
4. **Livelli Chiave**: Suggerisci uno Stop Loss logico e un Take Profit basato sulla volatilità implicita nel trend.
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
