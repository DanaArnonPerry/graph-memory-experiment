from __future__ import annotations
import os, time
import pandas as pd
import streamlit as st
from helpers import (
    DUR_GRAPH, DUR_CONTEXT, DUR_BLACK, DUR_ANSWER_MAX,
    ensure_id, default_v_for_pid, load_items, extract_questions, now_ms
)
from storage import append_result_row, download_full_results

st.set_page_config(page_title="graph-memory-experiment", layout="wide")

# ---------- Sidebar: setup ----------
st.sidebar.title("⚙️ הגדרות")
csv_path = st.sidebar.text_input("נתיב לקובץ CSV", value="data/MemoryTest.csv")
group = st.sidebar.selectbox("בחרי קבוצה לניסוי", options=[1,2,3], index=0, format_func=lambda x: f"קבוצה {x}")
participant_id_in = st.sidebar.text_input("מזהה משתתף", value=st.session_state.get("participant_id",""))
if st.sidebar.button("הקצה מזהה חדש"):
    st.session_state["participant_id"] = ""
participant_id = ensure_id()
v_override = st.sidebar.selectbox("בחרי עמודת ויזואליזציות (V1..V4)", options=["AUTO","V1","V2","V3","V4"], index=0)
v_col = default_v_for_pid(participant_id) if v_override == "AUTO" else v_override
st.sidebar.markdown(f"**עמודת V לנבדק:** `{v_col}`")

# ---------- Style controls (RTL & design) ----------
with st.sidebar.expander("🎨 עיצוב ותצוגה (RTL)", expanded=True):
    primary_color = st.color_picker("צבע ראשי", "#0C6CF2")
    heading_align = st.selectbox("יישור כותרות", ["right","center","left"], index=0)
    body_align = st.selectbox("יישור טקסט", ["right","center","left"], index=0)
    base_font_px = st.slider("גודל בסיס פונט (px)", 14, 24, 16)
    border_radius = st.slider("רדיוס פינות כפתורים (px)", 4, 24, 12)
    center_images = st.checkbox("מרכוז תמונות", True)
    max_img_h = st.number_input("גובה מקס׳ לתמונות (px, 0=ללא)", min_value=0, value=0, step=10)

# Apply RTL + styles
css = f"""
<style>
html, body, .block-container, [data-testid="stAppViewContainer"] {{
  direction: rtl;
}}
[data-testid="stSidebar"] .block-container {{
  direction: rtl;
  text-align: right;
}}
.block-container, .stMarkdown p, label, [data-baseweb="select"], [data-baseweb="radio"] {{
  text-align: {body_align};
}}
h1, h2, h3, h4, h5, h6 {{ text-align: {heading_align}; }}
html {{ font-size: {base_font_px}px; }}
.stButton button, .stDownloadButton button {{
  background-color: {primary_color} !important;
  border-color: {primary_color} !important;
  border-radius: {border_radius}px !important;
}}
[role="radiogroup"], [role="group"] {{ direction: rtl; }}
.stAlert {{ direction: rtl; text-align: right; }}
{("[data-testid='stImage'] {{ text-align: center; }}" if center_images else "")}
{("[data-testid='stImage'] img { max-height: "+str(int(max_img_h))+"px; object-fit: contain; }" if max_img_h and int(max_img_h)>0 else "")}
</style>
"""
st.markdown(css, unsafe_allow_html=True)

mode = st.sidebar.radio("מצב", ["ניסוי", "מנהל"], index=0)

# ---------- Load data ----------
@st.cache_data(show_spinner=False)
def _load_df(path: str):
    return load_items(path)

try:
    df = _load_df(csv_path)
except Exception as e:
    st.error(f"קריאת הקובץ נכשלה: {e}")
    st.stop()

if v_col not in df.columns:
    st.error(f"העמודה '{v_col}' לא קיימת ב-CSV. קיימות: {list(df.columns)}")
    st.stop()

items = df[df[v_col].notna()].reset_index(drop=True)
NUM_GRAPHS = min(12, len(items))

# ---------- Session ----------
if "phase" not in st.session_state:
    st.session_state["phase"] = "intro"
if "step" not in st.session_state:
    st.session_state["step"] = ("context", 0)
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
    """
    Safer timer: refreshes once per second via sleep+rerun (works on most Streamlit builds).
    """
    elapsed_s = (now_ms() - st.session_state["step_started_ms"]) / 1000.0
    remaining = max(0, int(limit_s - elapsed_s))
    if remaining > 0:
        import time as _t
        _t.sleep(1)
        try:
            st.experimental_rerun()
        except Exception:
            pass
    return remaining

def go_next(step=None):
    st.session_state["step_started_ms"] = now_ms()
    if step is not None:
        st.session_state["step"] = step


def _show_image(src, caption=None):
    """
    Robust image display:
    - Supports http(s) and local paths.
    - Converts common Google Drive URLs to direct view links.
    - Falls back to raw <img> HTML if st.image fails (prevents crashes).
    """
    import re
    def _gdrive_direct(u: str) -> str:
        if not isinstance(u, str):
            return u
        if "drive.google.com" not in u:
            return u
        # /file/d/<ID>/view
        m = re.search(r"/file/d/([^/]+)/", u)
        if m:
            return f"https://drive.google.com/uc?export=view&id={m.group(1)}"
        # open?id=<ID>
        m = re.search(r"[?&]id=([^&]+)", u)
        if m:
            return f"https://drive.google.com/uc?export=view&id={m.group(1)}"
        return u

    try:
        import re
        src2 = _gdrive_direct(src) if isinstance(src, str) else src
        st.image(src2, caption=caption, use_container_width=True)
    except Exception:
        # Fallback: render plain HTML <img> to avoid PIL/format detection errors
        if isinstance(src, str):
            safe_src = _gdrive_direct(src)
            st.markdown(f"<img src='{safe_src}' style='max-width:100%;width:100%;height:auto;display:block;'/>", unsafe_allow_html=True)
        else:
            st.warning("לא ניתן להציג את התמונה (פורמט לא נתמך).")
def record_answer(graph_order_index, graph_row_index, graph_id, qn, q_text, options, chosen, correct_letter, start_ms):
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

# ---------- Pages ----------
def page_intro():
    st.title("ניסוי זיכרון גרפים")
    st.subheader("graph-memory-experiment")
    st.markdown("""
ברוכה הבאה! בניסוי זה יוצגו לך גרפים קצרים עם הקשר, ולאחר מכן תישאלי שאלות בחירה מרובה.
משך הצגת כל גרף: **30 שניות**. שקף ההקשר: עד **2 שניות**. לכל שאלה ניתן לענות עד **2 דקות**.
לחצי על **המשך** כדי להתחיל.
    """)
    col1, col2 = st.columns([1,2])
    with col1:
        st.write("**פרטי משתתף**")
        st.write(f"מזהה משתתף: `{participant_id}`")
        st.write(f"קבוצה: **{group}**")
        st.write(f"עמודת גרפים: **{v_col}**")
    with col2:
        _show_image("images/imageChart1DC.PNG", caption="דוגמת גרף")
    if st.button("המשך ▶️"):
        st.session_state["phase"] = "running"
        go_next(("context", 0))


def show_context(idx: int, post=False):
    row = items.iloc[idx]
    # Counter line (e.g., 1/12) on the right
    st.markdown(f"<div style='text-align:right;font-size:1.25rem;color:#555;'>{idx+1}/{NUM_GRAPHS}</div>", unsafe_allow_html=True)
    # Big, bold context text
    ctx = row.get("TheContext","")
    ctx_html = f"<div style='text-align:right;font-weight:800;font-size:2rem;line-height:1.6'>{ctx}</div>"
    st.markdown(ctx_html, unsafe_allow_html=True)
    # Timer line
    remaining = time_left(DUR_CONTEXT)
    st.markdown(f"<div style='text-align:right;color:#666;'>⏳ עובר למסך הבא בעוד <b>{int(remaining)}</b> שניות.</div>", unsafe_allow_html=True)
    if st.button("המשך ▶️"):
        if group == 3 and not post:
            go_next(("graph", idx))
        elif group == 3 and post:
            if idx+1 < NUM_GRAPHS:
                go_next(("context", idx+1))
            else:
                go_next(("black", 0))
        else:
            go_next(("graph", idx))
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
    st.markdown(f"<div style='text-align:right;font-size:1.25rem;color:#555;'>{idx+1}/{NUM_GRAPHS}</div>", unsafe_allow_html=True)
    _show_image(row[v_col])
    remaining = time_left(DUR_GRAPH)
    st.markdown(f"⏳ הזמן שנותר: **{int(remaining)}** שניות")
    if st.button("המשך ▶️"):
        if group == 3:
            go_next(("post_context", idx))
        else:
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
        st.session_state["question_queue"].clear()
        for gidx in range(NUM_GRAPHS):
            for qn in [1,2,3]:
                st.session_state["question_queue"].append((gidx, qn))
        go_next(("questions", 0))

def show_question_for_graph(idx: int, qn: int):
    row = items.iloc[idx]
    q = [qq for qq in extract_questions(row, group) if qq["qnum"] == qn][0]
    st.subheader(f"שאלה {qn} על גרף {idx+1}/{NUM_GRAPHS}")
    if group in (1,2):
        _show_image(row[v_col])
    st.markdown(f"**{q['text']}**")
    key_choice = f"choice-{idx}-{qn}"
    key_button = f"submit-{idx}-{qn}"
    if key_choice not in st.session_state:
        st.session_state[key_choice] = None
    if "question_start_ms" not in st.session_state:
        st.session_state["question_start_ms"] = now_ms()
    remaining = time_left(DUR_ANSWER_MAX)
    choice = st.radio("בחרי תשובה:", ["A","B","C","D"], index=None, format_func=lambda x: f"{x}: {q['options'][x]}", key=key_choice)
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("שליחה והמשך ✅", key=key_button):
            chosen = st.session_state[key_choice]
            record_answer(idx+1, int(row.name), str(row.get("GraphID","")), qn, q["text"], q["options"], chosen, q["correct_letter"], st.session_state["question_start_ms"])
            st.session_state.pop("question_start_ms", None)
            if group in (1,2):
                if qn == 1 and group == 1:
                    if idx+1 < NUM_GRAPHS: go_next(("context", idx+1))
                    else: st.session_state["phase"] = "done"; go_next()
                elif qn < 3:
                    go_next((f"q{qn+1}", idx))
                else:
                    if idx+1 < NUM_GRAPHS: go_next(("context", idx+1))
                    else: st.session_state["phase"] = "done"; go_next()
            else:
                next_q_index = st.session_state["step"][1] + 1
                if next_q_index < len(st.session_state["question_queue"]): go_next(("questions", next_q_index))
                else: st.session_state["phase"] = "done"; go_next()
    with c2:
        st.write(f"⏳ זמן שנותר: **{int(remaining)}** שניות")
    if remaining <= 0:
        chosen = st.session_state.get(key_choice, None)
        record_answer(idx+1, int(row.name), str(row.get("GraphID","")), qn, q["text"], q["options"], chosen, q["correct_letter"], st.session_state.get("question_start_ms", now_ms()))
        st.session_state.pop("question_start_ms", None)
        if group in (1,2):
            if qn == 1 and group == 1:
                if idx+1 < NUM_GRAPHS: go_next(("context", idx+1))
                else: st.session_state["phase"] = "done"; go_next()
            elif qn < 3:
                go_next((f"q{qn+1}", idx))
            else:
                if idx+1 < NUM_GRAPHS: go_next(("context", idx+1))
                else: st.session_state["phase"] = "done"; go_next()
        else:
            next_q_index = st.session_state["step"][1] + 1
            if next_q_index < len(st.session_state["question_queue"]): go_next(("questions", next_q_index))
            else: st.session_state["phase"] = "done"; go_next()

def page_run():
    # ללא כותרת עליונה למשתתף
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
            st.dataframe(df)
            st.download_button("הורדת CSV", data=df.to_csv(index=False).encode("utf-8"), file_name="results_from_sheet.csv", mime="text/csv")
        else:
            st.info("אין Google Sheets מוגדר. מחפשת קובץ מקומי.")
            local = "results/results_local.csv"
            if os.path.exists(local):
                st.download_button("הורדת CSV מקומי", data=open(local,"rb").read(), file_name="results_local.csv")
            else:
                st.write("אין קובץ תוצאות מקומי.")
    else:
        st.info("הכניסי קוד גישה תקין לצפייה והורדה.")

# ---------- Router ----------
if mode == "מנהל":
    page_admin()
else:
    if st.session_state["phase"] == "intro":
        page_intro()
    elif st.session_state["phase"] == "running":
        page_run()
    else:
        page_done()
