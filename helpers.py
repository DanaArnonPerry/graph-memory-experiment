\
from __future__ import annotations
import hashlib, time, uuid
import pandas as pd
import streamlit as st

DUR_GRAPH = 30          # seconds
DUR_CONTEXT = 2         # seconds
DUR_BLACK = 3           # seconds
DUR_ANSWER_MAX = 120    # seconds

def now_ms() -> int:
    return int(time.time() * 1000)

def ensure_id():
    if "participant_id" not in st.session_state or not st.session_state["participant_id"]:
        st.session_state["participant_id"] = f"P-{uuid.uuid4().hex[:8]}"
    return st.session_state["participant_id"]

def default_v_for_pid(pid: str) -> str:
    h = int(hashlib.sha1(pid.encode("utf-8")).hexdigest(), 16)
    idx = (h % 4) + 1
    return f"V{idx}"  # V1..V4

def load_items(csv_path: str):
    df = pd.read_csv(csv_path)
    # Ensure predictable order; if there is GraphID column keep it
    if "GraphID" not in df.columns:
        df["GraphID"] = (df.index + 1).astype(str)
    return df

def extract_questions(row, group: int):
    questions = []
    # Group 1: only Q1 per graph
    # Group 2 & 3: Q1..Q3 per graph
    num_q = 1 if group == 1 else 3
    for i in range(1, num_q + 1):
        q_text = row.get(f"Question{i}Text", "")
        options = {
            "A": row.get(f"Q{i}OptionA", ""),
            "B": row.get(f"Q{i}OptionB", ""),
            "C": row.get(f"Q{i}OptionC", ""),
            "D": row.get(f"Q{i}OptionD", ""),
        }
        correct = row.get(f"Q{i}Correct", "")
        correct_letter, correct_text = None, None
        if isinstance(correct, str):
            cc = correct.strip()
            if cc.upper() in options:
                correct_letter = cc.upper()
                correct_text = options[correct_letter]
            else:
                # Try match by text
                for k, v in options.items():
                    if str(v).strip() == cc:
                        correct_letter = k
                        correct_text = v
                        break
        questions.append({
            "qnum": i,
            "text": q_text,
            "options": options,
            "correct_letter": correct_letter,
            "correct_text": correct_text,
        })
    return questions
