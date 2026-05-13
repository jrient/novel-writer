import secrets as _secrets

from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/novel_writer.db"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:8083"

    # JWT Authentication — 必须通过 .env 或环境变量设置，否则每次重启 token 失效
    JWT_SECRET_KEY: str = _secrets.token_urlsafe(64)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # GitHub OAuth
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/github/callback"

    # WeChat OAuth
    WECHAT_APP_ID: Optional[str] = None
    WECHAT_APP_SECRET: Optional[str] = None
    WECHAT_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/wechat/callback"

    # AI Providers
    DEFAULT_AI_PROVIDER: str = "openai"

    # 通用 AI 配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"

    OPENAI_FALLBACK_API_KEY: Optional[str] = None
    OPENAI_FALLBACK_BASE_URL: Optional[str] = None
    OPENAI_FALLBACK_MODEL: Optional[str] = None

    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "llama3"

    # DeepSeek
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_PRO_MODEL: str = "deepseek-v4-pro"
    DEEPSEEK_FLASH_MODEL: str = "deepseek-v4-flash"

    # 剧本/小说内容创作专用配置（已迁移至 DEEPSEEK_*，保留向后兼容）
    SCRIPT_CONTENT_API_KEY: Optional[str] = None
    SCRIPT_CONTENT_BASE_URL: str = "https://api.deepseek.com"
    SCRIPT_CONTENT_MODEL: str = "deepseek-v4-flash"

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

    # 改编模块配置
    ADAPTATION_MAX_CHARS: int = 200_000
    ADAPTATION_REWRITE_CONCURRENCY: int = 5
    ADAPTATION_PER_SCENE_TIMEOUT_SEC: int = 90
    ADAPTATION_EXTRACT_MODEL: Optional[str] = None
    ADAPTATION_REWRITE_MODEL: Optional[str] = None
    # 单次 LLM 调用 max_tokens 上限。reasoning 模型常需 1~2 万 token 给思考过程，
    # 太小会导致 finish_reason=length / content 为空。
    ADAPTATION_MAX_TOKENS: int = 64_000
    ADAPTATION_STALE_RUN_CLEANUP_AGE_SEC: int = 3600

    # AI Context Limits
    AI_CONTEXT_CHARACTER_LIMIT: int = 10
    AI_CONTEXT_WORLDBUILDING_LIMIT: int = 10
    AI_MAX_TOKENS_DEFAULT: int = 4000
    AI_MAX_TOKENS_STREAM: int = 8000

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
