"""AI provider API key resolution: Streamlit Cloud secrets locally falls back to .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_SECRETS_PATHS = (
    Path.home() / ".streamlit" / "secrets.toml",
    Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml",
)


def _get_api_key(secret_name):
    """Return the named API key, or None if it isn't configured anywhere.

    Tries st.secrets first (how keys are supplied on Streamlit Community
    Cloud), then falls back to the same-named environment variable
    (populated locally via a gitignored .env file). Never raises and never
    logs the key value.

    Merely referencing st.secrets when no secrets.toml exists at all (the
    local-dev case) renders a visible error banner as a Streamlit UI
    side-effect, independent of any try/except -- so the file's existence is
    checked first and st.secrets is only touched when it's actually there.
    """
    if any(p.exists() for p in _SECRETS_PATHS):
        try:
            import streamlit as st

            if secret_name in st.secrets:
                return st.secrets[secret_name]
        except Exception:
            pass

    return os.environ.get(secret_name) or None


def get_gemini_api_key():
    """Return the Gemini API key, or None if it isn't configured anywhere."""
    return _get_api_key("GEMINI_API_KEY")


def get_groq_api_key():
    """Return the Groq API key, or None if it isn't configured anywhere."""
    return _get_api_key("GROQ_API_KEY")


def get_cerebras_api_key():
    """Return the Cerebras API key, or None if it isn't configured anywhere."""
    return _get_api_key("CEREBRAS_API_KEY")
