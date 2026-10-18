"""Shared config: loads the repo-root .env and makes HTTPS work on every machine.

Import this before anything that opens network connections.
"""
import os
from pathlib import Path

import certifi
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# python.org builds of Python ship without CA certificates until "Install Certificates"
# is run, which breaks every HTTPS call to Agentverse. Point OpenSSL at certifi's bundle.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

ASI_ONE_API_KEY = os.getenv("ASI_ONE_API_KEY", "")
AGENTVERSE_API_KEY = os.getenv("AGENTVERSE_API_KEY", "")


def seed(name: str) -> str:
    """Seed for an agent, e.g. seed("coordinator") reads COORDINATOR_SEED."""
    return os.environ[f"{name.upper()}_SEED"]


def port(name: str, default: int) -> int:
    return int(os.getenv(f"{name.upper()}_PORT", str(default)))
