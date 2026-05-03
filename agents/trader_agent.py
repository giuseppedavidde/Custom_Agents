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
        geopolitics_context: Optional[str] = None,
        fundamentals_context: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Ask the AI to suggest optimal option strategies based on technical analysis
        AND pre-calculated Black-Scholes Greeks.

        Args:
            analysis: dict from detect_patterns() with indicators
            greeks_table: list of dicts from option_utils.compute_greeks_table()
                          Each dict: {strike, expiry, dte, call: {price, delta, gamma, theta, vega}, put: {...}}
            time_horizon: "weekly", "monthly", or "quarterly"

        Returns a tuple: (strategies_list, underlying_metrics_list)
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
        if geopolitics_context:
            prompt += f"""
CONTESTO MACRO E GEOPOLITICO RECENTE:
Considera il seguente scenario geopolitico per valutare la direzionalità e il rischio macro sistemico dell'asset. Usa questo contesto per bilanciare la tua propensione al rischio o per favorire strategie di copertura se il rischio sistemico (cigni neri, colli di bottiglia) è elevato:
{geopolitics_context}
"""

        if fundamentals_context:
            prompt += f"""
CONTESTO FONDAMENTALE E AZIONARIATO ISTITUZIONALE:
Usa questi dati finanziari e di ownership per validare il setup tecnico. Considera se la salute finanziaria e la presenza istituzionale supportano la direzione della strategia proposta:
{fundamentals_context}
"""

        if greeks_text:
            prompt += f"""
Greeks(IV={((hv or 0.30)*100):.1f}%,r=5%):
{greeks_text}
"""
        prompt += """Rules: 3 strategies, ALL legs specified, use ONLY listed strikes and the EXACT EXPIRATION DATE provided above. Do not invent dates.
ATTENZIONE ALLA MATEMATICA: Devi agire come una calcolatrice rigorosa. Quando sommi o sottrai decimali (es. 24.5 + 0.18), fallo passo dopo passo per evitare allucinazioni (il risultato è 24.68, non 26.30).  NON INVENTARE MAI LA MATEMATICA.
Respond ONLY valid JSON:
{"underlying_metrics": [{"metric": "P/E", "satisfied": "YES", "reason": "in linea col settore"}], "strategies":[{"name":"...","direction":"BULLISH/BEARISH/NEUTRAL","legs":[{"action":"BUY/SELL","quantity":1,"strike":0.0,"right":"C/P","expiry":"YYYYMMDD"}],"rationale":"cite real indicators+greeks and ESPLICITARE LA VOLATILITA (IBKR IV) ASSUNTA NEL PRICING (mostrata in Greeks(IV=...)) come possibile fonte di discrepanza dal mercato reale, MENTZIONANDO ANCHE IL RISCHIO GEOPOLITICO se rilevante.","max_profit":"$X","max_loss":"$X","breakeven":"X.XX","calculations":"Mostra i calcoli matematici espliciti, SCRITTI PASSO PER PASSO COME UN'EQUAZIONE VERIFICATA PUNTUALMENTE (es: 24.50 + 0.18 = 24.68) per profitto massimo, perdita massima e punti di pareggio","probability":65}]}"""

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
            underlying_metrics = data.get("underlying_metrics", [])

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

            return valid, underlying_metrics

        except json.JSONDecodeError as e:
            print(f"⚠️ AI returned invalid JSON for option strategy: {e}")
            try:
                print(f"   Raw response: {response.text[:500]}")
            except Exception:
                pass
            return [], []
        except Exception as e:
            print(f"❌ Error suggesting option strategy: {e}")
            return [], []

    def analyze_market(self, ticker, timeframe, active_analysis, fundamentals_context=None):
        """
        Generates an analysis prompt and queries the AI.

        Args:
            ticker (str): Ticker symbol.
            timeframe (str): Timeframe used.
            active_analysis (dict): Dictionary from technical_analysis.detect_patterns.
            fundamentals_context (str): Optional string containing financial and holders data.

        Returns:
            str: The AI's response formatted in a structured markdown block based on a strict JSON response.
        """

        # Construct the Prompt
        # We need to make sure values are strings or formatted numbers
        price = active_analysis.get("current_price", "N/A")
        rsi = active_analysis.get("rsi", "N/A")
        trend = active_analysis.get("trend", "Unknown")
        patterns = ", ".join(active_analysis.get("patterns", [])) or "None"
        volume = active_analysis.get("volume_info", "N/A")

        # Inject Coulling/Volman VPA knowledge for market analysis context
        vpa_knowledge = self.knowledge.get("vpa", "")
        vpa_section = ""
        if vpa_knowledge:
            vpa_section = f"""\nCONOSCENZA TEORICA (VPA & Price Action - Coulling/Volman):
{vpa_knowledge}
"""

        prompt = f"""Sei un trader esperto e analista quantitativo, specializzato in Volume Price Analysis (VPA) e Price Action. Agisci come un AutoTrader engine istituzionale.
I tuoi principi chiave sono basati su questa knowledge base teorica:
{vpa_section}
DATI DI MERCATO:
- Ticker: {ticker}
- Timeframe: {timeframe}
- Prezzo Attuale: {price}
- Trend Tecnico (EMA): {trend}
- RSI (14): {rsi}
- Volumi: {volume}
- Pattern Rilevati: {patterns}

{("DATI FONDAMENTALI E ISTITUZIONALI:\n" + fundamentals_context) if fundamentals_context else ""}

OBIETTIVO:
Analizza la situazione di mercato usando i principi di Volume Price Analysis (Anna Coulling) e i setup operativi (Bob Volman).
Applica le anomalie prezzo-volume (Sforzo senza Risultato, Risultato senza Sforzo, Selling Climax, Stopping Volume, Divergenza Trend/Volume) ai dati forniti.

FORMATO RISPOSTA RICHIESTO:
Rispondi ESCLUSIVAMENTE con un JSON valido strutturato come un Trading Signal istituzionale:
{{
  "action": "LONG" | "SHORT" | "WAIT",
  "vpa_analysis": "Valuta il rapporto prezzo-volume e identifica anomalie (max 3 righe)",
  "volman_setup": "C'è un setup operativo riconoscibile? (Sì/No/Forse) - specifica quale",
  "entry_price": 0.00,
  "stop_loss": 0.00,
  "take_profit": 0.00,
  "confidence": 0.0 a 1.0,
  "position_size_pct": 0.0 a 1.0 (es. 0.05 per il 5% del capitale),
  "metrics_matrix": [
    {"metric": "Trend EMA200", "satisfied": "YES", "reason": "Prezzo sopra la media"}
  ],
  "reasoning": "Spiegazione sintetica della decisione basata sui dati tecnici."
}}
"""

        try:
            # Require JSON output to enforce rigorous structure (AutoTrader style)
            model = self.ai.get_model(json_mode=True)
            response = model.generate_content(prompt)
            text = response.text.strip()

            # Clean potential markdown code fences
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
                if text.startswith("json"):
                    text = text[4:].strip()
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            try:
                data = json.loads(text)
                
                # Format the JSON into a clean, readable Markdown string
                action = data.get("action", "WAIT").upper()
                conf = data.get("confidence", 0.0) * 100
                
                formatted_response = f"### 🤖 AI AutoTrader Signal: **{action}** (Confidence: {conf:.1f}%)\n\n"
                
                if action != "WAIT":
                    formatted_response += f"**Entry Price:** ${data.get('entry_price', 'N/A')} | "
                    formatted_response += f"**Take Profit:** ${data.get('take_profit', 'N/A')} | "
                    formatted_response += f"**Stop Loss:** ${data.get('stop_loss', 'N/A')}\n"
                    formatted_response += f"**Suggested Size:** {data.get('position_size_pct', 0.0)*100:.1f}% of Capital\n\n"
                
                # Render Metrics Matrix
                metrics = data.get("metrics_matrix", [])
                if metrics:
                    formatted_response += "### 📊 Underlying Evaluation Matrix\n\n"
                    formatted_response += "| Metric | Satisfied? | Reason |\n"
                    formatted_response += "|---|---|---|\n"
                    for m in metrics:
                        # Emoticon per visuale veloce
                        sat = m.get("satisfied", "NO")
                        icon = "✅" if "yes" in str(sat).lower() else "❌"
                        formatted_response += f"| {m.get('metric', 'N/A')} | {icon} {sat} | {m.get('reason', 'N/A')} |\n"
                    formatted_response += "\n"

                formatted_response += f"**VPA Analysis:**\n{data.get('vpa_analysis', 'N/A')}\n\n"
                formatted_response += f"**Setup Volman:**\n{data.get('volman_setup', 'N/A')}\n\n"
                formatted_response += f"**Reasoning:**\n{data.get('reasoning', 'N/A')}"
                
                return formatted_response

            except json.JSONDecodeError:
                # Fallback if AI fails to return proper JSON despite strict prompting
                return text

        except Exception as e:
            return f"Error gathering AI analysis: {e}"

    def scan_put_selling_candidates(
        self, market_data: List[Dict[str, Any]], time_horizon: str = "monthly"
    ) -> str:
        """
        Scan a list of market candidates to identify the best ones for
        Cash-Secured Puts (first stage of Wheel Strategy).

        Args:
            market_data: List of dicts, each containing metrics like:
                - ticker (str)
                - price (float)
                - iv (float)
                - bid_ask_spread (float)
                - trend (str)
                - rsi (float)
            time_horizon: The user's intended investment horizon (e.g. weekly, monthly, quarterly)

        Returns:
            JSON string containing the ranked candidates and rationale.
        """
        # Inject Options Knowledge
        options_knowledge = self.knowledge.get("options", "")

        # Build market data block
        data_text_lines = []
        for item in market_data:
            line = (
                f"- Ticker: {item.get('ticker')}, Price: {item.get('price')}, "
                f"IV: {item.get('iv', 'N/A')}, Spread: {item.get('bid_ask_spread', 'N/A')}, "
                f"Trend: {item.get('trend', 'N/A')}, RSI: {item.get('rsi', 'N/A')}"
            )
            data_text_lines.append(line)

        data_text = "\n".join(data_text_lines)

        prompt = f"""Sei un trader esperto specializzato nella Wheel Strategy.
La tua conoscenza teorica di base:
{options_knowledge}

Il tuo compito odierno è analizzare la seguente lista di ticker e trovare i MIGLIORI candidati per la fase 1 della Wheel Strategy: Vendita di Cash-Secured Puts.

ORIZZONTE TEMPORALE SCELTO DALL'UTENTE: {time_horizon}
Tieni conto di questo orizzonte temporale quando suggerisci il delta e valuti se la volatilità o il trend attuale sono adatti (es. trend di breve vs lungo periodo).

Criteri chiave per la scelta:
1) Titoli di altissima qualità o ETF solidi (es. AAPL, MSFT, SPY, QQQ).
2) Spread Bid/Ask molto stretto (alta liquidità, indica facilità di entrata/uscita).
3) IV (Implied Volatility) relativamente alta, per incassare premi sostanziosi (generalmente IV Rank alto o IV > 30%), ma senza che sia sintomo di imminente bancarotta o cigno nero.
4) Trend preferibilmente non in caduta libera (evitare i "falling knives"), cercando trend laterali o rialzisti con un pullback temporaneo (es. RSI in ipervenduto in un trend primario toro).

DATI DI MERCATO (Scansione Attuale):
{data_text}

Rispondi ESCLUSIVAMENTE con un JSON valido strutturato in questo modo, analizzando ogni ticker fornito:
{{
  "best_candidates": [
    {{
      "ticker": "...",
      "score": "1-10",
      "rationale": "Spiega perché è eccellente per una Cash-Secured Put in base ai criteri specifici.",
      "suggested_delta": "es. 0.20-0.30"
    }}
  ],
  "rejected_candidates": [
    {{
      "ticker": "...",
      "reason": "Perché lo hai scartato (es. spread troppo largo, trend pessimo, scarsa qualità)."
    }}
  ],
  "market_overview": "Breve riassunto della situazione."
}}
"""

        try:
            model = self.ai.get_model(json_mode=True)
            response = model.generate_content(prompt)
            text = response.text.strip()

            # Clean potential markdown code fences
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
                if text.startswith("json"):
                    text = text[4:].strip()
            if text.endswith("```"):
                text = text[:-3]

            return text.strip()
        except Exception as e:
            return f'{{"error": "Failed to gather AI candidate analysis: {e}"}}'

    def analyze_geopolitical_risk(
        self, asset: str, current_events: str, framework: str = "Grand Chessboard (Brzezinski)"
    ) -> str:
        """
        Analyzes the geopolitical risk for a specific asset or region based on advanced
        geopolitical frameworks (e.g. Grand Chessboard, Prisoners of Geography, World Order)
        inspired by fincept-qt GeopoliticsAgents.
        
        Args:
            asset (str): The asset, ticker, or region to analyze (e.g. 'AAPL', 'Taiwan', 'Oil').
            current_events (str): A summary of the latest news or events affecting the asset.
            framework (str): The geopolitical framework to apply. Default is 'Grand Chessboard'.
            
        Returns:
            str: The AI's response formatted in a structured markdown block based on a JSON response.
        """
        
        prompt = f"""Sei un analista geopolitico senior e un macro-strategist istituzionale.
Stai valutando il rischio geopolitico per l'asset/regione: {asset}.

EVENTI CORRENTI:
{current_events}

FRAMEWORK RICHIESTO: {framework}
Usa i concetti dei seguenti framework per la tua analisi:
- **Grand Chessboard (Brzezinski)**: focus su Stati perno (Pivot States), controllo dell'Eurasia, infrastrutture energetiche (pipeline/chokepoints) e alleanze strategiche.
- **Prisoners of Geography (Tim Marshall)**: focus su limiti fisici, fiumi navigabili, catene montuose, porti in acque calde e colli di bottiglia marittimi.
- **World Order (Kissinger)**: focus su legittimità, equilibrio di potere (Westfaliano), competizione multipolare e clash di sfere d'influenza.

OBIETTIVO:
Valutare l'impatto strategico a lungo e medio termine degli eventi correnti su {asset} utilizzando la lente del framework richiesto. Non usare banalità, concentrati su colli di bottiglia concreti, catene di approvvigionamento, o assetti di potere regionali.

FORMATO RISPOSTA RICHIESTO:
Rispondi ESCLUSIVAMENTE con un JSON valido strutturato come un Geopolitical Risk Report:
{{
  "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "geographic_anchor": "Specifica il fattore geografico o l'infrastruttura chiave (es. Stretto di Hormuz, Fabbriche TSMC, Corridoio Suwałki).",
  "strategic_implication": "Cosa significa questo evento per le grandi potenze o per la catena di approvvigionamento macro? (max 3 righe)",
  "market_impact": "Come questo rischio geopolitico si traduce sull'asset in questione (impatto sui costi, supply chain, volatilità attesa)?",
  "black_swan_scenario": "Il peggior scenario plausibile (cigno nero geopolitico) da monitorare."
}}
"""

        try:
            model = self.ai.get_model(json_mode=True)
            response = model.generate_content(prompt)
            text = response.text.strip()

            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
                if text.startswith("json"):
                    text = text[4:].strip()
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            try:
                data = json.loads(text)
                
                risk = data.get("risk_level", "UNKNOWN").upper()
                
                formatted_response = f"### 🌍 Geopolitical Risk Analysis: **{risk}**\n\n"
                formatted_response += f"**Geographic/Strategic Anchor:**\n{data.get('geographic_anchor', 'N/A')}\n\n"
                formatted_response += f"**Strategic Implication ({framework}):**\n{data.get('strategic_implication', 'N/A')}\n\n"
                formatted_response += f"**Market Impact on {asset}:**\n{data.get('market_impact', 'N/A')}\n\n"
                formatted_response += f"**Black Swan Scenario:**\n{data.get('black_swan_scenario', 'N/A')}"
                
                return formatted_response

            except json.JSONDecodeError:
                return text

        except Exception as e:
            return f"Error gathering AI geopolitical analysis: {e}"
