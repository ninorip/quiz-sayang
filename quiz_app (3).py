
import os
import random
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MCQ Quiz", layout="wide")

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

# ==================================
# Data Loading (remote + local fallback)
# ==================================
@st.cache_data(ttl=60)
def load_questions_remote(url: str):
    """Load from a published Google Sheets CSV URL. Auto-refresh every 60s."""
    df = pd.read_csv(url, dtype=str).fillna("")
    df = normalize_and_validate(df)
    return df

@st.cache_data
def load_questions_local(base_name: str = "questions", sig: str = ""):
    """
    Load from CSV (preferred) or XLSX (fallback) in repo root.
    'sig' is a cache-buster derived from file_signature().
    """
    p = Path(base_name)
    csv_path = p.with_suffix(".csv")
    xlsx_path = p.with_suffix(".xlsx")

    df = None
    errors = []

    if csv_path.exists():
        trials = [
            dict(encoding="utf-8-sig", sep=None, engine="python"),
            dict(encoding="utf-8", sep=None, engine="python"),
            dict(encoding="latin1", sep=None, engine="python"),
        ]
        for t in trials:
            try:
                df = pd.read_csv(csv_path, dtype=str, on_bad_lines="skip", **t)
                break
            except Exception as e:
                errors.append(f"CSV read failed ({t}): {type(e).__name__}: {e}")

    if df is None and xlsx_path.exists():
        try:
            df = pd.read_excel(xlsx_path, dtype=str)  # requires openpyxl if you use XLSX
        except Exception as e:
            errors.append(f"Excel read failed: {type(e).__name__}: {e}")

    if df is None:
        st.error(
            "Couldn't load questions. Put **questions.csv** (preferred) or **questions.xlsx** in the repo root.\n\n"
            "Required columns: No, Question, A, B, C, D, Correct."
            + ("\n\nErrors:\n- " + "\n- ".join(errors) if errors else "")
        )
        st.stop()

    df = normalize_and_validate(df)
    return df

def normalize_and_validate(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize headers/values and ensure required columns exist."""
    def norm(s): return str(s).replace("\ufeff", "").strip()
    df.columns = [norm(c) for c in df.columns]
    required = ["No", "Question", "A", "B", "C", "D", "Correct"]
    for col in required:
        if col not in df.columns:
            df[col] = ""
    # Clean values
    for col in df.columns:
        df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    # Drop blank questions
    df = df[df["Question"] != ""].copy()
    # Coerce Correct
    df["Correct"] = df["Correct"].str.upper().where(df["Correct"].str.upper().isin(list("ABCD")), "")
    # Reorder
    extras = [c for c in df.columns if c not in required]
    return df[required + extras].reset_index(drop=True)

# Load from remote if configured, else local
REMOTE_URL = st.secrets.get("QUESTIONS_CSV_URL", "").strip()
if REMOTE_URL:
    df = load_questions_remote(REMOTE_URL)
    DATA_SOURCE = "Google Sheets (live)"
else:
    sig = file_signature("questions")
    df = load_questions_local("questions", sig)
    DATA_SOURCE = "Local file"

# ==================================
# Sidebar: Data debug + manual reload
# ==================================
with st.sidebar.expander("🧰 Data debug"):
    st.caption(f"Source: **{DATA_SOURCE}**")
    if REMOTE_URL:
        st.write("URL:", REMOTE_URL)
    st.write("CWD:", os.getcwd())
    st.write("Files:", os.listdir("."))
    st.write("Rows:", len(df))
    if st.button("🔄 Reload questions (clear cache)"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

# ==================================
# Quiz State & Helpers
# ==================================
def init_quiz(mode: str, num_questions: int, shuffle_questions: bool, shuffle_options: bool):
    total = len(df)
    num_questions = max(1, min(int(num_questions), total))

    q_indices = list(range(total))
    if shuffle_questions:
        random.seed()  # new shuffle per run
        random.shuffle(q_indices)
    q_indices = q_indices[:num_questions]

    # Per-question answer order (A-D minus blanks), optionally shuffled
    opt_order = {}
    for gid in q_indices:
        letters = [L for L in ["A", "B", "C", "D"] if str(df.iloc[gid][L]).strip() != ""]
        order = letters[:]
        if shuffle_options and len(order) > 1:
            random.shuffle(order)
        opt_order[gid] = order

    st.session_state.q_indices = q_indices
    st.session_state.idx = 0
    st.session_state.answers = {}       # {global_idx: "A"/"B"/"C"/"D"}
    st.session_state.correct_map = {i: (df.iloc[i]["Correct"] or "").strip().upper() for i in q_indices}
    st.session_state.score = 0
    st.session_state.finished = False
    st.session_state.mode = mode
    st.session_state.screen = "quiz"
    st.session_state.submitted = {}     # Practice: checked
    st.session_state.scored = set()     # Practice: which ones added to score
    st.session_state.flags = set()      # flagged question global indices
    st.session_state.opt_order = opt_order

def go_home():
    st.session_state.clear()
    st.session_state.screen = "home"
    st.rerun()

def go_next():
    st.session_state.idx += 1
    if st.session_state.idx >= len(st.session_state.q_indices):
        st.session_state.finished = True
        st.session_state.screen = "results"
    st.rerun()

def go_prev():
    st.session_state.idx = max(0, st.session_state.idx - 1)
    st.rerun()

def jump_to(local_idx: int):
    st.session_state.idx = max(0, min(local_idx, len(st.session_state.q_indices) - 1))
    st.rerun()

def render_options(gid, row):
    order = st.session_state.opt_order.get(gid, [L for L in ["A","B","C","D"] if str(row[L]).strip() != ""])
    labels = [f"{L}. {row[L]}" for L in order]
    return order, labels

def status_for(local_idx: int):
    gid = st.session_state.q_indices[local_idx]
    flagged = gid in st.session_state.flags
    answered = gid in st.session_state.answers

    if st.session_state.mode.startswith("Practice"):
        submitted = st.session_state.submitted.get(gid, False)
        if submitted:
            chosen = st.session_state.answers.get(gid, "")
            correct = st.session_state.correct_map.get(gid, "")
            if correct and chosen == correct:
                sym = "✅"; hint = "Answered & correct"
            else:
                sym = "❌"; hint = "Answered & incorrect"
        else:
            sym = "•" if answered else "◻️"
            hint = "Answered (not checked)" if answered else "Not answered"
    else:
        sym = "•" if answered else "◻️"
        hint = "Answered" if answered else "Not answered"

    if flagged:
        sym = f"⚑{sym}"; hint = "Flagged • " + hint
    return sym, hint

# ==================================
# Screens
# ==================================
def render_home():
    total = len(df)
    st.title("📝 MCQ Quiz")
    st.caption("Edit in Google Sheets or your repo; this app auto-refreshes.")

    c1, c2 = st.columns(2)
    c1.metric("Available questions", f"{total}")
    c2.caption("Practice = check first → Next/Previous • Exam = Save & Next, score at end")

    st.subheader("Mode")
    mode = st.radio("Select mode", ["Practice (instant feedback)", "Exam (score at end)"], index=0)

    st.subheader("Session")
    c3, c4 = st.columns([2, 1])
    with c3:
        num_questions = st.number_input("Number of questions", min_value=1, max_value=total, value=min(50, total), step=1)
    with c4:
        shuffle_q = st.checkbox("Shuffle questions", value=True)
    shuffle_opts = st.checkbox("Shuffle answer order", value=True)

    if st.button("▶ Start", type="primary", use_container_width=True):
        init_quiz(mode, num_questions, shuffle_q, shuffle_opts)
        st.rerun()

def render_question_map():
    st.markdown("##### Question Map")
    st.caption("Legend: ⚑ flagged • ✅ correct (practice) • ❌ incorrect (practice) • • answered • ◻️ not answered")
    n = len(st.session_state.q_indices)
    COLS = 12
    rows = (n + COLS - 1) // COLS
    for r in range(rows):
        cols = st.columns(COLS)
        for c in range(COLS):
            i = r * COLS + c
            if i >= n:
                continue
            sym, hint = status_for(i)
            label = f"{i+1}\n{sym}"
            if cols[c].button(label, key=f"jump_{i}", help=hint):
                jump_to(i)

def render_quiz():
    current = st.session_state.idx + 1
    total = len(st.session_state.q_indices)

    top_left, top_right = st.columns([2, 1])
    with top_left:
        st.progress((current - 1) / max(total, 1))
        st.caption(f"Question {current} of {total} • Mode: {st.session_state.mode} • Source: {'Google Sheets (live)' if REMOTE_URL else 'Local file'}")
    with top_right:
        if st.button("🏠 Home", use_container_width=True):
            go_home()

    with st.expander("📌 Navigate by question number", expanded=False):
        render_question_map()

    gid = st.session_state.q_indices[st.session_state.idx]
    row = df.iloc[gid]
    st.markdown(f"### {row['Question']}")

    order, labels = render_options(gid, row)

    # Flag/Unflag
    flag_col, _ = st.columns([1, 3])
    flagged = gid in st.session_state.flags
    if flag_col.button("Unflag ⚑" if flagged else "Flag ⚑", key=f"flag_{gid}"):
        if flagged: st.session_state.flags.discard(gid)
        else: st.session_state.flags.add(gid)
        st.rerun()

    # Answer form
    with st.form(key=f"form_{gid}"):
        prev_choice = st.session_state.answers.get(gid, None)
        prev_index = order.index(prev_choice) if prev_choice in order else None
        choice_idx = st.radio("Select your answer:",
                              options=list(range(len(labels))),
                              format_func=lambda i: labels[i],
                              index=prev_index)

        submit_label = "Check Answer ✅" if st.session_state.mode.startswith("Practice") else "Save Answer 💾"
        submitted = st.form_submit_button(submit_label, use_container_width=True)

    if submitted:
        if choice_idx is None:
            st.warning("Please select an option.")
            st.stop()

        chosen_letter = order[choice_idx]  # map to original A/B/C/D
        st.session_state.answers[gid] = chosen_letter

        if st.session_state.mode.startswith("Practice"):
            st.session_state.submitted[gid] = True
            correct_letter = st.session_state.correct_map.get(gid, "")
            if correct_letter and chosen_letter == correct_letter:
                st.success(f"✅ Hebat! Kamu pinter banget, jawaban kamu benar {chosen_letter}")
                if gid not in st.session_state.scored:
                    st.session_state.score += 1
                    st.session_state.scored.add(gid)
            else:
                if correct_letter in {"A", "B", "C", "D"}:
                    st.error(f"❌ Gapapa! Ayo coba lagi, jawaban yang benar {correct_letter}")
                else:
                    st.info("ℹ️ Kunci jawaban belum tersedia untuk soal ini.")
        else:
            # Exam: save & go next
            go_next()

    # Navigation
    navL, navR = st.columns([1, 1])
    if navL.button("◀ Previous", use_container_width=True):
        go_prev()

    if st.session_state.mode.startswith("Practice"):
        checked = st.session_state.submitted.get(gid, False)
        disable_next = not checked
        help_txt = None if checked else "Check answer first to proceed."
    else:
        disable_next = False
        help_txt = None

    if navR.button("Next ▶", use_container_width=True, disabled=disable_next, help=help_txt):
        go_next()

def render_results():
    st.header("📊 Results")
    total = len(st.session_state.q_indices)

    if st.session_state.mode.startswith("Exam"):
        score = 0
        for gid in st.session_state.q_indices:
            chosen = st.session_state.answers.get(gid, "")
            correct = st.session_state.correct_map.get(gid, "").upper()
            if correct and chosen == correct:
                score += 1
        st.session_state.score = score

    st.metric("Score", f"{st.session_state.score} / {total}")

    rows = []
    for gid in st.session_state.q_indices:
        q = df.iloc[gid]
        chosen = st.session_state.answers.get(gid, "")
        correct = st.session_state.correct_map.get(gid, "").upper()
        status = ("Correct ✅"
                  if correct and chosen == correct else
                  ("Incorrect ❌" if chosen and correct else
                   ("No key ℹ️" if not correct else "Unanswered ⚠️")))
        rows.append({
            "No": q["No"],
            "Question": q["Question"],
            "A": q["A"], "B": q["B"], "C": q["C"], "D": q["D"],
            "Chosen": chosen, "Correct": correct, "Status": status
        })
    review_df = pd.DataFrame(rows)
    st.dataframe(review_df, use_container_width=True)
    st.download_button("⬇️ Download review (CSV)",
                       data=review_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="quiz_review.csv", mime="text/csv")

    colA, colB = st.columns([1, 1])
    if colA.button("🏠 Home"):
        go_home()
    if colB.button("🔁 Restart same settings"):
        st.session_state.idx = 0
        st.session_state.answers = {}
        st.session_state.score = 0
        st.session_state.finished = False
        st.session_state.submitted = {}
        st.session_state.scored = set()
        st.session_state.screen = "quiz"
        st.rerun()

# ==================================
# Router
# ==================================
if "screen" not in st.session_state:
    st.session_state.screen = "home"

if st.session_state.screen == "home":
    render_home()
elif st.session_state.screen == "quiz":
    render_quiz()
elif st.session_state.screen == "results":
    render_results()
