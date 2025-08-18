\
import time
import pandas as pd
import gspread
from google.auth import default
from google.oauth2.service_account import Credentials
import streamlit as st

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _get_client():
    try:
        # Prefer service account from Streamlit secrets
        sa_info = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.warning("⚠️ לא נמצאו האישורים של Google ב-Secrets. שמירה תתבצע מקומית בלבד.")

def _open_or_create_ws(client, sheet_id: str, worksheet_name: str = "results"):
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=1000, cols=40)
    return ws

HEADER = [
    "timestamp_iso",
    "participant_id",
    "group",
    "v_col",
    "graph_order_index",
    "graph_row_index",
    "graph_id",
    "question_number",
    "question_text",
    "option_chosen_letter",
    "option_chosen_text",
    "correct_letter",
    "correct_text",
    "is_correct",
    "response_time_ms",
]

def ensure_header(ws):
    try:
        values = ws.row_values(1)
        if values != HEADER:
            ws.clear()
            ws.append_row(HEADER)
    except Exception:
        pass

def append_result_row(row_dict: dict):
    """
    Append a single result record to Google Sheets. Falls back to local CSV on failure.
    """
    record = [row_dict.get(k, "") for k in HEADER]
    # Try Google Sheets
    try:
        client = _get_client()
        if client:
            ws = _open_or_create_ws(client, st.secrets["google_sheets"]["sheet_id"], st.secrets["google_sheets"].get("worksheet_name","results"))
            ensure_header(ws)
            ws.append_row(record, value_input_option="USER_ENTERED")
            return True
    except Exception as e:
        st.error(f"❌ שמירה ל-Google Sheets נכשלה: {e}")
    # Local CSV fallback
    try:
        import os, csv, datetime
        local_dir = "results"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, "results_local.csv")
        file_exists = os.path.exists(local_path)
        with open(local_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(HEADER)
            writer.writerow(record)
        return False
    except Exception as e:
        st.error(f"❌ שמירה מקומית נכשלה: {e}")
        return False

def download_full_results():
    """
    Pull everything from Google Sheets into a pandas DataFrame.
    """
    client = _get_client()
    if not client:
        return None
    ws = _open_or_create_ws(client, st.secrets["google_sheets"]["sheet_id"], st.secrets["google_sheets"].get("worksheet_name","results"))
    ensure_header(ws)
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame(columns=HEADER)
    df = pd.DataFrame(rows[1:], columns=rows[0])
    return df
