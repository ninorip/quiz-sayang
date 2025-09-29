
import streamlit as st
import pandas as pd
from pathlib import Path
import random

st.set_page_config(page_title="MCQ Exam Simulator", layout="wide")

@st.cache_data
def load_questions(path: str):
    df = pd.read_excel(path).fillna("")
    # normalize columns
    expected = ["No","Question","A","B","C","D","Correct"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    df = df[expected]
    # Clean whitespace
    for col in ["Question","A","B","C","D","Correct"]:
        df[col] = df[col].astype(str).str.strip()
    return df

QUESTIONS_PATH = "questions.xlsx"
df = load_questions(QUESTIONS_PATH)

# Sidebar controls
st.sidebar.title("⚙️ Settings")
mode = st.sidebar.radio("Mode", ["Practice (instant feedback)", "Exam (score at end)"])
shuffle = st.sidebar.checkbox("Shuffle questions", value=True)
num_questions = st.sidebar.slider("Number of questions", min_value=1, max_value=len(df), value=min(50, len(df)))
reset = st.sidebar.button("🔁 Reset quiz")

# Session state init/reset
def init_state():
    st.session_state.q_indices = list(range(len(df)))
    if shuffle:
        random.seed(42)  # deterministic shuffle per run
        random.shuffle(st.session_state.q_indices)
    st.session_state.q_indices = st.session_state.q_indices[:num_questions]
    st.session_state.idx = 0
    st.session_state.answers = {}        # idx_in_df -> chosen option ("A"/"B"/"C"/"D")
    st.session_state.correct_map = {}    # idx_in_df -> correct letter
    for i in st.session_state.q_indices:
        st.session_state.correct_map[i] = (df.iloc[i]["Correct"] or "").strip().upper()
    st.session_state.score = 0
    st.session_state.finished = False
    st.session_state.review = []

if "idx" not in st.session_state or reset:
    init_state()

# Helpers
def display_question(dfrow, show_feedback: bool):
    st.markdown(f"### {dfrow['Question']}")
    options = [("A", dfrow["A"]), ("B", dfrow["B"]), ("C", dfrow["C"]), ("D", dfrow["D"])]
    options = [(k, v) for k,v in options if str(v).strip() != ""]
    labels = [f"{k}. {v}" for k,v in options]
    keys = [k for k,_ in options]
    return keys, labels

def next_question():
    st.session_state.idx += 1
    if st.session_state.idx >= len(st.session_state.q_indices):
        st.session_state.finished = True

# Main UI
st.title("📝 MCQ Exam Simulator")
st.caption(f"Questions loaded: {len(df)} | Current set: {len(st.session_state.q_indices)} | Mode: {mode}")

if not st.session_state.finished:
    cur_global_idx = st.session_state.q_indices[st.session_state.idx]
    row = df.iloc[cur_global_idx]
    keys, labels = display_question(row, show_feedback=(mode.startswith("Practice")))

    chosen = st.radio("Select your answer:", options=range(len(labels)), format_func=lambda i: labels[i], index=None, key=f"q_{cur_global_idx}")
    col1, col2, col3 = st.columns([1,1,2])

    if mode.startswith("Practice"):
        with col1:
            if st.button("Submit"):
                if chosen is None:
                    st.warning("Please select an option.")
                else:
                    chosen_letter = keys[chosen]
                    st.session_state.answers[cur_global_idx] = chosen_letter
                    correct_letter = st.session_state.correct_map.get(cur_global_idx, "").upper()
                    if correct_letter and chosen_letter == correct_letter:
                        st.success(f"✅ Correct! ({chosen_letter})")
                        st.session_state.score += 1
                    else:
                        if correct_letter in {"A","B","C","D"}:
                            st.error(f"❌ Incorrect. Correct answer: {correct_letter}")
                        else:
                            st.info("ℹ️ No answer key provided for this question.")
        with col2:
            if st.button("Next ▶"):
                next_question()
    else:
        # Exam mode: record answer, no feedback
        with col1:
            if st.button("Save Answer"):
                if chosen is None:
                    st.warning("Please select an option.")
                else:
                    st.session_state.answers[cur_global_idx] = keys[chosen]
                    st.success("Answer saved.")
        with col2:
            if st.button("Next ▶"):
                next_question()
        with col3:
            st.progress((st.session_state.idx)/max(1,len(st.session_state.q_indices)))

else:
    # Finished -> scoring (for Exam) + review table
    st.header("📊 Results")
    total = len(st.session_state.q_indices)
    if mode.startswith("Exam"):
        score = 0
        for i in st.session_state.q_indices:
            chosen = st.session_state.answers.get(i, "")
            correct = st.session_state.correct_map.get(i, "").upper()
            if correct and chosen == correct:
                score += 1
        st.session_state.score = score

    st.metric(label="Score", value=f"{st.session_state.score} / {len(st.session_state.q_indices)}")

    # Review
    import pandas as pd
    rows = []
    for i in st.session_state.q_indices:
        q = df.iloc[i]
        chosen = st.session_state.answers.get(i, "")
        correct = st.session_state.correct_map.get(i, "").upper()
        status = ("Correct ✅" if correct and chosen == correct else
                  ("Incorrect ❌" if chosen and correct else
                   ("No key ℹ️" if not correct else "Unanswered ⚠️")))
        rows.append({
            "No": int(q["No"]) if str(q["No"]).isdigit() else q["No"],
            "Question": q["Question"],
            "A": q["A"], "B": q["B"], "C": q["C"], "D": q["D"],
            "Chosen": chosen, "Correct": correct, "Status": status
        })
    review_df = pd.DataFrame(rows)
    st.dataframe(review_df, use_container_width=True)
    st.download_button("⬇️ Download review (CSV)", data=review_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="quiz_review.csv", mime="text/csv")

    if st.button("🔁 Restart"):
        init_state()
        st.rerun()
