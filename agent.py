# agent.py
import os
import fitz  # PyMuPDF
import re
import nltk
import numpy as np
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import google.generativeai as genai
from dotenv import load_dotenv

# ========== INITIAL SETUP ==========
load_dotenv(dotenv_path="./.env")


# Download necessary NLTK data silently
nltk.download("punkt", quiet=True)
nltk.download("stopwords", quiet=True)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
print("🔑 Gemini Key Loaded:", os.getenv("GEMINI_API_KEY")[:10], "...")

if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY not found in .env file.")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ========== EXTRACT Q&A FROM PDF ==========
def extract_pdf_text(pdf_path):
    """
    Reads a PDF and extracts (question, answer) pairs from Q/A format text.
    Expected pattern:
        Q: What is Olyphaunt Solutions?
        A: Olyphaunt Solutions is a healthcare IT consultancy...
    """
    qa_pairs = []
    try:
        with fitz.open(pdf_path) as reader:
            text = ""
            for page_num in range(len(reader)):
                text += reader[page_num].get_text("text")

        lines = text.split("\n")
        question, answer = None, ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect question
            if re.match(r"^(q\d*[\.\):]*|question[\.\):]*|q:)", line.lower()) or line.endswith("?"):
                if question and answer:
                    qa_pairs.append((question.strip(), answer.strip()))
                question = re.sub(r"^(q\d*[\.\):]*|question[\.\):]*|q:)", "", line, flags=re.I).strip()
                answer = ""

            # Detect answer
            elif re.match(r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)", line.lower()):
                answer_line = re.sub(r"^(a\d*[\.\):]*|a:|ans[\.\):]*|answer[\.\):]*)", "", line, flags=re.I).strip()
                answer += " " + answer_line

            # Continue the current answer
            elif question:
                answer += " " + line.strip()

        if question and answer:
            qa_pairs.append((question.strip(), answer.strip()))

        print(f"✅ Loaded {len(qa_pairs)} Q&A pairs from '{pdf_path}'")
        return qa_pairs

    except Exception as e:
        print(f"⚠️ Error reading PDF '{pdf_path}': {e}")
        return []


# ========== CHATBOT CLASS ==========
class OlyphauntChatbot:
    def __init__(self, qa_pairs):
        if not qa_pairs:
            raise ValueError("⚠️ No Q&A pairs found in PDF.")
        self.qa_pairs = qa_pairs
        self.questions = [q.lower() for q, _ in qa_pairs]
        self.answers = [a for _, a in qa_pairs]
        self.vectorizer = TfidfVectorizer(stop_words=stopwords.words("english"))
        self.question_vectors = self.vectorizer.fit_transform(self.questions)

    def respond(self, user_query):
        user_query = user_query.lower().strip()
        if not user_query:
            return "⚠️ Please enter a valid question."

        # Compute similarity between query and known FAQ questions
        query_vector = self.vectorizer.transform([user_query])
        similarities = cosine_similarity(query_vector, self.question_vectors)
        max_idx = np.argmax(similarities)
        score = similarities[0, max_idx]

        print(f"🔍 FAQ similarity score: {score:.2f}")

        # Only use FAQ if similarity > 0.7
        if score > 0.7:
            print("📘 Responding from FAQ database (High confidence).")
            return self.answers[max_idx]
        else:
            print("⚠️ Low similarity (< 0.7) → No response returned.")
            return "❌ Sorry, I don’t have enough information to answer that right now."

        # Fallback to Gemini for general response
        try:
            print("✨ No close FAQ found → Fallback to Gemini model...")
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(user_query)
            if response and hasattr(response, "text"):
                return response.text.strip()
            else:
                return "🤖 I'm not sure about that. Could you rephrase?"
        except Exception as e:
            print(f"❌ Gemini API error: {e}")
            return "⚠️ Olyph AI is currently offline. Please try again later."


# ========== INITIALIZE CHATBOT ==========
FAQ_PATH = "Olyphaunt FAQs.pdf"  # make sure this file is in the same folder
chatbot = OlyphauntChatbot(extract_pdf_text(FAQ_PATH))


# ========== FUNCTION CALLED FROM FLASK ==========
def handle_user_query(user_message: str):
    return chatbot.respond(user_message)
