# chat_agent.py
"""
Ask-me-anything agent for Olyph AI.

- Loads FAQ from PDF and does TF-IDF similarity.
- If FAQ match is weak, falls back to Azure OpenAI (chat completion).
"""

import os
import re
import fitz
import nltk
import numpy as np
from dotenv import load_dotenv
from pathlib import Path
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from openai import AzureOpenAI

# ---------- ENV + NLTK SETUP ----------
load_dotenv(dotenv_path="./.env")

nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

threshold = 0.6

# ---------- Azure/OpenAI config ----------
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "shruti-gpt-4o-mini")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

if not (AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT and AZURE_DEPLOYMENT_NAME and AZURE_API_VERSION):
    print("⚠️ Warning: Azure OpenAI config missing in environment. Chat fallback may be limited.")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

# ---------- PDF FAQ loader ----------
def extract_pdf_text(pdf_path: str):
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

            # Question line
            if re.match(r"^(q\d*[\.\):]*|question[\.\):]*|q:)", line.lower()) or line.endswith("?"):
                if question and answer:
                    qa_pairs.append((question.strip(), answer.strip()))
                question = re.sub(
                    r"^(q\d*[\.\):]*|question[\.\):]*|q:)",
                    "",
                    line,
                    flags=re.I,
                ).strip()
                answer = ""

            # Answer line
            elif re.match(r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)", line.lower()):
                answer_line = re.sub(
                    r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)",
                    "",
                    line,
                    flags=re.I,
                ).strip()
                answer += " " + answer_line

            # Continuation of answer
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
    qa_pairs = [
        (
            "What is Olyphaunt Solutions?",
            "Olyphaunt Solutions is a healthcare technology company.",
        )
    ]

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
        # robust extraction from different response shapes
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

    def respond(self, user_query: str) -> str:
        user_query_text = (user_query or "").strip()
        if not user_query_text:
            return "⚠️ Please enter a valid question."

        # 1) FAQ via TF-IDF similarity
        try:
            if self.question_vectors is not None:
                qvec = self.vectorizer.transform([user_query_text.lower()])
                sims = cosine_similarity(qvec, self.question_vectors)
                max_idx = int(sims.argmax())
                score = float(sims[0, max_idx])
                print(f"🔍 FAQ similarity score: {score:.2f}")
                if score >= threshold:
                    return self.answers[max_idx]
        except Exception as e:
            print("⚠️ FAQ check error:", e)

        # 2) Fallback: Azure OpenAI
        try:
            print("✨ Calling Azure Foundry chat completion...")
            messages = [
                {"role": "system", "content": "You are an assistant for Olyphaunt Solutions."},
                {"role": "user", "content": user_query_text},
            ]
            resp = client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.2,
                max_tokens=256,
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

# Single global chatbot instance
chatbot = OlyphauntChatbot(qa_pairs)

def handle_user_query(user_message: str) -> str:
  """
  Public function used by Flask route /ask.
  """
  return chatbot.respond(user_message)
