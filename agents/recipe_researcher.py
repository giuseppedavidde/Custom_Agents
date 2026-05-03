import json
import os
from typing import Dict, Any, Optional

try:
    from ollama import chat, web_fetch, web_search
except ImportError:
    chat = None
    web_fetch = None
    web_search = None

class RecipeResearcher:
    """
    Agent that autonomously browses the web using Ollama's native tool calling capabilities 
    (web_search and web_fetch) and fetches recipes according to predefined mathematical constraints.
    """
    def __init__(self, use_wsl: bool = True, model_name: str = "llama3.2", use_cli: bool = True, log_callback=None):
        self.use_wsl = use_wsl
        self.model_name = model_name
        self.use_cli = use_cli
        self.available_tools = {'web_search': web_search, 'web_fetch': web_fetch}
        
        if log_callback:
            if self.use_cli:
                log_callback(f"⚙️ Inizializzato RecipeResearcher. Using OpenClaw CLI approach (Model: {self.model_name}, WSL: {self.use_wsl})\n")
            else:
                if chat is None:
                    log_callback("❌ Errore: la libreria 'ollama' non è aggiornata o non è installata correttamente.\n")
                else:
                    log_callback(f"⚙️ Inizializzato RecipeResearcher. Using Native Ollama Python SDK with Web Search (Model: {self.model_name})\n")

    def _auto_approve_pairing(self, log_callback=None) -> None:
        """
        Esegue `openclaw devices list`, trova tutti i request ID in stato Pending
        e li approva automaticamente con `openclaw devices approve <id>`.
        L'ID cambia ad ogni nuova sessione, quindi questo step è necessario ogni volta.
        """
        import subprocess
        import re

        list_cmd = ["wsl", "bash", "-ic", "openclaw devices list"] if getattr(self, "use_wsl", False) \
                   else ["openclaw", "devices", "list"]

        try:
            result = subprocess.run(
                list_cmd,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
            )
            output = result.stdout + result.stderr

            # Cerca la sezione "Pending" e raccoglie tutti gli UUID che seguono
            # Gli UUID hanno il formato xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
            pending_section = re.split(r'Pending\s*\(\d+\)', output)
            if len(pending_section) < 2:
                if log_callback: log_callback("   ℹ️ Nessuna richiesta di pairing pendente trovata.\n")
                return

            # Prendiamo solo il testo tra "Pending" e "Paired" (o fine stringa)
            pending_text = re.split(r'Paired\s*\(\d+\)', pending_section[1])[0]

            # Estrae tutti gli UUID nella sezione Pending
            uuids = re.findall(
                r'\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b',
                pending_text, re.IGNORECASE
            )

            if not uuids:
                if log_callback: log_callback("   ℹ️ Nessun UUID pendente trovato.\n")
                return

            for request_id in uuids:
                approve_cmd = ["wsl", "bash", "-ic", f"openclaw devices approve {request_id}"] \
                              if getattr(self, "use_wsl", False) \
                              else ["openclaw", "devices", "approve", request_id]

                if log_callback: log_callback(f"   🔓 Auto-approvo pairing: {request_id}\n")
                approve_result = subprocess.run(
                    approve_cmd,
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15
                )
                approve_output = (approve_result.stdout + approve_result.stderr).strip()
                if log_callback and approve_output:
                    log_callback(f"   ↳ {approve_output}\n")

        except subprocess.TimeoutExpired:
            if log_callback: log_callback("   ⚠️ Timeout durante auto-approvazione pairing.\n")
        except Exception as e:
            if log_callback: log_callback(f"   ⚠️ Errore auto-approvazione pairing: {e}\n")

    def _execute_cli(self, prompt: str, log_callback=None) -> Optional[str]:
        """
        Esegue OpenClaw come processo in background, aspetta che il server HTTP sia pronto,
        poi invia il prompt via API OpenAI-compatible su localhost:18789 e restituisce la risposta.
        OpenClaw è una TUI/Web app e NON accetta input da stdin.
        """
        import subprocess
        import re
        import time
        import threading
        import requests

        OPENCLAW_PORT = 18789
        OPENCLAW_HOST = "127.0.0.1"
        SERVER_READY_TIMEOUT = 60   # secondi da aspettare che il server sia up
        API_TIMEOUT = 180           # secondi per la risposta AI

        if getattr(self, "use_wsl", False):
            inner_cmd = f"ollama launch openclaw --model {self.model_name} --yes"
            cmd = ["wsl", "bash", "-ic", inner_cmd]
        else:
            cmd = ["ollama", "launch", "openclaw", "--model", self.model_name, "--yes"]

        # Auto-approva il pairing prima di avviare (l'ID cambia ogni sessione)
        if log_callback: log_callback("🔗 Verifico e approvo eventuali pairing pendenti...\n")
        self._auto_approve_pairing(log_callback=log_callback)

        if log_callback: log_callback(f"> 🤖 Avvio OpenClaw in background: {' '.join(cmd)}\n")

        process = None
        token = None
        output_lines = []  # raccoglie sia stdout che stderr per trovare il token

        def _read_stream(stream):
            """Legge un stream in background e accumula le righe."""
            try:
                for line in stream:
                    output_lines.append(line)
            except Exception:
                pass

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,   # ora catturiamo stdout (il token può essere qui)
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            # Avviamo thread separate per stdout e stderr
            stdout_thread = threading.Thread(target=_read_stream, args=(process.stdout,), daemon=True)
            stderr_thread = threading.Thread(target=_read_stream, args=(process.stderr,), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            if log_callback: log_callback(f"   ⏳ Attendo che OpenClaw sia pronto su {OPENCLAW_HOST}:{OPENCLAW_PORT}...\n")

            # Poll HTTP finché il server risponde
            server_ready = False
            for _ in range(SERVER_READY_TIMEOUT * 2):  # ogni 0.5s
                time.sleep(0.5)
                try:
                    r = requests.get(f"http://{OPENCLAW_HOST}:{OPENCLAW_PORT}/", timeout=1)
                    if r.status_code < 500:
                        server_ready = True
                        break
                except requests.exceptions.ConnectionError:
                    pass
                # Controlla se il processo è già morto
                if process.poll() is not None:
                    break

            if not server_ready:
                if log_callback: log_callback(f"❌ OpenClaw non è diventato disponibile entro {SERVER_READY_TIMEOUT}s.\n")
                # Logga i messaggi stderr raccolti fin qui
                collected_stderr = "".join(stderr_lines)
                if log_callback and collected_stderr.strip():
                    log_callback(f"⚠️ Output processo:\n{collected_stderr}\n")
                return None

            # Estrai il token dall'output combinato (stdout + stderr) raccolto finora
            time.sleep(1)  # piccola attesa extra per dare tempo agli stream di popolarsi
            collected_output = "".join(output_lines)
            token_match = re.search(r'#token=([a-f0-9]+)', collected_output)
            if token_match:
                token = token_match.group(1)
                if log_callback: log_callback(f"   🔑 Token estratto: {token[:12]}...\n")
            else:
                if log_callback: log_callback(f"   ⚠️ Token non trovato nell'output, procedo senza autenticazione.\n")

            if log_callback: log_callback(f"   ✅ OpenClaw è pronto! Invio il prompt via API HTTP...\n")

            # Prepara gli headers con il token se disponibile
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }

            # Prova più endpoint in cascata (OpenClaw/Open-WebUI hanno path diversi)
            candidate_endpoints = [
                f"http://{OPENCLAW_HOST}:{OPENCLAW_PORT}/v1/chat/completions",
                f"http://{OPENCLAW_HOST}:{OPENCLAW_PORT}/api/v1/chat/completions",
                f"http://{OPENCLAW_HOST}:{OPENCLAW_PORT}/api/chat/completions",
                f"http://{OPENCLAW_HOST}:{OPENCLAW_PORT}/api/chat",
            ]

            response = None
            for api_url in candidate_endpoints:
                if log_callback: log_callback(f"   📤 Provo endpoint: {api_url}...\n")
                try:
                    r = requests.post(api_url, json=payload, headers=headers, timeout=API_TIMEOUT)
                    if r.status_code != 404:
                        response = r
                        response.raise_for_status()
                        break  # endpoint trovato!
                    else:
                        if log_callback: log_callback(f"   ↳ 404, provo il prossimo...\n")
                except requests.exceptions.HTTPError as e:
                    if log_callback: log_callback(f"   ↳ Errore HTTP {e}, provo il prossimo...\n")

            if response is None:
                if log_callback: log_callback(f"❌ Nessun endpoint API valido trovato su OpenClaw.\n")
                if log_callback: log_callback(f"   Output processo:\n{''.join(output_lines[:30])}\n")
                return None

            data = response.json()
            # Supporta sia formato OpenAI (choices[]) sia formato Ollama ({message})
            if "choices" in data:
                content = data["choices"][0].get("message", {}).get("content", "")
            elif "message" in data:
                content = data["message"].get("content", "")
            else:
                content = str(data)

            if log_callback: log_callback(f"✅ Risposta OpenClaw ricevuta ({len(content)} caratteri).\n")
            return content

        except requests.exceptions.HTTPError as e:
            if log_callback: log_callback(f"❌ Errore HTTP API OpenClaw: {e}\n")
            return None
        except requests.exceptions.Timeout:
            if log_callback: log_callback(f"❌ Timeout risposta OpenClaw API ({API_TIMEOUT}s).\n")
            return None
        except Exception as e:
            if log_callback: log_callback(f"❌ Errore d'esecuzione OpenClaw: {e}\n")
            return None
        finally:
            # Termina sempre il processo OpenClaw a fine sessione
            if process and process.poll() is None:
                if log_callback: log_callback(f"   🛑 Terminazione processo OpenClaw...\n")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    def _execute_ollama_agent(self, prompt: str, log_callback=None) -> Optional[str]:
        """
        Esegue la conversazione tool-enabled. Se use_cli è True, usa _execute_cli.
        Altrimenti usa l'SDK Python ufficiale in modalità nativa.
        """
        if self.use_cli:
            return self._execute_cli(prompt, log_callback)
            
        if chat is None:
            if log_callback: log_callback("❌ Operazione annullata: SDK Ollama mancante e use_cli=False.\n")
            return None
            
        messages = [{'role': 'user', 'content': prompt}]
        
        try:
            if log_callback: log_callback(f"> 🤖 Inizio Sessione Web Search [{self.model_name}]...\n")
            
            while True:
                response = chat(
                    model=self.model_name,
                    messages=messages,
                    tools=[web_search, web_fetch]
                )
                
                # Aggiungiamo sempre la risposta dell'assistente alla pipe del contesto
                messages.append(response.message)
                
                # Se il modello ha deciso autonomamente di usare i tools per navigare
                if response.message.tool_calls:
                    tool_names = [t.function.name for t in response.message.tool_calls]
                    if log_callback: log_callback(f"⚡ Il modello ha richiamato attivamente i tools internet: {tool_names}\n")
                    
                    for tool_call in response.message.tool_calls:
                        function_to_call = self.available_tools.get(tool_call.function.name)
                        if function_to_call:
                            # Log the arguments it's using
                            args = tool_call.function.arguments
                            if log_callback: log_callback(f"   🔎 Esecuzione {tool_call.function.name} con query: {args}\n")
                            
                            # Eseguiamo la query su internet
                            result = function_to_call(**args)
                            
                            # Riportiamo a Ollama cio che abbiamo letto (limitato per il context window)
                            messages.append({
                                'role': 'tool', 
                                'content': str(result)[:8000], 
                                'tool_name': tool_call.function.name
                            })
                            if log_callback: log_callback(f"   🌐 Ricevuti dati dal web, inseriti nel contesto AI.\n")
                        else:
                            messages.append({
                                'role': 'tool', 
                                'content': f'Tool {tool_call.function.name} not found', 
                                'tool_name': tool_call.function.name
                            })
                else:
                    # Non ci sono altre chiamate tool, il modello ha finito di estrarre e generato la risposta
                    if response.message.content:
                        if log_callback: log_callback(f"✅ Generazione del JSON finale completata!\n")
                        return response.message.content
                    break
                    
            return None
            
        except Exception as e:
            msg = f"❌ Errore critico Ollama SDK: {e}"
            print(msg)
            if log_callback: log_callback(msg + "\n")
            return None

    def search_recipe(self, macro_constraints: Dict[str, float], custom_request: str = "", log_callback=None) -> Optional[Dict[str, Any]]:
        """
        Genera il task per Ollama.
        """
        carbs = macro_constraints.get("c", 0)
        pro = macro_constraints.get("p", 0)
        fat = macro_constraints.get("f", 0)
        
        prompt = f"""
Sei un nutrizionista autonomo. Usa i tuoi tool di web search per cercare online su siti web affidabili di cucina fitness una ricetta appropriata.
Non inventare la ricetta, PRENDILA REALMENTE DA INTERNET USANDO LA RICERCA.
Requisiti generali: {custom_request if custom_request else 'Ricetta fitness sana'}
La ricetta idealmente dovrebbe poter coprire questi macros approssimativi 
(Carboidrati: {carbs}g, Proteine: {pro}g, Grassi: {fat}g). Nessun sandwich.

RESTITUISCI ESCLUSIVAMENTE RISPOSTA IN FORMATO JSON PURO E NIENT'ALTRO. Esempio formato:
{{
    "titolo": "Nome Ricetta Reale Trovata",
    "istruzioni": "Brevi istruzioni di cottura tratte dal sito",
    "nuovi_ingredienti_trovati": [
        {{"name": "Esempio", "pro": 10.0, "cho": 5.0, "fat": 2.0, "kcal": 100}}
    ]
}}
Non includere Markdown code block ```json ... ```, ma solo il json testuale puro.
"""
        raw_output = self._execute_ollama_agent(prompt, log_callback=log_callback)
        
        if not raw_output:
            return None
            
        try:
            import re
            json_match = re.search(r'(\{.*\})', raw_output, re.DOTALL)
            if json_match:
                clean_output = json_match.group(1)
            else:
                clean_output = raw_output.strip()
                if clean_output.startswith("```json"):
                    clean_output = clean_output[7:-3].strip()
                elif clean_output.startswith("```"):
                    clean_output = clean_output[3:-3].strip()
                
            recipe_data = json.loads(clean_output)
            return recipe_data
        except json.JSONDecodeError as e:
            msg = f"\n⚠️ Formato LLM finale invalido. Impossibile decodificare il JSON!\n{raw_output}"
            print(msg)
            if log_callback: log_callback(msg + "\n")
            return None

    def test_agent(self, log_callback=None) -> Optional[str]:
        """
        Esegue un task triviale per verificare i tool.
        """
        prompt = "Use your web_search tool to find out what 'Streamlit' framework is, and reply with a short 1-sentence summary based on the web results."
        return self._execute_ollama_agent(prompt, log_callback=log_callback)

if __name__ == "__main__":
    rr = RecipeResearcher()
    test_macros = {"p": 40.0, "c": 50.0, "f": 15.0}
    result = rr.search_recipe(test_macros)
    if result:
        print("\n🏆 Risultato:")
        print(json.dumps(result, indent=2))
