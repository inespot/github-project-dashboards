"""Entry point for the dashboard.

Run with:
    solara run dashboard.py
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()  # load GITHUB_TOKEN from .env before any API calls

# Re-export routes and Layout so Solara finds them at the module level.
from app import routes  # noqa: F401, E402
from app import Layout  # noqa: F401, E402
