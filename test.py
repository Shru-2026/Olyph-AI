from openai import OpenAI
from dotenv import load_dotenv
import os

# ========== INITIAL SETUP ==========
load_dotenv()
print("Loaded key:", os.getenv("OPENAI_API_KEY"))


# Load your API key from .env file
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_with_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

if __name__ == "__main__":
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit", "bye"]:
            break

        response = chat_with_gpt(user_input)
        print("Chatbot:", response)
