from .ai_provider import AIProvider
import json


class TraderAgent:
    def __init__(self, provider_type="gemini", model_name=None):
        self.ai = AIProvider(provider_type=provider_type, model_name=model_name)
        # Force JSON mode off for description unless we want strict JSON output
        # For this dashboard, natural language with a structure is better, but let's see.
        # The user example prompt suggests natural language output with specific fields.

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
