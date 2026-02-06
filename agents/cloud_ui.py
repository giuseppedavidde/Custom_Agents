"""Renderizza la UI per il Cloud Sync (GitHub)."""

import streamlit as st
import os
import io
import pandas as pd
import datetime
from agents.cloud_manager import CloudManager


def render_cloud_sync_ui(DATA_FILE, is_sidebar=True):
    """Renderizza la UI per il Cloud Sync (GitHub)."""
    parent = st.sidebar if is_sidebar else st

    if is_sidebar:
        parent.divider()

    # Se siamo in setup mode (no sidebar), espandiamo di default
    with parent.expander("☁️ Cloud Data Sync", expanded=not is_sidebar):
        # 1. Configurazione Token
        env_gh_token = os.getenv("GITHUB_TOKEN")
        github_token = st.text_input(
            "GitHub Token (PAT)",
            value=env_gh_token if env_gh_token else "",
            type="password",
            help="Richiesto per GitHub",
            key=f"gh_token_{'sb' if is_sidebar else 'main'}",
        )

        if CloudManager and github_token:
            cm = CloudManager(github_token)

            # Bottone per caricare risorse (Cacheando in session state per evitare chiamate API continue)
            if st.button(
                "🔄 Connetti / Cerca Repo",
                key=f"btn_conn_{'sb' if is_sidebar else 'main'}",
            ):
                with st.spinner("Cerco repository..."):
                    repos = cm.get_user_repos()
                    st.session_state["gh_repos"] = repos
                    if not repos:
                        st.warning("Nessun repository trovato o token invalido.")

            # 2. Selezione Repo
            repo_list = st.session_state.get("gh_repos", [])
            selected_repo = None

            if repo_list:
                selected_repo = st.selectbox(
                    "Seleziona Repository",
                    repo_list,
                    index=0,
                    key=f"sel_repo_{'sb' if is_sidebar else 'main'}",
                )
            else:
                st.info("Clicca 'Connetti' per caricare i tuoi repository.")

            # 3. Selezione File (Se repo selezionato)
            selected_file_remote = None
            if selected_repo:
                cache_key_files = f"gh_files_{selected_repo}"

                if cache_key_files not in st.session_state:
                    with st.spinner(f"Cerco file CSV..."):
                        files = cm.list_csv_files(selected_repo)
                        st.session_state[cache_key_files] = files

                file_list = st.session_state[cache_key_files]

                if file_list:
                    default_idx = 0
                    if "Budget App/budget_database.csv" in file_list:
                        default_idx = file_list.index("Budget App/budget_database.csv")

                    selected_file_remote = st.selectbox(
                        "File CSV",
                        file_list,
                        index=default_idx,
                        key=f"sel_file_{'sb' if is_sidebar else 'main'}",
                    )
                else:
                    st.warning("Nessun file .csv trovato.")
                    if st.button(
                        "Cerca di nuovo",
                        key=f"btn_refresh_{'sb' if is_sidebar else 'main'}",
                    ):
                        del st.session_state[cache_key_files]
                        st.rerun()

            # 4. Azioni
            if selected_repo and selected_file_remote:
                st.caption(f"Remote: `{selected_file_remote}`")

                c_down, c_up = st.columns(2)
                with c_down:
                    if st.button(
                        "⬇️ Pull", key=f"btn_pull_{'sb' if is_sidebar else 'main'}"
                    ):
                        with st.spinner("Scaricamento..."):
                            # Se non siamo in sidebar, DATA_FILE potrebbe non esistere, ma scaricandolo lo creiamo
                            ok, msg = cm.github_download(
                                selected_repo, selected_file_remote, DATA_FILE
                            )
                            if ok:
                                st.toast(f"Scaricato: {msg}", icon="✅")
                                st.rerun()
                            else:
                                st.error(msg)
                with c_up:
                    if st.button(
                        "⬆️ Push", key=f"btn_push_{'sb' if is_sidebar else 'main'}"
                    ):
                        with st.spinner("Caricamento..."):
                            ok, msg = cm.github_upload(
                                selected_repo,
                                selected_file_remote,
                                DATA_FILE,
                                commit_message="Update from Budget App Dashboard",
                            )
                            if ok:
                                st.toast(f"Caricato: {msg}", icon="✅")
                            else:
                                st.error(msg)
        else:
            if not CloudManager:
                st.error("Libreria mancante.")
            elif not github_token:
                st.info("Inserisci Token GitHub.")


def render_cloud_ui(
    repo_name="giuseppedavidde/Data_for_Analysis",
    file_path="Crypto_Portfolio_csv.csv",
    is_sidebar=True,
):
    """
    Renders the UI for Cloud Data Synchronization (Pull & Push).
    Stores pulled data in st.session_state['cloud_data'].
    Adapted for Crypto/Portfolio Dashboard.
    """
    # Lazy Import of Modules to avoid crashing in Budget App
    try:
        from modules.editor_utils import calculate_dca_update, df_to_csv_content
        from modules.collect_data_utils import load_portfolio_snapshot
    except ImportError:
        # If modules are not available, we cannot render this specialized UI
        # Should we show an error or just return?
        # If this function is called, it means the caller EXPECTS it to work.
        st.error("Modules for Crypto/Portfolio not found. Check installation.")
        return

    parent = st.sidebar if is_sidebar else st

    if is_sidebar:
        parent.divider()

    with parent.expander("☁️ Cloud Data Sync", expanded=False):
        token = os.getenv("GITHUB_TOKEN")

        if not token:
            st.error("Missing GITHUB_TOKEN in .env")
            return

        cm = CloudManager(token)

        col1, col2 = st.columns(2)

        with col1:
            if st.button("⬇️ Pull", key="btn_cloud_pull", width="stretch"):
                with st.spinner("Downloading..."):
                    # Use fetch_file_content (returns bytes)
                    success, result = cm.fetch_file_content(repo_name, file_path)

                    if success:
                        st.session_state["cloud_data"] = result  # Store bytes/str

                        st.toast("Data Pulled (In-Memory)", icon="✅")
                        st.rerun()
                    else:
                        st.error(result)

        with col2:
            if st.button("⬆️ Push", key="btn_cloud_push", width="stretch"):

                content_to_upload = st.session_state.get("cloud_data")

                if content_to_upload:
                    with st.spinner("Uploading..."):
                        # Ensure string format
                        if isinstance(content_to_upload, bytes):
                            try:
                                content_to_upload = content_to_upload.decode("utf-8")
                            except:
                                pass  # Keep bytes if decoding fails, though PyGithub might prefer bytes?
                                # PyGithub create_file wants str or bytes. update_file calls create_file underneath or similar.
                                # Let's assume decoding is safer if it was text.

                        success, message = cm.upload_file_content(
                            repo_name, file_path, content_to_upload
                        )
                        if success:
                            st.toast(message, icon="✅")
                        else:
                            st.error(message)
                else:
                    st.warning("No data loaded to push.")

    # --- Portfolio Editor Section ---
    # Only show if we have data in session state
    # --- Portfolio Editor Section ---
    # Always show the section, but disable inputs if no data
    with parent.expander("✏️ Portfolio Editor", expanded=False):
        if "cloud_data" not in st.session_state or not st.session_state["cloud_data"]:
            st.warning(
                "⚠️ Per modificare il portafoglio, scarica prima i dati (⬇️ Pull)."
            )
        else:
            st.info(
                "Aggiungi transazioni per aggiornare il DCA (Prezzo Medio Ponderato)."
            )

            # Load current data to get asset list
            try:
                raw_data = st.session_state["cloud_data"]
                if isinstance(raw_data, bytes):
                    buf = io.BytesIO(raw_data)
                else:
                    buf = io.StringIO(raw_data)
                current_df = load_portfolio_snapshot(buf)

                existing_assets = (
                    current_df["asset_collect"].unique().tolist()
                    if not current_df.empty
                    else []
                )
            except Exception:
                current_df = pd.DataFrame()
                existing_assets = []

            # Input Form (No st.form to allow live calculation/preview)
            col_a, col_b = st.columns(2)
            with col_a:
                # Allow selecting existing or typing new
                asset_input = st.selectbox(
                    "Asset", options=existing_assets + ["NEW..."], key="in_asset_select"
                )
                if asset_input == "NEW...":
                    selected_asset = st.text_input(
                        "Inserisci Simbolo (es. SOL)", key="in_asset_manual"
                    )
                else:
                    selected_asset = asset_input

            with col_b:
                # Transaction Type (Buy or Staking)
                trans_type = st.radio(
                    "Tipo Transazione",
                    ["Acquisto (Buy)", "Ricompensa Staking"],
                    horizontal=True,
                    key="in_trans_type",
                )
                is_staking = trans_type == "Ricompensa Staking"

            col_c, col_d = st.columns(2)
            with col_c:
                invested_label = (
                    "Investito (+/- EUR)"
                    if not is_staking
                    else "Valore Ricompensa (EUR)"
                )
                # Allow negative values for Sales (min_value=None or large negative)
                invested = st.number_input(
                    invested_label, step=0.01, format="%.2f", key="in_invested"
                )

            with col_d:
                # User inputs Quantity instead of Price
                quantity = st.number_input(
                    "Quantità Asset", step=0.00000001, format="%.8f", key="in_quantity"
                )

            col_e, col_f = st.columns(2)
            with col_e:
                # Date Selector (Default Today)
                trans_date = st.date_input(
                    "Data Transazione", datetime.date.today(), key="in_trans_date"
                )

            # Live Preview: Implied Price & Impact
            # If Quantity and Invested are set, we can calc Implied Price
            implied_price = 0.0
            if quantity != 0 and invested != 0:
                implied_price = abs(invested / quantity)  # Price is always positive

            if quantity != 0:
                st.metric("Prezzo Implicito (Stimato)", f"{implied_price:,.4f} EUR")
                new_shares_buy = quantity

                # Calculate Impact
                curr_shares = 0.0
                curr_price = 0.0
                curr_invested = 0.0

                # Check if asset exists
                if (
                    selected_asset != "NEW..."
                    and not current_df.empty
                    and "asset_collect" in current_df.columns
                ):
                    mask = current_df["asset_collect"] == selected_asset
                    if mask.any():
                        idx = current_df[mask].index[0]
                        curr_shares = current_df.at[idx, "amount_asset_collect"]
                        curr_price = current_df.at[idx, "median_price"]
                        curr_invested = current_df.at[idx, "amount_fiat_collect"]

                total_shares = curr_shares + new_shares_buy
                # Logic: Staking adds 0 cost to Invested
                fiat_impact = 0.0 if is_staking else invested

                total_invested = curr_invested + fiat_impact
                new_avg_price = total_invested / total_shares if total_shares > 0 else 0

                # Calc PCT Changes
                pct_price = (
                    ((new_avg_price - curr_price) / curr_price * 100)
                    if curr_price > 0
                    else 0.0
                )
                pct_shares = (
                    ((total_shares - curr_shares) / curr_shares * 100)
                    if curr_shares > 0
                    else 100.0
                )

                # Display Summary Table
                st.markdown("### 📊 Anteprima Impatto DCA")
                summary_data = {
                    "Metric": ["Prezzo Medio (EUR)", "Quantità Asset"],
                    "Attuale": [f"{curr_price:,.4f}", f"{curr_shares:.8f}"],
                    "Nuovo (Stimato)": [f"{new_avg_price:,.4f}", f"{total_shares:.8f}"],
                    "Variazione %": [f"{pct_price:+.2f}%", f"{pct_shares:+.2f}%"],
                }
                st.table(pd.DataFrame(summary_data))

                if is_staking:
                    st.success(
                        "ℹ️ Staking: Il costo totale investito rimarrà invariato, abbattendo il prezzo medio."
                    )

            else:
                if invested != 0:
                    st.caption("Inserisci la quantità per calcolare il prezzo.")

            # Action Button
            if st.button("Aggiungi Transazione", type="primary", width="stretch"):
                if not selected_asset:
                    st.error("Seleziona o inserisci un asset.")
                elif invested == 0 and not is_staking:
                    st.error("Inserisci importi validi (diverso da 0).")
                elif quantity == 0:
                    st.error("La quantità non può essere 0.")
                else:
                    # Perform Update with Quantity
                    updated_df = calculate_dca_update(
                        current_df,
                        selected_asset,
                        invested,
                        quantity,
                        is_staking=is_staking,
                        update_date=trans_date,
                        buy_price=implied_price,
                    )

                    # Convert back to CSV
                    new_csv_content = df_to_csv_content(updated_df)

                    # Update Session State
                    st.session_state["cloud_data"] = new_csv_content

                    st.toast(f"DCA Aggiornato per {selected_asset}!", icon="✅")
                    st.rerun()
