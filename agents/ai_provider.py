"""Modulo AI Provider per la selezione dinamica del modello Gemini e Ollama."""

from typing import Optional, List, Any, Union, Iterator
import os
import time
import random
import re
import ollama
import requests
from bs4 import BeautifulSoup

from google import genai
from google.genai import types
from google.api_core.exceptions import (
    ResourceExhausted,
    ServiceUnavailable,
    NotFound,
    InvalidArgument,
    InternalServerError,
)

# Tentativo di importazione sicura per Ollama e PyMuPDF (fitz)
try:
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    import io

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None

try:
    import groq

    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    import openai as openai_lib

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def process_multimodal_input(
    prompt: Any, model_name: str = "Modello AI"
) -> tuple[str, list]:
    """
    Estrae testo e immagini dal prompt multimodale.
    Converte PDF in testo usando PyMuPDF per maggiore robustezza.
    """
    final_text_parts = []
    images = []

    print(f"🤖 Pre-processing: Analizzando input per {model_name}...")

    if isinstance(prompt, list):
        for i, part in enumerate(prompt):
            if isinstance(part, str):
                final_text_parts.append(part)
            elif isinstance(part, dict) and "mime_type" in part and "data" in part:
                mime = part["mime_type"]
                data = part["data"]
                size_kb = len(data) / 1024

                print(f"   -> Part {i}: Rilevato {mime} ({size_kb:.1f} KB)")

                if mime == "application/pdf":
                    # PDF Text Extraction Handling with PyMuPDF
                    if PYMUPDF_AVAILABLE:
                        try:
                            print("      -> Avvio estrazione PDF con PyMuPDF...")
                            doc = fitz.open(stream=data, filetype="pdf")
                            text_content = []
                            for page_num, page in enumerate(doc):
                                page_text = page.get_text()
                                if page_text.strip():
                                    text_content.append(page_text)
                                print(
                                    f"         Pagina {page_num+1}: {len(page_text)} caratteri estratti."
                                )

                            extracted = "\n".join(text_content)
                            if extracted.strip():
                                final_text_parts.append(
                                    f"\n--- INIZIO CONTENUTO PDF ---\n{extracted}\n--- FINE CONTENUTO PDF ---\n"
                                )
                                print("      ✅ Estrazione completata con successo.")
                            else:
                                print(
                                    "      ⚠️ WARNING: Il PDF sembra vuoto o contiene solo immagini (no OCR)."
                                )
                        except Exception as e:
                            print(f"      ❌ Errore critico lettura PDF: {e}")
                            final_text_parts.append(
                                f"\n[ERRORE durante l'estrazione del PDF: {e}]\n"
                            )
                    else:
                        print(
                            "      ❌ PyMuPDF non installato! Impossibile leggere PDF."
                        )
                        final_text_parts.append(
                            "\n[AVVISO: Impossibile leggere il PDF fornito perché la libreria PyMuPDF (fitz) non è installata. Esegui 'pip install pymupdf'.]\n"
                        )
                elif mime.startswith("image/"):
                    images.append(data)
                    print("      -> Immagine aggiunta al payload.")
                else:
                    print(f"      ⚠️ MIME type {mime} non supportato, ignorato.")
    else:
        final_text_parts.append(str(prompt))

    full_text = "\n".join(final_text_parts)
    print(f"📝 Prompt finale: {len(full_text)} caratteri, {len(images)} immagini.")
    return full_text, images


class GroqWrapper:
    """Wrapper per Groq (LPU Inference Engine)."""

    def __init__(self, provider, model_name: str, json_mode: bool = False):
        self.provider = provider
        self.model_name = model_name or "llama-3.3-70b-versatile"
        self.json_mode = json_mode
        self.client = groq.Groq(api_key=self.provider.api_key)

    def generate_content(self, prompt: Any):
        """Genera contenuto usando Groq."""
        try:
            content, images = process_multimodal_input(prompt, self.model_name)

            if images:
                content += "\n[Image attached - Groq Vision not yet fully implemented in this wrapper]\n"

            messages = [{"role": "user", "content": content}]

            response = self.client.chat.completions.create(
                messages=messages,
                model=self.model_name,
                response_format={"type": "json_object"} if self.json_mode else None,
            )

            # Simulate response object with .text attribute
            class Response:
                def __init__(self, text):
                    self.text = text

            return Response(response.choices[0].message.content)

        except Exception as e:
            raise RuntimeError(f"Groq Error: {e}")

    def generate_stream(self, prompt: Any):
        """Genera in streaming usando Groq."""
        try:
            content, images = process_multimodal_input(prompt, self.model_name)

            if images:
                content += "\n[Image attached - Groq Vision not yet fully implemented in this wrapper]\n"

            messages = [{"role": "user", "content": content}]

            stream = self.client.chat.completions.create(
                messages=messages,
                model=self.model_name,
                response_format={"type": "json_object"} if self.json_mode else None,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"❌ Errore Groq Stream: {e}"


class OllamaWrapper:
    """Wrapper per chiamate a modelli locali via Ollama."""

    def __init__(self, model_name: str, json_mode: bool = False):
        self.model_name = model_name
        self.json_mode = json_mode

    def generate_content(self, prompt: Any):
        """Esegue la chiamata a Ollama."""
        try:
            prompt_text, images = process_multimodal_input(prompt, self.model_name)

            # Opzioni per forzare l'uso della GPU e Context Size adeguato
            options = {
                "num_gpu": 999,
                "num_ctx": 4096,  # Ridotto per stabilità su GPU integrate
                "temperature": 0.0,  # Bassa temperatura per estrazione dati
            }
            format_param = "json" if self.json_mode else None

            # Parametri chiamata
            kwargs = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt_text}],
                "format": format_param,
                "options": options,
                "stream": True,  # Usiamo stream interna per debug
            }

            if images:
                # Aggiungi immagini al messaggio utente
                kwargs["messages"][0]["images"] = images

            print(
                f"⏳ Ollama: Invio richiesta a {self.model_name} (Ctx: 4096, Temp: 0)..."
            )
            start_t = time.time()

            full_response = ""
            stream = ollama.chat(**kwargs)

            print("   Receiving: ", end="", flush=True)
            for chunk in stream:
                part = chunk.get("message", {}).get("content", "")
                full_response += part
                print(".", end="", flush=True)  # Feedback visivo
            print(" Done.")

            duration = time.time() - start_t
            print(
                f"✅ Ollama: Risposta ricevuta in {duration:.2f}s. Lunghezza: {len(full_response)} chars."
            )

            class Response:
                """Response wrapper per uniformità."""

                text = full_response

            return Response()

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"❌ Errore Ollama ({self.model_name}): {e}")
            raise e

    def generate_stream(self, prompt: Any):
        """Esegue la chiamata a Ollama in streaming."""
        try:
            prompt_text, images = process_multimodal_input(prompt, self.model_name)
            options = {"num_gpu": 999}

            kwargs = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt_text}],
                "stream": True,
                "options": options,
            }

            if images:
                kwargs["messages"][0]["images"] = images

            stream = ollama.chat(**kwargs)

            for chunk in stream:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content

        except Exception as e:
            yield f"❌ Errore Ollama Stream: {e}"


class GeminiWrapper:
    """Wrapper per Google Gemini con gestione retry e backoff (Google GenAI SDK v1)."""

    def __init__(self, provider, json_mode: bool):
        self.provider = provider
        self.json_mode = json_mode
        self.client = genai.Client(api_key=self.provider.api_key)

    def _prepare_contents(self, prompt: Any) -> list:
        """Prepara il contenuto per la nuova API."""
        contents = []
        if isinstance(prompt, str):
            contents.append(prompt)
        elif isinstance(prompt, list):
            for part in prompt:
                if isinstance(part, str):
                    contents.append(part)
                elif isinstance(part, dict) and "mime_type" in part and "data" in part:
                    # Handle raw bytes input (custom standard used in this project)
                    contents.append(
                        types.Part.from_bytes(
                            data=part["data"], mime_type=part["mime_type"]
                        )
                    )
                else:
                    # Fallback string
                    contents.append(str(part))
        return contents

    def generate_content(self, prompt):
        """Genera contenuto con Exponential Backoff."""
        max_retries = 5
        base_delay = 2
        last_error = None

        # Config
        config = types.GenerateContentConfig(
            response_mime_type="application/json" if self.json_mode else "text/plain"
        )

        contents = self._prepare_contents(prompt)

        for attempt in range(max_retries):
            try:
                start_time = time.time()

                response = self.client.models.generate_content(
                    model=self.provider.current_model_name,
                    contents=contents,
                    config=config,
                )

                # Logging Token Usage e Modello
                try:
                    usage = response.usage_metadata
                    input_tokens = usage.prompt_token_count
                    output_tokens = usage.candidates_token_count
                    total_tokens = usage.total_token_count
                    model_used = self.provider.current_model_name

                    self.provider.log_debug(
                        f"🤖 GENAI CALL | Model: {model_used} | Tokens: {input_tokens} in + {output_tokens} out = {total_tokens} tot | Time: {time.time()-start_time:.2f}s"
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    self.provider.log_debug(
                        f"🤖 GENAI CALL | Model: {self.provider.current_model_name} | (Token info non avail)"
                    )

                return response
            except ResourceExhausted as e:
                last_error = e
                wait = (base_delay * (2**attempt)) + random.uniform(0, 1)
                self.provider.log_debug(f"⚠️ Quota 429. Attendo {wait:.1f}s...")
                time.sleep(wait)
                if attempt >= 2 and self.provider.downgrade_model():
                    pass  # Retry with new model
            except (ServiceUnavailable, InternalServerError) as e:
                last_error = e
                time.sleep(5)
            except (NotFound, InvalidArgument) as e:
                last_error = e
                self.provider.log_debug(f"❌ Errore Modello {e}. Switching...")
                if self.provider.downgrade_model():
                    pass
                else:
                    break
            except Exception as e:  # pylint: disable=broad-exception-caught
                last_error = e
                self.provider.log_debug(f"❌ Errore: {e}")
                break

        raise RuntimeError(
            f"Impossibile generare contenuto Gemini. Last Error: {last_error}"
        )

    def generate_stream(self, prompt):
        """Genera contenuto in streaming."""
        try:
            contents = self._prepare_contents(prompt)
            response = self.client.models.generate_content_stream(
                model=self.provider.current_model_name, contents=contents
            )
            for chunk in response:
                yield chunk.text
        except Exception as e:
            yield f"❌ Errore Gemini Stream: {e}"


class PuterWrapper:
    """Wrapper per Claude via Puter.com OpenAI-compatible API (gratuito, senza Anthropic key)."""

    PUTER_BASE_URL = "https://api.puter.com/puterai/openai/v1/"

    def __init__(self, provider, model_name: str, json_mode: bool = False):
        self.provider = provider
        self.model_name = model_name or "claude-sonnet-4-6"
        self.json_mode = json_mode
        if not OPENAI_AVAILABLE:
            raise ImportError("Libreria 'openai' non installata. Esegui: pip install openai")
        self.client = openai_lib.OpenAI(
            base_url=self.PUTER_BASE_URL,
            api_key=self.provider.api_key or "dummy",  # Puter accepts any non-empty token
        )

    def _build_messages(self, prompt: Any) -> list:
        """Converte il prompt (stringa o multimodale) in messaggi OpenAI."""
        content, images = process_multimodal_input(prompt, self.model_name)
        if images:
            content += "\n[Note: Image attachments are not supported via Puter API wrapper]\n"
        return [{"role": "user", "content": content}]

    def generate_content(self, prompt: Any):
        """Genera contenuto usando Puter/Claude (sincrono)."""
        try:
            messages = self._build_messages(prompt)
            kwargs = {
                "model": self.model_name,
                "messages": messages,
            }
            if self.json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)

            class Response:
                def __init__(self, text):
                    self.text = text

            return Response(response.choices[0].message.content)
        except Exception as e:
            raise RuntimeError(f"Puter/Claude Error: {e}") from e

    def generate_stream(self, prompt: Any):
        """Genera in streaming usando Puter/Claude."""
        try:
            messages = self._build_messages(prompt)
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta is not None:
                    yield delta
        except Exception as e:
            yield f"❌ Errore Puter/Claude Stream: {e}"


class AIProvider:
    """Factory per modelli AI (Cloud/Local) con Caching."""

    DOCS_URL = "https://ai.google.dev/gemini-api/docs/models.md.txt?hl=it"
    # Fallback solidi per Gemini: Rimosso 2.0-flash per instabilità (429 errors)
    FALLBACK_ORDER = [
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
    ]

    GROQ_MODELS = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
        "gemma-7b-it",
    ]

    PUTER_MODELS = [
        "claude-3-7-sonnet",
        "claude-3-5-sonnet",
        "claude-3-haiku",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "claude-haiku-4-5",
        "claude-sonnet-4-5",
    ]

    PUTER_BASE_URL = "https://api.puter.com/puterai/openai/v1/"

    _cached_chain: Optional[List[str]] = None
    _last_scrape_time: float = 0

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider_type: str = "gemini",
        model_name: Optional[str] = None,
    ):
        """
        Inizializza il provider.
        IMPORTANTE: Configura immediatamente la catena o il modello in base al provider_type.
        """
        self.provider_type = provider_type.lower()
        self.target_model = model_name

        # Gestione API Key: Priorità a quella passata, poi Env (specifico per provider)
        if self.provider_type == "groq":
            self.api_key = api_key or os.getenv("GROQ_API_KEY")
        elif self.provider_type == "puter":
            self.api_key = api_key or os.getenv("PUTER_API_KEY")
        else:
            self.api_key = api_key or os.getenv("GOOGLE_API_KEY")

        self.debug_mode = os.getenv("AI_DEBUG", "true").lower() == "true"

        # Variabili di stato
        self.current_model_index = 0
        self.current_model_name = ""
        self.available_models_chain: List[str] = []

        # --- LOGICA DI INIZIALIZZAZIONE DEL PROVIDER ---
        if self.provider_type == "gemini":
            if not self.api_key:
                # Non raisiamo errore subito per non bloccare UI se manca key
                print("⚠️ API Key mancante per Gemini. Impossibile inizializzare.")
                return

            # genai.configure NOT needed for Client
            self._init_gemini_chain()

        elif self.provider_type == "ollama":
            if not OLLAMA_AVAILABLE:
                raise ImportError(
                    "Libreria 'ollama' non installata. Esegui: pip install ollama"
                )
            # Per Ollama non c'è una catena complessa, usiamo il modello target
            self.current_model_name = self.target_model or "llama3"
            self.log_debug(
                f"🤖 AI Provider impostato su Ollama: {self.current_model_name}"
            )

        elif self.provider_type == "groq":
            if not GROQ_AVAILABLE:
                raise ImportError(
                    "Libreria 'groq' non installata. Esegui: pip install groq"
                )
            if not self.api_key:
                print("⚠️ API Key mancante per Groq.")
                # Non raisiamo qui per permettere alla UI di chiedere la key
            self.current_model_name = self.target_model or "llama-3.3-70b-versatile"
            self.log_debug(
                f"🤖 AI Provider impostato su Groq: {self.current_model_name}"
            )

        elif self.provider_type == "puter":
            if not OPENAI_AVAILABLE:
                raise ImportError(
                    "Libreria 'openai' non installata. Esegui: pip install openai"
                )
            # For Puter, api_key holds the Puter auth token
            self.api_key = api_key or os.getenv("PUTER_API_KEY")
            if not self.api_key:
                print("⚠️ PUTER_API_KEY mancante. Inserisci il token Puter.")
            self.current_model_name = self.target_model or "claude-sonnet-4-6"
            self.log_debug(
                f"🤖 AI Provider impostato su Puter/Claude: {self.current_model_name}"
            )

    @staticmethod
    def get_supported_providers() -> List[str]:
        """Restituisce la lista dei provider supportati."""
        return ["Gemini", "Groq", "Ollama", "Puter"]

    @staticmethod
    def get_groq_models(api_key: Optional[str] = None) -> List[str]:
        """Recupera la lista dei modelli da Groq via API."""
        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            return AIProvider.GROQ_MODELS or []

        url = "https://api.groq.com/openai/v1/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Extract model IDs
                models = [m["id"] for m in data.get("data", [])]
                # Filter/Sort if needed (e.g., prioritize llama-3)
                return sorted(models)
            else:
                print(f"⚠️ Groq API Error {response.status_code}: {response.text}")
                return AIProvider.GROQ_MODELS
        except Exception as e:
            print(f"⚠️ Error fetching Groq models: {e}")
            return AIProvider.GROQ_MODELS

    @staticmethod
    def get_gemini_models(api_key: Optional[str] = None) -> List[str]:
        """Recupera la lista dei modelli Gemini disponibili (da cache o fallback)."""
        if AIProvider._cached_chain and (
            time.time() - AIProvider._last_scrape_time < 3600
        ):
            return AIProvider._cached_chain

        try:
            temp_provider = AIProvider(api_key=api_key, provider_type="gemini")
            if temp_provider.available_models_chain:
                return temp_provider.available_models_chain
        except Exception:
            pass

        return AIProvider.FALLBACK_ORDER

    @staticmethod
    def get_ollama_models() -> List[str]:
        """Recupera la lista dei modelli locali installati su Ollama."""
        if not OLLAMA_AVAILABLE:
            return []
        try:
            # ollama.list() ritorna un dict con 'models'
            models_info = ollama.list()  # pyright: ignore[reportUnboundVariable]
            return [
                m.get("model") or m.get("name") for m in models_info.get("models", [])
            ]
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"⚠️ Errore listing Ollama: {e}")
            return []

    @staticmethod
    def get_puter_models() -> List[str]:
        """Restituisce la lista dei modelli AI (Claude/Gemini) disponibili via Puter."""
        return list(AIProvider.PUTER_MODELS)

    def log_debug(self, message: str):
        """Log di debug se abilitato."""
        if self.debug_mode:
            print(message)

    def get_model(self, json_mode: bool = False) -> Any:
        """Restituisce l'istanza del modello AI richiesto."""
        if self.provider_type == "ollama":
            return OllamaWrapper(self.current_model_name, json_mode)
        elif self.provider_type == "groq":
            return GroqWrapper(self, self.current_model_name, json_mode)
        elif self.provider_type == "puter":
            return PuterWrapper(self, self.current_model_name, json_mode)
        return GeminiWrapper(self, json_mode)

    def _init_gemini_chain(self):
        """Inizializza la catena Gemini con priorità al modello richiesto."""
        # Se l'utente ha chiesto un modello specifico, lo mettiamo in cima
        if self.target_model:
            self.available_models_chain = [self.target_model] + self.FALLBACK_ORDER
        # Altrimenti usiamo la cache se valida
        elif AIProvider._cached_chain and (
            time.time() - AIProvider._last_scrape_time < 3600
        ):
            self.available_models_chain = AIProvider._cached_chain
        # Altrimenti scraping
        else:
            scraped_models = self._build_gemini_chain()
            # Uniamo i fallback (che includono i preview) con quelli trovati dallo scraping, rimuovendo duplicati e preservando l'ordine
            self.available_models_chain = list(
                dict.fromkeys(self.FALLBACK_ORDER + scraped_models)
            )

            if self.available_models_chain:
                AIProvider._cached_chain = self.available_models_chain
                AIProvider._last_scrape_time = time.time()

        # Fallback finale se tutto fallisce
        if not self.available_models_chain:
            self.available_models_chain = self.FALLBACK_ORDER

        self.current_model_index = 0
        self.current_model_name = self.available_models_chain[0]
        self.log_debug(
            f"🤖 AI Provider Gemini pronto. Modello: {self.current_model_name}"
        )

    def downgrade_model(self) -> bool:
        """Passa al modello successivo nella catena di fallback."""
        if self.current_model_index + 1 < len(self.available_models_chain):
            self.current_model_index += 1
            self.current_model_name = self.available_models_chain[
                self.current_model_index
            ]
            return True
        return False

    def _build_gemini_chain(self) -> List[str]:
        """Costruisce lista modelli via scraping."""
        try:
            response = requests.get(self.DOCS_URL, timeout=4)
            if response.status_code != 200:
                response = requests.get(self.DOCS_URL.replace(".md.txt", ""), timeout=4)
                if response.status_code != 200:
                    return []

            text = response.text
            # Try to catch model names from markdown links (e.g. models/(gemini-3.1-pro-preview))
            candidates = set(re.findall(r"models/(gemini-[a-zA-Z0-9\-\.]+)", text))

            # Fallback for plain text or HTML if no models found
            if not candidates:
                soup = BeautifulSoup(text, "html.parser")
                text = soup.get_text()
                candidates = set(re.findall(r"(gemini-[a-zA-Z0-9\-\.]+)", text))

            # Strip trailing periods from sentence endings
            candidates = {m.rstrip(".") for m in candidates}
            valid = [
                m
                for m in candidates
                if "vision" not in m
                and "audio" not in m
                and "tts" not in m
                and "image" not in m
            ]
            # Prioritizza quelli con 'flash' o 'pro'
            return sorted(valid, reverse=True)
        except Exception:  # pylint: disable=broad-exception-caught
            return []
