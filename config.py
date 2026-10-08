import os
from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str):
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    # MySQL (same credentials for every tenant DB, only db_name changes)
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASS = os.getenv("DB_PASS", "")

    # Auth
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_MAX_AGE_SECONDS = int(os.getenv("JWT_MAX_AGE_SECONDS", "60"))

    ALLOWED_ORIGINS = _split_csv(os.getenv("ALLOWED_ORIGINS", ""))

    # LLM
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    #OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    #OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    DEFAULT_LANG = os.getenv("DEFAULT_LANG", "fr")


settings = Settings()

if not settings.JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not set. Set it in the environment (.env) and make sure "
        "it matches the secret used by chatbot_client.php on the PHP side."
    )
