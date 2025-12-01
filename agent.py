# agent.py
"""
Combined chatbot + report agent.

- Chatbot logic (FAQ + Azure fallback) kept from original.
- Report agent functions added/fixed:
  - uses google service account credentials from env or creds/service_account.json
  - uses requests.Session for gspread client.session (fixes attribute error)
  - fetches sheet by ID (falls back to REPORT_SHEET_ID env)
  - returns BytesIO CSV or XLSX for download
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

# Load environment variables
load_dotenv(dotenv_path="./.env")

# ---------- Azure/OpenAI config ----------
nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "shruti-gpt-4o-mini")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

if not (AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT and AZURE_DEPLOYMENT_NAME and AZURE_API_VERSION):
    # only warn here; chat will try fallback behavior
    print("⚠️ Warning: Azure OpenAI config missing in .env (AZURE_OPENAI_KEY/ENDPOINT/etc). Chat fallback may fail.")

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
        self.vectorizer = TfidfVectorizer(stop_words=sw)
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
            if isinstance(choice, dict) and "message" in choice and isinstance(choice["message"], dict):
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

        # Try FAQ via TF-IDF similarity
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

        # Fallback to Azure Foundry Chat
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
            print("RAW RESPONSE:", resp)
            if hasattr(resp, "choices") and len(resp.choices) > 0:
                choice0 = resp.choices[0]
                text = self._extract_text_from_choice(choice0)
                if text:
                    return text.strip()
            return "🤖 I'm not certain about that. Could you rephrase or provide more details?"
        except Exception as e:
            print(f"❌ Azure Foundry error: {type(e).__name__}: {e}")
            return "⚠️ Olyph AI is currently offline or Azure OpenAI returned an error. Please try again later."

chatbot = OlyphauntChatbot(qa_pairs)

def handle_user_query(user_message: str):
    return chatbot.respond(user_message)

# ------------------ REPORT AGENT: fetch Google Sheet and return bytes ------------------

# Scopes we need for reading sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

def _get_service_account_credentials():
    """
    Returns google.oauth2.service_account.Credentials by reading either:
      - path provided in GOOGLE_SERVICE_ACCOUNT_JSON (file path), or
      - JSON content provided in GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT (string)
      - fallback: creds/service_account.json
    """
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "").strip()
    if content:
        try:
            info = json.loads(content)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return creds
        except Exception as e:
            raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT: {e}")
    if path and os.path.exists(path):
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
        return creds
    alt = os.path.join(os.getcwd(), "creds", "service_account.json")
    if os.path.exists(alt):
        creds = Credentials.from_service_account_file(alt, scopes=SCOPES)
        return creds
    raise FileNotFoundError("Service account JSON not found. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT.")

def get_gspread_client():
    """
    Create a gspread client authenticated with the service account.
    Use google.auth.transport.requests.AuthorizedSession so requests include OAuth2 tokens.
    """
    creds = _get_service_account_credentials()
    client = gspread.Client(auth=creds)
    # Attach an AuthorizedSession so HTTP calls include the OAuth2 credentials
    client.session = AuthorizedSession(creds)
    return client

def fetch_sheet_as_dataframe(sheet_id=None, sheet_name_or_index=None, value_render_option="FORMATTED_VALUE"):
    """
    Fetch a sheet and return a pandas DataFrame. Falls back to REPORT_SHEET_ID env if sheet_id is None.
    """
    if not sheet_id:
        sheet_id = os.getenv("REPORT_SHEET_ID", "").strip()
        if not sheet_id:
            raise ValueError("No sheet_id provided and REPORT_SHEET_ID is not set in environment.")

    # determine sheet index/name
    if sheet_name_or_index is None:
        env_sheet = os.getenv("REPORT_SHEET_NAME_OR_INDEX", "").strip()
        if env_sheet != "":
            try:
                sheet_name_or_index = int(env_sheet)
            except ValueError:
                sheet_name_or_index = env_sheet
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
    """
    Main helper to produce BytesIO, filename, mimetype
    """
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
