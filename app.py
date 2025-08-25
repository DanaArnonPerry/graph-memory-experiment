# -*- coding: utf-8 -*-
# experiment.py — Streamlit app: ניסוי זיכרון גרפים (v1.1.0)
# Author: ChatGPT

import os
import time
import uuid
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import pandas as pd
import streamlit as st

# =============================
# ---- Configuration -----------
# =============================

APP_TITLE = "ניסוי זיכרון גרפים"
VERSION = "1.1.0"

# Durations (seconds) — per spec
DUR_GRAPH = int(os.environ.get("DUR_GRAPH", 30))       # צפייה בגרף
DUR_CONTEXT = int(os.environ.get("DUR_CONTEXT", 30))   # מסך הקשר (לפני/אחרי)
DUR_BLACK = int(os.environ.get("DUR_BLACK", 30))       # מסך שחור / הפסקה
DUR_ANSWER_MAX = int(os.environ.get("DUR_ANSWER_MAX", 120))  # זמן תשובה מקסימלי לשאלה

MAX_GRAPHS = int(os.environ.get("MAX_GRAPHS", 12))     # מקסימום גרפים לניסוי
RANDOMIZE_ORDER = os.environ.get("RANDOMIZE_ORDER", "0") == "1"  # ערבוב סדר הגרפים (אופציונלי)

RESULTS_DIR = os.environ.get("RESULTS_DIR", "results")
RESULTS_CSV = os.path.join(RESULTS_DIR, "results_local.csv")

# Admin code — from secrets or env var
ADMIN_CODE = st.secrets.get("app", {}).get("admin_code", None) if hasattr(st, "secrets") else None
if not ADMIN_CODE:
    ADMIN_CODE = os.environ.get("ADMIN_CODE", "")

# =============================
# ---- Utilities ---------------
# =============================

def ensure_dirs():
    os.makedirs(RESULTS_DIR, exist_ok=True)

def rtl_css():
    st.markdown(
        """
        <style>
        html, body, [class*="css"]  { direction: rtl; text-align: right; }
        [data-testid="stAppViewContainer"] { direction: rtl; }
        /* UI polish (based on best-practices): hide menu/footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: visible;}
        .timer { font-size: 1.6rem; font-weight: 800; }
        .muted { color: #666; }
        .center { text-align: center; }
        .blackout { background: black; height: 60vh; border-radius: 12px; }
        .qbox { padding: 1rem; border: 1px solid #eee; border-radius: 12px; background:#fafafa; }
        .small { font-size: 0.9rem;}
        .pill { padding: 2px 8px; border-radius: 1rem; background:#eee; margin-inline-start:8px;}
        </style>
        """,
        unsafe_allow_html=True
    )

def now_ts() -> str:
    return pd.Timestamp.utcnow().isoformat()

def unique_participant_id() -> str:
    pid = st.session_state.get("participant_id")
    if not pid:
        pid = str(uuid.uuid4())
        st.session_state["participant_id"] = pid
    return pid

def error_box(msg: str):
    st.error(msg, icon="⚠️")

def info_box(msg: str):
    st.info(msg)

def success_box(msg: str):
    st.success(msg)

def warn_box(msg: str):
    st.warning(msg)

def load_csv(path: str = "MemoryTest.csv") -> pd.DataFrame:
    if not os.path.exists(path):
        error_box(f"לא נמצא קובץ הנתונים '{path}'. יש למקם את הקובץ בתיקייה הראשית של האפליקציה.")
        st.stop()
    try:
        df = pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="cp1255")
    if df.empty:
        error_box("קובץ ה-CSV ריק.")
        st.stop()
    return df

def detect_color_column(df: pd.DataFrame) -> Optional[str]:
    for cand in ["color","Color","colour","Colour","צבע","dominant_color","DominantColor","graph_color"]:
        if cand in df.columns:
            return cand
    return None

def detect_columns(df: pd.DataFrame) -> Dict[str, Any]:
    # Try to detect stimulus image columns and question columns
    image_cols = [c for c in df.columns if c.upper() in ["V1", "V2", "V3", "V4"]]
    if len(image_cols) == 0:
        warn_box("לא נמצאו עמודות V1-V4 עבור תמונות הגרפים. ניתן עדיין להריץ את הניסוי (יוצגו מצייני מקום).")
    context_col = None
    for cand in ["context", "Context", "CONTEXT", "title", "Title", "כותרת", "message", "Message"]:
        if cand in df.columns:
            context_col = cand
            break
    # Question structure: Q1, Q1_A..Q1_D, Q1_correct | repeated for Q2,Q3
    q_sets = []
    for qi in [1,2,3]:
        q = f"Q{qi}"
        if q in df.columns:
            opts = [f"Q{qi}_A", f"Q{qi}_B", f"Q{qi}_C", f"Q{qi}_D"]
            present_opts = [c for c in opts if c in df.columns]
            correct = f"Q{qi}_correct" if f"Q{qi}_correct" in df.columns else None
            # optional type column
            qtype_col = f"Q{qi}_type" if f"Q{qi}_type" in df.columns else None
            q_sets.append({"q": q, "opts": present_opts, "correct": correct, "qtype": qtype_col})
    return {"images": image_cols, "context": context_col, "qsets": q_sets, "color_col": detect_color_column(df)}

def pick_image(row: pd.Series, image_cols: List[str]) -> Optional[str]:
    for c in image_cols:
        val = str(row.get(c, "")).strip()
        if val and val.lower() != "nan":
            return val
    return None

def image_exists(path: str) -> bool:
    if not path:
        return False
    if path.startswith("http://") or path.startswith("https://"):
        return True  # Let browser fetch
    return os.path.exists(path)

def placeholder_image():
    st.markdown('<div class="center muted">תמונה אינה זמינה — בדקו את הנתיב בעמודות V1-V4</div>', unsafe_allow_html=True)
    st.image("https://placehold.co/800x500/EEE/AAA?text=Graph+Placeholder", use_container_width=True)

def show_timer(seconds_left: int, label: str):
    st.markdown(f'<div class="timer center">{label}: {seconds_left} שניות</div>', unsafe_allow_html=True)

def init_state():
    defaults = dict(
        phase="intro",
        group=None,               # 1,2,3
        trial_index=0,            # which graph (0..N-1)
        in_question_index=0,      # 0..(num_q-1) inside a trial
        timeline_start=None,      # time.time() when a phase started
        all_trials=[],            # list of trials
        q_per_graph={1:1, 2:3, 3:3},
        results=[],               # appended dicts
        ready_to_advance=False,
        admin=False,
    )
    for k,v in defaults.items():
        st.session_state.setdefault(k, v)

def reset_all():
    st.session_state.clear()
    init_state()

# =============================
# ---- Data structures --------
# =============================

@dataclass
class Trial:
    idx: int
    context_text: str
    image_path: Optional[str]
    questions: List[Dict[str, Any]]  # each: {"text": str, "options": List[str], "correct": Optional[str], "qtype": "content"|"color"}
    meta: Dict[str, Any]             # includes optional 'color_value'

# =============================
# ---- Experiment building ----
# =============================

def classify_qtype(text: str, explicit_type: Optional[str]) -> str:
    if explicit_type:
        t = str(explicit_type).strip().lower()
        if t in ["color","צבע","colour"]:
            return "color"
        if t in ["content","תוכן"]:
            return "content"
    # heuristic by text
    if "color" in text.lower() or "צבע" in text:
        return "color"
    return "content"

def build_trials(df: pd.DataFrame, colmap: Dict[str, Any]) -> List[Trial]:
    trials: List[Trial] = []
    image_cols = colmap["images"]
    context_col = colmap["context"]
    qsets = colmap["qsets"]
    color_col = colmap["color_col"]

    df_ = df.iloc[:MAX_GRAPHS].copy()
    if RANDOMIZE_ORDER:
        df_ = df_.sample(frac=1, random_state=None).reset_index(drop=True)

    for i, row in df_.iterrows():
        ctx = str(row.get(context_col, "")).strip() if context_col else ""
        img = pick_image(row, image_cols)
        color_value = str(row.get(color_col, "")).strip() if color_col else ""
        qs: List[Dict[str, Any]] = []
        for qdef in qsets:
            qtext = str(row.get(qdef["q"], "")).strip() if qdef["q"] in row else ""
            opts = [str(row.get(c, "")).strip() for c in qdef["opts"]] if qdef["opts"] else []
            opts = [o for o in opts if o != "" and o.lower() != "nan"]
            correct = str(row.get(qdef["correct"], "")).strip() if qdef["correct"] else None
            explicit_type = row.get(qdef.get("qtype")) if qdef.get("qtype") else None
            qtype = classify_qtype(qtext, explicit_type)
            qs.append({"text": qtext, "options": opts, "correct": correct, "qtype": qtype})
        if not qs:
            qs = [
                {"text": "מהו המסר המרכזי של הגרף?", "options": [], "correct": None, "qtype": "content"},
                {"text": "איזו קטגוריה גבוהה יותר?", "options": [], "correct": None, "qtype": "content"},
                {"text": "איזה צבע הופיע בגרף?", "options": [], "correct": None, "qtype": "color"},
            ]
        trials.append(Trial(
            idx=int(i),
            context_text=ctx,
            image_path=img,
            questions=qs,
            meta={**row.to_dict(), "color_value": color_value}
        ))
    return trials

# =============================
# ---- Persistence -------------
# =============================

def append_result(row: Dict[str, Any]):
    ensure_dirs()
    st.session_state["results"].append(row)
    df = pd.DataFrame([row])
    if not os.path.exists(RESULTS_CSV):
        df.to_csv(RESULTS_CSV, index=False, encoding="utf-8")
    else:
        df.to_csv(RESULTS_CSV, mode="a", header=False, index=False, encoding="utf-8")

def delay_category_for_group(group:int) -> str:
    if group == 1:
        return "immediate"
    if group == 2:
        return "short"
    return "long"

# =============================
# ---- Phases ------------------
# =============================

def phase_intro(df: pd.DataFrame):
    st.header(APP_TITLE)
    st.write("ברוכים הבאים לניסוי. קראו את ההנחיות ובחרו קבוצת ניסוי או הקצאה אקראית.")
    with st.expander("הנחיות", expanded=True):
        st.markdown("""
        - תראו עד **12 גרפים**. זמני הצגה קבועים מראש.
        - **קבוצה 1 (ביקורת):** צפייה בגרף 30 שניות → שאלה אחת מיידית (עד 2 דק').
        - **קבוצה 2 (טווח קצר):** גרף 30 שניות → מסך שחור 30 שניות → 3 שאלות (עד 2 דק' לשאלה).
        - **קבוצה 3 (טווח ארוך):** (הקשר → גרף → הקשר) × 12 → מסך שחור 30 שניות → 36 שאלות. לאחר כל גרף תתבקשו לדרג **רמת ביטחון** בזכירתו.
        """)
    col1, col2 = st.columns([1,2])
    with col1:
        randomize = st.checkbox("הקצאה אקראית לקבוצה")
    with col2:
        group = st.radio("בחרו קבוצה", [1,2,3], horizontal=True, index=0, format_func=lambda x: f"קבוצה {x}")
    if randomize:
        import random
        group = random.choice([1,2,3])
        st.caption(f"נבחרה אקראית: קבוצה {group}")
    name = st.text_input("שם/כינוי משתתף (אופציונלי):", value=st.session_state.get("participant_name",""))
    if name:
        st.session_state["participant_name"] = name

    if st.button("התחלה ▶️", type="primary"):
        st.session_state["group"] = group
        # Build trials
        colmap = detect_columns(df)
        trials = build_trials(df, colmap)
        if not trials:
            error_box("לא נמצאו גירויים תקינים בקובץ. ודאו שקיימת לפחות שורה אחת.")
            st.stop()
        st.session_state["all_trials"] = trials
        st.session_state["phase"] = "context_pre" if group in [2,3] else "graph"
        st.session_state["trial_index"] = 0
        st.session_state["in_question_index"] = 0
        st.session_state["timeline_start"] = time.time()
        st.experimental_rerun()

def current_trial() -> "Trial":
    idx = st.session_state["trial_index"]
    return st.session_state["all_trials"][idx]

def next_trial_or_phase_after_questions():
    group = st.session_state["group"]
    ti = st.session_state["trial_index"]
    total = len(st.session_state["all_trials"])
    if group in [1,2]:
        if ti+1 < total:
            st.session_state["trial_index"] = ti + 1
            st.session_state["in_question_index"] = 0
            st.session_state["phase"] = "context_pre" if group == 2 else "graph"
            st.session_state["timeline_start"] = time.time()
        else:
            st.session_state["phase"] = "summary"
    else:
        if ti+1 < total:
            st.session_state["trial_index"] = ti + 1
            st.session_state["phase"] = "context_pre"
            st.session_state["timeline_start"] = time.time()
        else:
            st.session_state["phase"] = "blackout_all"
            st.session_state["timeline_start"] = time.time()

def auto_advance_if_due(seconds_total: int):
    start = st.session_state["timeline_start"]
    elapsed = int(time.time() - start) if start else 0
    left = max(0, seconds_total - elapsed)
    show_timer(left, "זמן נותר")
    if left <= 0:
        st.session_state["ready_to_advance"] = True
    else:
        st.session_state["ready_to_advance"] = False
    return left

def phase_context_pre():
    t = current_trial()
    st.subheader("הקשר")
    if t.context_text:
        st.write(t.context_text)
    else:
        st.caption("אין טקסט הקשר לשורה זו.")
    auto_advance_if_due(DUR_CONTEXT)
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        st.session_state["phase"] = "graph"
        st.session_state["timeline_start"] = time.time()
        st.experimental_rerun()

def phase_graph(show_during_questions: bool):
    t = current_trial()
    st.subheader(f"גרף {st.session_state['trial_index']+1} מתוך {len(st.session_state['all_trials'])}")
    img = t.image_path
    if img and image_exists(img):
        st.image(img, use_container_width=True)
    else:
        placeholder_image()
    auto_advance_if_due(DUR_GRAPH)
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        group = st.session_state["group"]
        if group == 1:
            st.session_state["phase"] = "questions"
        elif group == 2:
            st.session_state["phase"] = "blackout_trial"
        elif group == 3:
            st.session_state["phase"] = "context_post"
        st.session_state["timeline_start"] = time.time()
        st.experimental_rerun()

def phase_context_post():
    t = current_trial()
    st.subheader("הקשר (חזרה)")
    if t.context_text:
        st.write(t.context_text)
    else:
        st.caption("אין טקסט הקשר לשורה זו.")
    auto_advance_if_due(DUR_CONTEXT)
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        # After context_post in group 3, ask for confidence
        if st.session_state["group"] == 3:
            st.session_state["phase"] = "confidence"
            st.session_state["timeline_start"] = time.time()
        else:
            next_trial_or_phase_after_questions()
        st.experimental_rerun()

def phase_blackout_trial():
    st.subheader("הפסקה")
    st.markdown('<div class="blackout"></div>', unsafe_allow_html=True)
    auto_advance_if_due(DUR_BLACK)
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        st.session_state["phase"] = "questions"
        st.session_state["timeline_start"] = time.time()
        st.experimental_rerun()

def record_answer(trial: "Trial", q_idx: int, answer: Any, rt_sec: float, correct_value: Optional[str]):
    # correctness (supports letters A/B/C/D or full text match)
    is_correct = None
    q = trial.questions[q_idx]
    options = q.get("options") or []
    if correct_value is not None and str(correct_value).strip() != "":
        def normalize(s): return str(s).strip().lower()
        ans_norm = normalize(answer)
        corr_norm = normalize(correct_value)
        # If correct given as letter, map to option text
        letters = ["a","b","c","d","א","ב","ג","ד"]
        if corr_norm in letters and options:
            idx = letters.index(corr_norm) % 4
            corr_text = options[idx] if idx < len(options) else ""
        else:
            corr_text = correct_value
        is_correct = (ans_norm == normalize(corr_text)) or (options and ans_norm == normalize(correct_value))
    # Append row
    row = dict(
        ts=now_ts(),
        app_version=VERSION,
        record_type="answer",
        participant_id=unique_participant_id(),
        participant_name=st.session_state.get("participant_name",""),
        group=st.session_state["group"],
        delay_category=delay_category_for_group(st.session_state["group"]),
        trial_index=st.session_state["trial_index"],
        question_index=q_idx,
        question_text=q.get("text",""),
        question_type=q.get("qtype","content"),
        answer=answer,
        is_correct=is_correct,
        rt_sec=round(rt_sec, 3),
        image_path=trial.image_path or "",
        context_text=trial.context_text or "",
        color_shown=trial.meta.get("color_value",""),
        meta_json=json.dumps(trial.meta, ensure_ascii=False),
    )
    append_result(row)

def record_confidence(trial: "Trial", confidence_percent: int):
    row = dict(
        ts=now_ts(),
        app_version=VERSION,
        record_type="confidence",
        participant_id=unique_participant_id(),
        participant_name=st.session_state.get("participant_name",""),
        group=st.session_state["group"],
        trial_index=st.session_state["trial_index"],
        confidence_percent=int(confidence_percent),
        image_path=trial.image_path or "",
        context_text=trial.context_text or "",
        meta_json=json.dumps(trial.meta, ensure_ascii=False),
    )
    append_result(row)

def phase_confidence():
    t = current_trial()
    st.subheader("הערכת זכירה")
    st.write("דרגו עד כמה אתם בטוחים שתזכרו את הגרף הזה בהמשך (באחוזים).")
    val = st.slider("רמת ביטחון בזכירת הגרף", 0, 100, 60, step=5)
    col1, col2 = st.columns(2)
    if col1.button("אישור"):
        record_confidence(t, val)
        next_trial_or_phase_after_questions()
        st.experimental_rerun()
    col2.caption("הדירוג נשמר לקובץ התוצאות.")

def phase_questions(show_graph: bool):
    group = st.session_state["group"]
    t = current_trial()
    if show_graph and t.image_path:
        st.image(t.image_path, use_column_width=True)
    elif show_graph and not t.image_path:
        placeholder_image()

    num_q = st.session_state["q_per_graph"][group]
    q_i = st.session_state["in_question_index"]
    question = t.questions[q_i] if q_i < len(t.questions) else {"text":"", "options":[], "correct":None, "qtype":"content"}

    st.subheader(f"שאלה {q_i+1} מתוך {num_q}")
    st.markdown(f'<div class="qbox">{question.get("text","")}</div>', unsafe_allow_html=True)

    start = st.session_state.get("timeline_start", time.time())
    elapsed = time.time() - start
    left = max(0, DUR_ANSWER_MAX - int(elapsed))
    show_timer(left, "זמן לשאלה")
    too_late = left <= 0

    answer_key = f"answer_{t.idx}_{q_i}"
    if question.get("options"):
        answer_value = st.radio("בחרו תשובה:", question["options"], key=answer_key, index=0 if question["options"] else None, horizontal=True)
    else:
        answer_value = st.text_input("התשובה שלכם:", key=answer_key)

    colA, colB = st.columns([1,1])
    with colA:
        can_submit = (answer_value is not None and str(answer_value).strip() != "") or too_late
        if st.button("שליחה", disabled=not can_submit) or too_late:
            rt = time.time() - start
            record_answer(t, q_i, (answer_value or ""), rt, question.get("correct"))
            st.session_state["in_question_index"] = q_i + 1
            st.session_state["timeline_start"] = time.time()
            if st.session_state["in_question_index"] >= num_q:
                st.session_state["in_question_index"] = 0
                next_trial_or_phase_after_questions()
            st.experimental_rerun()
    with colB:
        st.button("דלג", help="מעבר ללא תשובה (למחקר בלבד)")

def phase_blackout_all():
    st.subheader("מסך שחור — נא להמתין")
    st.markdown('<div class="blackout"></div>', unsafe_allow_html=True)
    auto_advance_if_due(DUR_BLACK)
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        st.session_state["phase"] = "all_questions"
        st.session_state["trial_index"] = 0
        st.session_state["in_question_index"] = 0
        st.session_state["timeline_start"] = time.time()
        st.experimental_rerun()

def phase_all_questions():
    total = len(st.session_state["all_trials"])
    t_idx = st.session_state["trial_index"]
    q_i = st.session_state["in_question_index"]
    t = current_trial()
    num_q = 3  # per spec
    st.subheader(f"שאלות — גרף {t_idx+1} מתוך {total}, שאלה {q_i+1} מתוך {num_q}")
    question = t.questions[q_i] if q_i < len(t.questions) else {"text":"", "options":[], "correct":None, "qtype":"content"}
    st.markdown(f'<div class="qbox">{question.get("text","")}</div>', unsafe_allow_html=True)

    start = st.session_state.get("timeline_start", time.time())
    elapsed = time.time() - start
    left = max(0, DUR_ANSWER_MAX - int(elapsed))
    show_timer(left, "זמן לשאלה")
    too_late = left <= 0

    answer_key = f"answer_all_{t.idx}_{q_i}"
    if question.get("options"):
        answer_value = st.radio("בחרו תשובה:", question["options"], key=answer_key, index=0 if question["options"] else None, horizontal=True)
    else:
        answer_value = st.text_input("התשובה שלכם:", key=answer_key)

    colA, colB = st.columns([1,1])
    with colA:
        can_submit = (answer_value is not None and str(answer_value).strip() != "") or too_late
        if st.button("שליחה", disabled=not can_submit) or too_late:
            rt = time.time() - start
            record_answer(t, q_i, (answer_value or ""), rt, question.get("correct"))
            st.session_state["in_question_index"] = q_i + 1
            st.session_state["timeline_start"] = time.time()
            if st.session_state["in_question_index"] >= num_q:
                st.session_state["in_question_index"] = 0
                if t_idx + 1 < total:
                    st.session_state["trial_index"] = t_idx + 1
                else:
                    st.session_state["phase"] = "summary"
            st.experimental_rerun()
    with colB:
        st.button("דלג", help="מעבר ללא תשובה")

def phase_summary():
    st.header("סיום הניסוי ✅")
    st.write("תודה רבה על השתתפותכם!")
    ensure_dirs()
    if os.path.exists(RESULTS_CSV):
        st.download_button(
            "הורדת נתונים (CSV)",
            data=open(RESULTS_CSV, "rb").read(),
            file_name=os.path.basename(RESULTS_CSV),
            mime="text/csv"
        )
    st.write("ניתן לסגור את החלון.")

# =============================
# ---- Admin -------------------
# =============================

def admin_panel():
    st.sidebar.markdown("---")
    st.sidebar.subheader("מסך מנהל 🛠️")
    code = st.sidebar.text_input("קוד מנהל", type="password")
    if st.sidebar.button("כניסה"):
        if code and ADMIN_CODE and code == ADMIN_CODE:
            st.session_state["admin"] = True
        else:
            warn_box("קוד מנהל שגוי או לא הוגדר.")
    if st.session_state.get("admin", False):
        st.sidebar.success("מצב מנהל פעיל")
        st.sidebar.button("איפוס ניסוי", on_click=reset_all)
        st.sidebar.write(f"משתתף: `{unique_participant_id()}`")
        if os.path.exists(RESULTS_CSV):
            st.sidebar.download_button(
                "הורדת תוצאות",
                data=open(RESULTS_CSV, "rb").read(),
                file_name=os.path.basename(RESULTS_CSV),
                mime="text/csv"
            )
        st.sidebar.markdown("### מצב")
        st.sidebar.code(f"RANDOMIZE_ORDER={RANDOMIZE_ORDER}")
        st.sidebar.markdown("### הגדרות זמנים")
        st.sidebar.caption("שינוי ערכים דורש הרצה מחדש של האפליקציה (דרך משתני סביבה).")
        st.sidebar.code(f"""DUR_GRAPH={DUR_GRAPH}\nDUR_CONTEXT={DUR_CONTEXT}\nDUR_BLACK={DUR_BLACK}\nDUR_ANSWER_MAX={DUR_ANSWER_MAX}\nMAX_GRAPHS={MAX_GRAPHS}""")
        st.sidebar.markdown("### קפיצה שלב")
        phases = ["intro","context_pre","graph","context_post","confidence","blackout_trial","questions","blackout_all","all_questions","summary"]
        sel = st.sidebar.selectbox("בחר שלב", phases, index=phases.index(st.session_state["phase"]))
        if st.sidebar.button("מעבר"):
            st.session_state["phase"] = sel
            st.session_state["timeline_start"] = time.time()
            st.experimental_rerun()

# =============================
# ---- Main --------------------
# =============================

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="collapsed", page_icon="📊")
    rtl_css()
    init_state()
    admin_panel()  # sidebar
    st.caption(f"גרסה {VERSION}")

    # Load and validate CSV
    df = load_csv("MemoryTest.csv")
    colmap = detect_columns(df)
    if not colmap["images"]:
        warn_box("עמודות V1-V4 אינן קיימות — ודאו שה-CSV שלכם כולל לפחות אחת מהעמודות V1..V4 עם נתיבי תמונות תקינים.")
    else:
        missing = 0
        for p in df[colmap["images"]].fillna("").astype(str).values.flatten().tolist():
            if p and (not p.startswith("http")) and (not os.path.exists(p)):
                missing += 1
                if missing > 3:
                    break
        if missing > 0:
            warn_box("נמצאו נתיבי תמונות שאינם קיימים במערכת. ודאו שהתמונות זמינות מקומית או כ-URL.")

    # Router
    phase = st.session_state["phase"]
    group = st.session_state["group"]
    if phase == "intro":
        phase_intro(df); return

    if not st.session_state.get("all_trials"):
        st.session_state["all_trials"] = build_trials(df, colmap)

    if phase == "context_pre":
        phase_context_pre()
    elif phase == "graph":
        phase_graph(show_during_questions=(group in [1,2]))
    elif phase == "context_post":
        phase_context_post()
    elif phase == "confidence":
        phase_confidence()
    elif phase == "blackout_trial":
        phase_blackout_trial()
    elif phase == "questions":
        phase_questions(show_graph=(group in [1,2]))
    elif phase == "blackout_all":
        phase_blackout_all()
    elif phase == "all_questions":
        phase_all_questions()
    elif phase == "summary":
        phase_summary()
    else:
        warn_box("שלב לא מוכר — מאפסים את הניסוי.")
        reset_all()

if __name__ == "__main__":
    main()
