import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # --- Core ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # --- Database ---
    _db_url = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(basedir, "kairozen.db"))
    # Render/Heroku style fix: postgres:// -> postgresql://
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Provider (khmer-smm.com) ---
    PROVIDER_API_URL = os.environ.get("PROVIDER_API_URL", "https://khmer-smm.com/api/v2")
    PROVIDER_API_KEY = os.environ.get("PROVIDER_API_KEY", "")

    # --- Pricing ---
    DEFAULT_MARKUP_PERCENT = float(os.environ.get("DEFAULT_MARKUP_PERCENT", "30"))

    # --- CamRapidPay (KHQR) ---
    CAMRAPID_API_KEY = os.environ.get("CAMRAPID_API_KEY", "")
    CAMRAPID_CREATE_URL = os.environ.get(
        "CAMRAPID_CREATE_URL", "https://pay.camrapidpay.com/api/v1/khqr/create-payments"
    )
    CAMRAPID_CHECK_URL = os.environ.get(
        "CAMRAPID_CHECK_URL", "https://pay.camrapidpay.com/check-transaction-api"
    )

    # --- Admin bootstrap ---
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@kairozen.local")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")
