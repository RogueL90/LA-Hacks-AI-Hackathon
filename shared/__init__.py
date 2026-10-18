"""Shared contracts and payment helpers.

Importing anything from `shared` first loads .env and the CA bundle (shared.config), so HTTPS
to Agentverse and Stripe works even when a module imports uagents before anything else.
"""
from shared import config  # noqa: F401
