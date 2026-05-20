"""Modulo OpencodeAgent per interagire con opencode via subprocess."""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterator, Optional

from pydantic import BaseModel, Field

from .knowledge_loader import load_all_knowledge as _load_all_wiki


class OpencodeConfig(BaseModel):
    """Configurazione per OpencodeAgent."""

    model: Optional[str] = None
    timeout: int = Field(default=300, ge=30, le=3600)


class OpencodeResult(BaseModel):
    """Risultato di una chiamata a opencode."""

    success: bool
    text: str
    session_id: Optional[str] = None
    tokens_used: Optional[int] = None
    error: Optional[str] = None



def load_all_knowledge() -> dict[str, str]:
    """Load all knowledge bases from the LLM_Wiki/Trading_Wiki."""
    return _load_all_wiki()


_MODEL_CACHE: list[str] | None = None
_MODEL_CACHE_TIME: float = 0


def is_local_server_running(host: str = "127.0.0.1", port: int = 8080) -> bool:
    """Verifica se la porta del server locale è aperta."""
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except Exception:
        return False


def _fetch_models() -> list[str]:
    """Fetch available models via `opencode models`."""
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            models = [m.strip() for m in result.stdout.splitlines() if m.strip()]
            if models:
                return sorted(models)
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return ["opencode/deepseek-v4-flash-free"]


def get_models(*, force: bool = False) -> list[str]:
    """Cached model list, refreshed every 60s (or immediately if force=True)."""
    global _MODEL_CACHE, _MODEL_CACHE_TIME  # pylint: disable=global-statement
    now = time.monotonic()
    if force or _MODEL_CACHE is None or now - _MODEL_CACHE_TIME > 60:
        _MODEL_CACHE = _fetch_models()
        _MODEL_CACHE_TIME = now
    return list(_MODEL_CACHE)


class OpencodeAgent:  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    """Agente per interagire con opencode via subprocess."""

    def __init__(self, config: OpencodeConfig) -> None:
        self.config = config
        self.knowledge = load_all_knowledge()

    def _run(self, prompt: str) -> Iterator[str]:
        """Run opencode run --format json with the given prompt.

        For long prompts (>10k chars), writes to a temp file and uses
        shell redirection to avoid OS argument length limits.
        """
        model = self.config.model
        default_model = None
        opencode_json_path = os.path.expanduser("~/.config/opencode/opencode.json")
        if os.path.isfile(opencode_json_path):
            try:
                with open(opencode_json_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    default_model = config_data.get("model")
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        effective_model = model or default_model
        is_local = False
        if effective_model:
            is_local = "local" in effective_model.lower()
        else:
            is_local = True

        if is_local:
            if not is_local_server_running():
                fallback_model = "opencode/deepseek-v4-flash-free"
                if "streamlit" in sys.modules:
                    try:
                        import streamlit as st  # pylint: disable=import-outside-toplevel
                        st.sidebar.warning(
                            f"Server locale offline. Ripiego su {fallback_model}"
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass
                else:
                    print(
                        f"Server locale offline. Ripiego su {fallback_model}",
                        file=sys.stderr,
                    )
                model = fallback_model

        # For long prompts, write to temp file to avoid argument length limits
        temp_path = None
        use_shell = len(prompt) > 10000

        if use_shell:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                temp_path = f.name
            cmd = f"opencode run --format json < '{temp_path}'"
            if model:
                cmd += f" --model {model}"
        else:
            cmd = ["opencode", "run", "--format", "json", prompt]
            if model:
                cmd.extend(["--model", model])

        try:
            if use_shell:
                proc = subprocess.Popen(  # pylint: disable=consider-using-with
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            else:
                proc = subprocess.Popen(  # pylint: disable=consider-using-with
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
        except FileNotFoundError:
            yield "\n**Errore: opencode non trovato.**\n"
            return

        stdout_queue = queue.Queue()
        def read_stdout(stream, q):
            try:
                for line in iter(stream.readline, ''):
                    q.put(line)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            finally:
                stream.close()

        stdout_thread = threading.Thread(
            target=read_stdout, args=(proc.stdout, stdout_queue)
        )
        stdout_thread.daemon = True
        stdout_thread.start()

        stderr_queue = queue.Queue()
        def read_stderr(stream, q):
            try:
                for line in iter(stream.readline, ''):
                    q.put(line)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            finally:
                stream.close()

        stderr_thread = threading.Thread(
            target=read_stderr, args=(proc.stderr, stderr_queue)
        )
        stderr_thread.daemon = True
        stderr_thread.start()

        start_time = time.time()
        timeout = self.config.timeout

        try:
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    proc.kill()
                    yield f"\n**Errore: Timeout di esecuzione superato ({timeout}s).**\n"
                    break

                try:
                    raw_line = stdout_queue.get(timeout=0.1)
                except queue.Empty:
                    if proc.poll() is not None:
                        break
                    continue

                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "text":
                    text = event.get("part", {}).get("text", "")
                    if text:
                        yield text
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        # Read accumulated stderr lines
        stderr_lines = []
        while not stderr_queue.empty():
            try:
                stderr_lines.append(stderr_queue.get_nowait())
            except queue.Empty:
                break

        stderr_msg = "".join(stderr_lines).strip()

        if proc.returncode != 0 and proc.returncode not in (-9, -15):
            msg = stderr_msg[:500] if stderr_msg else ""
            if msg:
                yield f"\n**Errore subprocess (exit {proc.returncode}): {msg}**\n"
            else:
                yield f"\n**Errore subprocess (exit {proc.returncode})**\n"

        # Cleanup temp file
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def create_session(self) -> str:
        """Return a placeholder session ID (opencode run is stateless)."""
        return f"session-{int(time.time())}"

    def stream_prompt(self, prompt: str) -> Iterator[str]:
        """Send a one-shot prompt and stream response via subprocess."""
        yield from self._run(prompt)

    def stream_chat(self, message: str, session_id: str) -> Iterator[str]:  # pylint: disable=unused-argument
        """Send a message (session_id is ignored — subprocess is stateless)."""
        yield from self._run(message)

    def run_prompt(self, prompt: str) -> OpencodeResult:
        """Run a prompt and return the complete result (blocking)."""
        chunks: list[str] = []
        try:
            for chunk in self.stream_prompt(prompt):
                chunks.append(chunk)
        except Exception as e:  # pylint: disable=broad-exception-caught
            return OpencodeResult(
                success=False, text="", error=f"Errore durante l'esecuzione: {e}"
            )
        text = "".join(chunks)
        if not text:
            return OpencodeResult(
                success=False, text="", error="Nessun output ricevuto da opencode"
            )
        return OpencodeResult(success=True, text=text)

    def run_technical_analysis(
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
        """Stream technical analysis using opencode with VPA knowledge."""
        prompt = self._build_technical_prompt(
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
            knowledge=self.knowledge.get("vpa", ""),
        )
        yield from self.stream_prompt(prompt)

    @staticmethod
    def _build_technical_prompt(
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
        knowledge: str = "",
    ) -> str:
        """Build a technical analysis prompt optionally including knowledge."""
        change_str = f" ({change:+.2f}%)" if change is not None else ""
        patterns_str = ", ".join(patterns) if patterns else "Nessuno"
        adx_str = f"{adx:.1f}" if adx is not None else "N/A"
        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
        sk = f"{stoch_k:.1f}/{stoch_d:.1f}" if stoch_k is not None else "N/A"
        wr = f"{williams_r:.1f}" if williams_r is not None else "N/A"
        macd_str = (
            f"MACD={macd:.4f} Signal={macd_signal:.4f} Hist={macd_histogram:.4f}"
            if macd is not None
            else "N/A"
        )
        bw = f"{bb_width:.2f}" if bb_width is not None else "N/A"
        vr = f"{volume_ratio:.2f}x" if volume_ratio is not None else "N/A"

        prompt_parts = []
        if knowledge:
            prompt_parts.append(
                f"CONOSCENZA TEORICA (VPA & Price Action - Coulling/Volman):\n{knowledge}\n"
            )

        prompt_parts.append(f"""
DATI DI MERCATO:
- Ticker: {ticker}
- Prezzo: {price}{change_str}
- Trend: {trend} (ADX: {adx_str})
- RSI(14): {rsi_str}
- Stocastico: {sk}
- Williams %R: {wr}
- MACD: {macd_str}
- Bollinger: posizione={bb_position}, larghezza={bw}
- Volume: {vr} ({volume_signal})
- Pattern: {patterns_str}
""")

        if holders_text:
            prompt_parts.append(f"\nAZIONARIATO ISTITUZIONALE:\n{holders_text}\n")
        if financials_text:
            prompt_parts.append(f"\nDATI FINANZIARI:\n{financials_text}\n")

        prompt_parts.append("""
OBIETTIVO:
Analizza la situazione di mercato. Produci un'analisi strutturata con:
1. Valutazione del trend e della sua forza
2. Livelli chiave di supporto e resistenza
3. Segnale operativo (LONG/SHORT/WAIT) con confidence 0-100
4. Eventuali pattern o setup riconoscibili
""")

        return "\n".join(prompt_parts)

    @staticmethod
    def _parse_signal_from_text(text: str) -> dict[str, Any]:
        """Extract signal and confidence from response text."""
        sig = "WAIT"
        confidence = 0.0
        text_upper = text.upper()

        if '"SIGNAL"' in text_upper or '"signal"' in text:
            try:
                data = json.loads(text)
                sig = data.get("signal", "WAIT").upper()
                confidence = float(data.get("confidence", 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        if sig == "WAIT":
            if "LONG" in text_upper and "SHORT" not in text_upper:
                sig = "LONG"
            elif "SHORT" in text_upper and "LONG" not in text_upper:
                sig = "SHORT"

        return {"signal": sig, "confidence": confidence}

    def get_available_models(self) -> list[str]:
        """Return list of available models."""
        return get_models()

    @staticmethod
    def render_streamlit_sidebar() -> Optional[OpencodeConfig]:
        """Render configuration UI in Streamlit sidebar."""
        try:
            import streamlit as st  # pylint: disable=import-outside-toplevel
        except ImportError:
            return None

        enabled = st.sidebar.checkbox(
            "Opencode Agent",
            value=False,
            help="Usa opencode per analisi AI (server mode)",
        )
        if not enabled:
            return None

        st.sidebar.success("Opencode: Pronto")

        agent = OpencodeAgent(OpencodeConfig())
        cache_key = "opencode_models_cache"
        sel_key = "opencode_model_sel_val"

        if cache_key not in st.session_state:
            with st.sidebar.status("Caricamento modelli..."):
                st.session_state[cache_key] = agent.get_available_models()

        models = st.session_state[cache_key]
        model_options = ["  (nessuno - default)"] + models

        current_idx = 0
        saved_model = st.session_state.get(sel_key, "")
        if saved_model and saved_model in models:
            current_idx = models.index(saved_model) + 1

        col_model, col_refresh = st.sidebar.columns([4, 1])
        with col_model:
            selected = st.selectbox(
                "Modello",
                options=model_options,
                index=current_idx,
                key="opencode_model_sel",
                help="Scegli il modello AI. '(nessuno)' = default configurato.",
                format_func=lambda x: x.replace("opencode/", "").replace("-free", " *"),
            )
        with col_refresh:
            st.markdown("")
            if st.button("🔄", key="opencode_refresh_btn", help="Aggiorna lista modelli"):
                with st.sidebar.status("Caricamento modelli..."):
                    st.session_state[cache_key] = get_models(force=True)
                st.session_state.pop(sel_key, None)
                st.rerun()

        model = selected.replace("  (nessuno - default)", "").strip() or None
        st.session_state[sel_key] = model or ""

        timeout = st.sidebar.slider(
            "Timeout (s)", 30, 600, 300, 30,
            help="Tempo massimo di attesa per la risposta",
        )

        return OpencodeConfig(
            model=model,
            timeout=timeout,
        )
