from setuptools import setup, find_packages

setup(
    name="custom_agents",
    version="0.1.0",
    description="Centralized Agents for Streamlit Projects",
    packages=find_packages(),  # This will find the 'agents' package
    install_requires=[
        "google-genai",
        "ollama",
        "requests",
        "beautifulsoup4",
        "pymupdf",
        "pandas",
        "streamlit",
        "PyGithub",
        "google-api-core",
        "groq",
    ],
)
