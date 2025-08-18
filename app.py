import csv, os
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]

HEADER = [
    "timestamp_iso","participant_id","group","v_col","graph_order_index","graph_row_index","graph_id",
    "question_number","question_text","option_chosen_letter","option_chosen_text",
    "correct_letter","correct_text","is_correct","response_time_ms",
]

def _get_client():
    try:
        sa_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(credentials)
    except Exception:
        st.warning("⚠️ אין אישורי Google ב-Secrets – שמירה תהיה מקומית בלבד.")
        return None

def _open(ws_name="results"):
    client = _get_client()
    if not client: return None, None
    sh = client.open_by_key(st.secrets["google_sheets"]["sheet_id"])
    try:
        ws = sh.worksheet(st.secrets["google_sheets"].get("worksheet_name", ws_name))
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=ws_name, rows=2000, cols=40)
    return sh, ws

def ensure_header(ws):
    vals = ws.get_all_values()
    if not vals or vals[0] != HEADER:
        ws.clear()
        ws.append_row(HEADER)

def append_result_row(row_dict):
    record = [row_dict.get(k, "") for k in HEADER]
    try:
        sh, ws = _open()
        if ws:
            ensure_header(ws)
            ws.append_row(record, value_input_option="USER_ENTERED")
            return True
    except Exception as e:
        st.error(f"❌ שמירה ל-Google Sheets נכשלה: {e}")
    # local fallback
    os.makedirs("results", exist_ok=True)
    path = os.path.join("results","results_local.csv")
    new = not os.path.exists(path)
    with open(path,"a",newline="",encoding="utf-8") as f:
        w = csv.writer(f)
        if new: w.writerow(HEADER)
        w.writerow(record)
    return False

def download_full_results():
    client = _get_client()
    if not client: return None
    sh = client.open_by_key(st.secrets["google_sheets"]["sheet_id"])
    ws_name = st.secrets["google_sheets"].get("worksheet_name","results")
    try:
        ws = sh.worksheet(ws_name)
    except Exception:
        return pd.DataFrame(columns=HEADER)
    rows = ws.get_all_values()
    if not rows: return pd.DataFrame(columns=HEADER)
    return pd.DataFrame(rows[1:], columns=rows[0])
