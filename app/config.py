import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    app_name: str = "PACT (Proactive AutoPay Compliance & Tracking)"
    app_version: str = "1.0.0"
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")
    database_path: str = os.getenv("DATABASE_PATH", "pact.db")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))

settings = Settings()
