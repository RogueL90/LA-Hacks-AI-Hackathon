"""Environment config. Values come from space_service/.env (never committed)."""
import os
from pathlib import Path

from dotenv import load_dotenv

SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(SERVICE_DIR / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
# low | medium | high: more effort = more thinking = slower and pricier.
ANTHROPIC_EFFORT = os.getenv("ANTHROPIC_EFFORT", "low")
SENTRY_DSN = os.getenv("SENTRY_DSN", "")

# Absolute base URLs; Space.viewer_url / snapshot_url are built from these.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
VIEWER_BASE_URL = os.getenv("VIEWER_BASE_URL", "http://localhost:5173").rstrip("/")

# Comma-separated origins allowed to call the API (the viewer).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

DATA_DIR = Path(os.getenv("DATA_DIR", SERVICE_DIR / "data"))
PREBUILT_DIR = SERVICE_DIR / "prebuilt"

# While the real pipeline is being built, /spaces/build returns the prebuilt demo.
USE_PREBUILT = os.getenv("USE_PREBUILT", "1") == "1"
DEMO_SPACE_ID = "demo_home_01"
