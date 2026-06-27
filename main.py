"""
Main entry point — re-exports the Flask app from detective-api
so gunicorn can find it as `main:app`.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "detective-api"))

from app import app  # noqa: F401
