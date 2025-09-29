
import os
import random
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MCQ Quiz", layout="wide")

# =========================
# Data Loading
# =========================
@st.cache_data
def load_questions(base_name: str = "questions"):
    """
    Loads questions from CSV (preferred) or XLSX (fallback).
    Expected columns: No, Question, A, B, C, D, Correct
    Returns a dataframe with those columns, all strings, trimmed.
    """
    p = Path(base_name)
    csv_path = p.with_suffix(".csv")
    xlsx_path = p.with_suffix(".xlsx")

    df = None
    errors = []

    # Try CSV with tolerant settings
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

    # Fallback: Excel
    if df is None and xlsx_path.exists():
        try:
            df = pd.read_excel(xlsx_path, dtype=str)
        except Exception as e:
            errors.append(f"Excel read failed: {type(e).__name__}: {e}")

    if df is None:
        st.error(
            "Couldn't load questions. Place **questions.csv** (preferred) or **questions.xlsx** "
            "in the same folder as the app. Required columns: No, Question, A, B, C, D, Correct."
            + ("\n\nErrors:\n- " + "\n- ".join(errors) if errors else "")
        )
        st.stop()

    # Normalize headers
    def norm(s):
        return str(s).replace("\\ufeff","").strip()
    df.columns = [norm(c) for c in df.columns]

    # Ensure required columns exist
    required = ["No","Question","A","B","C","D","Correct"]
    for col in required:
        if col not in df.columns:
            df[col] = ""

    df = df[required].fillna("")
    for col in required:
        df[col] = df[col].astype(str).str.strip()

    # Drop rows with no question text
    df = df[df["Question"] != ""]
    df = df.reset_index(drop=True)
    return df

df = load_questions("questions")

# =========================
# Helpers & State
# =========================
def init_quiz(mode: str, num_questions: int, shuffle: bool):
    total = len(df)
    num_questions = max(1, min(num_questions, total))

    q_indices = list(range(total))
    if shuffle:
        random.seed()  # new shuffle per run
        random.shuffle(q_indices)
    q_indices = q_indices[:num_questions]

    st.session_state.q_indices = q_indices
    st.session_state.idx = 0
    st.session_state.answers = {}     # {global_idx: "A"/"B"/"C"/"D"}
    st.session_state.correct_map = {i: (df.iloc[i]["Correct"] or "").strip().upper() for i in q_indices}
    st.session_state.score = 0
    st.session_state.finished = False
    st.session_state.mode = mode
    st.session_state.screen = "quiz"
    st.session_state.submitted = {}   # {global_idx: bool} for practice flow
    st.session_state.scored = set()   # which have already incremented score in practice
    st.session_state.flags = set()    # flagged questions (global idx)

def go_home():
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
    st.session_state.idx = max(0, min(local_idx, len(st.session_state.q_indices)-1))
    st.rerun()

def render_question_row(row):
    options = [("A", row["A"]), ("B", row["B"]), ("C", row["C"]), ("D", row["D"])]
    options = [(k, v) for k, v in options if str(v).strip() != ""]
    labels = [f"{k}. {v}" for k, v in options]
    keys = [k for k,_ in options]
    return keys, labels

def status_for(local_idx: int):
    """Return (symbol, help_text) for the question in the session set at position local_idx."""
    global_idx = st.session_state.q_indices[local_idx]
    flagged = global_idx in st.session_state.flags
    answered = global_idx in st.session_state.answers

    if st.session_state.mode.startswith("Practice"):
        submitted = st.session_state.submitted.get(global_idx, False)
        if submitted:
            chosen = st.session_state.answers.get(global_idx, "")
            correct = st.session_state.correct_map.get(global_idx, "")
            if correct and chosen == correct:
                sym = "✅"  # correct (checked)
                hint = "Answered & correct"
            else:
                sym = "❌"  # incorrect (checked)
                hint = "Answered & incorrect"
        else:
            sym = "•" if answered else "◻️"
            hint = "Answered (not checked)" if answered else "Not answered"
    else:
        sym = "•" if answered else "◻️"
        hint = "Answered" if answered else "Not answered"

    if flagged:
        # Prepend flag symbol
        sym = f"⚑{sym}"
        hint = "Flagged • " + hint
    return sym, hint

# =========================
# Screens
# =========================
def render_home():
    total = len(df)
    st.title("📝 MCQ Quiz")
    st.caption("Choose a mode, enter how many questions, and press Start.")

    c1, c2 = st.columns(2)
    c1.metric("Available questions", f"{total}")
    c2.caption("Practice = check first → Next/Previous • Exam = Save & Next, score at end")

    st.subheader("Mode")
    mode = st.radio(
        "Select mode",
        ["Practice (instant feedback)", "Exam (score at end)"],
        index=0,
    )

    st.subheader("Session")
    c3, c4 = st.columns([2,1])
    with c3:
        num_questions = st.number_input("Number of questions", min_value=1, max_value=total, value=min(50, total), step=1)
    with c4:
        shuffle = st.checkbox("Shuffle", value=True)

    start = st.button("▶ Start", type="primary", use_container_width=True)
    if start:
        init_quiz(mode, int(num_questions), shuffle)
        st.rerun()

def render_question_map():
    st.markdown("##### Question Map")
    # Legend
    st.caption("Legend: ⚑ flagged • ✅ correct (practice) • ❌ incorrect (practice) • • answered • ◻️ not answered")
    n = len(st.session_state.q_indices)
    COLS = 12
    rows = (n + COLS - 1) // COLS
    for r in range(rows):
        cols = st.columns(COLS)
        for c in range(COLS):
            i = r*COLS + c
            if i >= n:
                continue
            sym, hint = status_for(i)
            label = f"{i+1}\n{sym}"
            # Use a compact button; key must be unique
            if cols[c].button(label, key=f"jump_{i}", help=hint):
                jump_to(i)

def render_quiz():
    # Header with progress + map
    current = st.session_state.idx + 1
    total = len(st.session_state.q_indices)

    top_left, top_right = st.columns([2,1])
    with top_left:
        st.progress((current-1)/max(total,1))
        st.caption(f"Question {current} of {total} • Mode: {st.session_state.mode}")
    with top_right:
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.clear()
            st.session_state.screen = "home"
            st.rerun()

    with st.expander("📌 Navigate by question number", expanded=False):
        render_question_map()

    # Current question
    cur_global_idx = st.session_state.q_indices[st.session_state.idx]
    row = df.iloc[cur_global_idx]
    st.markdown(f"### {row['Question']}")

    keys, labels = render_question_row(row)

    # Flag / Unflag control
    flag_col, _ = st.columns([1,3])
    flagged = cur_global_idx in st.session_state.flags
    flag_label = "Unflag ⚑" if flagged else "Flag ⚑"
    if flag_col.button(flag_label, key=f"flag_{cur_global_idx}"):
        if flagged:
            st.session_state.flags.discard(cur_global_idx)
        else:
            st.session_state.flags.add(cur_global_idx)
        st.rerun()

    # Form: in Practice -> Check (no auto-advance). In Exam -> Save & Next.
    with st.form(key=f"form_{cur_global_idx}"):
        prev_choice = st.session_state.answers.get(cur_global_idx, None)
        prev_index = keys.index(prev_choice) if prev_choice in keys else None

        choice_idx = st.radio(
            "Select your answer:",
            options=list(range(len(labels))),
            format_func=lambda i: labels[i],
            index=prev_index
        )

        submit_label = "Check Answer ✅" if st.session_state.mode.startswith("Practice") else "Save Answer 💾"
        submitted = st.form_submit_button(submit_label, use_container_width=True)

    if submitted:
        if choice_idx is None:
            st.warning("Please select an option.")
            st.stop()
        chosen_letter = keys[choice_idx]
        st.session_state.answers[cur_global_idx] = chosen_letter

        if st.session_state.mode.startswith("Practice"):
            st.session_state.submitted[cur_global_idx] = True
            correct_letter = st.session_state.correct_map.get(cur_global_idx, "")
            if correct_letter and chosen_letter == correct_letter:
                st.success(f"✅ Correct! ({chosen_letter})")
                if cur_global_idx not in st.session_state.scored:
                    st.session_state.score += 1
                    st.session_state.scored.add(cur_global_idx)
            else:
                if correct_letter in {"A","B","C","D"}:
                    st.error(f"❌ Incorrect. Correct answer: {correct_letter}")
                else:
                    st.info("ℹ️ No answer key provided for this question.")
        else:
            # Exam: save & go next
            go_next()

    # Navigation controls
    navL, navR = st.columns([1,1])
    if navL.button("◀ Previous", use_container_width=True):
        go_prev()

    if st.session_state.mode.startswith("Practice"):
        checked = st.session_state.submitted.get(cur_global_idx, False)
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
        # Compute score now
        score = 0
        for i in st.session_state.q_indices:
            chosen = st.session_state.answers.get(i, "")
            correct = st.session_state.correct_map.get(i, "").upper()
            if correct and chosen == correct:
                score += 1
        st.session_state.score = score

    st.metric("Score", f"{st.session_state.score} / {total}")

    # Review table
    rows = []
    for i in st.session_state.q_indices:
        q = df.iloc[i]
        chosen = st.session_state.answers.get(i, "")
        correct = st.session_state.correct_map.get(i, "").upper()
        status = ("Correct ✅" if correct and chosen == correct else
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

    colA, colB = st.columns([1,1])
    if colA.button("🏠 Home"):
        st.session_state.clear()
        st.session_state.screen = "home"
        st.rerun()
    if colB.button("🔁 Restart same settings"):
        st.session_state.idx = 0
        st.session_state.answers = {}
        st.session_state.score = 0
        st.session_state.finished = False
        st.session_state.submitted = {}
        st.session_state.scored = set()
        st.session_state.screen = "quiz"
        st.rerun()

# =========================
# Router
# =========================
if "screen" not in st.session_state:
    st.session_state.screen = "home"

if st.session_state.screen == "home":
    render_home()
elif st.session_state.screen == "quiz":
    render_quiz()
elif st.session_state.screen == "results":
    render_results()
