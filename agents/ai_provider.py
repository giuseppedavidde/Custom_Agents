"""Modulo AI Provider per la selezione dinamica del modello Gemini e Ollama."""

from typing import Optional, List, Any, Union, Iterator
import os
import time
import random
import re
import ollama
import requests
import subprocess
import glob
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


class OpenRouterWrapper:
    """Wrapper per OpenRouter OpenAI-compatible API."""

    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, provider, model_name: str, json_mode: bool = False):
        self.provider = provider
        # Fallback to a common model if none provided
        self.model_name = model_name or "anthropic/claude-3.5-sonnet"
        self.json_mode = json_mode
        if not OPENAI_AVAILABLE:
            raise ImportError("Libreria 'openai' non installata. Esegui: pip install openai")
        
        self.client = openai_lib.OpenAI(
            base_url=self.OPENROUTER_BASE_URL,
            api_key=self.provider.api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/giuseppe/antigravity",
                "X-OpenRouter-Title": "Antigravity Local Engine"
            }
        )

    def _build_messages(self, prompt: Any) -> list:
        content, images = process_multimodal_input(prompt, self.model_name)
        if images:
            content += "\n[Note: Image attachments currently simplified in OpenRouter wrapper]\n"
        return [{"role": "user", "content": content}]

    def generate_content(self, prompt: Any):
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
            raise RuntimeError(f"OpenRouter Error: {e}") from e

    def generate_stream(self, prompt: Any):
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
            yield f"❌ Errore OpenRouter Stream: {e}"


class LlamaCppWrapper:
    """Wrapper per llama.cpp server (OpenAI-compatible API)."""

    def __init__(self, model_name: str, host: str = "localhost", port: int = 8080, json_mode: bool = False):
        self.model_name = model_name
        self.host = host
        self.port = port
        self.json_mode = json_mode
        self.base_url = f"http://{host}:{port}/v1"
        if not OPENAI_AVAILABLE:
            raise ImportError("Libreria 'openai' non installata. Esegui: pip install openai")
        self.client = openai_lib.OpenAI(
            base_url=self.base_url,
            api_key="no-key",  # llama-server non richiede API key
        )

    def generate_content(self, prompt: Any):
        """Genera contenuto usando llama-server."""
        try:
            content, images = process_multimodal_input(prompt, self.model_name)

            if images:
                content += "\n[Note: Image attachments are not supported via llama.cpp server]\n"

            messages = [{"role": "user", "content": content}]
            kwargs = {
                "model": self.model_name,
                "messages": messages,
            }
            if self.json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            print(f"⏳ LlamaCpp: Invio richiesta a {self.model_name} ({self.base_url})...")
            start_t = time.time()

            response = self.client.chat.completions.create(**kwargs)

            duration = time.time() - start_t
            result_text = response.choices[0].message.content

            # Extract token usage from llama-server response
            usage = getattr(response, "usage", None)
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or 0
            tokens_per_sec = completion_tokens / duration if duration > 0 else 0

            print(
                f"✅ LlamaCpp: {len(result_text)} chars | "
                f"{completion_tokens} tokens out / {total_tokens} tot | "
                f"{tokens_per_sec:.1f} t/s | {duration:.2f}s"
            )

            class Response:
                def __init__(self, text, _completion_tokens, _total_tokens, _tps, _duration):
                    self.text = text
                    self.completion_tokens = _completion_tokens
                    self.total_tokens = _total_tokens
                    self.tokens_per_sec = _tps
                    self.duration_sec = _duration

            return Response(result_text, completion_tokens, total_tokens, tokens_per_sec, duration)

        except Exception as e:
            raise RuntimeError(f"LlamaCpp Error: {e}") from e

    def generate_stream(self, prompt: Any):
        """Genera in streaming usando llama-server."""
        try:
            content, images = process_multimodal_input(prompt, self.model_name)

            if images:
                content += "\n[Note: Image attachments are not supported via llama.cpp server]\n"

            messages = [{"role": "user", "content": content}]
            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "stream": True,
            }
            if self.json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            stream = self.client.chat.completions.create(**kwargs)

            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta is not None:
                    yield delta

        except Exception as e:
            yield f"❌ Errore LlamaCpp Stream: {e}"


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

    # Preferred model for PDF reading: moonshotai/kimi-k2-instruct
    PREFERRED_GROQ_MODEL = "moonshotai/kimi-k2-instruct"

    GROQ_MODELS = [
        "moonshotai/kimi-k2-instruct",  # Best for PDF reading
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

    LLAMACPP_HOST = "localhost"
    LLAMACPP_PORT = 8080
    LLAMACPP_SERVER_SCRIPT = os.path.expanduser(
        "~/Progetti/llama_turboquant/start_server.fish"
    )
    LLAMACPP_MODELS_DIR = os.path.expanduser(
        "~/Progetti/llama_turboquant/models"
    )

    @staticmethod
    def is_llamacpp_running() -> bool:
        """Verifica se il processo llama-server è in esecuzione."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "llama-server"],
                capture_output=True, timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_local_llamacpp_models() -> List[str]:
        """Recupera la lista dei file .gguf presenti nella cartella modelli locale."""
        if not os.path.exists(AIProvider.LLAMACPP_MODELS_DIR):
            return []
        model_files = glob.glob(os.path.join(AIProvider.LLAMACPP_MODELS_DIR, "*.gguf"))
        return sorted([os.path.basename(m) for m in model_files])

    @staticmethod
    def start_llamacpp_server(model_filename: str = "", thinking_mode: str = "") -> int:
        """
        Avvia il server LlamaCpp in background.
        Restituisce il PID del processo.
        """
        env = os.environ.copy()
        env["GGML_CUDA_ENABLE_UNIFIED_MEMORY"] = "1"
        env["HSA_OVERRIDE_GFX_VERSION"] = "11.0.3"
        if model_filename:
            env["LLAMA_MODEL_FILENAME"] = model_filename
        if thinking_mode:
            env["LLAMA_THINKING_MODE"] = thinking_mode
            
        proc = subprocess.Popen(
            ["fish", AIProvider.LLAMACPP_SERVER_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        return proc.pid

    @staticmethod
    def stop_llamacpp_server() -> None:
        """Termina il server LlamaCpp."""
        subprocess.run(["pkill", "-f", "llama-server"], timeout=5)

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
        elif self.provider_type == "openrouter":
            self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
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
            self.current_model_name = self.target_model or AIProvider.PREFERRED_GROQ_MODEL
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

        elif self.provider_type == "openrouter":
            if not OPENAI_AVAILABLE:
                raise ImportError(
                    "Libreria 'openai' non installata. Esegui: pip install openai"
                )
            # For OpenRouter, api_key holds the OpenRouter auth token
            self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
            if not self.api_key:
                print("⚠️ OPENROUTER_API_KEY mancante. Inserisci il token OpenRouter.")
            self.current_model_name = self.target_model or "anthropic/claude-3.5-sonnet"
            self.log_debug(
                f"🤖 AI Provider impostato su OpenRouter: {self.current_model_name}"
            )

        elif self.provider_type == "llamacpp":
            if not OPENAI_AVAILABLE:
                raise ImportError(
                    "Libreria 'openai' non installata. Esegui: pip install openai"
                )
            # Recupera il primo modello disponibile dal server
            models = self.get_llamacpp_models()
            self.current_model_name = self.target_model or (models[0] if models else "default")
            self.log_debug(
                f"🤖 AI Provider impostato su LlamaCpp: {self.current_model_name}"
            )

    @staticmethod
    def get_supported_providers() -> List[str]:
        """Restituisce la lista dei provider supportati.

        LlamaCpp viene incluso se lo script del server è presente su disco,
        indipendentemente dal fatto che il server sia in esecuzione.
        """
        providers = ["Gemini", "Groq", "Ollama", "Puter", "OpenRouter"]
        if os.path.isfile(AIProvider.LLAMACPP_SERVER_SCRIPT):
            providers.append("LlamaCpp")
        return providers

    @staticmethod
    def get_groq_models(api_key: Optional[str] = None) -> List[str]:
        """Recupera la lista dei modelli da Groq via API.

        Se moonshotai/kimi-k2-instruct è disponibile viene posto in prima posizione
        (miglior modello per PDF reading). Altrimenti la lista è restituita invariata.
        """
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
                sorted_models = sorted(models)
                # Prioritize preferred PDF model if available
                preferred = AIProvider.PREFERRED_GROQ_MODEL
                if preferred in sorted_models:
                    sorted_models.remove(preferred)
                    sorted_models.insert(0, preferred)
                return sorted_models
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

    @staticmethod
    def get_openrouter_models(api_key: Optional[str] = None) -> List[str]:
        """Recupera la lista dei modelli OpenRouter via API."""
        api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-pro-1.5"]
        
        url = "https://openrouter.ai/api/v1/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = [m["id"] for m in data.get("data", [])]
                # Default list on top
                defaults = ["anthropic/claude-3.7-sonnet", "openai/gpt-4o", "google/gemini-2.5-flash"]
                available_defaults = [m for m in defaults if m in models]
                others = sorted([m for m in models if m not in defaults])
                return available_defaults + others
            else:
                return ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-pro-1.5"]
        except Exception:
            return ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-pro-1.5"]

    @staticmethod
    def detect_llamacpp(host: str = None, port: int = None) -> bool:
        """Verifica se llama-server è raggiungibile."""
        host = host or AIProvider.LLAMACPP_HOST
        port = port or AIProvider.LLAMACPP_PORT
        try:
            r = requests.get(f"http://{host}:{port}/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    @staticmethod
    def get_llamacpp_models(host: str = None, port: int = None) -> List[str]:
        """Recupera i modelli caricati da llama-server /v1/models."""
        host = host or AIProvider.LLAMACPP_HOST
        port = port or AIProvider.LLAMACPP_PORT
        try:
            r = requests.get(f"http://{host}:{port}/v1/models", timeout=3)
            if r.status_code == 200:
                data = r.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            print(f"⚠️ Error fetching LlamaCpp models: {e}")
        return []

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
        elif self.provider_type == "openrouter":
            return OpenRouterWrapper(self, self.current_model_name, json_mode)
        elif self.provider_type == "llamacpp":
            return LlamaCppWrapper(
                self.current_model_name,
                host=self.LLAMACPP_HOST,
                port=self.LLAMACPP_PORT,
                json_mode=json_mode,
            )
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

    @staticmethod
    def render_streamlit_sidebar() -> Tuple[str, Optional[str]]:
        """
        Rende l'interfaccia utente (UI) per la selezione del provider e del modello AI
        nella sidebar di Streamlit. 
        
        Questa funzione è l'unico punto di verità per aggiungere nuovi provider,
        in modo che i frontend (come ibkr_trading.py) non debbano essere aggiornati.

        Ritorna:
            Tuple[str, Optional[str]]: (provider_selezionato, modello_selezionato)
        """
        import streamlit as st

        st.sidebar.title("AI Model")
        supported_providers = AIProvider.get_supported_providers()
        
        # Selezione Provider
        ai_provider = st.sidebar.selectbox(
            "Provider",
            supported_providers,
            format_func=lambda x: (
                "☁️ Gemini (Cloud)" if x.lower() == "gemini"
                else "🖥️ Ollama (Local)" if x.lower() == "ollama"
                else "⚡ Groq (LPU Cloud)" if x.lower() == "groq"
                else "🧠 Claude (Puter Free)" if x.lower() == "puter"
                else "🌐 OpenRouter (Unified API)" if x.lower() == "openrouter"
                else "🦙 LlamaCpp (TurboQuant)" if x.lower() == "llamacpp"
                else x
            ),
        )
        ai_provider = ai_provider.lower()
        ai_model_name = None

        if ai_provider == "ollama":
            ollama_models = AIProvider.get_ollama_models()
            if ollama_models:
                ai_model_name = st.sidebar.selectbox("Model", ollama_models)
            else:
                st.sidebar.warning("No Ollama models found. Is Ollama running?")
                
        elif ai_provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                api_key = st.sidebar.text_input("OpenRouter API Key", type="password")
                if api_key:
                    os.environ["OPENROUTER_API_KEY"] = api_key

            if not os.getenv("OPENROUTER_API_KEY"):
                st.sidebar.warning("🔑 OpenRouter API Key required.")
            else:
                openrouter_models = AIProvider.get_openrouter_models()
                ai_model_name = st.sidebar.selectbox("Model", openrouter_models)

        elif ai_provider == "llamacpp":
            _lcpp_script = AIProvider.LLAMACPP_SERVER_SCRIPT
            _lcpp_script_exists = os.path.isfile(_lcpp_script)
            _lcpp_running = AIProvider.is_llamacpp_running()

            if _lcpp_running:
                st.sidebar.markdown("**LlamaCpp Server:** 🟢 Running")
            else:
                st.sidebar.markdown("**LlamaCpp Server:** ⚫ Not running")

            if not _lcpp_running and _lcpp_script_exists:
                st.sidebar.markdown("**Server Settings**")
                _model_names = AIProvider.get_local_llamacpp_models()
                if _model_names:
                    st.sidebar.selectbox("LlamaCpp Model", _model_names, key="lcpp_model_sel")
                    st.sidebar.selectbox("Thinking Mode", ["1", "2"], format_func=lambda x: "ON (Reasoning)" if x == "1" else "OFF (Fast Instruct)", key="lcpp_think_sel")
                else:
                    st.sidebar.caption("⚠️ Nessun file .gguf trovato nella cartella modelli.")

            _lcpp_col1, _lcpp_col2 = st.sidebar.columns(2)
            with _lcpp_col1:
                if st.button("🚀 Start Server", key="lcpp_start", disabled=not _lcpp_script_exists or _lcpp_running):
                    try:
                        model = st.session_state.get("lcpp_model_sel", "")
                        thinking = st.session_state.get("lcpp_think_sel", "")
                        pid = AIProvider.start_llamacpp_server(model, thinking)
                        st.session_state["_lcpp_pid"] = pid
                        st.toast(f"LlamaCpp server launched (PID {pid}). Loading model...", icon="🦙")
                        import time as _time
                        _time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to launch llama-server: {e}")
            with _lcpp_col2:
                if st.button("⏹️ Stop Server", key="lcpp_stop", disabled=not _lcpp_running):
                    try:
                        AIProvider.stop_llamacpp_server()
                        st.session_state.pop("_lcpp_pid", None)
                        st.toast("LlamaCpp server stopped.", icon="⏹️")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to stop llama-server: {e}")

            if not _lcpp_script_exists:
                st.sidebar.caption(f"⚠️ Server script not found: `{_lcpp_script}`")

            if _lcpp_running and AIProvider.detect_llamacpp():
                lcpp_models = AIProvider.get_llamacpp_models()
                if lcpp_models:
                    ai_model_name = st.sidebar.selectbox("Model", lcpp_models)
                else:
                    st.sidebar.info("⏳ Server is starting, model loading...")
            else:
                if not _lcpp_running:
                    st.sidebar.info("Start the server to use LlamaCpp.")

        elif ai_provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                api_key = st.sidebar.text_input("Groq API Key", type="password")
                if api_key:
                    os.environ["GROQ_API_KEY"] = api_key

            if not os.getenv("GROQ_API_KEY"):
                st.sidebar.warning("🔑 Groq API Key required.")
            else:
                try:
                    groq_models = AIProvider.get_groq_models(api_key=os.getenv("GROQ_API_KEY"))
                except Exception as e:
                    st.sidebar.error(f"Debug Info: {e}")
                    print(f"Error fetching Groq models: {e}")
                    groq_models = []

                if not groq_models:
                    st.sidebar.error("❌ Could not fetch Groq models. Check API Key.")
                else:
                    ai_model_name = st.sidebar.selectbox("Model", groq_models)

        elif ai_provider == "puter":
            puter_key = os.getenv("PUTER_API_KEY")
            if not puter_key:
                puter_key = st.sidebar.text_input(
                    "Puter Auth Token",
                    type="password",
                    help="Get your token from puter.com → Settings. Stored as PUTER_API_KEY env var.",
                )
                if puter_key:
                    os.environ["PUTER_API_KEY"] = puter_key

            if not os.getenv("PUTER_API_KEY"):
                st.sidebar.warning("🔑 Puter Auth Token required. Get it from puter.com.")
            else:
                puter_models = AIProvider.get_puter_models()
                ai_model_name = st.sidebar.selectbox("Claude Model", puter_models)

        else:
            # Gemini
            try:
                gemini_models = AIProvider.get_gemini_models()
            except Exception as e:
                st.sidebar.error(f"Debug Info: {e}")
                print(f"Error fetching Gemini models: {e}")
                gemini_models = AIProvider.FALLBACK_ORDER

            if not gemini_models:
                st.sidebar.error("❌ Could not fetch Gemini models.")
            else:
                ai_model_name = st.sidebar.selectbox("Model", gemini_models)

        return ai_provider, ai_model_name

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
