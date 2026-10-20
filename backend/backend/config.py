from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from psycopg.conninfo import conninfo_to_dict
from psycopg import ProgrammingError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).with_name(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr = SecretStr("")
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "nifs_ocean"
    db_user: str = "postgres"
    db_password: SecretStr = SecretStr("")
    db_sslmode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = "prefer"
    db_connect_timeout: int = Field(default=5, ge=1, le=30)
    db_statement_timeout_ms: int = Field(default=15000, ge=1)
    # 로컬 주소(localhost/127.0.0.1)는 항상 허용. 그 밖의 앱 주소는 .env에 JSON 목록으로 추가.
    # 예: CORS_ORIGINS=["https://my-app.example.com"]
    cors_origins: list[str] = []

    def connection_kwargs(self) -> dict:
        if self.database_url.get_secret_value():
            try:
                params = conninfo_to_dict(self.database_url.get_secret_value())
            except ProgrammingError:
                raise ValueError("DATABASE_URL must be a valid PostgreSQL connection string.") from None
            # URL settings take precedence over legacy DB_* connection fields.
            params.setdefault("sslmode", "require")
            params.setdefault("connect_timeout", self.db_connect_timeout)
            return params
        return {
            "host": self.db_host,
            "port": self.db_port,
            "dbname": self.db_name,
            "user": self.db_user,
            "password": self.db_password.get_secret_value(),
            "sslmode": self.db_sslmode,
            "connect_timeout": self.db_connect_timeout,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
