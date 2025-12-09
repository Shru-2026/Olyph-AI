import os
import json
import gspread
from google.oauth2.service_account import Credentials
from openai import AzureOpenAI
from dotenv import load_dotenv 

# Load environment variables from .env
load_dotenv()

# ================== GOOGLE SHEETS SETUP ==================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "creds", "service_account.json")

# TODO: put your actual spreadsheet ID here (from the sheet URL)
SPREADSHEET_ID = "1KPfFT8UZ3nJNstgivfbiRf3vjLpILsChYSrJ0tD8L9c"
SHEET_NAME = "Form Responses 1"   # change if your tab name is different

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
print(f"[SURVEY] Using service account file: {SERVICE_ACCOUNT_FILE}")
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
print("[SURVEY] Google Sheets client authorized.")


# ================== SURVEY CONFIG ==================

QUESTION_COLUMNS = {
    "Q1": "What is your vision for a digital hospital?",
    "Q2": "How will your hospital benefit if your hospital is NABH compliant?",
    "Q3": "How will your hospital benefit if your hospital is ABDM compliant?",
}
SCORE_COLUMNS = {
    "Q1": "Score Q1",
    "Q2": "Score Q2",
    "Q3": "Score Q3",
}

# TODO: fill your real model answers here
MODEL_ANSWERS = {
    "Q1": "Paperless. No duplication of work. No manual entries in registers.",
    "Q2": "Better Credit from government and Insurance companies. Faster reimbursement of Insurance claims. Better trust by patients",
    "Q3": "Stand out from competition. Will get more patients. Patients will trust us more.",
}


# ================== AZURE OPENAI SETUP ==================

AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT") 
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY") 
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME") 

azure_client = AzureOpenAI(
    api_key=AZURE_API_KEY,
    api_version="2024-02-15-preview",
    azure_endpoint=AZURE_ENDPOINT,
)
print("[SURVEY] Azure OpenAI client initialized.")


# ================== AI SCORING ==================

def score_answers_with_azure(user_answers: dict) -> dict:
    print(f"[SURVEY] Scoring answers with Azure: {user_answers}")

    system_msg = {
        "role": "system",
        "content": (
            "You are an examiner for a hospital onboarding survey.\n"
            "For each question, compare the user's answer to the model answer "
            "and give a score between 0 and 1.\n"
            "0 = completely wrong, 1 = fully correct.\n"
            "Return ONLY valid JSON like:\n"
            '{ "scores": {"Q1": 0-1, "Q2": 0-1, "Q3": 0-1}, "total": 0-3 }'
        ),
    }

    blocks = []
    for qid, model_ans in MODEL_ANSWERS.items():
        blocks.append(
            f"Question: {qid}\n"
            f"Model answer: {model_ans}\n"
            f"User answer: {user_answers.get(qid, '')}\n"
        )

    user_msg = {
        "role": "user",
        "content": "\n\n".join(blocks),
    }

    resp = azure_client.chat.completions.create(
        model=AZURE_DEPLOYMENT_NAME,
        messages=[system_msg, user_msg],
        temperature=0.0,
        max_tokens=300,
    )

    raw = resp.choices[0].message.content
    print(f"[SURVEY] Raw Azure response: {raw}")

    try:
        data = json.loads(raw)
        scores = {k: float(v) for k, v in data.get("scores", {}).items()}
        total = float(data.get("total", 0.0))
        result = {**scores, "total": total}
        print(f"[SURVEY] Parsed scores: {result}")
        return result
    except Exception as e:
        print("[SURVEY] ❌ Error parsing Azure JSON:", type(e).__name__, e)
        # fallback zeros so process continues
        fallback = {qid: 0.0 for qid in QUESTION_COLUMNS.keys()}
        fallback["total"] = 0.0
        return fallback


# ================== MAIN SURVEY PROCESS ==================

def process_unscored_responses():
    print("[SURVEY] Starting process_unscored_responses()")

    sh = gc.open_by_key(SPREADSHEET_ID)
    print(f"[SURVEY] Opened spreadsheet: {sh.title}")

    ws = sh.worksheet(SHEET_NAME)
    print(f"[SURVEY] Using sheet/tab: {SHEET_NAME}")

    header = ws.row_values(1)
    print(f"[SURVEY] Header row: {header}")
    col_index = {name: idx + 1 for idx, name in enumerate(header)}

    required_cols = list(QUESTION_COLUMNS.values()) + list(SCORE_COLUMNS.values()) + ["Total"]
    for col in required_cols:
        if col not in col_index:
            raise ValueError(f"[SURVEY] Required column '{col}' not found in header.")

    rows = ws.get_all_records()
    print(f"[SURVEY] Total data rows found: {len(rows)}")

    updated_count = 0

    for i, row in enumerate(rows, start=2):
        print(f"[SURVEY] ---- Row {i} ----")
        print(f"[SURVEY] Row data: {row}")

        existing_score_q1 = str(row.get("Score Q1", "")).strip()
        if existing_score_q1 not in ["", "0", "0.0"]:
            print("[SURVEY] Row already scored, skipping.")
            continue

        user_answers = {
            qid: row.get(col_name, "")
            for qid, col_name in QUESTION_COLUMNS.items()
        }
        print(f"[SURVEY] User answers: {user_answers}")

        scores = score_answers_with_azure(user_answers)

        # Write per-question scores
        for qid, score_col in SCORE_COLUMNS.items():
            score_val = scores.get(qid, 0.0)
            row_col = col_index[score_col]
            print(f"[SURVEY] Writing {score_val} to {score_col} (row {i}, col {row_col})")
            ws.update_cell(i, row_col, score_val)

        total_score = scores.get("total", 0.0)
        total_col = col_index["Total"]
        print(f"[SURVEY] Writing total {total_score} to Total (row {i}, col {total_col})")
        ws.update_cell(i, total_col, total_score)

        updated_count += 1

    print(f"[SURVEY] Finished. Updated {updated_count} row(s).")
    return f"Survey scoring completed. Updated {updated_count} new row(s)."


if __name__ == "__main__":
    msg = process_unscored_responses()
    print("[SURVEY] Result:", msg)
