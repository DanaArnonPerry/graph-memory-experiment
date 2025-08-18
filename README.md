# graph-memory-experiment

Streamlit app for a memory-of-graphs experiment with **three groups**.  
Data is read from a CSV that contains contexts, questions, answer options, and 4 visual columns `V1..V4` with image URLs for the charts.  
Results are appended to **Google Sheets** (by ID) with a local CSV fallback.

---

## Folder layout
```
graph-memory-experiment/
├── app.py
├── helpers.py
├── storage.py
├── requirements.txt
├── data/
│   └── MemoryTest.csv        # your experiment CSV (a copy of the uploaded file)
├── images/
│   └── imageChart1DC.PNG     # sample chart for the intro screen
└── .streamlit/
    ├── config.toml
    └── secrets_template.toml
```

## CSV columns expected

Minimum columns (per row = 1 *graph*):

- `GraphID` (optional; falls back to row number)
- `TheContext` (short text page shown before each graph for up to 2s)
- `V1`, `V2`, `V3`, `V4` — **URLs** of the images to be shown for each assignment arm
- `Question1Text`, `Q1OptionA`, `Q1OptionB`, `Q1OptionC`, `Q1OptionD`, `Q1Correct`  
- `Question2Text`, `Q2OptionA`, `Q2OptionB`, `Q2OptionC`, `Q2OptionD`, `Q2Correct`  
- `Question3Text`, `Q3OptionA`, `Q3OptionB`, `Q3OptionC`, `Q3OptionD`, `Q3Correct`

`QxCorrect` can be either the **letter** (`A`/`B`/`C`/`D`) or the **exact text** of the correct option.

## Assignment logic (`V1..V4`)

Each participant is assigned a single V-column (V1, V2, V3, or V4).  
By default this is derived from the participant's ID (stable hash, round‑robin). You can override it from the sidebar.

## Timing

- Context screen: **2s** (auto-advance; also has a *Continue* button)
- Graph screen: **30s** (auto-advance; also has a *Continue* button)
- Per-question answer time: **120s** (auto-advance on timeout)

**Group 1 (Control):** 12 graphs (same V column). For each graph: context → 30s graph → 1 question about that graph (graph visible on question screen).  
**Group 2 (Short-term memory):** 12 graphs (same V). For each graph: context → 30s graph → 3 questions about that graph (graph visible on question screens).  
**Group 3 (Delayed recall):** 12 graphs (same V). For each graph: context → 30s graph → (optional post-context, 2s). After all graphs: 3s black screen, then 36 questions (3 per graph) **without** the graphs.

All navigation (besides auto‑advance) is via the **Continue** button.

## Results schema

Each answer is appended as one row (to Google Sheets or local CSV fallback):

- timestamp_iso, participant_id, group, v_col, graph_order_index (1..12), graph_row_index (0‑based from CSV), graph_id  
- question_number (1..3), question_text  
- option_chosen_letter, option_chosen_text, correct_letter, correct_text, is_correct  
- response_time_ms

## Google Sheets setup

1. Create a Google **Service Account** and enable the **Google Sheets API**.
2. Share your sheet with the SA `client_email` (Editor).
3. In Streamlit Cloud, open *Settings → Secrets* and paste the contents of `.streamlit/secrets_template.toml`, filling your values.
   - `google_sheets.sheet_id` should be `1aCJ2L2JQdREv5n0JZLxwvD_6i-ARRUDPy7EpGTIuJXc` (given).
4. The app writes to a worksheet named `results` (auto‑created if missing).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

- Push this folder to GitHub as **graph-memory-experiment**.
- Create a new app in Streamlit Cloud pointing to `app.py` on the main branch.
- Add the **Secrets** from `.streamlit/secrets_template.toml` (with your real values).

## Admin page

Switch *מצב* to **מנהל** in the sidebar, enter the admin code (from secrets or `ADMIN_CODE` env var), and download the results.

---

© 2025 — Designed for the *graph‑memory‑experiment*.
