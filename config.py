"""
Configuration classes for Flask Portfolio CMS.
Uses environment variables exclusively for sensitive values.
"""
import os
from datetime import timedelta


class Config:
    """Base configuration shared by all environments."""

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY") or "CHANGE-ME-BEFORE-DEPLOYING"
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1-hour CSRF token validity

    # ── Session ───────────────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///portfolio.db")
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # ── Email ─────────────────────────────────────────────────────────────────
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True").lower() in ("true", "1", "on")
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "").replace(" ", "").strip()
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME", "")
    ).strip()
    CONTACT_RECIPIENT_EMAIL = os.environ.get(
        "CONTACT_RECIPIENT_EMAIL", os.environ.get("MAIL_USERNAME", "")
    )
    ALLOWED_ADMIN_EMAILS = [
        email.strip() for email in os.environ.get(
            "ALLOWED_ADMIN_EMAILS", "safiullah477845@gmail.com"
        ).split(",") if email.strip()
    ]

    # ── Uploads ───────────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB upload limit
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


class DevelopmentConfig(Config):
    """Development environment — debug ON, relaxed security."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    """Testing environment — in-memory SQLite, CSRF disabled."""
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False


class ProductionConfig(Config):
    """Production environment — strict security, HTTPS-aware cookies."""
    DEBUG = False
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "True").lower() in ("true", "1", "on")
    SESSION_COOKIE_SAMESITE = "Lax"
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year static cache

    @classmethod
    def validate(cls):
        """Raise at startup if critical production secrets are missing."""
        key = os.environ.get("SECRET_KEY", "")
        if not key or key in (
            "CHANGE-ME-BEFORE-DEPLOYING",
            "change-this-to-a-secure-random-key-before-deploying",
            "generate-a-secure-random-secret-key",
        ):
            raise RuntimeError(
                "SECRET_KEY must be set to a secure random value in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(key) < 32:
            raise RuntimeError(
                "SECRET_KEY is too short. Use at least 32 random bytes."
            )


# ── Environment name → Config class map ──────────────────────────────────────
config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
