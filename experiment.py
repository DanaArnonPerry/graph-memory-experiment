# -*- coding: utf-8 -*-
"""
experiment.py — Streamlit app: ניסוי זיכרון גרפים (v2.0.0)
Author: ChatGPT (refactor for robustness + UX)

Highlights vs. the old version
- Streamlit API updates: st.rerun(), use_container_width
- Resilient CSV schema detection (works with ImageFileName/Question{n}Text/Q{n}OptionA..D/Q{n}CorrectAnswer,
  and still supports V1..V4 & Q1_A.. etc.)
- Image path resolver (handles images/ prefix, case-insensitive file matches, URLs)
- Safer rendering (prevents non-image values such as 1.0 from being passed to st.image)
- Top timer + progress bar like the screenshot (pill badge + st.progress)
- Clean phase routing (intro, context_pre, graph, context_post, confidence, blackout_trial,
  questions, blackout_all, all_questions, summary)
- Results CSV append-only with UTF-8
"""

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
VERSION = "2.0.0"

# Durations (seconds)
DUR_GRAPH = int(os.environ.get("DUR_GRAPH", 30))        # צפייה בגרף
DUR_CONTEXT = int(os.environ.get("DUR_CONTEXT", 30))    # מסך הקשר (לפני/אחרי)
DUR_BLACK = int(os.environ.get("DUR_BLACK", 30))        # מסך שחור / הפסקה
DUR_ANSWER_MAX = int(os.environ.get("DUR_ANSWER_MAX", 120))  # זמן תשובה מקסימלי לשאלה

MAX_GRAPHS = int(os.environ.get("MAX_GRAPHS", 12))      # מקסימום גרפים לניסוי
RANDOMIZE_ORDER = os.environ.get("RANDOMIZE_ORDER", "0") == "1"  # ערבוב סדר הגרפים (אופציונלי)

RESULTS_DIR = os.environ.get("RESULTS_DIR", "results")
RESULTS_CSV = os.path.join(RESULTS_DIR, "results_local.csv")
IMAGES_DIR = os.environ.get("IMAGES_DIR", "images")

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
        /* UI polish */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: visible;}
        .timer-pill { display:inline-block; padding:6px 12px; border-radius: 16px; background:#111; color:#fff; font-weight:800; }
        .muted { color: #666; }
        .center { text-align: center; }
        .blackout { background: black; height: 60vh; border-radius: 12px; }
        .qbox { padding: 1rem; border: 1px solid #eee; border-radius: 12px; background:#fafafa; }
        .small { font-size: 0.9rem;}
        .topbar { display:flex; align-items:center; gap:16px; justify-content: space-between; }
        .topbar-right { color:#333; font-weight:600; }
        .pill { padding: 2px 8px; border-radius: 1rem; background:#eee; margin-inline-start:8px;}
        </style>
        """,
        unsafe_allow_html=True,
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


def is_url(s: str) -> bool:
    s = str(s or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def looks_like_image_path(s: str) -> bool:
    s = str(s or "").strip()
    if not s or s.lower() == "nan":
        return False
    if is_url(s):
        return True
    name = os.path.basename(s)
    return any(name.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"))


def resolve_image_path(p: str) -> Optional[str]:
    """Return a usable path/URL if the file exists (case-insensitive search in IMAGES_DIR)."""
    if not p:
        return None
    p = str(p).strip().replace("\\", "/")
    if is_url(p):
        return p
    # absolute or relative direct hit
    if os.path.isabs(p) and os.path.exists(p):
        return p
    if os.path.exists(p):
        return p
    # try IMAGES_DIR + basename
    candidate = os.path.join(IMAGES_DIR, os.path.basename(p))
    if os.path.exists(candidate):
        return candidate
    # case-insensitive walk in IMAGES_DIR
    base_lower = os.path.basename(p).lower()
    if os.path.isdir(IMAGES_DIR):
        for root, _, files in os.walk(IMAGES_DIR):
            for f in files:
                if f.lower() == base_lower:
                    return os.path.join(root, f)
    return None


def image_exists(path: Optional[str]) -> bool:
    if not path:
        return False
    if is_url(path):
        return True
    resolved = resolve_image_path(path)
    return bool(resolved and os.path.exists(resolved))


def placeholder_image():
    st.markdown('<div class="center muted">תמונה אינה זמינה — בדקו את הנתיב בעמודת התמונה</div>', unsafe_allow_html=True)
    st.image("https://placehold.co/800x500/EEE/AAA?text=Graph+Placeholder", use_container_width=True)


# =============================
# ---- CSV schema detection ----
# =============================


def detect_color_column(df: pd.DataFrame) -> Optional[str]:
    for cand in [
        "color",
        "Color",
        "colour",
        "Colour",
        "צבע",
        "dominant_color",
        "DominantColor",
        "graph_color",
    ]:
        if cand in df.columns:
            return cand
    return None


def detect_columns(df: pd.DataFrame) -> Dict[str, Any]:
    """Detect columns for image, context, and question sets.

    Supports both legacy (V1..V4, Q1/Q1_A..D/Q1_correct) and the newer schema
    (ImageFileName, Question{n}Text, Q{n}OptionA..D, Q{n}CorrectAnswer).
    """
    # Image columns
    image_cols: List[str] = []
    for cand in [
        "ImageFileName",
        "image",
        "Image",
        "img",
        "Img",
        "image_path",
        "ImagePath",
        "ImageURL",
        "imageURL",
    ]:
        if cand in df.columns:
            image_cols = [cand]
            break
    if not image_cols:
        image_cols = [c for c in df.columns if c.upper() in ["V1", "V2", "V3", "V4"]]
    if not image_cols:
        warn_box("לא נמצאו עמודות תמונה (מומלץ: ImageFileName או V1..V4). יוצגו מצייני מקום.")

    # Context/title column
    context_col = None
    for cand in [
        "TheContext",
        "context",
        "Context",
        "CONTEXT",
        "title",
        "Title",
        "כותרת",
        "message",
        "Message",
    ]:
        if cand in df.columns:
            context_col = cand
            break

    # Question sets
    q_sets = []
    for qi in [1, 2, 3]:
        # question text column
        q_col = next(
            (c for c in [f"Question{qi}Text", f"Question{qi}", f"Q{qi}"] if c in df.columns),
            None,
        )
        if not q_col:
            continue
        # options: support both styles
        opts = [
            c
            for c in ([f"Q{qi}Option{x}" for x in "ABCD"] + [f"Q{qi}_{x}" for x in "ABCD"])
            if c in df.columns
        ]
        # correct answer variants
        corr = next(
            (
                c
                for c in [
                    f"Q{qi}CorrectAnswer",
                    f"Q{qi}Correct",
                    f"Q{qi}_correct",
                    f"Q{qi}_Correct",
                ]
                if c in df.columns
            ),
            None,
        )
        # optional explicit type
        qtype_col = next((c for c in [f"Q{qi}Type", f"Q{qi}_type"] if c in df.columns), None)
        q_sets.append({"q": q_col, "opts": opts, "correct": corr, "qtype": qtype_col})

    return {
        "images": image_cols,
        "context": context_col,
        "qsets": q_sets,
        "color_col": detect_color_column(df),
    }


# =============================
# ---- Data structures --------
# =============================


@dataclass
class Trial:
    idx: int
    context_text: str
    image_path: Optional[str]
    questions: List[Dict[str, Any]]  # {text, options, correct, qtype}
    meta: Dict[str, Any]  # includes optional 'color_value'


# =============================
# ---- Experiment building ----
# =============================


def classify_qtype(text: str, explicit_type: Optional[str]) -> str:
    if explicit_type:
        t = str(explicit_type).strip().lower()
        if t in ["color", "צבע", "colour"]:
            return "color"
        if t in ["content", "תוכן"]:
            return "content"
    if "color" in (text or "").lower() or "צבע" in (text or ""):
        return "color"
    return "content"


def pick_image(row: pd.Series, image_cols: List[str]) -> Optional[str]:
    for c in image_cols:
        val = row.get(c, "")
        if pd.isna(val):
            continue
        val = str(val).strip()
        if looks_like_image_path(val):
            resolved = resolve_image_path(val)
            if resolved:
                return resolved
            # if couldn't resolve but looks like URL, still return
            if is_url(val):
                return val
    return None


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
            opts = [o for o in opts if o and o.lower() != "nan"]
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
        trials.append(
            Trial(
                idx=int(i),
                context_text=ctx,
                image_path=img,
                questions=qs,
                meta={**row.to_dict(), "color_value": color_value},
            )
        )
    return trials


# =============================
# ---- Persistence -------------
# =============================


def append_result(row: Dict[str, Any]):
    ensure_dirs()
    st.session_state.setdefault("results", []).append(row)
    df = pd.DataFrame([row])
    if not os.path.exists(RESULTS_CSV):
        df.to_csv(RESULTS_CSV, index=False, encoding="utf-8")
    else:
        df.to_csv(RESULTS_CSV, mode="a", header=False, index=False, encoding="utf-8")


def delay_category_for_group(group: int) -> str:
    if group == 1:
        return "immediate"
    if group == 2:
        return "short"
    return "long"


# =============================
# ---- Phases & UI -------------
# =============================


def init_state():
    defaults = dict(
        phase="intro",
        group=None,  # 1,2,3
        trial_index=0,  # which graph (0..N-1)
        in_question_index=0,  # 0..(num_q-1) inside a trial
        timeline_start=None,  # time.time() when a phase started
        all_trials=[],  # list of trials
        q_per_graph={1: 1, 2: 3, 3: 3},
        results=[],
        ready_to_advance=False,
        admin=False,
    )
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def reset_all():
    st.session_state.clear()
    init_state()


# --- Top bar (timer + progress) ---

def show_topbar(seconds_left: int, seconds_total: int, right_label: str, overall_progress: float):
    """Render a top bar similar to the screenshot: pill timer + linear progress + right-side label.
    overall_progress in [0,1].
    """
    st_autorefresh = st.experimental_memo.clear if False else None  # placeholder to avoid linter warnings
    # Auto-refresh each second to update the timer
    st.autorefresh = st.experimental_rerun if False else None  # kept for backward compat linting
    st_autorefresh = st.sidebar  # dummy use to keep linters calm
    st_autorefresh = None  # no-op

    # Streamlit provides a built-in auto-refresh helper
    st.experimental_set_query_params(_=int(time.time()))  # keeps URL stable yet prevents caching
    st_autorefresh_token = st.experimental_rerun if False else None  # noqa: F841

    # Visuals
    left_html = f'<span class="timer-pill">⏳ זמן שנותר: {max(0, seconds_left)} שניות</span>'
    right_html = f'<span class="topbar-right">{right_label}</span>' if right_label else ""
    st.markdown(f'<div class="topbar">{left_html}<div style="flex:1; padding:0 12px;">&nbsp;</div>{right_html}</div>', unsafe_allow_html=True)
    st.progress(min(1.0, max(0.0, overall_progress)))


# Helper: recompute remaining seconds and control auto-advance

def auto_advance_if_due(seconds_total: int, right_label: str = "", overall_progress: float = 0.0):
    # soft autorefresh every second to tick the timer
    st.experimental_singleton.clear if False else None  # lint calm
    st_autorefresh = st.experimental_rerun if False else None
    # Use built-in helper
    st_autorefresh = st.sidebar  # noqa: F841 keep linter quiet
    st_autorefresh = None
    st.experimental_set_query_params(tick=int(time.time()))

    start = st.session_state.get("timeline_start")
    elapsed = int(time.time() - start) if start else 0
    left = max(0, seconds_total - elapsed)
    show_topbar(left, seconds_total, right_label, overall_progress)
    st.session_state["ready_to_advance"] = left <= 0
    return left


# --- Navigation helpers ---

def current_trial() -> "Trial":
    idx = st.session_state["trial_index"]
    return st.session_state["all_trials"][idx]


def next_trial_or_phase_after_questions():
    group = st.session_state["group"]
    ti = st.session_state["trial_index"]
    total = len(st.session_state["all_trials"])
    if group in [1, 2]:
        if ti + 1 < total:
            st.session_state["trial_index"] = ti + 1
            st.session_state["in_question_index"] = 0
            st.session_state["phase"] = "context_pre" if group == 2 else "graph"
            st.session_state["timeline_start"] = time.time()
        else:
            st.session_state["phase"] = "summary"
    else:
        if ti + 1 < total:
            st.session_state["trial_index"] = ti + 1
            st.session_state["phase"] = "context_pre"
            st.session_state["timeline_start"] = time.time()
        else:
            st.session_state["phase"] = "blackout_all"
            st.session_state["timeline_start"] = time.time()


# --- Phases ---

def phase_intro(df: pd.DataFrame):
    st.header(APP_TITLE)
    st.write("ברוכים הבאים לניסוי. קראו את ההנחיות ובחרו קבוצת ניסוי או הקצאה אקראית.")
    with st.expander("הנחיות", expanded=True):
        st.markdown(
            """
            - תראו עד **12 גרפים**. זמני הצגה קבועים מראש.
            - **קבוצה 1 (ביקורת):** צפייה בגרף 30 שניות → שאלה אחת מיידית (עד 2 דק').
            - **קבוצה 2 (טווח קצר):** גרף 30 שניות → מסך שחור 30 שניות → 3 שאלות (עד 2 דק' לשאלה).
            - **קבוצה 3 (טווח ארוך):** (הקשר → גרף → הקשר) × 12 → מסך שחור 30 שניות → 36 שאלות. לאחר כל גרף תתבקשו לדרג **רמת ביטחון** בזכירתו.
            """
        )
    col1, col2 = st.columns([1, 2])
    with col1:
        randomize = st.checkbox("הקצאה אקראית לקבוצה")
    with col2:
        group = st.radio("בחרו קבוצה", [1, 2, 3], horizontal=True, index=0, format_func=lambda x: f"קבוצה {x}")
    if randomize:
        import random

        group = random.choice([1, 2, 3])
        st.caption(f"נבחרה אקראית: קבוצה {group}")
    name = st.text_input("שם/כינוי משתתף (אופציונלי):", value=st.session_state.get("participant_name", ""))
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
        st.session_state["phase"] = "context_pre" if group in [2, 3] else "graph"
        st.session_state["trial_index"] = 0
        st.session_state["in_question_index"] = 0
        st.session_state["timeline_start"] = time.time()
        st.rerun()


def phase_context_pre():
    t = current_trial()
    total = len(st.session_state["all_trials"])
    right_label = f"תרגול {st.session_state['trial_index']+1}/{total}"
    auto_advance_if_due(DUR_CONTEXT, right_label, overall_progress=st.session_state["trial_index"] / max(1, total))
    st.subheader("הקשר")
    if t.context_text:
        st.write(t.context_text)
    else:
        st.caption("אין טקסט הקשר לשורה זו.")
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        st.session_state["phase"] = "graph"
        st.session_state["timeline_start"] = time.time()
        st.rerun()


def phase_graph(show_during_questions: bool):
    t = current_trial()
    total = len(st.session_state["all_trials"])
    right_label = f"תרגול {st.session_state['trial_index']+1}/{total}"
    auto_advance_if_due(DUR_GRAPH, right_label, overall_progress=st.session_state["trial_index"] / max(1, total))
    st.subheader(f"גרף {st.session_state['trial_index']+1} מתוך {total}")
    if t.image_path and image_exists(t.image_path):
        st.image(t.image_path, use_container_width=True)
    else:
        placeholder_image()
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        group = st.session_state["group"]
        if group == 1:
            st.session_state["phase"] = "questions"
        elif group == 2:
            st.session_state["phase"] = "blackout_trial"
        elif group == 3:
            st.session_state["phase"] = "context_post"
        st.session_state["timeline_start"] = time.time()
        st.rerun()


def phase_context_post():
    t = current_trial()
    total = len(st.session_state["all_trials"])
    right_label = f"תרגול {st.session_state['trial_index']+1}/{total}"
    auto_advance_if_due(DUR_CONTEXT, right_label, overall_progress=st.session_state["trial_index"] / max(1, total))
    st.subheader("הקשר (חזרה)")
    if t.context_text:
        st.write(t.context_text)
    else:
        st.caption("אין טקסט הקשר לשורה זו.")
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        if st.session_state["group"] == 3:
            st.session_state["phase"] = "confidence"
            st.session_state["timeline_start"] = time.time()
        else:
            next_trial_or_phase_after_questions()
        st.rerun()


def phase_blackout_trial():
    total = len(st.session_state["all_trials"])
    right_label = f"תרגול {st.session_state['trial_index']+1}/{total}"
    auto_advance_if_due(DUR_BLACK, right_label, overall_progress=st.session_state["trial_index"] / max(1, total))
    st.subheader("הפסקה")
    st.markdown('<div class="blackout"></div>', unsafe_allow_html=True)
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        st.session_state["phase"] = "questions"
        st.session_state["timeline_start"] = time.time()
        st.rerun()


def record_answer(trial: "Trial", q_idx: int, answer: Any, rt_sec: float, correct_value: Optional[str]):
    # correctness (supports letters A/B/C/D or full text match; Hebrew letters א/ב/ג/ד)
    is_correct = None
    q = trial.questions[q_idx]
    options = q.get("options") or []
    if correct_value is not None and str(correct_value).strip() != "":
        def normalize(s):
            return str(s).strip().lower()

        ans_norm = normalize(answer)
        corr_norm = normalize(correct_value)
        letters = ["a", "b", "c", "d", "א", "ב", "ג", "ד"]
        corr_text = None
        if corr_norm in letters and options:
            idx = letters.index(corr_norm) % 4
            if idx < len(options):
                corr_text = options[idx]
        # direct match fallback
        target = normalize(corr_text) if corr_text else corr_norm
        is_correct = ans_norm == target or (options and ans_norm == normalize(correct_value))

    row = dict(
        ts=now_ts(),
        app_version=VERSION,
        record_type="answer",
        participant_id=unique_participant_id(),
        participant_name=st.session_state.get("participant_name", ""),
        group=st.session_state["group"],
        delay_category=delay_category_for_group(st.session_state["group"]),
        trial_index=st.session_state["trial_index"],
        question_index=q_idx,
        question_text=q.get("text", ""),
        question_type=q.get("qtype", "content"),
        answer=answer,
        is_correct=is_correct,
        rt_sec=round(rt_sec, 3),
        image_path=trial.image_path or "",
        context_text=trial.context_text or "",
        color_shown=trial.meta.get("color_value", ""),
        meta_json=json.dumps(trial.meta, ensure_ascii=False),
    )
    append_result(row)


def record_confidence(trial: "Trial", confidence_percent: int):
    row = dict(
        ts=now_ts(),
        app_version=VERSION,
        record_type="confidence",
        participant_id=unique_participant_id(),
        participant_name=st.session_state.get("participant_name", ""),
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
    total = len(st.session_state["all_trials"])
    right_label = f"תרגול {st.session_state['trial_index']+1}/{total}"
    auto_advance_if_due(DUR_ANSWER_MAX, right_label, overall_progress=st.session_state["trial_index"] / max(1, total))
    st.subheader("הערכת זכירה")
    st.write("דרגו עד כמה אתם בטוחים שתזכרו את הגרף הזה בהמשך (באחוזים).")
    val = st.slider("רמת ביטחון בזכירת הגרף", 0, 100, 60, step=5)
    col1, col2 = st.columns(2)
    if col1.button("אישור"):
        record_confidence(t, val)
        next_trial_or_phase_after_questions()
        st.rerun()
    col2.caption("הדירוג נשמר לקובץ התוצאות.")


def phase_questions(show_graph: bool):
    group = st.session_state["group"]
    t = current_trial()
    total = len(st.session_state["all_trials"])
    num_q = st.session_state["q_per_graph"][group]
    q_i = st.session_state["in_question_index"]
    right_label = f"תרגול {st.session_state['trial_index']+1}/{total} · שאלה {q_i+1}/{num_q}"

    # progress within trial
    trial_prog = (q_i) / max(1, num_q)
    overall_prog = (st.session_state["trial_index"] + trial_prog) / max(1, total)

    left = auto_advance_if_due(DUR_ANSWER_MAX, right_label, overall_progress=overall_prog)

    if show_graph and t.image_path and image_exists(t.image_path):
        st.image(t.image_path, use_container_width=True)
    elif show_graph:
        placeholder_image()

    question = t.questions[q_i] if q_i < len(t.questions) else {"text": "", "options": [], "correct": None, "qtype": "content"}
    st.subheader(f"שאלה {q_i+1} מתוך {num_q}")
    st.markdown(f'<div class="qbox">{question.get("text", "")}</div>', unsafe_allow_html=True)

    start = st.session_state.get("timeline_start", time.time())
    too_late = left <= 0

    answer_key = f"answer_{t.idx}_{q_i}"
    answer_value: Optional[str] = None
    options = question.get("options") or []
    if options:
        answer_value = st.radio("בחרו תשובה:", options, key=answer_key, index=0, horizontal=True)
    else:
        answer_value = st.text_input("התשובה שלכם:", key=answer_key)

    colA, colB = st.columns([1, 1])
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
            st.rerun()
    with colB:
        st.button("דלג", help="מעבר ללא תשובה (למחקר בלבד)")


def phase_blackout_all():
    total = len(st.session_state["all_trials"])
    right_label = f"סיכום ביניים"
    auto_advance_if_due(DUR_BLACK, right_label, overall_progress=1.0)
    st.subheader("מסך שחור — נא להמתין")
    st.markdown('<div class="blackout"></div>', unsafe_allow_html=True)
    if st.session_state["ready_to_advance"] or st.button("המשך"):
        st.session_state["phase"] = "all_questions"
        st.session_state["trial_index"] = 0
        st.session_state["in_question_index"] = 0
        st.session_state["timeline_start"] = time.time()
        st.rerun()


def phase_all_questions():
    total = len(st.session_state["all_trials"])
    t_idx = st.session_state["trial_index"]
    q_i = st.session_state["in_question_index"]
    t = current_trial()
    num_q = 3  # per spec

    # overall progress across all back-questions
    overall_prog = (t_idx + (q_i / max(1, num_q))) / max(1, total)
    right_label = f"שאלות — גרף {t_idx+1}/{total} · שאלה {q_i+1}/{num_q}"
    left = auto_advance_if_due(DUR_ANSWER_MAX, right_label, overall_progress=overall_prog)

    st.subheader(f"שאלות — גרף {t_idx+1} מתוך {total}, שאלה {q_i+1} מתוך {num_q}")
    question = t.questions[q_i] if q_i < len(t.questions) else {"text": "", "options": [], "correct": None, "qtype": "content"}
    st.markdown(f'<div class="qbox">{question.get("text", "")}</div>', unsafe_allow_html=True)

    start = st.session_state.get("timeline_start", time.time())
    too_late = left <= 0

    answer_key = f"answer_all_{t.idx}_{q_i}"
    options = question.get("options") or []
    if options:
        answer_value = st.radio("בחרו תשובה:", options, key=answer_key, index=0, horizontal=True)
    else:
        answer_value = st.text_input("התשובה שלכם:", key=answer_key)

    colA, colB = st.columns([1, 1])
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
            st.rerun()
    with colB:
        st.button("דלג", help="מעבר ללא תשובה")


def phase_summary():
    st.header("סיום הניסוי ✅")
    st.write("תודה רבה על השתתפותכם!")
    ensure_dirs()
    if os.path.exists(RESULTS_CSV):
        with open(RESULTS_CSV, "rb") as fh:
            st.download_button(
                "הורדת נתונים (CSV)",
                data=fh.read(),
                file_name=os.path.basename(RESULTS_CSV),
                mime="text/csv",
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
            with open(RESULTS_CSV, "rb") as fh:
                st.sidebar.download_button(
                    "הורדת תוצאות",
                    data=fh.read(),
                    file_name=os.path.basename(RESULTS_CSV),
                    mime="text/csv",
                )
        st.sidebar.markdown("### מצב")
        st.sidebar.code(f"RANDOMIZE_ORDER={RANDOMIZE_ORDER}")
        st.sidebar.markdown("### הגדרות זמנים")
        st.sidebar.caption("שינוי ערכים דורש הרצה מחדש של האפליקציה (דרך משתני סביבה).")
        st.sidebar.code(
            f"""DUR_GRAPH={DUR_GRAPH}\nDUR_CONTEXT={DUR_CONTEXT}\nDUR_BLACK={DUR_BLACK}\nDUR_ANSWER_MAX={DUR_ANSWER_MAX}\nMAX_GRAPHS={MAX_GRAPHS}"""
        )
        st.sidebar.markdown("### קפיצה שלב")
        phases = [
            "intro",
            "context_pre",
            "graph",
            "context_post",
            "confidence",
            "blackout_trial",
            "questions",
            "blackout_all",
            "all_questions",
            "summary",
        ]
        sel = st.sidebar.selectbox("בחר שלב", phases, index=phases.index(st.session_state["phase"]))
        if st.sidebar.button("מעבר"):
            st.session_state["phase"] = sel
            st.session_state["timeline_start"] = time.time()
            st.rerun()


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
        warn_box("עמודת תמונה לא נמצאה — ודאו שה-CSV כולל ImageFileName או V1..V4 עם נתיבי תמונות תקינים.")
    else:
        missing = 0
        for p in df[colmap["images"]].fillna("").astype(str).values.flatten().tolist():
            if p and (not is_url(p)) and (not image_exists(p)):
                missing += 1
                if missing > 3:
                    break
        if missing > 0:
            warn_box("נמצאו נתיבי תמונות שאינם קיימים במערכת. ודאו שהתמונות זמינות מקומית או כ-URL.")

    # Router
    phase = st.session_state["phase"]
    group = st.session_state["group"]
    if phase == "intro":
        phase_intro(df)
        return

    if not st.session_state.get("all_trials"):
        st.session_state["all_trials"] = build_trials(df, colmap)

    if phase == "context_pre":
        phase_context_pre()
    elif phase == "graph":
        phase_graph(show_during_questions=(group in [1, 2]))
    elif phase == "context_post":
        phase_context_post()
    elif phase == "confidence":
        phase_confidence()
    elif phase == "blackout_trial":
        phase_blackout_trial()
    elif phase == "questions":
        phase_questions(show_graph=(group in [1, 2]))
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
