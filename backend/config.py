import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# All the Groq models you’re okay using, in priority order
MODEL_FALLBACKS = [
    "llama-3.2-8b-instant",   # fast, small
    "llama-3.1-8b-instant",   # stable fallback
    "mixtral-8x7b",           # large, high-quality
]

# Connect to Groq API
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)

def get_available_model():
    """Try to find the first available model from MODEL_FALLBACKS."""
    try:
        available = [m.id for m in client.models.list().data]
    except Exception as e:
        print("⚠️ Could not list models:", e)
        return MODEL_FALLBACKS[0]  # fallback to first

    for m in MODEL_FALLBACKS:
        if m in available:
            print(f"✅ Using available model: {m}")
            return m

    print("⚠️ No preferred model found; defaulting to first fallback")
    return MODEL_FALLBACKS[0]

# Pick the active model automatically
MODEL = get_available_model()

with open("model_log.txt", "a", encoding="utf-8") as f:
    from datetime import datetime
    f.write(f"[{datetime.now()}] Active model: {MODEL}\n")
