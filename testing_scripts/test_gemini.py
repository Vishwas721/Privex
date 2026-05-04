import os

from dotenv import load_dotenv
from google.genai.errors import APIError
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables from .env
load_dotenv()


def test_gemini_connection() -> None:
    print("[INFO] Initializing Gemini connection test...")

    # Prefer the newer Gemini-specific key, then fall back to the legacy Google key.
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY or GOOGLE_API_KEY not found in environment variables.")
        return

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        print("[INFO] Available Models:")
        for model in client.models.list():
            supported_methods = getattr(model, "supported_generation_methods", []) or []
            if "generateContent" in supported_methods:
                print(model.name)
    except Exception as exc:
        print(f"[WARN] Could not list models via google.genai: {exc}")

    try:
        # Initialize the model used by memory_agent testing.
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite-preview",
            api_key=api_key,
            temperature=0.0,
            retries=2,
        )

        print("[INFO] Sending test payload to Google servers...")
        response = llm.invoke(
            "Hello! This is a simple API test. "
            "Reply with 'Connection successful!' if you receive this."
        )

        print("\n[SUCCESS] Model responded:")
        print(f"[MODEL] {response.content}\n")

    except APIError as exc:
        print("\n[ERROR] API ERROR CAUGHT:")
        print(f"Details: {exc}")
        if "503" in str(exc):
            print("Diagnosis: Google servers are overloaded (503 Unavailable).")
    except Exception as exc:
        print("\n[ERROR] UNEXPECTED ERROR CAUGHT:")
        print(f"Details: {exc}")


if __name__ == "__main__":
    test_gemini_connection()
