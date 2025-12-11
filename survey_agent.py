# survey_agent_debug.py
import os
import json
import math
import gspread
from google.oauth2.service_account import Credentials
from openai import AzureOpenAI
from dotenv import load_dotenv
import traceback
from collections import Counter

load_dotenv()

# -----------------------
# CONFIG / ENV
# -----------------------
DEBUG = os.getenv("SURVEY_DEBUG", "") not in ("", "0", "false", "False")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# -----------------------
# GOOGLE SHEETS AUTH
# -----------------------
def get_google_creds():
    json_content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "").strip()
    if json_content:
        try:
            info = json.loads(json_content)
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT: {e}")

    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_path and os.path.exists(json_path):
        return Credentials.from_service_account_file(json_path, scopes=SCOPES)

    render_path = "/etc/secrets/service_account.json"
    if os.path.exists(render_path):
        return Credentials.from_service_account_file(render_path, scopes=SCOPES)

    local_path = os.path.join(os.getcwd(), "creds", "service_account.json")
    if os.path.exists(local_path):
        return Credentials.from_service_account_file(local_path, scopes=SCOPES)

    raise FileNotFoundError("No Google credentials found for survey agent!")

creds = get_google_creds()
gc = gspread.authorize(creds)
if DEBUG:
    print("[SURVEY][DEBUG] Google Sheets client authorized.")


# -----------------------
# SURVEY / QUESTIONS
# -----------------------
SPREADSHEET_ID = os.getenv("SURVEY_SHEET_ID", "17bCNu8teY-KM5154YVA1_90xLKBlMrLAKkjy0AVJK1w")
SHEET_NAME = os.getenv("SURVEY_SHEET_NAME", "Form Responses 1")

QUESTION_COLUMNS = {
    "Q1": "What is your vision for a digital hospital?",
    "Q2": "How will your hospital benefit if your hospital is NABH compliant?",
    "Q3": "How will your hospital benefit if your hospital is ABDM compliant?",
}
SCORE_COLUMNS = {"Q1": "Score Q1", "Q2": "Score Q2", "Q3": "Score Q3"}

MODEL_ANSWERS = {
    "Q1": "Paperless. No duplication of work. No manual entries in registers.",
    "Q2": "Better credit from government and insurance companies. Faster reimbursement of insurance claims. Better trust by patients.",
    "Q3": "Stand out from competition. Will get more patients. Patients will trust us more.",
}


# -----------------------
# AZURE OPENAI SETUP
# -----------------------
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("AZURE_EMBEDDINGS_DEPLOYMENT_NAME")

if not AZURE_ENDPOINT or not AZURE_API_KEY:
    raise RuntimeError("AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_KEY not set!")

azure_client = AzureOpenAI(api_key=AZURE_API_KEY, api_version="2024-02-15-preview", azure_endpoint=AZURE_ENDPOINT)
if DEBUG:
    print("[SURVEY][DEBUG] Azure OpenAI client initialized.")


# -----------------------
# FALLBACK EMBEDDING (bag-of-words)
# -----------------------
def simple_bow_embedding(a_text: str, b_text: str):
    """
    Build a bag-of-words embedding for two texts so both vectors have the same dims.
    Returns tuple (vec_for_a, vec_for_b) of lists (floats), normalized to unit length.
    """
    def tokenize(s):
        if not s:
            return []
        return [tok.lower() for tok in s.split()]

    a_tokens = tokenize(a_text)
    b_tokens = tokenize(b_text)
    vocab = list(dict.fromkeys(a_tokens + b_tokens))  # preserve order, unique

    a_counts = Counter(a_tokens)
    b_counts = Counter(b_tokens)

    a_vec = [float(a_counts.get(w, 0)) for w in vocab]
    b_vec = [float(b_counts.get(w, 0)) for w in vocab]

    # normalize to unit length (L2) to behave like embeddings
    def normalize(v):
        norm = math.sqrt(sum(x * x for x in v))
        if norm == 0.0:
            return v
        return [x / norm for x in v]

    return normalize(a_vec), normalize(b_vec)


# -----------------------
# AZURE EMBEDDING WRAPPER (safe)
# -----------------------
def get_embedding_safe(text: str):
    """
    Try Azure embeddings first. If it fails or response shape unexpected,
    return None so caller can use fallback.
    """
    text = (text or "").strip()
    if not text:
        return None

    try:
        resp = azure_client.embeddings.create(model=AZURE_EMBEDDINGS_DEPLOYMENT_NAME, input=text)
        # robust access:
        embedding = None
        if hasattr(resp, "data") and isinstance(resp.data, list) and len(resp.data) > 0:
            # check attribute name used by SDK (embedding or vector)
            item = resp.data[0]
            # some SDK variants: item.embedding or item["embedding"]
            if hasattr(item, "embedding"):
                embedding = item.embedding
            elif isinstance(item, dict) and "embedding" in item:
                embedding = item["embedding"]
        # final check
        if embedding is None:
            if DEBUG:
                print("[SURVEY][DEBUG] Azure embedding returned unexpected structure. Using fallback.")
            return None
        # ensure list of floats
        embedding = [float(x) for x in embedding]
        return embedding
    except Exception as e:
        if DEBUG:
            print("[SURVEY][DEBUG] Azure embedding call failed:", e)
            traceback.print_exc()
        return None


# -----------------------
# COSINE SIMILARITY
# -----------------------
def cosine_similarity(vec1, vec2):
    """Return cosine similarity in [-1, 1]."""
    if vec1 is None or vec2 is None:
        return 0.0
    if len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(b * b for b in vec2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


# -----------------------
# SCORING: MUST BE 0..1 (50% -> 0.5)
# -----------------------
def score_single_pair(model_answer: str, user_answer: str):
    """
    Returns continuous score in [0.0, 1.0].
      - Attempts Azure embeddings; if not available, uses simple bag-of-words fallback.
      - raw_sim = cosine_similarity(...)  # -1..1
      - mapped_score = max(0.0, raw_sim)  # negative -> 0; positive used directly
      - rounds to 1 decimal for sheet storage
    """
    # try azure embedding
    model_vec = get_embedding_safe(model_answer)
    user_vec = get_embedding_safe(user_answer) if user_answer else None

    if model_vec is not None and user_vec is not None:
        if DEBUG:
            print(f"[SURVEY][DEBUG] Using Azure embeddings: len={len(model_vec)}")
            print("  sample model_vec[:5]:", model_vec[:5])
            print("  sample user_vec[:5]: ", user_vec[:5])
    else:
        # use fallback (bag-of-words) to ensure both vectors same dims
        if DEBUG:
            print("[SURVEY][DEBUG] Using fallback bag-of-words embeddings.")
        model_vec, user_vec = simple_bow_embedding(model_answer, user_answer or "")

    raw_sim = cosine_similarity(model_vec, user_vec)  # -1..1
    mapped = max(0.0, raw_sim)  # per your requirement: 0.5->0.5, negatives -> 0
    final = round(mapped, 1)  # <-- single digit after decimal
    if DEBUG:
        print(f"[SURVEY][DEBUG] raw_sim={raw_sim:.6f} mapped={mapped:.6f} final={final}")
    return final


def score_answers_with_azure(user_answers: dict) -> dict:
    scores = {}
    total = 0.0
    for qid, model_answer in MODEL_ANSWERS.items():
        user_answer = (user_answers.get(qid) or "").strip()
        if not user_answer:
            scores[qid] = 0.0
        else:
            try:
                s = score_single_pair(model_answer, user_answer)
                scores[qid] = s
                total += s
            except Exception as e:
                if DEBUG:
                    print(f"[SURVEY][DEBUG] Error scoring {qid}:", e)
                    traceback.print_exc()
                scores[qid] = 0.0
    scores["total"] = round(total, 1)  # <-- single digit after decimal for total too
    if DEBUG:
        print("[SURVEY][DEBUG] Scored answers:", scores)
    return scores


# -----------------------
# PROCESS SHEET
# -----------------------
def process_unscored_responses():
    if DEBUG:
        print("[SURVEY][DEBUG] Starting processing...")

    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    header = ws.row_values(1)
    col_index = {name: idx + 1 for idx, name in enumerate(header)}

    required = list(QUESTION_COLUMNS.values()) + list(SCORE_COLUMNS.values()) + ["Total"]
    for col in required:
        if col not in col_index:
            raise ValueError(f"Missing required column: {col}")

    rows = ws.get_all_records()
    if DEBUG:
        print(f"[SURVEY][DEBUG] Rows fetched: {len(rows)}")

    updated = 0
    for i, row in enumerate(rows, start=2):
        # treat any non-empty Score Q1 as already scored
        if str(row.get("Score Q1", "")).strip() != "":
            continue

        answers = {qid: row.get(col) for qid, col in QUESTION_COLUMNS.items()}
        # Debug one-off: print the answers if debug and short dataset
        if DEBUG:
            print(f"[SURVEY][DEBUG] Row {i} answers:", answers)

        scores = score_answers_with_azure(answers)

        if DEBUG:
            # print rather than write when debug to avoid accidental writes
            print(f"[SURVEY][DEBUG] Row {i} computed scores:", scores)
        else:
            for qid, col in SCORE_COLUMNS.items():
                ws.update_cell(i, col_index[col], scores.get(qid, 0.0))
            ws.update_cell(i, col_index["Total"], scores.get("total", 0.0))
        updated += 1

    if DEBUG:
        print(f"[SURVEY][DEBUG] Done. Would have updated {updated} rows (DEBUG mode).")
    else:
        print(f"Done. Updated {updated} rows.")
    return f"Updated {updated} responses"


if __name__ == "__main__":
    process_unscored_responses()
