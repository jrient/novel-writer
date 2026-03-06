from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/novel_writer.db"

    # AI Providers
    DEFAULT_AI_PROVIDER: str = "openai"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"

    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3"

    # Embedding
    EMBEDDING_API_BASE: str = "https://yibuapi.com/v1"
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Jina API
    JINA_API_KEY: Optional[str] = None

    # Google Gemini API
    GEMINI_API_KEY: Optional[str] = None

    # Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
