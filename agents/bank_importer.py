"""
Module for handling Bank CSV Import and AI Categorization.
This module encapsulates the logic to read a bank export file, 
categorize its transactions using an AI model, and aggregate the results
to match the Budget Application's database schema.
"""

import io
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from .merchant_utils import normalize_merchant
except ImportError:  # pragma: no cover - esecuzione diretta del modulo
    from merchant_utils import normalize_merchant

if TYPE_CHECKING:
    from .opencode_agent import OpencodeAgent


# Categoria pseudo-valida usata per i trasferimenti tra conti propri e le voci
# da escludere dai totali: viene assegnata, mostrata nella review e salvata in
# ``transactions``, ma NON viene sommata negli aggregati (non è tra le
# target_categories).
EXCLUDED_CATEGORY = "Escluso"

# Mappatura deterministica dei tipi di transazione di Trade Republic.
# Priorità assoluta: un tipo strutturale (BUY/TRANSFER/...) non ha un
# "merchant" reale, quindi va categorizzato per tipo e NON passa dall'LLM.
TR_TYPE_MAP = {
    "BUY": "Investimenti",
    "TRANSFER_INSTANT_OUTBOUND": EXCLUDED_CATEGORY,
    "TRANSFER_INSTANT_INBOUND": EXCLUDED_CATEGORY,
    "FREE_RECEIPT": EXCLUDED_CATEGORY,
    "BENEFITS_SAVEBACK": "Reddito aggiuntivo",
    "INTEREST_PAYMENT": "Reddito aggiuntivo",
}

# Categorie tedesche (Anadi) con mapping deterministico -> italiano.
# Le voci NON presenti qui (Unkategorisiert, Sonstiges, Veranlagung) vanno
# all'LLM (o al merchant-map lookup).
GERMAN_CATEGORY_MAP = {
    "Lebensmittel": "Alimentari",
    "Bargeld": "Bancomat",
    "Versicherung": "Immobili (affitto, mutuo, tasse, assicurazione)",
    "Wohnen & Haushalt": "Immobili (affitto, mutuo, tasse, assicurazione)",
    "Gesundheit": "Medicinali",
    "Einkünfte": "Stipendio",
    "Kommunikation & Medien": "PayPal + Abbonamenti",
}

# Token "benzinaio" per discriminare Mobilität -> Carburante.
_FUEL_TOKENS = ("JET", "DISKONT", "TANKSTELLE")

# Token "ristorante/bar/caffè" per discriminare Freizeit & Genuss -> Cene, Pranzo.
_RESTAURANT_TOKENS = (
    "restaurant", "ristorante", "trattoria", "osteria", "pizzeria", "bar",
    "cafe", "caff", "coffee", "bistro", "gelateria", "enoteca", "sushi",
    "wurstel", "ditsch", "stroeck", "mcdonald", "kfc", "piadineria", "salud",
    "racers", "mcmullens", "yarra", "meschik", "dampfer", "terrazza", "egglab",
    "hungry", "starbucks", "bakery", "pastry", "konditorei",
)


class AiStats(BaseModel):
    """Statistiche del run di categorizzazione AI (diagnostica UI).

    Serializzata da ``process_file`` sotto la chiave ``ai_stats``. Retro-
    compatibile: è una chiave nuova e non sostituisce le esistenti.
    """

    mode: Literal["hybrid", "llm_only"] = "hybrid"
    llm_sent: int = 0
    llm_mapped: int = 0
    llm_failed: int = 0
    errors: List[str] = Field(default_factory=list)


class BankImporter:
    """Handles the import and processing of bank statements."""

    def __init__(
        self,
        ai_provider=None,
        opencode_agent: Optional["OpencodeAgent"] = None,
    ):
        """
        Args:
            ai_provider: An instance of the AIProvider class to be used for categorization.
            opencode_agent: An instance of OpencodeAgent to use instead of AIProvider.
        """
        self.ai_provider = ai_provider
        self.opencode_agent = opencode_agent

    @staticmethod
    def _record_ai_error(stats, message: str) -> None:
        """Logga un errore di categorizzazione AI e lo accumula in ``stats``.

        NON solleva eccezioni: un fallimento della categorizzazione resta un
        dato del run (visibile nella UI), non un crash per l'utente.
        """
        logger.error("Categorizzazione AI fallita: %s", message)
        if stats is not None and len(stats.errors) < 20:
            stats.errors.append(str(message)[:500])

    def _load_db(self):
        """Importa lazy il modulo db della Budget App (opzionale).

        Ritorna il modulo se importabile, altrimenti None. Così il pacchetto
        `agents` resta installabile/importabile anche senza Budget_App: in
        quel caso la mappatura è vuota e si procede tutto via LLM.
        """
        try:
            import db as _db
            return _db
        except Exception:
            return None

    def _load_merchant_map(self):
        """Ritorna {merchant_normalized: MerchantEntry} (dict vuoto se assente)."""
        _db = self._load_db()
        if _db is None:
            return {}
        try:
            return _db.get_merchant_map()
        except Exception:
            return {}

    def _persist_llm_mappings(self, batch_mappings, id_to_desc):
        """Salva le categorie apprese dall'LLM come source='llm'.

        Non sovrascrive MAI le correzioni manuali (garantito da upsert_merchant).
        """
        _db = self._load_db()
        if _db is None:
            return
        for idx, category in batch_mappings.items():
            desc = id_to_desc.get(idx)
            if not desc:
                continue
            try:
                _db.upsert_merchant(
                    normalize_merchant(desc), category, source="llm", confidence=0.7
                )
            except Exception:
                pass

    def _clean_amount(self, amount_str):
        """Converts German format (1.234,56) to float (1234.56)."""
        if pd.isna(amount_str) or amount_str == "":
            return 0.0
        if isinstance(amount_str, (int, float)):
            return float(amount_str)
        
        # Remove thousands separator (.), replace decimal separator (,)
        clean = str(amount_str).replace('.', '')
        clean = clean.replace(',', '.')
        try:
            return float(clean)
        except ValueError:
            return 0.0

    def _load_csv(self, file_buffer):
        """Loads CSV from buffer trying different encodings and separators."""
        # Try different encodings
        encodings = ['latin1', 'cp1252', 'utf-8']
        
        for enc in encodings:
            try:
                file_buffer.seek(0)
                # First try semicolon
                df = pd.read_csv(file_buffer, sep=';', encoding=enc)
                if len(df.columns) <= 1:
                    # If only 1 column was found, it's likely a comma separated file
                    file_buffer.seek(0)
                    df = pd.read_csv(file_buffer, sep=',', encoding=enc)
                return df
            except UnicodeDecodeError:
                continue
            except Exception as e:
                # Other exceptions like parsing errors, try next encoding just in case, but usually it fails
                pass
                
        raise Exception("Failed to read CSV with supported encodings (latin1, cp1252, utf-8)")

    def _standardize_columns(self, df):
        """Identifies key columns and creates standardized columns for internal use."""
        # Create a lowercase mapping of the columns
        lower_cols = {str(col).lower(): col for col in df.columns}
        
        amount_aliases = ['betrag', 'amount', 'importo', 'value', 'importo in eur']
        date_aliases = ['buchungsdatum', 'date', 'data', 'valuta', 'datetime', 'data contabile']
        desc_aliases = ['umsatztext', 'buchungstext', 'description', 'descrizione', 'causale', 'name', 'payment_reference', 'name des partners', 'counterparty_name', 'descrizione operazione']
        cat_aliases = ['kategorie', 'category', 'categoria']
        name_aliases = ['name', 'counterparty_name', 'name des partners', 'descrizione operazione']
        type_aliases = ['type', 'transaction_type', 'tipo']

        # 1. Amount
        df['Std_Amount'] = 0
        for alias in amount_aliases:
            if alias in lower_cols:
                df['Std_Amount'] = df[lower_cols[alias]]
                break

        # 1.5 Taxes and Fees
        tax_aliases = ['tax', 'tassa', 'steuer', 'imposta']
        fee_aliases = ['fee', 'commissione', 'gebühr', 'commission']

        df['Std_Tax'] = 0
        for alias in tax_aliases:
            if alias in lower_cols:
                df['Std_Tax'] = df[lower_cols[alias]]
                break
                
        df['Std_Fee'] = 0
        for alias in fee_aliases:
            if alias in lower_cols:
                df['Std_Fee'] = df[lower_cols[alias]]
                break

        # 1.6 Transaction type (Trade Republic: BUY/TRANSFER/CARD_TRANSACTION/...)
        df['Std_Type'] = ''
        for alias in type_aliases:
            if alias in lower_cols:
                df['Std_Type'] = df[lower_cols[alias]].fillna('').astype(str)
                break

        # 2. Date
        df['Std_Date'] = ''
        for alias in date_aliases:
            if alias in lower_cols:
                df['Std_Date'] = df[lower_cols[alias]]
                break

        # 3. Category
        df['Std_Category'] = 'Da Categorizzare'
        for alias in cat_aliases:
            if alias in lower_cols:
                df['Std_Category'] = df[lower_cols[alias]]
                break

        # 3.5 Merchant name (identità pulita del negozio, per il lookup seed)
        df['Std_Name'] = ''
        for alias in name_aliases:
            if alias in lower_cols:
                df['Std_Name'] = df[lower_cols[alias]].fillna('').astype(str)
                break

        # 4. Description (Concatenate all matching description columns)
        desc_parts = []
        for alias in desc_aliases:
            if alias in lower_cols:
                desc_parts.append(df[lower_cols[alias]].fillna('').astype(str))
        
        if desc_parts:
            # Concatenate them into a single string separated by space
            df['Std_Description'] = pd.concat(desc_parts, axis=1).agg(' '.join, axis=1).str.strip()
        else:
            df['Std_Description'] = ''
            
        return df

    def _map_german_category(self, german_cat, desc):
        """Mappa deterministica una categoria tedesca (Anadi) in italiano.

        Ritorna la categoria italiana, oppure None per le voci NON mappabili
        deterministicamente (Unkategorisiert/Sonstiges/Veranlagung...) che
        devono andare all'LLM o al merchant-map lookup.
        """
        cat = (german_cat or "").strip()

        # Mobilität: Carburante se benzinaio, altrimenti Trasporti.
        if cat == "Mobilität":
            d = (desc or "").upper()
            if any(tok in d for tok in _FUEL_TOKENS):
                return "Carburante"
            return "Trasporti"

        # Freizeit & Genuss: Cene, Pranzo se ristorante/bar/caffè dal nome.
        if cat == "Freizeit & Genuss":
            d = (desc or "").lower()
            if any(tok in d for tok in _RESTAURANT_TOKENS):
                return "Cene, Pranzo"
            return "Viaggi, Divertimento"

        if cat not in GERMAN_CATEGORY_MAP:
            return None

        return GERMAN_CATEGORY_MAP[cat]

    def _map_trade_type(self, std_type):
        """Categoria deterministica per i tipi Trade Republic, o None."""
        t = (std_type or "").strip().upper()
        return TR_TYPE_MAP.get(t)

    def _deterministic_category(self, std_type, std_category, desc):
        """Categoria deterministica (senza LLM) per una riga, o None.

        Priorità: tipo Trade Republic (strutturale) -> categoria tedesca.
        """
        det = self._map_trade_type(std_type)
        if det is not None:
            return det
        return self._map_german_category(std_category, desc)

    def process_file(
        self,
        file_buffer,
        target_categories,
        income_cols,
        progress_callback=None,
        classify_mode: Literal["hybrid", "llm_only"] = "hybrid",
    ):
        """
        Processes the uploaded bank file (CSV or PDF).
        
        Args:
            file_buffer: The file object from streamlit uploader.
            target_categories (list): List of valid expense/income categories.
            income_cols (list): List of categories considered as Income.
            progress_callback (func): Optional callback (percent: float, message: str).
            classify_mode (Literal["hybrid", "llm_only"]): Modalità di
                classificazione. "hybrid" (default) usa le scorciatoie
                deterministiche (tipo Trade Republic, merchant_map, categoria
                tedesca) e invia all'LLM solo il residuo. "llm_only" bypassa
                TUTTE le scorciatoie deterministiche: ogni transazione passa
                dall'LLM (utile per misurare l'Opzione A senza che la mappatura
                negozi->categorie "nasconda" il lavoro del modello).

        Returns:
            dict: {
                'detailed_df': DataFrame with individual transactions and AI mappings.
                'aggregated_df': DataFrame with monthly totals matching the budget DB.
                'report_md': Markdown string for the comparison report.
            }
        """
        if classify_mode not in ("hybrid", "llm_only"):
            raise ValueError(
                f"classify_mode non valido: {classify_mode!r}. "
                "Valori ammessi: 'hybrid', 'llm_only'."
            )

        # 0. Detect File Type
        file_name = file_buffer.name.lower()
        
        # 1. Load Data
        df = None
        if file_name.endswith('.pdf'):
            if progress_callback:
                progress_callback(0.0, "Estrazione dati da PDF (Multimodale)...")
            try:
                # Read bytes for PDF
                pdf_bytes = file_buffer.getvalue()
                df = self._extract_from_pdf(pdf_bytes)
            except Exception as e:
                raise ValueError(f"Errore estrazione PDF: {e}")
        else:
            # Assume CSV
            df = self._load_csv(file_buffer)
            
        if df is None or df.empty:
            raise ValueError("File is empty or could not be read.")

        # 1.5 Standardize Columns
        df = self._standardize_columns(df)

        # 2. Prepare for Categorization
        if self.opencode_agent:
            model = None
        else:
            model = self.ai_provider.get_model(json_mode=True)

        mappings = {}

        # 2.5 Merchant-map pre-lookup: le transazioni già note NON vanno all'LLM.
        # In modalità "llm_only" la mappa viene bypassata per intero, così ogni
        # transazione passa dall'LLM (misura pulita dell'Opzione A).
        if classify_mode == "hybrid":
            merchant_map = self._load_merchant_map()
        else:
            merchant_map = {}

        if classify_mode == "hybrid":
            # Categoria deterministica (tipo Trade Republic / categoria tedesca)
            # calcolata per riga. Serve a mostrare una categoria italiana valida
            # anche per le righe non processate dall'LLM.
            deterministic = {}
            for index, row in df.iterrows():
                deterministic[index] = self._deterministic_category(
                    row.get('Std_Type', ''),
                    row.get('Std_Category', ''),
                    row.get('Std_Description', ''),
                )

            # Analyzed_Category = categoria deterministica se presente, altrimenti
            # la categoria originale (per il confronto nella review/report).
            df['Analyzed_Category'] = [
                deterministic.get(i) or str(df.at[i, 'Std_Category'])
                for i in df.index
            ]
        else:
            # Modalità "llm_only": nessuna scorciatoia deterministica.
            # Analyzed_Category coincide con la categoria originale della banca.
            df['Analyzed_Category'] = [
                str(df.at[i, 'Std_Category']) for i in df.index
            ]

        items_to_process = []
        id_to_desc = {}
        for index, row in df.iterrows():
            desc = row.get('Std_Description', '')
            amount = row.get('Std_Amount', '0')
            old_cat = row.get('Std_Category', '')
            std_name = row.get('Std_Name', '')
            std_type = row.get('Std_Type', '')

            item = {
                "id": index,
                "description": desc,
                "amount": amount,
                "old_category": old_cat
            }
            id_to_desc[index] = desc

            if classify_mode == "hybrid":
                # 1) Tipo Trade Republic (strutturale): priorità massima. Per i tipi
                #    BUY/TRANSFER/FREE_RECEIPT/... il campo "name" NON è un negozio
                #    ma il titolo/counterparty, quindi va categorizzato per tipo.
                det_type = self._map_trade_type(std_type)
                if det_type is not None:
                    mappings[index] = det_type
                    continue

                # 2) Merchant-map lookup: usa il nome pulito se presente, altrimenti
                #    la descrizione. Qualunque categoria (INCLUSA 'Escluso') viene
                #    assegnata direttamente, saltando l'LLM.
                key = normalize_merchant(std_name) or normalize_merchant(desc)
                entry = merchant_map.get(key) if key else None
                if entry is not None:
                    mappings[index] = entry.category
                    continue

                # 3) Categoria tedesca deterministica (Anadi): salta l'LLM.
                det_german = self._map_german_category(old_cat, desc)
                if det_german is not None:
                    mappings[index] = det_german
                    continue

            # 4) Altrimenti -> LLM. In modalità "llm_only" ogni transazione
            #    arriva sempre qui per essere categorizzata dal modello.
            items_to_process.append(item)

        # Statistiche diagnostiche del run AI (niente più fallimenti silenziosi).
        ai_stats = AiStats(mode=classify_mode, llm_sent=len(items_to_process))
        valid_cats = set(target_categories) | {EXCLUDED_CATEGORY}

        # 3. Process in Batches (solo le transazioni non note)
        
        BATCH_SIZE = 20
        total_batches = (len(items_to_process) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, len(items_to_process), BATCH_SIZE):
            current_batch_num = i // BATCH_SIZE + 1
            if progress_callback:
                # Adjust progress to account for PDF step
                base_c = 0.2 if file_name.endswith('.pdf') else 0.0
                if items_to_process:
                    percent = base_c + (i / len(items_to_process)) * (0.9 - base_c)
                else:
                    percent = 0.9
                progress_callback(percent, f"Analisi AI in corso: Batch {current_batch_num}/{max(total_batches, 1)}...")
            
            batch = items_to_process[i:i+BATCH_SIZE]

            if self.opencode_agent:
                batch_mappings = self._categorize_with_opencode(
                    batch, target_categories, ai_stats
                )
            else:
                batch_mappings = self._categorize_with_ai(
                    model, batch, target_categories, ai_stats
                )

            if batch_mappings:
                mappings.update(batch_mappings)
                self._persist_llm_mappings(batch_mappings, id_to_desc)
                ai_stats.llm_mapped += sum(
                    1 for cat in batch_mappings.values() if cat in valid_cats
                )
        
        if progress_callback:
            progress_callback(0.9, "Applicazione modifiche e calcoli finali...")

        # 4. Apply Mappings
        df['New_Category'] = df['Analyzed_Category']  # Default
        for idx, new_cat in mappings.items():
            if idx in df.index and new_cat in valid_cats:
                df.at[idx, 'New_Category'] = new_cat

        # 5. Clean Data for Aggregation
        df['Betrag_Float'] = df['Std_Amount'].apply(self._clean_amount)
        
        if 'Std_Fee' in df.columns:
            df['Fee_Float'] = df['Std_Fee'].apply(self._clean_amount)
        else:
            df['Fee_Float'] = 0.0
            
        if 'Std_Tax' in df.columns:
            df['Tax_Float'] = df['Std_Tax'].apply(self._clean_amount)
        else:
            df['Tax_Float'] = 0.0
            
        # Algebraic sum: if amount is positive and tax is negative, it reduces the net amount
        # If amount is negative and fee is negative, it increases the total expense
        df['Betrag_Float'] = df['Betrag_Float'] + df['Fee_Float'] + df['Tax_Float']

        # Parse Dates
        df['DateObj'] = pd.to_datetime(df['Std_Date'], format='%d/%m/%Y', errors='coerce')
        mask = df['DateObj'].isna()
        if mask.any():
            df.loc[mask, 'DateObj'] = pd.to_datetime(df.loc[mask, 'Std_Date'], format='%Y-%m-%d', errors='coerce')
        mask = df['DateObj'].isna()
        if mask.any():
            try:
                df.loc[mask, 'DateObj'] = pd.to_datetime(df.loc[mask, 'Std_Date'], format='mixed', dayfirst=True, errors='coerce')
            except Exception:
                df.loc[mask, 'DateObj'] = pd.to_datetime(df.loc[mask, 'Std_Date'], errors='coerce')

        df['Year'] = df['DateObj'].dt.year
        df['MonthNum'] = df['DateObj'].dt.month
        df['Month'] = df['DateObj'].dt.strftime('%B')

        # 6. Generate Report Markdown
        report_md = self.generate_report(df)

        # 7. Aggregate
        aggregated_df = self.aggregate_data(df, target_categories, income_cols)
        
        ai_stats.llm_failed = max(ai_stats.llm_sent - ai_stats.llm_mapped, 0)

        if progress_callback:
            progress_callback(1.0, "Fatto!")

        return {
            'detailed_df': df,
            'aggregated_df': aggregated_df,
            'report_md': report_md,
            'ai_stats': ai_stats.model_dump(),
        }

    def _extract_from_pdf(self, pdf_bytes):
        """Extracts transactions from PDF bytes using Multimodal AI."""
        prompt = """
        Extract ALL bank transactions from this PDF statement.
        Return a JSON list of objects with these exact fields:
        - "Buchungsdatum": Date DD.MM.YYYY
        - "Umsatztext": Description/Payee
        - "Betrag": Amount as string (e.g. "-12,50" or "1.200,00"). Use European format.
        
        Example JSON:
        [
          {"Buchungsdatum": "01.01.2024", "Umsatztext": "Amazon", "Betrag": "-25,90"},
          {"Buchungsdatum": "15.01.2024", "Umsatztext": "Salary", "Betrag": "2500,00"}
        ]
        """
        
        model = self.ai_provider.get_model(json_mode=True)
        
        # Multimodal call: [Text, PDF_Bytes]
        # AIProvider wrapper (GeminiWrapper) usually handles list if valid.
        # We need to pass mime_type wrapper or raw bytes if supported.
        # Checking AIProvider implementation from context:
        # It handles `final_prompt` which can be structure with mime_type.
        

        
        request_content = [
            prompt,
            {"mime_type": "application/pdf", "data": pdf_bytes}
        ]
        
        response = model.generate_content(request_content)
        text_resp = response.text if hasattr(response, 'text') else str(response)
        
        # Clean markdown
        if "```json" in text_resp:
            text_resp = text_resp.replace("```json", "").replace("```", "")
        
        data = json.loads(text_resp)
        
        # Use 'transactions' key if wrapped, else assume list
        if isinstance(data, dict):
            data = data.get('transactions', data.get('items', []))
            
        df = pd.DataFrame(data)
        
        return df 


    @staticmethod
    def _build_letter_index(target_categories: List[str]) -> Optional[Dict[str, str]]:
        """Builds a compact ``LETTER -> category`` index for the AI prompt.

        Assigns A..Z to the first 26 categories. Returns ``None`` when the
        category list cannot be encoded with single letters, so callers can
        fall back to the legacy verbose JSON schema.
        """
        if not target_categories or len(target_categories) > 26:
            return None
        return {
            chr(ord("A") + i): cat
            for i, cat in enumerate(target_categories)
        }

    @staticmethod
    def _build_letter_prompt(batch: List[Dict[str, Any]], letter_index: Dict[str, str]) -> str:
        """Builds the ultra-compact categorization prompt (letter schema).

        Instead of repeating the full category name for every transaction, the
        model only has to emit one letter per id, drastically shrinking the
        generated output.
        """
        letters_block = "\n".join(
            f"{letter}={cat}" for letter, cat in letter_index.items()
        )
        return f"""
        You are an expert financial assistant.
        Your task is to MAP bank transactions to valid budget categories.

        CATEGORY_LETTERS (answer with the single LETTER, not the full name):
        {letters_block}

        RULES:
        1. "Freizeit & Genuss" is generic. You MUST be specific based on the description:
        - Restaurants, Bars, Food delivery -> 'Cene, Pranzo'
        - Pharmacies (Apotheke, DM often), Doctors -> 'Medicinali'
        - Trains, Buses, Taxi, Uber -> 'Trasporti'
        - Flights, Hotels, Airbnb, Cinema, Events -> 'Viaggi, Divertimento'
        - Gas stations (Tankstelle) -> 'Carburante'
        - Subscriptions (Spotify, Netflix) -> 'PayPal + Abbonamenti'
        2. "Lebensmittel" (Groceries) or Supermarkets -> 'Alimentari'.
        3. "Mobilität" usually maps to 'Carburante' or 'Trasporti'.
        4. "Miete" (Rent) / Insurance -> 'Immobili (affitto, mutuo, tasse, assicurazione)'.
        5. Salary/Wages -> 'Stipendio'.
        6. Incoming transfers -> 'Reddito aggiuntivo' (unless typical salary).

        TRANSACTIONS:
        {json.dumps(batch)}

        Return ONLY a JSON object mapping each transaction id to its single
        category LETTER, e.g. {{"12":"A","13":"C"}}.
        """

    @staticmethod
    def _parse_letter_mappings(
        text: str,
        batch: List[Dict[str, Any]],
        letter_index: Dict[str, str],
    ) -> Dict[int, str]:
        """Parses the compact ``{"id": "LETTER"}`` AI response.

        Accepts JSON objects (also wrapped in markdown fences or embedded in
        prose) and plain ``id: LETTER`` / ``id=LETTER`` lines. Ids not present
        in ``batch`` and letters outside ``letter_index`` are ignored.

        Returns ``{index: category}``.
        """
        if not text or not letter_index:
            return {}

        valid_ids = {
            int(item["id"])
            for item in batch
            if item.get("id") is not None
        }
        upper_index = {key.upper(): value for key, value in letter_index.items()}

        def _letter_to_category(raw: Any) -> Optional[str]:
            if raw is None:
                return None
            match = re.search(r"[A-Za-z]", str(raw))
            if not match:
                return None
            return upper_index.get(match.group(0).upper())

        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1]
        cleaned = cleaned.strip()

        result: Dict[int, str] = {}

        candidate = cleaned
        if not candidate.startswith("{"):
            start, end = candidate.find("{"), candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = candidate[start:end + 1]
        if candidate.startswith("{"):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    try:
                        tid = int(str(key).strip().strip('"').strip("'"))
                    except (TypeError, ValueError):
                        continue
                    if tid not in valid_ids:
                        continue
                    category = _letter_to_category(value)
                    if category:
                        result[tid] = category

        if not result:
            for match in re.finditer(r"[\"']?(\d+)[\"']?\s*[:=]\s*[\"']?([A-Za-z])", cleaned):
                tid = int(match.group(1))
                if tid not in valid_ids:
                    continue
                category = upper_index.get(match.group(2).upper())
                if category:
                    result[tid] = category

        return result

    def _categorize_with_ai(self, model, batch, target_categories, stats=None):
        """Categorize a batch using the AIProvider model.

        Uses the compact letter schema (one letter per transaction) and falls
        back to the legacy verbose JSON schema when the category list cannot be
        encoded as single letters or the letter response is unparsable.

        Ritorna un dict {id: new_category} delle categorie assegnate. In caso di
        errore provider/parsing logga e accumula la diagnostica in ``stats``
        (NON solleva eccezioni).
        """
        letter_index = self._build_letter_index(target_categories)
        if letter_index is None:
            logger.warning("Più di 26 categorie: uso lo schema JSON verboso.")
            return self._categorize_with_ai_json(
                model, batch, target_categories, stats
            )

        prompt_text = self._build_letter_prompt(batch, letter_index)
        try:
            response = model.generate_content(prompt_text)
            text_response = response.text if hasattr(response, 'text') else str(response)
            batch_mappings = self._parse_letter_mappings(text_response, batch, letter_index)
            if not batch_mappings:
                logger.warning(
                    "Schema a lettere inutilizzabile: fallback a JSON verboso."
                )
                return self._categorize_with_ai_json(
                    model, batch, target_categories, stats
                )
            return batch_mappings
        except Exception as e:  # pylint: disable=broad-except
            self._record_ai_error(
                stats, f"AIProvider (letter schema) error: {e!r}"
            )
            return {}

    def _categorize_with_ai_json(self, model, batch, target_categories, stats=None):
        """Legacy verbose categorization path (one full category per id).

        Kept as a defensive fallback for the letter schema.
        """
        prompt_text = f"""
        You are an expert financial assistant.
        Your task is to MAP bank transactions to valid budget categories.

        VALID CATEGORIES (Exact Match Required):
        {target_categories}

        RULES:
        1. "Freizeit & Genuss" is generic. You MUST be specific based on the description:
        - Restaurants, Bars, Food delivery -> 'Cene, Pranzo'
        - Pharmacies (Apotheke, DM often), Doctors -> 'Medicinali'
        - Trains, Buses, Taxi, Uber -> 'Trasporti'
        - Flights, Hotels, Airbnb, Cinema, Events -> 'Viaggi, Divertimento'
        - Gas stations (Tankstelle) -> 'Carburante'
        - Subscriptions (Spotify, Netflix) -> 'PayPal + Abbonamenti'
        2. "Lebensmittel" (Groceries) or Supermarkets -> 'Alimentari'.
        3. "Mobilität" usually maps to 'Carburante' or 'Trasporti'.
        4. "Miete" (Rent) / Insurance -> 'Immobili (affitto, mutuo, tasse, assicurazione)'.
        5. Salary/Wages -> 'Stipendio'.
        6. Incoming transfers -> 'Reddito aggiuntivo' (unless typical salary).

        TRANSACTIONS:
        {json.dumps(batch)}

        Return JSON:
        {{ "mappings": [ {{ "id": <id>, "new_category": "<ValidCategory>" }} ] }}
        """
        text_response = ""
        try:
            response = model.generate_content(prompt_text)
            text_response = response.text if hasattr(response, 'text') else str(response)
            if "```json" in text_response:
                text_response = text_response.replace("```json", "").replace("```", "")
            result = json.loads(text_response)
            batch_mappings = {}
            for m in result.get("mappings", []):
                batch_mappings[m['id']] = m['new_category']
            return batch_mappings
        except Exception as e:  # pylint: disable=broad-except
            self._record_ai_error(
                stats,
                f"AIProvider (JSON schema) error: {e!r}; "
                f"raw={text_response[:500]!r}",
            )
            return {}

    def _categorize_with_opencode(self, batch, target_categories, stats=None):
        """Categorize a batch of transactions using OpencodeAgent.

        Uses the compact letter schema with a verbose JSON fallback (see
        ``_categorize_with_ai``). Gli errori provider/parsing sono loggati e
        accumulati in ``stats`` invece di essere silenziosi.
        """
        letter_index = self._build_letter_index(target_categories)
        if letter_index is None:
            logger.warning("Più di 26 categorie: uso lo schema JSON verboso.")
            return self._categorize_with_opencode_json(
                batch, target_categories, stats
            )

        prompt_text = self._build_letter_prompt(batch, letter_index)
        result = self.opencode_agent.run_prompt(prompt_text)
        if not result.success:
            self._record_ai_error(
                stats, f"OpenCode (letter schema) error: {result.error}"
            )
            return {}

        batch_mappings = self._parse_letter_mappings(result.text, batch, letter_index)
        if not batch_mappings:
            logger.warning(
                "Schema a lettere inutilizzabile: fallback a JSON verboso."
            )
            return self._categorize_with_opencode_json(
                batch, target_categories, stats
            )
        return batch_mappings

    def _categorize_with_opencode_json(self, batch, target_categories, stats=None):
        """Legacy verbose OpenCode categorization path (fallback)."""
        prompt_text = f"""
        You are an expert financial assistant.
        Your task is to MAP bank transactions to valid budget categories.

        VALID CATEGORIES (Exact Match Required):
        {target_categories}

        RULES:
        1. "Freizeit & Genuss" is generic. You MUST be specific based on the description:
        - Restaurants, Bars, Food delivery -> 'Cene, Pranzo'
        - Pharmacies (Apotheke, DM often), Doctors -> 'Medicinali'
        - Trains, Buses, Taxi, Uber -> 'Trasporti'
        - Flights, Hotels, Airbnb, Cinema, Events -> 'Viaggi, Divertimento'
        - Gas stations (Tankstelle) -> 'Carburante'
        - Subscriptions (Spotify, Netflix) -> 'PayPal + Abbonamenti'
        2. "Lebensmittel" (Groceries) or Supermarkets -> 'Alimentari'.
        3. "Mobilität" usually maps to 'Carburante' or 'Trasporti'.
        4. "Miete" (Rent) / Insurance -> 'Immobili (affitto, mutuo, tasse, assicurazione)'.
        5. Salary/Wages -> 'Stipendio'.
        6. Incoming transfers -> 'Reddito aggiuntivo' (unless typical salary).

        TRANSACTIONS:
        {json.dumps(batch)}

        Return ONLY valid JSON (no markdown):
        {{ "mappings": [ {{ "id": <id>, "new_category": "<ValidCategory>" }} ] }}
        """
        result = self.opencode_agent.run_prompt(prompt_text)
        if not result.success:
            self._record_ai_error(
                stats, f"OpenCode (JSON schema) error: {result.error}"
            )
            return {}

        text = result.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            parsed = json.loads(text)
            batch_mappings = {}
            for m in parsed.get("mappings", []):
                batch_mappings[m['id']] = m['new_category']
            return batch_mappings
        except (json.JSONDecodeError, KeyError) as e:
            self._record_ai_error(
                stats,
                f"OpenCode (JSON schema) parse error: {e!r}; raw={text[:500]!r}",
            )
            return {}

    def generate_report(self, df):
        """Generates a markdown table highlighting changes."""
        md = "| Date | Description | Amount | Original Category | **New AI Category** |\n"
        md += "|---|---|---|---|---|\n"
        
        for idx, row in df.iterrows():
            desc = str(row.get('Std_Description', ''))[:40]
            old = row.get('Analyzed_Category', '')
            new = row.get('New_Category', '')
            amt = row.get('Betrag_Float', 0)
            date = str(row.get('Std_Date', ''))
            
            # Formatting
            desc = desc.replace("|", "-") # Avoid breaking MD table
            
            # Highlight changes
            if old != new:
                new_display = f"**:green[{new}]**" # Streamlit markdown color
            else:
                new_display = new
            
            md += f"| {date} | {desc} | {amt:.2f} | {old} | {new_display} |\n"
            
        return md

    def aggregate_data(self, df, target_categories, income_cols):
        """Aggregates transactions into monthly totals per category."""
        
        def adjust_sign(row):
            val = row['Betrag_Float']
            cat = row['New_Category']
            if cat in income_cols:
                return val if val > 0 else 0 
            else:
                # Expenses: Convert negative bank amount to positive budget amount
                return -val

        df['Budget_Amount'] = df.apply(adjust_sign, axis=1)

        pivot_df = df.pivot_table(
            index=['Year', 'MonthNum', 'Month'], 
            columns='New_Category', 
            values='Budget_Amount', 
            aggfunc='sum',
            fill_value=0.0
        ).reset_index()

        # Ensure all columns exist
        for cat in target_categories:
            if cat not in pivot_df.columns:
                pivot_df[cat] = 0.0

        # Calculate Totals
        present_income = [c for c in income_cols if c in pivot_df.columns]
        present_expense = [c for c in target_categories if c not in income_cols and c in pivot_df.columns]

        pivot_df['Totale Entrate'] = pivot_df[present_income].sum(axis=1)
        pivot_df['Totale Uscite'] = pivot_df[present_expense].sum(axis=1)
        pivot_df['Reddito meno spese'] = pivot_df['Totale Entrate'] - pivot_df['Totale Uscite']
        pivot_df['Risparmio %'] = pivot_df.apply(
            lambda row: (row['Reddito meno spese'] / row['Totale Entrate'] * 100) if row['Totale Entrate'] != 0 else 0, 
            axis=1
        )
        
        # Return aggregated df
        return pivot_df

    @staticmethod
    def build_transaction_records(detailed_df, source="bank_import"):
        """Build transaction records (list of dicts) matching the Budget App
        ``transactions`` table schema: date, description, amount, category,
        source, month_ref.

        Called by the Budget App after the user confirms an import, so the
        individual (daily) transactions can be persisted alongside the monthly
        pivot.
        """
        records = []
        for _, row in detailed_df.iterrows():
            date_obj = row.get("DateObj")
            if pd.notna(date_obj) and hasattr(date_obj, "strftime"):
                date_str = date_obj.strftime("%Y-%m-%d")
            else:
                date_str = str(row.get("Std_Date", ""))

            year = row.get("Year")
            month = row.get("Month", "")
            month_ref = f"{month} {int(year)}" if pd.notna(year) else ""

            amount = row.get("Betrag_Float", 0.0)

            records.append(
                {
                    "date": date_str,
                    "description": str(row.get("Std_Description", "")),
                    "amount": float(amount) if pd.notna(amount) else 0.0,
                    "category": str(row.get("New_Category", "") or ""),
                    "source": source,
                    "month_ref": month_ref,
                }
            )
        return records
