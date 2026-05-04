"""Static SPA assets path (Demo Chat UI); mirrors app/static layout used by itsm-app."""

from __future__ import annotations

import os

# Resolved directory for HTML/CSS/JS served from app.static mount in main.py
DIR = os.path.join(os.path.dirname(__file__), "..", "static")
STATIC_DIR = os.path.normpath(DIR)
