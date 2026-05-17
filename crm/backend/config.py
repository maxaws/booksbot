from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./crm.db"
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]
    env: Literal["development", "production"] = "production"

    # JWT — override via .env in production
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_RANDOM_64_CHAR_STRING"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 h

    # Admin credentials — set ADMIN_PASSWORD_HASH in .env (bcrypt)
    admin_username: str = "admin"
    admin_password_hash: str = ""  # empty = login disabled until configured

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
