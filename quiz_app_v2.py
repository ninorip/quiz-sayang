
import streamlit as st
import pandas as pd
from pathlib import Path
import random

st.set_page_config(page_title="MCQ Exam Simulator", layout="wide")

@st.cache_data
def load_questions(base_name: str):
    """Load questions from CSV (preferred) or XLSX (fallback)."""
    p = Path(base_name)
    df = None
    if p.with_suffix(".csv").exists():
        df = pd.read_csv(p.with_suffix(".csv"))
    elif p.with_suffix(".xlsx").exists():
        import pandas as pd
        df = pd.read_excel(p.with_suffix(".xlsx"))
    else:
        st.error("No questions file found. Put 'questions.csv' or 'questions.xlsx' alongside this app.")
        st.stop()

    df = df.fillna("")
    expected = ["No","Question","A","B","C","D","Correct"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    df = df[expected]
    for col in ["Question","A","B","C","D","Correct"]:
        df[col] = df[col].astype(str).str.strip()
    return df

QUESTIONS_PATH = "questions"  # will try questions.csv then questions.xlsx
df = load_questions(QUESTIONS_PATH)

# Sidebar
st.sidebar.title("⚙️ Settings")
mode = st.sidebar.radio("Mode", ["Practice (instant feedback)", "Exam (score at end)"])
shuffle = st.sidebar.checkbox("Shuffle questions", value=True)
num_questions = st.sidebar.slider("Number of questions", 1, len(df), min(50, len(df)))
if st.sidebar.button("🔁 Reset quiz", use_container_width=True):
    st.session_state.clear()
    st.experimental_rerun()

# Init session state
def init_state():
    st.session_state.q_indices = list(range(len(df)))
    if shuffle:
        random.seed(42)
        random.shuffle(st.session_state.q_indices)
    st.session_state.q_indices = st.session_state.q_indices[:num_questions]
    st.session_state.idx = 0
    st.session_state.answers = {}        # global_idx -> chosen ("A"/"B"/"C"/"D")
    st.session_state.correct_map = {i: (df.iloc[i]["Correct"] or "").strip().upper()
                                    for i in st.session_state.q_indices}
    st.session_state.score = 0
    st.session_state.finished = False

if "q_indices" not in st.session_state:
    init_state()

# Helpers
def clamp_idx():
    st.session_state.idx = max(0, min(st.session_state.idx, len(st.session_state.q_indices)-1))

def go_next():
    st.session_state.idx += 1
    if st.session_state.idx >= len(st.session_state.q_indices):
        st.session_state.finished = True
    st.rerun()

def go_prev():
    st.session_state.idx -= 1
    clamp_idx()
    st.rerun()

def render_question(row):
    options = [("A", row["A"]), ("B", row["B"]), ("C", row["C"]), ("D", row["D"])]
    options = [(k, v) for k, v in options if str(v).strip() != ""]
    labels = [f"{k}. {v}" for k, v in options]
    keys = [k for k,_ in options]
    return keys, labels

# Title + progress
st.title("📝 MCQ Exam Simulator")
current = st.session_state.idx + 1
total = len(st.session_state.q_indices)
st.progress((current-1)/max(total,1))
st.caption(f"Question {current} of {total} • Mode: {mode}")

if not st.session_state.finished:
    cur_global_idx = st.session_state.q_indices[st.session_state.idx]
    row = df.iloc[cur_global_idx]
    st.markdown(f"### {row['Question']}")

    keys, labels = render_question(row)
    # Create a form so that a single submit does everything (prevents double-click behaviour)
    with st.form(key=f"form_{cur_global_idx}"):
        # Persist previously chosen answer for convenience
        prev_choice = st.session_state.answers.get(cur_global_idx, None)
        # Map prev_choice letter back to index
        prev_index = None
        if prev_choice in keys:
            prev_index = keys.index(prev_choice)
        choice_idx = st.radio("Select your answer:", options=list(range(len(labels))),
                              format_func=lambda i: labels[i], index=prev_index, key=f"radio_{cur_global_idx}")
        cols = st.columns([1,1,6])
        submit_label = "Submit & Next ▶" if mode.startswith("Practice") else "Save & Next ▶"
        submitted = cols[0].form_submit_button(submit_label, use_container_width=True)
        prev_btn = cols[1].form_submit_button("◀ Previous", use_container_width=True)

    if submitted:
        if choice_idx is None:
            st.warning("Please select an option.")
        else:
            chosen_letter = keys[choice_idx]
            st.session_state.answers[cur_global_idx] = chosen_letter
            correct_letter = st.session_state.correct_map.get(cur_global_idx, "").upper()
            if mode.startswith("Practice"):
                # Immediate feedback
                if correct_letter and chosen_letter == correct_letter:
                    st.success(f"✅ Correct! ({chosen_letter})")
                    st.session_state.score += 1
                else:
                    if correct_letter in {"A","B","C","D"}:
                        st.error(f"❌ Incorrect. Correct answer: {correct_letter}")
                    else:
                        st.info("ℹ️ No answer key provided for this question.")
            # Advance to next question after a short message
            go_next()

    if prev_btn:
        go_prev()

else:
    # Results
    st.header("📊 Results")
    if mode.startswith("Exam"):
        score = 0
        for i in st.session_state.q_indices:
            chosen = st.session_state.answers.get(i, "")
            correct = st.session_state.correct_map.get(i, "").upper()
            if correct and chosen == correct:
                score += 1
        st.session_state.score = score

    st.metric("Score", f"{st.session_state.score} / {len(st.session_state.q_indices)}")

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
    st.download_button("⬇️ Download review (CSV)", data=review_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="quiz_review.csv", mime="text/csv")
    if st.button("🔁 Restart"):
        st.session_state.clear()
        st.experimental_rerun()
