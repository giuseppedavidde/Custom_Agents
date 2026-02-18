# Custom Agents 🕵️‍♂️

Centralized Python package containing shared logic, AI providers, and cloud managers for the personal finance ecosystem (`Budget_App`, `Crypto_Tracker`, `Portfolio_Reader`).

## 📦 Installation

This package is designed to be installed directly from GitHub via `pip`.

### For Usage in `requirements.txt` (Streamlit Cloud)
Add the following line to your `requirements.txt` file:

```text
git+https://github.com/giuseppedavidde/Custom_Agents.git#egg=custom_agents
```

### For Local Development
You can install it in editable mode if you want to modify the agents while working on another project:

```bash
pip install -e /path/to/Custom_Agents
# OR if you just want to use it
pip install git+https://github.com/giuseppedavidde/Custom_Agents.git
```

---

## 🛠 Modules

### 1. `AIProvider` (`agents.ai_provider`)
Unified interface for interacting with LLMs (**Google Gemini** and **Ollama**).
*   **Features**:
    *   Automatic fallback between Gemini models (Pro, Flash, etc.).
    *   Local inference support via Ollama.
    *   Multimodal support (Text, Images, PDF parsing).
    *   Caching system to avoid scraping model lists too often.

**Usage:**
```python
from agents.ai_provider import AIProvider

# Gemini (Cloud)
ai = AIProvider(api_key="...", provider_type="gemini", model_name="gemini-1.5-flash")
response = ai.get_model().generate_content("Hello AI!")

# Ollama (Local)
ai = AIProvider(provider_type="ollama", model_name="llama3")
```

### 2. `CloudManager` (`agents.cloud_manager`)
Manages synchronization with a central GitHub repository for data persistence.
*   **Features**:
    *   Download/Upload files (CSV, etc.) to a private repo.
    *   List CSV files in a repository.
    *   Handles file creation vs updates automatically.

**Usage:**
```python
from agents.cloud_manager import CloudManager

cm = CloudManager(github_token="ghp_...")
cm.github_upload("user/repo", "remote_file.csv", "local_file.csv")
```

### 3. `render_cloud_sync_ui` (`agents.cloud_ui`)
Pre-built Streamlit UI component for cloud synchronization.
*   **Features**:
    *   Renders buttons for **Pull** (Download) and **Push** (Upload).
    *   Visual feedback (Toast messages, Error alerts).
    *   Configurable for Sidebar or Main page.

**Usage:**
```python
import streamlit as st
from agents.cloud_ui import render_cloud_sync_ui

render_cloud_sync_ui("local_database.csv", is_sidebar=True)
```

### 4. `BankImporter` (`agents.bank_importer`)
Utilities for parsing and categorizing bank exports.

---

## 🔒 Security
*   **API Keys**: Never hardcode keys. Use `.env` files or Streamlit Secrets (`st.secrets`).
*   **Gemini**: Requires `GOOGLE_API_KEY`.
*   **GitHub**: Requires a Personal Access Token (PAT) for cloud sync.
