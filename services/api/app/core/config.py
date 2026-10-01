from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Platform configuration loaded from environment."""
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    LOG_LEVEL: str = Field(default="INFO")

    # API
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")

    # Security
    SECRET_KEY: str = Field(default="dev_secret_key_needs_replacement_in_production_32chars")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    ADMIN_EMAIL: str = Field(default="admin@tradeforge.io")

    # Database & Redis
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./tradeforge_dev.db")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

settings = Settings()
