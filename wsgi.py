# ── SecureMedia — WSGI entry point for Gunicorn ──
"""Production entry-point used by Gunicorn / Docker."""

from app import create_app

app = create_app("config.ProductionConfig")
