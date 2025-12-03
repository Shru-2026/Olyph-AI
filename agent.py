# agent.py
"""
Combined chatbot + report agent.

- Chatbot logic (FAQ + Azure fallback) kept from original.
- Report agent functions updated:
  - Proper Render support for Google Credentials via Secret Files.
  - Attempts paths in this order:

    1. GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT  (raw JSON)
    2. GOOGLE_SERVICE_ACCOUNT_JSON          (file path)
    3. /etc/secrets/service_account.json    (Render Secret File)
    4. ./creds/service_account.json         (local development)

  - Uses AuthorizedSession for gspread.
"""

import os
import re
import io
import json
import fitz
import nltk
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from nltk.corpus import stopwords

# Google Sheets deps
import pandas as pd
import gspread
import requests
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession

# Azure OpenAI client (kept as in your original code)
from openai import AzureOpenAI

# Load .env for local development
load_dotenv(dotenv_path="./.env")

# ---------- Azure/OpenAI config ----------
nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "shruti-gpt-4o-mini")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

if not (AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT and AZURE_DEPLOYMENT_NAME and AZURE_API_VERSION):
    print("⚠️ Warning: Azure OpenAI config missing in environment.")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

# ---------- PDF FAQ loader ----------
def extract_pdf_text(pdf_path):
    qa_pairs = []
    try:
        with fitz.open(pdf_path) as doc:
            text = ""
            for p in range(len(doc)):
                text += doc[p].get_text("text")
        lines = text.splitlines()
        question, answer = None, ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.match(r"^(q\d*[\.\):]*|question[\.\):]*|q:)", line.lower()) or line.endswith("?"):
                if question and answer:
                    qa_pairs.append((question.strip(), answer.strip()))
                question = re.sub(r"^(q\d*[\.\):]*|question[\.\):]*|q:)", "", line, flags=re.I).strip()
                answer = ""
            elif re.match(r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)", line.lower()):
                answer_line = re.sub(r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)", "", line, flags=re.I).strip()
                answer += " " + answer_line
            elif question:
                answer += " " + line
        if question and answer:
            qa_pairs.append((question.strip(), answer.strip()))
        print(f"✅ Loaded {len(qa_pairs)} Q&A pairs from '{pdf_path}'")
        return qa_pairs
    except Exception as e:
        print(f"⚠️ Error reading PDF '{pdf_path}': {type(e).__name__}: {e}")
        return []

FAQ_PATH = "Olyphaunt FAQs.pdf"
qa_pairs = extract_pdf_text(FAQ_PATH)
if not qa_pairs:
    qa_pairs = [("What is Olyphaunt Solutions?", "Olyphaunt Solutions is a healthcare technology company.")]

# ---------- Chatbot class ----------
class OlyphauntChatbot:
    def __init__(self, qa_pairs):
        self.qa_pairs = qa_pairs
        self.questions = [q.lower() for q, _ in qa_pairs]
        self.answers = [a for _, a in qa_pairs]
        sw = stopwords.words("english")
        self.vectorizer = TfididfVectorizer(stop_words=sw)

        try:
            self.question_vectors = self.vectorizer.fit_transform(self.questions)
        except Exception as e:
            print("⚠️ Vectorizer fit failed:", e)
            self.question_vectors = None

    def _extract_text_from_choice(self, choice):
        try:
            if hasattr(choice, "message"):
                msg = choice.message
                if isinstance(msg, dict) and "content" in msg:
                    return msg.get("content")
                if hasattr(msg, "content"):
                    return msg.content
        except Exception:
            pass

        try:
            if isinstance(choice, dict) and "message" in choice:
                return choice["message"].get("content")
        except Exception:
            pass

        try:
            if hasattr(choice, "text"):
                return choice.text
        except Exception:
            pass

        return None

    def respond(self, user_query):
        user_query_text = (user_query or "").strip()
        if not user_query_text:
            return "⚠️ Please enter a valid question."

        # Try FAQ
        try:
            if self.question_vectors is not None:
                qvec = self.vectorizer.transform([user_query_text.lower()])
                sims = cosine_similarity(qvec, self.question_vectors)
                max_idx = int(np.argmax(sims))
                score = float(sims[0, max_idx])
                print(f"🔍 FAQ similarity score: {score:.2f}")
                if score >= 0.7:
                    return self.answers[max_idx]
        except Exception as e:
            print("⚠️ FAQ check error:", e)

        # Azure fallback
        try:
            print("✨ Calling Azure Foundry chat completion...")
            messages = [
                {"role": "system", "content": "You are an assistant for Olyphaunt Solutions."},
                {"role": "user", "content": user_query_text}
            ]
            resp = client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.2,
                max_tokens=512
            )
            if hasattr(resp, "choices") and len(resp.choices) > 0:
                choice0 = resp.choices[0]
                text = self._extract_text_from_choice(choice0)
                if text:
                    return text.strip()
            return "🤖 I'm not certain about that. Could you rephrase?"
        except Exception as e:
            print(f"❌ Azure Foundry error: {type(e).__name__}: {e}")
            return "⚠️ Olyph AI is currently offline. Please try again."

chatbot = OlyphauntChatbot(qa_pairs)

def handle_user_query(user_message: str):
    return chatbot.respond(user_message)


# ----------------------------------------------------------------------------
# GOOGLE SHEETS — UPDATED CREDENTIAL LOADING (RENDER SUPPORT)
# ----------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _get_service_account_credentials():
    """
    Returns service account credentials using this priority:

    1. GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT  → raw JSON
    2. GOOGLE_SERVICE_ACCOUNT_JSON          → file path
    3. /etc/secrets/service_account.json    → Render Secret File
    4. ./creds/service_account.json         → local fallback
    """

    # 1) JSON Content provided directly
    content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "").strip()
    if content:
        try:
            info = json.loads(content)
            print("🔐 Using JSON content from GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT: {e}")

    # 2) External JSON file path (set explicitly)
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if path and os.path.exists(path):
        print(f"🔐 Using GOOGLE_SERVICE_ACCOUNT_JSON at: {path}")
        return Credentials.from_service_account_file(path, scopes=SCOPES)

    # 3) Render Secret File (auto)
    render_default = "/etc/secrets/service_account.json"
    if os.path.exists(render_default):
        print(f"🔐 Using Render Secret File: {render_default}")
        return Credentials.from_service_account_file(render_default, scopes=SCOPES)

    # 4) Local development fallback
    local_path = os.path.join(os.getcwd(), "creds", "service_account.json")
    if os.path.exists(local_path):
        print(f"🔐 Using local creds: {local_path}")
        return Credentials.from_service_account_file(local_path, scopes=SCOPES)

    raise FileNotFoundError(
        "Service account JSON not found.\n"
        "Set GOOGLE_SERVICE_ACCOUNT_JSON or upload a Secret File."
    )


def get_gspread_client():
    creds = _get_service_account_credentials()
    client = gspread.Client(auth=creds)
    client.session = AuthorizedSession(creds)
    return client


def fetch_sheet_as_dataframe(sheet_id=None, sheet_name_or_index=None, value_render_option="FORMATTED_VALUE"):
    if not sheet_id:
        sheet_id = os.getenv("REPORT_SHEET_ID", "").strip()
        if not sheet_id:
            raise ValueError("Missing sheet_id and REPORT_SHEET_ID.")

    if sheet_name_or_index is None:
        env = os.getenv("REPORT_SHEET_NAME_OR_INDEX", "").strip()
        if env != "":
            try:
                sheet_name_or_index = int(env)
            except:
                sheet_name_or_index = env
        else:
            sheet_name_or_index = 0

    client = get_gspread_client()
    spreadsheet = client.open_by_key(sheet_id)

    if isinstance(sheet_name_or_index, int):
        worksheet = spreadsheet.get_worksheet(sheet_name_or_index)
    else:
        worksheet = spreadsheet.worksheet(sheet_name_or_index)

    records = worksheet.get_all_records(value_render_option=value_render_option)
    df = pd.DataFrame(records)
    return df


def dataframe_to_csv_bytes(df):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf


def dataframe_to_excel_bytes(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    buf.seek(0)
    return buf


def generate_report_bytes(sheet_id=None, sheet=None, fmt="csv"):
    df = fetch_sheet_as_dataframe(sheet_id=sheet_id, sheet_name_or_index=sheet)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    chosen_id = sheet_id or os.getenv("REPORT_SHEET_ID", "unknown")

    if fmt.lower() in ("csv", "text/csv"):
        bio = dataframe_to_csv_bytes(df)
        filename = f"sheet_{chosen_id}_{timestamp}.csv"
        mimetype = "text/csv"
    elif fmt.lower() in ("xlsx", "excel"):
        bio = dataframe_to_excel_bytes(df)
        filename = f"sheet_{chosen_id}_{timestamp}.xlsx"
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        raise ValueError("Unsupported format. Use 'csv' or 'xlsx'.")

    return bio, filename, mimetype
