"""
backend/config.py  —  Owner: Rani Gupta (24BIT0543)
=====================================================
All configuration comes from environment variables (optionally a local .env that is
git-ignored). Nothing secret has a default value.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("config")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


@dataclass
class Settings:
    environment: str = "development"
    database_url: str = f"sqlite:///{ROOT / 'runtime' / 'app.db'}"
    auto_migrate: bool = True
    secret_key: str = ""
    jwt_issuer: str = "healthcare-cloud-framework"
    jwt_audience: str = "hcf-api"
    access_token_minutes: int = 60
    password_iterations: int = 310_000
    cors_origins: list[str] = field(default_factory=list)
    max_body_bytes: int = 256 * 1024
    rate_limit_per_minute: int = 600
    model_dir: Path = ROOT / "models" / "latency_lstm"
    runtime_dir: Path = ROOT / "runtime"
    cloud_adapter: str = "local"  # local | s3
    s3_bucket: str = ""
    execution_max_attempts: int = 3
    alerts_sync: bool = False  # True = dispatch inside the request (tests / demos)
    alert_notify_severities: list[str] = field(default_factory=lambda: ["CRITICAL"])
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    alert_email_to: str = ""
    alert_webhook_url: str = ""
    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    frontend_dist: Path = ROOT / "frontend" / "dist"

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        _load_dotenv(ROOT / ".env")
        e = os.environ.get
        s = cls(
            environment=e("ENVIRONMENT", "development"),
            database_url=e("DATABASE_URL", cls.database_url),
            auto_migrate=_bool("AUTO_MIGRATE", True),
            secret_key=e("SECRET_KEY", ""),
            access_token_minutes=int(e("ACCESS_TOKEN_EXPIRE_MINUTES", 60)),
            password_iterations=int(e("PASSWORD_HASH_ITERATIONS", 310_000)),
            cors_origins=_list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
            max_body_bytes=int(e("MAX_BODY_BYTES", 256 * 1024)),
            rate_limit_per_minute=int(e("RATE_LIMIT_PER_MINUTE", 600)),
            model_dir=Path(e("MODEL_DIR", str(ROOT / "models" / "latency_lstm"))),
            runtime_dir=Path(e("RUNTIME_DIR", str(ROOT / "runtime"))),
            cloud_adapter=e("CLOUD_ADAPTER", "local"),
            s3_bucket=e("S3_BUCKET", ""),
            execution_max_attempts=int(e("EXECUTION_MAX_ATTEMPTS", 3)),
            alerts_sync=_bool("ALERTS_SYNC", False),
            alert_notify_severities=_list("ALERT_NOTIFY_SEVERITIES", "CRITICAL"),
            telegram_bot_token=e("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=e("TELEGRAM_CHAT_ID", ""),
            smtp_host=e("SMTP_HOST", ""),
            smtp_port=int(e("SMTP_PORT", 587)),
            smtp_username=e("SMTP_USERNAME", ""),
            smtp_password=e("SMTP_PASSWORD", ""),
            smtp_from=e("SMTP_FROM", ""),
            alert_email_to=e("ALERT_EMAIL_TO", ""),
            alert_webhook_url=e("ALERT_WEBHOOK_URL", ""),
            bootstrap_admin_username=e("BOOTSTRAP_ADMIN_USERNAME", ""),
            bootstrap_admin_password=e("BOOTSTRAP_ADMIN_PASSWORD", ""),
            frontend_dist=Path(e("FRONTEND_DIST", str(ROOT / "frontend" / "dist"))),
        )
        for k, v in overrides.items():
            setattr(s, k, v)
        if not s.secret_key:
            if s.environment == "production":
                raise RuntimeError("SECRET_KEY must be set in production")
            s.secret_key = secrets.token_hex(32)
            log.warning(
                "SECRET_KEY not set: generated a random key for this process; tokens will not "
                "survive a restart. Set SECRET_KEY in .env."
            )
        return s
