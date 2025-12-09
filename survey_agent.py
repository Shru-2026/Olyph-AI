import os
import json
import gspread
from google.oauth2.service_account import Credentials
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

# ======================================================
#       GOOGLE SHEETS AUTHENTICATION (Render-safe)
# ======================================================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_google_creds():
    """Try all possible ways to load Google creds."""
    # 1️⃣ Raw JSON from environment (best for Render)
    json_content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "").strip()
    if json_content:
        print("🔐 [SURVEY] Using GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
        try:
            info = json.loads(json_content)
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT: {e}")

    # 2️⃣ Env var pointing to a path
    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_path and os.path.exists(json_path):
        print(f"🔐 [SURVEY] Using GOOGLE_SERVICE_ACCOUNT_JSON at: {json_path}")
        return Credentials.from_service_account_file(json_path, scopes=SCOPES)

    # 3️⃣ Render Secret File location
    render_path = "/etc/secrets/service_account.json"
    if os.path.exists(render_path):
        print(f"🔐 [SURVEY] Using Render secret file: {render_path}")
        return Credentials.from_service_account_file(render_path, scopes=SCOPES)

    # 4️⃣ Local fallback
    local_path = os.path.join(os.getcwd(), "creds", "service_account.json")
    if os.path.exists(local_path):
        print(f"🔐 [SURVEY] Using local creds: {local_path}")
        return Credentials.from_service_account_file(local_path, scopes=SCOPES)

    raise FileNotFoundError("❌ No Google credentials found for survey agent!")

creds = get_google_creds()
gc = gspread.authorize(creds)
print("[SURVEY] Google Sheets client authorized.")


# ======================================================
#       SURVEY CONFIG
# ======================================================
SPREADSHEET_ID = os.getenv("SURVEY_SHEET_ID", "17bCNu8teY-KM5154YVA1_90xLKBlMrLAKkjy0AVJK1w")
SHEET_NAME = os.getenv("SURVEY_SHEET_NAME", "Form Responses 1")

QUESTION_COLUMNS = {
    "Q1": "What is your vision for a digital hospital?",
    "Q2": "How will your hospital benefit if your hospital is NABH compliant?",
    "Q3": "How will your hospital benefit if your hospital is ABDM compliant?",
}
SCORE_COLUMNS = { "Q1": "Score Q1", "Q2": "Score Q2", "Q3": "Score Q3" }

MODEL_ANSWERS = {
    "Q1": "Paperless. No duplication of work. No manual entries in registers.",
    "Q2": "Better Credit from government and Insurance companies. Faster reimbursement of Insurance claims. Better trust by patients",
    "Q3": "Stand out from competition. Will get more patients. Patients will trust us more.",
}


# ======================================================
#       AZURE OPENAI
# ======================================================
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")

azure_client = AzureOpenAI(
    api_key=AZURE_API_KEY,
    api_version="2024-02-15-preview",
    azure_endpoint=AZURE_ENDPOINT,
)
print("[SURVEY] Azure OpenAI client initialized.")


# ======================================================
#       SCORING FUNCTION
# ======================================================
def score_answers_with_azure(user_answers: dict) -> dict:
    print(f"[SURVEY] Scoring answers with Azure: {user_answers}")

    messages = [{
        "role": "system",
        "content": (
            "You are an examiner for a hospital onboarding survey.\n"
            "Compare answers with model answers and assign 0-1 score per question.\n"
            "Return ONLY JSON:\n"
            '{"scores":{"Q1":0-1,"Q2":0-1,"Q3":0-1},"total":0-3}'
        ),
    }, {
        "role": "user",
        "content": "\n\n".join([
            f"Question {qid}\nModel: {MODEL_ANSWERS[qid]}\nUser: {user_answers.get(qid,'')}"
            for qid in QUESTION_COLUMNS.keys()
        ])
    }]

    try:
        resp = azure_client.chat.completions.create(
            model=AZURE_DEPLOYMENT_NAME,
            messages=messages,
            temperature=0.0,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content
        print("[SURVEY] Raw:", raw)

        data = json.loads(raw)
        scores = {k: float(v) for k, v in data.get("scores", {}).items()}
        total = float(data.get("total", 0.0))
        scores["total"] = total
        return scores

    except Exception as e:
        print("❌ JSON Parse Error:", e)
        fallback = {qid: 0.0 for qid in QUESTION_COLUMNS.keys()}
        fallback["total"] = 0.0
        return fallback


# ======================================================
#       PROCESS NEW RESPONSES
# ======================================================
def process_unscored_responses():
    print("[SURVEY] Processing unscored responses…")

    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    header = ws.row_values(1)
    col_index = {name: idx + 1 for idx, name in enumerate(header)}

    required = list(QUESTION_COLUMNS.values()) + list(SCORE_COLUMNS.values()) + ["Total"]
    for col in required:
        if col not in col_index:
            raise ValueError(f"Missing required column: {col}")

    rows = ws.get_all_records()
    print(f"[SURVEY] Rows: {len(rows)}")

    updated = 0

    for i, row in enumerate(rows, start=2):
        if str(row.get("Score Q1", "")).strip() not in ["", "0", "0.0"]:
            continue  # already scored

        answers = {qid: row.get(col) for qid, col in QUESTION_COLUMNS.items()}
        scores = score_answers_with_azure(answers)

        # Write per-question score
        for qid, col in SCORE_COLUMNS.items():
            ws.update_cell(i, col_index[col], scores.get(qid, 0.0))

        ws.update_cell(i, col_index["Total"], scores.get("total", 0.0))
        updated += 1

    print(f"[SURVEY] Done. Updated {updated} rows.")
    return f"Updated {updated} responses"


if __name__ == "__main__":
    print(process_unscored_responses())
