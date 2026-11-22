from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "sqlite:///./signal_stack.db"
    
    # LLM Settings
    DEFAULT_LLM_PROVIDER: Literal["groq", "gemini", "mock"] = "gemini"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_FALLBACK_MODELS: list[str] = [
        "gemini-flash-lite-latest",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3-flash-preview",
        "gemini-flash-latest"
    ]


    
    # Reddit Settings
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    
    # Crawler Settings
    USER_AGENT: str = "SignalStackBot/1.0 (+https://github.com/signalstack/crawler-policy)"
    CRAWL_CONCURRENCY: int = 3
    CRAWL_DELAY_SECONDS: float = 2.0
    RESPECT_ROBOTS_TXT: bool = True
    
    # Signal Recency & Priority Ranking Configuration
    MAX_RECENT_SIGNAL_DAYS: int = 90
    WEIGHT_RELEVANCE: float = 0.30
    WEIGHT_IMPACT: float = 0.20
    WEIGHT_URGENCY: float = 0.15
    WEIGHT_CREDIBILITY: float = 0.15
    WEIGHT_RECENCY: float = 0.10
    WEIGHT_NOVELTY: float = 0.10
    
    # Scheduler
    BRIEF_SCHEDULE_CRON: str = "0 6 * * 1"

settings = Settings()

