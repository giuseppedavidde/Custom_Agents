"""Normalizzazione condivisa dei nomi dei negozi (merchant).

Funzione pura, senza dipendenze esterne (solo `re`), usata sia dal flusso di
import (bank_importer) sia dalla UI (budget_app / db) per costruire la chiave
di lookup della mappatura negozio -> categoria. La STESSA funzione viene usata
sia per la chiave di lookup sia per la chiave salvata, così la mappatura resta
coerente ovunque.
"""

import re

# Token "riempitivi" comuni negli estratti conto bancari (store/branch markers)
# che non fanno parte del nome reale del negozio.
_FILLER_TOKENS = {"dankt", "fil", "filiale", "filiale.", "fill."}

# Pattern che identificano descrizioni di servizio PayPal (rate, installments,
# trasferimenti, ricariche). Se dopo "PAYPAL *" troviamo uno di questi, la
# transazione è del conto PayPal stesso -> chiave "paypal".
_PAYPAL_SERVICE_PATTERNS = (
    r"rate",
    r"\binst\b",
    r"installment",
    r"paga\s+in",
    r"transfer",
    r"top\s*up",
    r"topup",
    r"guthaben",
    r"aufladung",
    r"^in\s+\d",
)


def _looks_like_paypal_service(rest: str) -> bool:
    """True se il testo residuo dopo 'paypal *' è un descrittore di servizio."""
    return any(re.search(p, rest) for p in _PAYPAL_SERVICE_PATTERNS)


def _strip_store_suffix(tokens: list[str]) -> str:
    """Rimuove i suffissi numerici/filiale mantenendo un nome significativo.

    Esempi: 'dm fil a055' -> 'dm'; 'mcdonalds 42' -> 'mcdonalds';
    'interspar dankt 8820' -> 'interspar'; 'billa dankt 0007950' -> 'billa'.

    Non rimuove MAI l'ultimo token se è l'unico presente (così codici come
    'cm103', 'p01', '1859', 'pv8628' restano intatti).
    """
    tokens = [t for t in tokens if t not in _FILLER_TOKENS]

    # Codici negozio/filiale: 0-2 lettere + 3-7 cifre (es. 'a055', '0199'),
    # oppure puramente numerici di qualsiasi lunghezza.
    store_code_re = re.compile(r"^[a-z]{0,2}\d{3,7}$")

    while len(tokens) > 1:
        last = tokens[-1]
        if last.isdigit() or store_code_re.fullmatch(last):
            tokens.pop()
        else:
            break
    return " ".join(tokens)


def normalize_merchant(desc: str) -> str:
    """Normalizza una descrizione bancaria in una chiave merchant stabile."""
    if desc is None:
        return ""
    s = str(desc).lower().strip()
    if not s:
        return ""

    # PayPal: "paypal *paga in 3 rate" -> "paypal" (servizio rate/installment);
    # altrimenti "paypal *<negozio>" -> "<negozio>" (PayPal è solo processore).
    paypal_match = re.match(r"^paypal\s*\*?\s*(.*)$", s)
    if paypal_match:
        rest = paypal_match.group(1).strip()
        if not rest or _looks_like_paypal_service(rest):
            return "paypal"
        s = rest

    # Processori di pagamento puri (SumUp / Square): rimuovi il prefisso e
    # mantieni il nome del negozio che segue.
    s = re.sub(r"^(sumup|sq)\b\s*\*?\s*", "", s)

    # Prefissi marketplace Amazon (www.amazon.xxx / amazon.xxx).
    s = re.sub(r"^(www\.)?amazon\.[a-z0-9.]+\s*", "", s)

    # Trasferimenti/SEPA: il nome della controparte è seguito da "IBAN: ...".
    # Tronca alla comparsa di "IBAN" così "Katja Stefanie Davidde IBAN: AT27..."
    # diventa "katja stefanie davidde" e matcha la voce seed (Escluso).
    s = re.split(r"\biban\b", s)[0].strip()

    # Punteggiatura/separatori -> spazi, poi collassa gli spazi multipli.
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Rimuove suffissi numerici/filiale (store/branch codes).
    s = _strip_store_suffix(s.split())

    return s[:60].strip()
