import os
import streamlit as st
from github import Github, GithubException


class CloudManager:
    """Gestisce la sincronizzazione dei dati con il Cloud (GitHub)."""

    def __init__(self, github_token=None):
        self.github_token = github_token
        self.gh = None
        if self.github_token:
            self.gh = Github(self.github_token)

    def is_connected(self):
        """Verifica se la connessione al Cloud (GitHub) è stabilita."""
        return self.gh is not None

    def github_download(self, repo_name, file_path_remote, file_path_local):
        """Scarica un file da GitHub e sovrascrive quello locale."""
        if not self.gh:  # pylint: disable=using-constant-test
            raise Exception("GitHub Token non fornito.")

        try:
            repo = self.gh.get_repo(repo_name)
            contents = repo.get_contents(file_path_remote)

            # Scrivi contenuto locale
            # contents.decoded_content è in bytes
            with open(file_path_local, "wb") as f:
                f.write(contents.decoded_content)

            return True, f"File scaricato da {repo_name}/{file_path_remote}"

        except GithubException as e:
            return False, f"Errore GitHub: {e.status} - {e.data.get('message', '')}"
        except Exception as e:  # pylint: disable=broad-exception-caught
            return False, f"Errore generico: {str(e)}"

    def fetch_file_content(self, repo_name, file_path_remote):
        """Scarica il contenuto di un file da GitHub e lo restituisce (bytes)."""
        if not self.gh:
            raise Exception("GitHub Token non fornito.")

        try:
            repo = self.gh.get_repo(repo_name)
            contents = repo.get_contents(file_path_remote)
            return True, contents.decoded_content
        except GithubException as e:
            return False, f"Errore GitHub: {e.status} - {e.data.get('message', '')}"
        except Exception as e:
            return False, f"Errore generico: {str(e)}"

    def upload_file_content(
        self, repo_name, file_path_remote, content, commit_message="Update data"
    ):
        """Carica contenuto (str o bytes) su GitHub (Check if exists -> Update or Create)."""
        if not self.gh:
            raise Exception("GitHub Token non fornito.")

        try:
            repo = self.gh.get_repo(repo_name)

            # Cerca se il file esiste già (per prendere l'SHA necessario per l'update)
            try:
                contents = repo.get_contents(file_path_remote)
                # Update
                # Note: content should be string or bytes. PyGithub handles it.
                repo.update_file(contents.path, commit_message, content, contents.sha)
                return True, "File aggiornato con successo."
            except GithubException as e:
                if e.status == 404:
                    # Create
                    repo.create_file(file_path_remote, commit_message, content)
                    return True, "File creato con successo."
                else:
                    raise e

        except GithubException as e:
            return False, f"Errore GitHub: {e.status} - {e.data.get('message', '')}"
        except Exception as e:
            return False, f"Errore generico: {str(e)}"

    def github_upload(
        self,
        repo_name,
        file_path_remote,
        file_path_local,
        commit_message="Update data from Budget App",
    ):
        """Carica un file locale su GitHub."""
        if not os.path.exists(file_path_local):
            return False, "File locale non trovato."

        try:
            with open(file_path_local, "r", encoding="utf-8") as f:  # Assumi CSV utf-8
                content = f.read()

            return self.upload_file_content(
                repo_name, file_path_remote, content, commit_message
            )

        except Exception as e:
            return False, f"Errore generico: {str(e)}"

    def get_user_repos(self):
        """Restituisce una lista di nomi dei repository dell'utente autenticato."""
        if not self.gh:
            raise Exception("GitHub Token non fornito.")
        try:
            user = self.gh.get_user()
            # Prendiamo i repo, magari ordinati per ultimo aggiornamento
            repos = user.get_repos(sort="updated", direction="desc")
            return [repo.full_name for repo in repos]  # "user/repo"
        except Exception as e:
            return []

    def list_csv_files(self, repo_name):
        """Cerca ricorsivamente tutti i file .csv nel repository."""
        if not self.gh:
            raise Exception("GitHub Token non fornito.")

        csv_files = []
        try:
            repo = self.gh.get_repo(repo_name)
            contents = repo.get_contents("")

            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    contents.extend(repo.get_contents(file_content.path))
                else:
                    if file_content.path.endswith(".csv"):
                        csv_files.append(file_content.path)

                # Safety break se ci sono troppi file (es. > 1000) per evitare blocchi
                if len(csv_files) > 100:
                    pass

            return csv_files
        except Exception as e:
            return []
