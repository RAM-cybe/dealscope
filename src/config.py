"""Gemini API key resolution: Streamlit Cloud secrets locally falls back to .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_SECRETS_PATHS = (
    Path.home() / ".streamlit" / "secrets.toml",
    Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml",
)


def get_gemini_api_key():
    """Return the Gemini API key, or None if it isn't configured anywhere.

    Tries st.secrets first (how the key is supplied on Streamlit Community
    Cloud), then falls back to the GEMINI_API_KEY environment variable
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

            if "GEMINI_API_KEY" in st.secrets:
                return st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass

    return os.environ.get("GEMINI_API_KEY") or None
