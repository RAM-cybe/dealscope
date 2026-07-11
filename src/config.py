"""Gemini API key resolution: Streamlit Cloud secrets locally falls back to .env."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_gemini_api_key():
    """Return the Gemini API key, or None if it isn't configured anywhere.

    Tries st.secrets first (how the key is supplied on Streamlit Community
    Cloud), then falls back to the GEMINI_API_KEY environment variable
    (populated locally via a gitignored .env file). Never raises and never
    logs the key value.
    """
    try:
        import streamlit as st

        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    return os.environ.get("GEMINI_API_KEY") or None
