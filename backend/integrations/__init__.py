"""External integrations: Slack and Gmail.

Both clients construct cheaply and read their credentials lazily from the
keyring, degrading to safe no-ops when unconfigured. They are exposed here so the
tool system (Phase 6) and agents can import them from one place.
"""

from backend.integrations.gmail_client import GmailClient
from backend.integrations.slack_client import SlackClient

__all__ = ["GmailClient", "SlackClient"]
