\
from __future__ import annotations
import time, json, os
import pandas as pd
import streamlit as st
from helpers import (
    DUR_GRAPH, DUR_CONTEXT, DUR_BLACK, DUR_ANSWER_MAX,
    ensure_id, default_v_for_pid, load_items, extract_questions, now_ms
)
from storage import append_result_row, download_full_results

st.set_page_config(page_title="graph-memory-experiment", layout="wide")

# ---- Sidebar: setup ----
st.sidebar.title("⚙️ הגדרות")
csv_path = st.sidebar.text_input("נתיב לקובץ CSV", value="data/MemoryTest.csv")
group = st.sidebar.selectbox("בחרי קבוצה לניסוי", options=[1,2,3], index=0, format_func=lambda x: f"קבוצה {x}")
participant_id = st.sidebar.text_input("מזהה משתתף", value=st.session_state.get("participant_id",""))
if st.sidebar.button("הקצה מזהה חדש"):
    st.session_state["participant_id"] = ""
participant_id = ensure_id()
v_override = st.sidebar.selectbox("בחרי עמודת ויזואליזציות (V1..V4)", options=["AUTO","V1","V2","V3","V4"], index=0)
if v_override == "AUTO":
    v_col = default_v_for_pid(participant_id)
else:
    v_col = v_override

st.sidebar.markdown(f"**עמודת V לנבדק:** `{v_col}`")
st.sidebar.markdown("---")
mode = st.sidebar.radio("מצב", ["ניסוי", "מנהל"], index=0)

# --- Load data
@st.cache_data(show_spinner=False)
def _load_df(path: str):
    return load_items(path)

try:
    df = _load_df(csv_path)
except Exception as e:
    st.error(f"קריאת הקובץ נכשלה: {e}")
    st.stop()

# Keep only rows that have a URL in the chosen V column
if v_col not in df.columns:
    st.error(f"העמודה '{v_col}' לא קיימת ב-CSV. עמודות קיימות: {list(df.columns)}")
    st.stop()

items = df[df[v_col].notna()].reset_index(drop=True)
NUM_GRAPHS = min(12, len(items))

# Session init
if "phase" not in st.session_state:
    st.session_state["phase"] = "intro"  # intro -> running -> done
if "step" not in st.session_state:
    st.session_state["step"] = ("context", 0)  # (phase_name, graph_index) or ("questions", queue_index)
if "step_started_ms" not in st.session_state:
    st.session_state["step_started_ms"] = now_ms()
if "question_queue" not in st.session_state:
    st.session_state["question_queue"] = []

def reset_run():
    st.session_state["phase"] = "intro"
    st.session_state["step"] = ("context", 0)
    st.session_state["step_started_ms"] = now_ms()
    st.session_state["question_queue"] = []

def time_left(limit_s: int):
    elapsed_s = (now_ms() - st.session_state["step_started_ms"]) / 1000.0
    remaining = max(0, limit_s - elapsed_s)
    # auto refresh every second to update timers
    st.experimental_rerun() if remaining == 0 else st.autorefresh(interval=1000, key=f"tick-{st.session_state['step']}")
    return remaining

def go_next(step=None):
    st.session_state["step_started_ms"] = now_ms()
    if step is not None:
        st.session_state["step"] = step

def append_question_queue_for_graph(gidx: int):
    # push q1..q3 for this graph
    for qn in [1,2,3]:
        st.session_state["question_queue"].append((gidx, qn))

def record_answer(graph_order_index: int, graph_row_index: int, graph_id: str, qn: int, q_text: str, options: dict, chosen: str|None, correct_letter: str|None, start_ms: int):
    response_time_ms = now_ms() - start_ms
    chosen_text = options.get(chosen, "") if chosen else ""
    correct_text = options.get(correct_letter, "") if correct_letter else ""
    is_correct = (chosen is not None and correct_letter is not None and chosen == correct_letter)
    row = {
        "timestamp_iso": pd.Timestamp.utcnow().isoformat(),
        "participant_id": participant_id,
        "group": group,
        "v_col": v_col,
        "graph_order_index": graph_order_index,
        "graph_row_index": graph_row_index,
        "graph_id": graph_id,
        "question_number": qn,
        "question_text": q_text,
        "option_chosen_letter": chosen if chosen else "",
        "option_chosen_text": chosen_text,
        "correct_letter": correct_letter if correct_letter else "",
        "correct_text": correct_text,
        "is_correct": bool(is_correct),
        "response_time_ms": int(response_time_ms),
    }
    append_result_row(row)

# --------------------- UI Pages ----------------------
def page_intro():
    st.title("ניסוי זיכרון גרפים")
    st.subheader("graph-memory-experiment")
    st.markdown("""
ברוכה הבאה! בניסוי זה יוצגו לך גרפים קצרים עם הקשר, ולאחר מכן תישאלי שאלות בחירה מרובה.
משך הצגת כל גרף: **30 שניות**. שקף ההקשר: עד **2 שניות**. לכל שאלה ניתן לענות עד **2 דקות**.  
לחצי על **המשך** כדי להתחיל.
    """)
    left, right = st.columns([1,2])
    with left:
        st.write("**פרטי משתתף**")
        st.write(f"מזהה משתתף: `{participant_id}`")
        st.write(f"קבוצה: **{group}**")
        st.write(f"עמודת גרפים: **{v_col}**")
    with right:
        st.image("images/imageChart1DC.PNG", caption="דוגמת גרף", use_column_width=True)
    if st.button("המשך ▶️"):
        st.session_state["phase"] = "running"
        go_next(("context", 0))

def show_context(idx: int, post=False):
    row = items.iloc[idx]
    st.subheader(f"שקף הקשר {'(אחרי הגרף)' if post else ''} — גרף {idx+1}/{NUM_GRAPHS}")
    ctx = row.get("TheContext", "")
    st.info(ctx if isinstance(ctx, str) else "")
    remaining = time_left(DUR_CONTEXT)
    st.markdown(f"⏳ עובר למסך הבא בעוד **{int(remaining)}** שניות.")
    if st.button("המשך ▶️"):
        if group == 3 and not post:
            go_next(("graph", idx))
        elif group == 3 and post:
            # after post-context for G3
            if idx+1 < NUM_GRAPHS:
                go_next(("context", idx+1))
            else:
                go_next(("black", 0))
        else:
            # groups 1/2: context -> graph
            go_next(("graph", idx))

    # auto-advance
    if remaining <= 0:
        if group == 3 and not post:
            go_next(("graph", idx))
        elif group == 3 and post:
            if idx+1 < NUM_GRAPHS:
                go_next(("context", idx+1))
            else:
                go_next(("black", 0))
        else:
            go_next(("graph", idx))

def show_graph(idx: int):
    row = items.iloc[idx]
    st.subheader(f"הצגת גרף {idx+1}/{NUM_GRAPHS}")
    st.image(row[v_col], use_column_width=True)
    remaining = time_left(DUR_GRAPH)
    st.markdown(f"⏳ הזמן שנותר: **{int(remaining)}** שניות")
    if st.button("המשך ▶️"):
        if group == 3:
            go_next(("post_context", idx))
        else:
            # go to questions for this graph
            go_next(("q1", idx))
    if remaining <= 0:
        if group == 3:
            go_next(("post_context", idx))
        else:
            go_next(("q1", idx))

def show_black():
    st.subheader("אתחול זיכרון...")
    st.markdown("🕶️ מסך שחור קצר לפני שלב השאלות המרוכזות")
    remaining = time_left(DUR_BLACK)
    st.markdown(f"⏳ {int(remaining)}")
    if remaining <= 0:
        # prepare queue of 36 questions (3 per graph)
        st.session_state["question_queue"].clear()
        for gidx in range(NUM_GRAPHS):
            for qn in [1,2,3]:
                st.session_state["question_queue"].append((gidx, qn))
        go_next(("questions", 0))

def show_question_for_graph(idx: int, qn: int):
    row = items.iloc[idx]
    questions = extract_questions(row, group)
    q = [q for q in questions if q["qnum"] == qn][0]
    st.subheader(f"שאלה {qn} על גרף {idx+1}/{NUM_GRAPHS}")
    # For groups 1/2: show the graph alongside the question (per spec group 1 shows same graph with question)
    if group in (1,2):
        st.image(row[v_col], use_column_width=True)
    st.markdown(f"**{q['text']}**")
    key_choice = f"choice-{idx}-{qn}"
    key_button = f"submit-{idx}-{qn}"
    if key_choice not in st.session_state:
        st.session_state[key_choice] = None
    if "question_start_ms" not in st.session_state:
        st.session_state["question_start_ms"] = now_ms()
    remaining = time_left(DUR_ANSWER_MAX)
    choice = st.radio("בחרי תשובה:", options=["A","B","C","D"], format_func=lambda x: f"{x}: {q['options'][x]}", index=None, key=key_choice)
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("שליחה והמשך ✅", key=key_button):
            chosen = st.session_state[key_choice]
            record_answer(idx+1, int(row.name), str(row.get("GraphID","")), qn, q["text"], q["options"], chosen, q["correct_letter"], st.session_state["question_start_ms"])
            st.session_state.pop("question_start_ms", None)
            # advance within graph's questions
            if group in (1,2):
                if qn == 1 and group == 1:
                    # next graph
                    if idx+1 < NUM_GRAPHS:
                        go_next(("context", idx+1))
                    else:
                        st.session_state["phase"] = "done"
                        go_next()
                elif qn < 3:
                    go_next((f"q{qn+1}", idx))
                else:
                    if idx+1 < NUM_GRAPHS:
                        go_next(("context", idx+1))
                    else:
                        st.session_state["phase"] = "done"
                        go_next()
            else:
                # group 3: we're in consolidated questions queue
                next_q_index = st.session_state["step"][1] + 1
                if next_q_index < len(st.session_state["question_queue"]):
                    go_next(("questions", next_q_index))
                else:
                    st.session_state["phase"] = "done"
                    go_next()
    with col2:
        st.write(f"⏳ זמן שנותר: **{int(remaining)}** שניות")
    # Time-out auto-advance
    if remaining <= 0:
        chosen = st.session_state.get(key_choice, None)
        record_answer(idx+1, int(row.name), str(row.get("GraphID","")), qn, q["text"], q["options"], chosen, q["correct_letter"], st.session_state.get("question_start_ms", now_ms()))
        st.session_state.pop("question_start_ms", None)
        if group in (1,2):
            if qn == 1 and group == 1:
                if idx+1 < NUM_GRAPHS:
                    go_next(("context", idx+1))
                else:
                    st.session_state["phase"] = "done"
                    go_next()
            elif qn < 3:
                go_next((f"q{qn+1}", idx))
            else:
                if idx+1 < NUM_GRAPHS:
                    go_next(("context", idx+1))
                else:
                    st.session_state["phase"] = "done"
                    go_next()
        else:
            next_q_index = st.session_state["step"][1] + 1
            if next_q_index < len(st.session_state["question_queue"]):
                go_next(("questions", next_q_index))
            else:
                st.session_state["phase"] = "done"
                go_next()

def page_run():
    st.caption(f"משתתף: `{participant_id}` | קבוצה {group} | עמודת {v_col} | סך הכל {NUM_GRAPHS} גרפים")
    # Router of steps
    step_name, idx = st.session_state["step"]
    if step_name == "context":
        show_context(idx, post=False)
    elif step_name == "graph":
        show_graph(idx)
    elif step_name == "post_context":
        show_context(idx, post=True)
    elif step_name == "black":
        show_black()
    elif step_name in ("q1","q2","q3"):
        qn = int(step_name[1])
        show_question_for_graph(idx, qn)
    elif step_name == "questions":
        gidx, qn = st.session_state["question_queue"][idx]
        show_question_for_graph(gidx, qn)
    else:
        st.write("מצב לא ידוע")
    if st.button("איפוס ▶️ התחל מחדש"):
        reset_run()
        st.experimental_rerun()

def page_done():
    st.success("תודה על ההשתתפות!")
    st.markdown("הנתונים נשמרו. אפשר לסגור את החלון.")
    if st.button("התחל שוב"):
        reset_run()
        st.experimental_rerun()

def page_admin():
    st.header("מסך מנהל")
    code = st.text_input("הזיני קוד גישה", type="password")
    admin_code = os.environ.get("ADMIN_CODE", None)
    try:
        admin_code = admin_code or st.secrets["app"]["admin_code"]
    except Exception:
        pass
    if code and admin_code and code == admin_code:
        st.success("ברוכה הבאה, מנהלת.")
        df = download_full_results()
        if df is not None:
            st.write("תוצאות מגוגל שיטס:")
            st.dataframe(df)
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("הורדת CSV", data=csv_bytes, file_name="results_from_sheet.csv", mime="text/csv")
        else:
            st.info("לא הוגדרו אישורי Google. מציג קובץ מקומי אם קיים.")
            local = "results/results_local.csv"
            if os.path.exists(local):
                st.download_button("הורדת CSV מקומי", data=open(local, "rb").read(), file_name="results_local.csv")
            else:
                st.write("אין קובץ תוצאות מקומי.")
    else:
        st.info("הכניסי קוד גישה תקין כדי לצפות ולהוריד תוצאות.")

# -------------- Router --------------
if mode == "מנהל":
    page_admin()
else:
    if st.session_state["phase"] == "intro":
        page_intro()
    elif st.session_state["phase"] == "running":
        page_run()
    else:
        page_done()
