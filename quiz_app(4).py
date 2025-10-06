import os
import random
import hashlib
import re
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MCQ Quiz", layout="wide")

# ==================================
# Globals / Config
# ==================================
OPTION_LETTERS = ["A", "B", "C", "D", "E"]  # Support up to A–E

# ==================================
# Helpers
# ==================================
def file_signature(base_name="questions"):
    """MD5 hash of local questions file to bust cache when it changes."""
    p = Path(base_name)
    candidate = p.with_suffix(".csv") if p.with_suffix(".csv").exists() else p.with_suffix(".xlsx")
    if not candidate.exists():
        return "nofile"
    return hashlib.md5(candidate.read_bytes()).hexdigest()


def available_options_for_row(row) -> list:
    """Return the option letters that are non-empty for this row, in order."""
    return [L for L in OPTION_LETTERS if str(row.get(L, "")).strip() != ""]


def normalize_and_validate(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize headers/values and ensure required columns exist (A–E supported)."""
    def norm(s): return str(s).replace("\ufeff", "").strip()
    df.columns = [norm(c) for c in df.columns]

    # Core required columns
    required_core = ["No", "Question", "Correct"]
    for col in required_core:
        if col not in df.columns:
            df[col] = ""

    # Ensure all A–E exist (some banks might only have A–D; we'll create blank E if missing)
    for col in OPTION_LETTERS:
        if col not in df.columns:
            df[col] = ""

    # Clean values & trim whitespace
    for col in df.columns:
        df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()

    # Drop blank questions
    df = df[df["Question"] != ""].copy()

    # Coerce Correct to A–E only (empty otherwise)
    df["Correct"] = df["Correct"].str.upper().where(df["Correct"].str.upper().isin(OPTION_LETTERS), "")

    # Reorder with a stable order: core, A–E, then extras
    ordered = required_core + OPTION_LETTERS
    extras = [c for c in df.columns if c not in ordered]
    return df[ordered + extras].reset_index(drop=True)


# ==================================
# Data Loading (remote + local fallback)
# ==================================
def _to_csv_url(u: str) -> str:
    """Convert common Google Sheets view/public URLs into CSV export URL."""
    u = (u or "").strip()
    if "docs.google.com/spreadsheets" not in u:
        return u
    m = re.search(r"/spreadsheets/d/([^/]+)/", u)
    gid_match = re.search(r"[?#&]gid=(\d+)", u)
    if m:
        sheet_id = m.group(1)
        gid = gid_match.group(1) if gid_match else "0"
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    return u


@st.cache_data(ttl=60)
def load_questions_remote(url: str):
    """Load from a published Google Sheets CSV URL. Auto-refresh every 60s. Robust parsing."""
    csv_url = _to_csv_url(url)

    trials = [
        dict(encoding="utf-8-sig", sep=None, engine="python", on_bad_lines="skip"),
        dict(encoding="utf-8",     sep=None, engine="python", on_bad_lines="skip"),
        dict(encoding="latin1",    sep=None, engine="python", on_bad_lines="skip"),
    ]

    last_err =_
