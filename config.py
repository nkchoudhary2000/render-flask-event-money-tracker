import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-key-change-in-production-123456789")
    
    # Database configuration
    # Fix Render's postgres:// URI scheme if present (SQLAlchemy 1.4+ expects postgresql://)
    raw_db_url = os.getenv("DATABASE_URL", "sqlite:///event_tracker.db")
    if raw_db_url.startswith("postgres://"):
        raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    } if not raw_db_url.startswith("sqlite") else {}

    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Application base URL
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")

    # Google OAuth 2.0 & Drive API settings
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_DRIVE_FOLDER_NAME = os.getenv("GOOGLE_DRIVE_FOLDER_NAME", "EventMoneyTracker_Receipts")
    
    # OAuth Scopes
    GOOGLE_OAUTH_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/drive.file"
    ]

    # File uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf", "json", "csv"}

    # Flasgger Swagger configuration
    SWAGGER = {
        "title": "Event Money Tracker API",
        "uiversion": 3,
        "version": "1.0.0",
        "description": "Comprehensive REST API for Event Money Tracking, Category Management, Cash Flow Aggregations, Google Drive Integration, and Admin Backup/Restore.",
        "termsOfService": "",
        "specs_route": "/apidocs/",
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/apispec.json",
                "rule_filter": lambda rule: True,  # include all endpoints
                "model_filter": lambda tag: True,
            }
        ],
        "headers": []
    }

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    LOG_LEVEL = "DEBUG"

class ProductionConfig(Config):
    """Production configuration for Render.com."""
    DEBUG = False
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    LOG_LEVEL = "DEBUG"
    WTF_CSRF_ENABLED = False

config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}
