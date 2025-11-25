# agent.py (robust response parsing)
import os
import re
import fitz
import nltk
import numpy as np
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from nltk.corpus import stopwords

from openai import AzureOpenAI

load_dotenv(dotenv_path="./.env")

nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "shruti-gpt-4o-mini")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-15-preview")

if not (AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT and AZURE_DEPLOYMENT_NAME and AZURE_API_VERSION):
    raise ValueError("Missing Azure OpenAI configuration in .env.")

client = AzureOpenAI(
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

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
        """
        Robustly extract assistant text from a choice object/dict supporting multiple shapes.
        """
        # 1) choice has attribute 'message' which is an object with attribute 'content'
        try:
            if hasattr(choice, "message"):
                msg = choice.message
                # if msg is a dict-like
                if isinstance(msg, dict) and "content" in msg:
                    return msg.get("content")
                # if msg is an object with .content attribute
                if hasattr(msg, "content"):
                    return msg.content
        except Exception:
            pass

        # 2) choice is a dict with nested message->content
        try:
            if isinstance(choice, dict) and "message" in choice and isinstance(choice["message"], dict):
                return choice["message"].get("content")
        except Exception:
            pass

        # 3) legacy: choice has .text
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
            # DEBUG: print raw response (safe in dev)
            print("RAW RESPONSE:", resp)

            if hasattr(resp, "choices") and len(resp.choices) > 0:
                choice0 = resp.choices[0]
                text = self._extract_text_from_choice(choice0)
                if text:
                    return text.strip()

            # parsing fallback
            return "🤖 I'm not certain about that. Could you rephrase or provide more details?"
        except Exception as e:
            print(f"❌ Azure Foundry error: {type(e).__name__}: {e}")
            return "⚠️ Olyph AI is currently offline or Azure OpenAI returned an error. Please try again later."

chatbot = OlyphauntChatbot(qa_pairs)

def handle_user_query(user_message: str):
    return chatbot.respond(user_message)
