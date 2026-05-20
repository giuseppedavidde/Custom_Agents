"""TraderAgent: AI-powered trading analysis and option strategy suggestions.

Uses the LLM_Wiki/Trading_Wiki knowledge base for domain-specific expertise
in options, VPA, Wyckoff method, and scalping strategies.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from .ai_provider import AIProvider
from .knowledge_loader import load_all_knowledge as _load_all_wiki


class TraderAgent:
    """AI-powered trading agent for market analysis and option strategies.

    Loads knowledge from the LLM_Wiki/Trading_Wiki and provides methods for:
    - Suggesting option strategies based on technical analysis and Greeks
    - Analyzing market conditions using VPA and Wyckoff principles
    - Scanning for put selling candidates (Wheel Strategy)
    - Analyzing geopolitical risk
    """

    def __init__(self, provider_type: str = "gemini", model_name: Optional[str] = None):
        self.ai = AIProvider(provider_type=provider_type, model_name=model_name)
        self.knowledge = self._load_knowledge()
        # Backward-compat alias used by suggest_option_strategy prompt
        self.knowledge_base = self.knowledge.get("options", "")

    def _load_knowledge(self) -> dict:
        """Load all knowledge bases from the LLM_Wiki/Trading_Wiki."""
        return _load_all_wiki()

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
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
        """Ask the AI to suggest optimal option strategies.

        Based on technical analysis AND pre-calculated Black-Scholes Greeks.

        Args:
            ticker: Stock ticker symbol.
            analysis: dict from detect_patterns() with indicators.
            expirations: List of available expiration dates (YYYYMMDD).
            strikes: List of available strike prices.
            underlying_price: Current price of the underlying asset.
            time_horizon: "weekly", "monthly", or "quarterly".
            greeks_table: Pre-computed Greeks from option_utils.compute_greeks_table().
            iv: Implied volatility override.
            geopolitics_context: Optional geopolitical context string.
            fundamentals_context: Optional financial/ownership data string.

        Returns:
            Tuple of (strategies_list, underlying_metrics_list).
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
            macd_sig = analysis.get("macd_signal", "")
            macd_hist = analysis.get("macd_histogram", "")
            ind.append(
                f"MACD:{analysis['macd']:.4f}/Sig:{macd_sig}/H:{macd_hist}"
            )
        if analysis.get("bb_upper"):
            bb_w = analysis.get("bb_width", "")
            ind.append(
                f"BB:{analysis['bb_lower']:.2f}"
                f"-{analysis['bb_upper']:.2f}(w={bb_w})"
            )
        if hv:
            ind.append(f"HV:{hv * 100:.1f}%")
        if analysis.get("volume_ratio"):
            ind.append(f"Vol:{analysis['volume_ratio']}x")
        if patterns != "None":
            ind.append(f"Pat:{patterns}")
        indicators_text = " | ".join(ind)

        # Filter strikes near ATM (+-10% to reduce rows)
        atm_range = underlying_price * 0.10
        nearby_strikes = sorted(
            [s for s in strikes if abs(s - underlying_price) <= atm_range]
        )
        if len(nearby_strikes) < 4:
            nearby_strikes = sorted(strikes[:20])

        # Filter expirations based on actual time difference from today
        today_date = datetime.date.today()

        def get_days_to_exp(exp_str: str) -> int:
            try:
                exp_date = datetime.datetime.strptime(
                    exp_str, "%Y%m%d"
                ).date()
                return (exp_date - today_date).days
            except (ValueError, TypeError):
                return 0

        # Target days for each horizon
        horizon_targets = {
            "weekly": 7,
            "monthly": 30,
            "quarterly": 90,
        }
        target_days = horizon_targets.get(time_horizon, 30)

        # Sort ALL expirations by closeness to target date
        sorted_exps = sorted(
            expirations, key=lambda x: abs(get_days_to_exp(x) - target_days)
        )

        # Take the top 3 closest expirations
        limited_exps = sorted(sorted_exps[:3])

        horizon_label = {
            "weekly": "1-2wk",
            "monthly": "1-2mo",
            "quarterly": "3-6mo",
        }.get(time_horizon, "1-2mo")

        # Build compact CSV Greeks table
        greeks_text = ""
        if greeks_table:
            nearby_strikes_set = set(float(s) for s in nearby_strikes)
            limited_exps_set = set(str(e) for e in limited_exps)

            greeks_lines = ["K,D,C\u0394,C\u0398,C$,P\u0394,P\u0398,P$,V"]
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
                    f"{p['delta']:+.2f},{p['theta']:+.3f},{p['price']:.2f},"
                    f"{c['vega']:.3f}"
                )
            greeks_text = "\n".join(greeks_lines)

        today_str = datetime.date.today().strftime("%Y-%m-%d")

        prompt = (
            f"Sei un trader di opzioni istituzionale.\n"
            f"I tuoi principi chiave sono basati su questa knowledge base:\n\n"
            f"CONOSCENZA TEORICA (Regole di Trading e Adjustments):\n"
            f"{self.knowledge_base}\n\n"
            f"DATI DI MERCATO REALI (Modello Black-Scholes):\n"
            f"DATA ODIERNA: {today_str} (Usa questa data per calcolare i "
            f"giorni a scadenza. Le scadenze sono nel formato YYYYMMDD)\n"
            f"{ticker}: {indicators_text}\n"
            f"Horizon (Categoria): {horizon_label}\n"
            f"SCADENZA ESATTA DA UTILIZZARE (OBBLIGATORIO): "
            f"{','.join(limited_exps)}\n"
            f"Strikes: {','.join(str(s) for s in nearby_strikes)}\n"
        )
        if geopolitics_context:
            prompt += (
                f"\nCONTESTO MACRO E GEOPOLITICO RECENTE:\n"
                f"Considera il seguente scenario geopolitico per valutare "
                f"la direzionalità e il rischio macro sistemico dell'asset:\n"
                f"{geopolitics_context}\n"
            )

        if fundamentals_context:
            prompt += (
                f"\nCONTESTO FONDAMENTALE E AZIONARIATO ISTITUZIONALE:\n"
                f"Usa questi dati finanziari e di ownership per validare "
                f"il setup tecnico:\n"
                f"{fundamentals_context}\n"
            )

        if greeks_text:
            iv_pct = (hv or 0.30) * 100
            prompt += (
                f"\nGreeks(IV={iv_pct:.1f}%,r=5%):\n"
                f"{greeks_text}\n"
            )

        rules = (
            "Rules: 3 strategies, ALL legs specified, use ONLY listed "
            "strikes and the EXACT EXPIRATION DATE provided above. "
            "Do not invent dates.\n"
            "ATTENZIONE ALLA MATEMATICA: Devi agire come una calcolatrice "
            "rigorosa. NON INVENTARE MAI LA MATEMATICA.\n"
            "Respond ONLY valid JSON:\n"
            '{"underlying_metrics": [{"metric": "P/E", '
            '"satisfied": "YES", "reason": "in linea col settore"}], '
            '"strategies":[{"name":"...",'
            '"direction":"BULLISH/BEARISH/NEUTRAL",'
            '"legs":[{"action":"BUY/SELL","quantity":1,'
            '"strike":0.0,"right":"C/P","expiry":"YYYYMMDD"}],'
            '"rationale":"cite real indicators+greeks",'
            '"max_profit":"$X","max_loss":"$X",'
            '"breakeven":"X.XX",'
            '"calculations":"Mostra i calcoli matematici espliciti",'
            '"probability":65}]}'
        )
        prompt += rules

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

            # Convert available data to sets for fast lookup
            valid_strikes_set = set(float(s) for s in nearby_strikes)
            valid_exps_set = set(limited_exps)
            sorted_strikes = sorted(valid_strikes_set)

            # Validate and enrich each strategy
            valid = []
            for s in strategies[:3]:
                if not isinstance(s, dict) or "name" not in s or "legs" not in s:
                    continue
                valid_legs = self._validate_legs(
                    s.get("legs", []),
                    valid_strikes_set,
                    valid_exps_set,
                    sorted_strikes,
                    limited_exps,
                    greeks_lookup,
                )
                if not valid_legs:
                    continue

                s["legs"] = valid_legs
                self._calculate_math(s, valid_legs)

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
            print(f"AI returned invalid JSON for option strategy: {e}")
            try:
                print(f"   Raw response: {response.text[:500]}")
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            return [], []
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error suggesting option strategy: {e}")
            return [], []

    @staticmethod
    def _validate_legs(
        legs: list,
        valid_strikes_set: set,
        valid_exps_set: set,
        sorted_strikes: list,
        limited_exps: list,
        greeks_lookup: dict,
    ) -> list:
        """Validate and snap option legs to available IBKR chain."""
        valid_legs = []
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            if not all(k in leg for k in ("action", "strike", "right", "expiry")):
                continue

            leg["action"] = str(leg["action"]).upper()
            leg["right"] = str(leg["right"]).upper()
            leg.setdefault("quantity", 1)
            if leg["right"] not in ("C", "P"):
                leg["right"] = "C"
            if leg["action"] not in ("BUY", "SELL"):
                leg["action"] = "BUY"

            # Snap strike to nearest valid IBKR strike
            try:
                leg_strike = float(leg["strike"])
            except (ValueError, TypeError):
                leg_strike = 0.0

            if leg_strike not in valid_strikes_set and valid_strikes_set:
                nearest = min(
                    sorted_strikes,
                    key=lambda x, ls=leg_strike: abs(x - ls),
                )
                print(
                    f"Strike {leg_strike} not in IBKR chain "
                    f"-> snapped to {nearest}"
                )
                leg["strike"] = nearest
                leg["strike_corrected"] = True
            else:
                leg["strike"] = leg_strike

            # Snap expiry to nearest valid IBKR expiry
            leg_exp = str(leg["expiry"]).strip()
            if leg_exp not in valid_exps_set and valid_exps_set:
                try:
                    exp_int = int(leg_exp)
                    nearest_exp = min(
                        limited_exps,
                        key=lambda x, ei=exp_int: abs(int(x) - ei),
                    )
                except (ValueError, TypeError):
                    nearest_exp = limited_exps[0]

                print(
                    f"Expiry {leg_exp} not in IBKR chain "
                    f"-> snapped to {nearest_exp}"
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

        return valid_legs

    @staticmethod
    def _calculate_math(strategy: dict, valid_legs: list) -> None:
        """Calculate P/L locally rather than trusting AI arithmetic."""
        try:
            net_cost = 0.0
            for leg in valid_legs:
                leg_price = leg.get("greeks", {}).get("price", 0.0)
                if leg["action"] == "BUY":
                    net_cost += leg_price * leg["quantity"]
                else:
                    net_cost -= leg_price * leg["quantity"]

            net_cost = round(net_cost, 2)
            is_credit = net_cost < 0
            abs_cost = abs(net_cost)
            premium = round(abs_cost * 100, 2)

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

                is_call = valid_legs[0]["right"] == "C"
                if is_call:
                    lower_strike = min(strike1, strike2)
                    be = lower_strike + abs_cost
                else:
                    higher_strike = max(strike1, strike2)
                    be = higher_strike - abs_cost

                calc_text = (
                    f"Python Math Engine:\n"
                    f"Net Premium: ${premium} "
                    f"({'Credit' if is_credit else 'Debit'} "
                    f"di {abs_cost} * 100)\n"
                    f"Max Risk: ${max_risk}\n"
                    f"Max Reward: ${max_reward}\n"
                    f"Breakeven (Approx): {round(be, 2)}\n"
                )
                strategy["max_profit"] = f"${max_reward}"
                strategy["max_loss"] = f"${max_risk}"
                strategy["breakeven"] = str(round(be, 2))
                strategy["calculations"] = (
                    calc_text
                    + "\n(AI Rationale: "
                    + str(strategy.get("calculations", ""))
                    + ")"
                )
            elif len(valid_legs) == 1:
                leg = valid_legs[0]
                max_risk = (
                    premium if leg["action"] == "BUY" else "Unlimited"
                )
                be = (
                    leg["strike"] + abs_cost
                    if leg["right"] == "C"
                    else leg["strike"] - abs_cost
                )
                sign = "+" if leg["right"] == "C" else "-"
                strategy["max_loss"] = f"${max_risk}"
                strategy["breakeven"] = str(round(be, 2))
                strategy["calculations"] = (
                    f"Python Math: Premium pagato ${premium}. "
                    f"Breakeven = {leg['strike']} {sign} {abs_cost} "
                    f"= {round(be, 2)}\n\n"
                    f"AI: {strategy.get('calculations', '')}"
                )
        except Exception as ex:  # pylint: disable=broad-exception-caught
            print(
                f"Local math overlay failed, "
                f"falling back to AI texts. Err: {ex}"
            )

    def analyze_market(
        self,
        ticker: str,
        timeframe: str,
        active_analysis: dict,
        fundamentals_context: Optional[str] = None,
    ) -> str:
        """Generate an analysis prompt and query the AI.

        Args:
            ticker: Ticker symbol.
            timeframe: Timeframe used.
            active_analysis: Dict from technical_analysis.detect_patterns.
            fundamentals_context: Optional financial and holders data.

        Returns:
            AI response formatted as structured markdown.
        """
        price = active_analysis.get("current_price", "N/A")
        rsi = active_analysis.get("rsi", "N/A")
        trend = active_analysis.get("trend", "Unknown")
        patterns = ", ".join(active_analysis.get("patterns", [])) or "None"
        volume = active_analysis.get("volume_info", "N/A")

        vpa_knowledge = self.knowledge.get("vpa", "")
        vpa_section = ""
        if vpa_knowledge:
            vpa_section = (
                f"\nCONOSCENZA TEORICA (VPA & Price Action):\n"
                f"{vpa_knowledge}\n"
            )

        fund_section = ""
        if fundamentals_context:
            fund_section = (
                f"DATI FONDAMENTALI E ISTITUZIONALI:\n"
                f"{fundamentals_context}\n"
            )

        prompt = (
            f"Sei un trader esperto e analista quantitativo, specializzato "
            f"in Volume Price Analysis (VPA) e Price Action. "
            f"Agisci come un AutoTrader engine istituzionale.\n"
            f"I tuoi principi chiave sono basati su questa knowledge base:\n"
            f"{vpa_section}"
            f"DATI DI MERCATO:\n"
            f"- Ticker: {ticker}\n"
            f"- Timeframe: {timeframe}\n"
            f"- Prezzo Attuale: {price}\n"
            f"- Trend Tecnico (EMA): {trend}\n"
            f"- RSI (14): {rsi}\n"
            f"- Volumi: {volume}\n"
            f"- Pattern Rilevati: {patterns}\n\n"
            f"{fund_section}"
            f"OBIETTIVO:\n"
            f"Analizza la situazione di mercato usando i principi di "
            f"Volume Price Analysis (Anna Coulling) e i setup operativi "
            f"(Bob Volman).\n"
            f"Applica le anomalie prezzo-volume (Sforzo senza Risultato, "
            f"Risultato senza Sforzo, Selling Climax, Stopping Volume, "
            f"Divergenza Trend/Volume) ai dati forniti.\n\n"
            f"FORMATO RISPOSTA RICHIESTO:\n"
            f"Rispondi ESCLUSIVAMENTE con un JSON valido strutturato "
            f"come un Trading Signal istituzionale:\n"
            f'{{"action": "LONG" | "SHORT" | "WAIT", '
            f'"vpa_analysis": "Valuta il rapporto prezzo-volume '
            f'e identifica anomalie (max 3 righe)", '
            f'"volman_setup": "C\'e un setup operativo riconoscibile? '
            f"(Si/No/Forse) - specifica quale\", "
            f'"entry_price": 0.00, "stop_loss": 0.00, '
            f'"take_profit": 0.00, "confidence": 0.0 a 1.0, '
            f'"position_size_pct": 0.0 a 1.0, '
            f'"metrics_matrix": ['
            f'{{"metric": "Trend EMA200", '
            f'"satisfied": "YES", '
            f'"reason": "Prezzo sopra la media"}}], '
            f'"reasoning": "Spiegazione sintetica della decisione '
            f'basata sui dati tecnici."}}\n'
        )

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
            text = text.strip()

            try:
                data = json.loads(text)
                return self._format_analysis_response(data)
            except json.JSONDecodeError:
                return text

        except Exception as e:  # pylint: disable=broad-exception-caught
            return f"Error gathering AI analysis: {e}"

    @staticmethod
    def _format_analysis_response(data: dict) -> str:
        """Format JSON analysis response into readable markdown."""
        action = data.get("action", "WAIT").upper()
        conf = data.get("confidence", 0.0) * 100

        formatted = (
            f"### AI AutoTrader Signal: **{action}** "
            f"(Confidence: {conf:.1f}%)\n\n"
        )

        if action != "WAIT":
            entry = data.get("entry_price", "N/A")
            tp = data.get("take_profit", "N/A")
            sl = data.get("stop_loss", "N/A")
            size = data.get("position_size_pct", 0.0) * 100
            formatted += (
                f"**Entry Price:** ${entry} | "
                f"**Take Profit:** ${tp} | "
                f"**Stop Loss:** ${sl}\n"
                f"**Suggested Size:** {size:.1f}% of Capital\n\n"
            )

        # Render Metrics Matrix
        metrics = data.get("metrics_matrix", [])
        if metrics:
            formatted += "### Underlying Evaluation Matrix\n\n"
            formatted += "| Metric | Satisfied? | Reason |\n"
            formatted += "|---|---|---|\n"
            for m in metrics:
                sat = m.get("satisfied", "NO")
                icon = "[+]" if "yes" in str(sat).lower() else "[-]"
                formatted += (
                    f"| {m.get('metric', 'N/A')} "
                    f"| {icon} {sat} "
                    f"| {m.get('reason', 'N/A')} |\n"
                )
            formatted += "\n"

        vpa = data.get("vpa_analysis", "N/A")
        volman = data.get("volman_setup", "N/A")
        reasoning = data.get("reasoning", "N/A")
        formatted += (
            f"**VPA Analysis:**\n{vpa}\n\n"
            f"**Setup Volman:**\n{volman}\n\n"
            f"**Reasoning:**\n{reasoning}"
        )

        return formatted

    def scan_put_selling_candidates(
        self, market_data: List[Dict[str, Any]], time_horizon: str = "monthly"
    ) -> str:
        """Scan market candidates for Cash-Secured Puts (Wheel Strategy).

        Args:
            market_data: List of dicts with ticker, price, iv, spread, etc.
            time_horizon: User's intended investment horizon.

        Returns:
            JSON string with ranked candidates and rationale.
        """
        options_knowledge = self.knowledge.get("options", "")

        data_text_lines = []
        for item in market_data:
            line = (
                f"- Ticker: {item.get('ticker')}, "
                f"Price: {item.get('price')}, "
                f"IV: {item.get('iv', 'N/A')}, "
                f"Spread: {item.get('bid_ask_spread', 'N/A')}, "
                f"Trend: {item.get('trend', 'N/A')}, "
                f"RSI: {item.get('rsi', 'N/A')}"
            )
            data_text_lines.append(line)

        data_text = "\n".join(data_text_lines)

        prompt = (
            f"Sei un trader esperto specializzato nella Wheel Strategy.\n"
            f"La tua conoscenza teorica di base:\n"
            f"{options_knowledge}\n\n"
            f"Il tuo compito odierno e' analizzare la seguente lista di "
            f"ticker e trovare i MIGLIORI candidati per la fase 1 della "
            f"Wheel Strategy: Vendita di Cash-Secured Puts.\n\n"
            f"ORIZZONTE TEMPORALE SCELTO DALL'UTENTE: {time_horizon}\n"
            f"Tieni conto di questo orizzonte temporale quando suggerisci "
            f"il delta e valuti se la volatilita' o il trend attuale sono "
            f"adatti.\n\n"
            f"Criteri chiave per la scelta:\n"
            f"1) Titoli di altissima qualita' o ETF solidi "
            f"(es. AAPL, MSFT, SPY, QQQ).\n"
            f"2) Spread Bid/Ask molto stretto (alta liquidita').\n"
            f"3) IV (Implied Volatility) relativamente alta "
            f"(IV Rank alto o IV > 30%).\n"
            f"4) Trend preferibilmente non in caduta libera "
            f"(evitare i falling knives).\n\n"
            f"DATI DI MERCATO (Scansione Attuale):\n"
            f"{data_text}\n\n"
            f"Rispondi ESCLUSIVAMENTE con un JSON valido:\n"
            f'{{"best_candidates": ['
            f'{{"ticker": "...", "score": "1-10", '
            f'"rationale": "...", "suggested_delta": "es. 0.20-0.30"}}'
            f'], "rejected_candidates": ['
            f'{{"ticker": "...", "reason": "..."}}'
            f'], "market_overview": "Breve riassunto."}}\n'
        )

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

            return text.strip()
        except Exception as e:  # pylint: disable=broad-exception-caught
            return f'{{"error": "Failed to gather AI candidate analysis: {e}"}}'

    def analyze_geopolitical_risk(
        self,
        asset: str,
        current_events: str,
        framework: str = "Grand Chessboard (Brzezinski)",
    ) -> str:
        """Analyze geopolitical risk for an asset or region.

        Args:
            asset: The asset, ticker, or region to analyze.
            current_events: Summary of latest news affecting the asset.
            framework: Geopolitical framework to apply.

        Returns:
            AI response formatted as structured markdown.
        """
        prompt = (
            f"Sei un analista geopolitico senior e un macro-strategist "
            f"istituzionale.\n"
            f"Stai valutando il rischio geopolitico per "
            f"l'asset/regione: {asset}.\n\n"
            f"EVENTI CORRENTI:\n"
            f"{current_events}\n\n"
            f"FRAMEWORK RICHIESTO: {framework}\n"
            f"Usa i concetti dei seguenti framework per la tua analisi:\n"
            f"- Grand Chessboard (Brzezinski): focus su Stati perno "
            f"(Pivot States), controllo dell'Eurasia, infrastrutture "
            f"energetiche e alleanze strategiche.\n"
            f"- Prisoners of Geography (Tim Marshall): focus su limiti "
            f"fisici, fiumi navigabili, catene montuose, porti in acque "
            f"calde e colli di bottiglia marittimi.\n"
            f"- World Order (Kissinger): focus su legittimita', equilibrio "
            f"di potere (Westfaliano), competizione multipolare e clash "
            f"di sfere d'influenza.\n\n"
            f"OBIETTIVO:\n"
            f"Valutare l'impatto strategico a lungo e medio termine degli "
            f"eventi correnti su {asset} utilizzando la lente del framework "
            f"richiesto. Non usare banalita', concentrati su colli di "
            f"bottiglia concreti, catene di approvvigionamento, o assetti "
            f"di potere regionali.\n\n"
            f"FORMATO RISPOSTA RICHIESTO:\n"
            f"Rispondi ESCLUSIVAMENTE con un JSON valido:\n"
            f'{{"risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL", '
            f'"geographic_anchor": "Specifica il fattore geografico o '
            f"l'infrastruttura chiave.\", "
            f'"strategic_implication": "Cosa significa questo evento per '
            f'le grandi potenze? (max 3 righe)", '
            f'"market_impact": "Come questo rischio geopolitico si '
            f'traduce sull\'asset?", '
            f'"black_swan_scenario": "Il peggior scenario plausibile '
            f'(cigno nero geopolitico) da monitorare."}}\n'
        )

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
                return self._format_geopolitical_response(data, asset, framework)
            except json.JSONDecodeError:
                return text

        except Exception as e:  # pylint: disable=broad-exception-caught
            return f"Error gathering AI geopolitical analysis: {e}"

    @staticmethod
    def _format_geopolitical_response(
        data: dict, asset: str, framework: str
    ) -> str:
        """Format geopolitical JSON response into readable markdown."""
        risk = data.get("risk_level", "UNKNOWN").upper()
        anchor = data.get("geographic_anchor", "N/A")
        strategic = data.get("strategic_implication", "N/A")
        impact = data.get("market_impact", "N/A")
        swan = data.get("black_swan_scenario", "N/A")

        return (
            f"### Geopolitical Risk Analysis: **{risk}**\n\n"
            f"**Geographic/Strategic Anchor:**\n{anchor}\n\n"
            f"**Strategic Implication ({framework}):**\n{strategic}\n\n"
            f"**Market Impact on {asset}:**\n{impact}\n\n"
            f"**Black Swan Scenario:**\n{swan}"
        )
