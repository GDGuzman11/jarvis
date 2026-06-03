"""Typed credential access for Jarvis via the Windows Credential Manager.

Per Security Rule 1 ("Zero secrets in files") all real API keys and OAuth
secrets live in the OS keyring (Windows Credential Manager) under the service
name ``jarvis``. Each credential is stored with a stable username matching the
variable names documented in ``.env.example`` (e.g. ``ANTHROPIC_API_KEY``).

This module exposes a typed getter/setter for every credential. Getters raise
:class:`MissingCredentialError` when a value is absent rather than silently
returning ``None`` so that misconfiguration fails loud and early.

NO SECRETS ARE STORED IN THIS FILE — only ``keyring`` calls.

To populate a credential::

    from backend.security import keystore
    keystore.set_anthropic_api_key("sk-ant-...")

To read one::

    api_key = keystore.get_anthropic_api_key()
"""

from __future__ import annotations

import keyring

# Service name registered in the Windows Credential Manager. Matches the
# documented service name in .env.example.
SERVICE_NAME: str = "jarvis"

# Keyring usernames for each credential. These mirror the variable names in
# .env.example exactly so a value set via the env template's instructions and a
# value set via this module are interchangeable.
ANTHROPIC_API_KEY: str = "ANTHROPIC_API_KEY"
ELEVENLABS_API_KEY: str = "ELEVENLABS_API_KEY"
ELEVENLABS_VOICE_ID: str = "ELEVENLABS_VOICE_ID"
SLACK_BOT_TOKEN: str = "SLACK_BOT_TOKEN"
SLACK_APP_TOKEN: str = "SLACK_APP_TOKEN"
SLACK_SIGNING_SECRET: str = "SLACK_SIGNING_SECRET"
GMAIL_CLIENT_ID: str = "GMAIL_CLIENT_ID"
GMAIL_CLIENT_SECRET: str = "GMAIL_CLIENT_SECRET"
GMAIL_REDIRECT_URI: str = "GMAIL_REDIRECT_URI"
GMAIL_REFRESH_TOKEN: str = "GMAIL_REFRESH_TOKEN"

# Canonical list of every credential username this keystore manages. Useful for
# audits (e.g. the security-agent) and the first-run setup wizard.
ALL_CREDENTIALS: tuple[str, ...] = (
    ANTHROPIC_API_KEY,
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    SLACK_BOT_TOKEN,
    SLACK_APP_TOKEN,
    SLACK_SIGNING_SECRET,
    GMAIL_CLIENT_ID,
    GMAIL_CLIENT_SECRET,
    GMAIL_REDIRECT_URI,
    GMAIL_REFRESH_TOKEN,
)


class MissingCredentialError(RuntimeError):
    """Raised when a requested credential is not present in the keyring."""

    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(
            f"Credential '{username}' is not set in the Windows Credential "
            f"Manager under service '{SERVICE_NAME}'. Store it via "
            f"backend.security.keystore (e.g. set_{username.lower()}(...)) or "
            f"the first-run setup wizard before starting Jarvis."
        )


def _get(username: str) -> str:
    """Return a credential value, raising if it is missing or blank."""
    value = keyring.get_password(SERVICE_NAME, username)
    if value is None or value == "":
        raise MissingCredentialError(username)
    return value


def _set(username: str, value: str) -> None:
    """Store a credential value, rejecting empty values."""
    if not isinstance(value, str) or value == "":
        raise ValueError(
            f"Refusing to store an empty value for credential '{username}'."
        )
    keyring.set_password(SERVICE_NAME, username, value)


def _delete(username: str) -> None:
    """Remove a credential if present; a no-op when it does not exist."""
    try:
        keyring.delete_password(SERVICE_NAME, username)
    except keyring.errors.PasswordDeleteError:
        # Already absent — deletion is idempotent from the caller's view.
        pass


def has_credential(username: str) -> bool:
    """Return True if the credential exists and is non-empty."""
    value = keyring.get_password(SERVICE_NAME, username)
    return bool(value)


def missing_credentials() -> list[str]:
    """Return the usernames of every managed credential not yet set."""
    return [name for name in ALL_CREDENTIALS if not has_credential(name)]


# ---------------------------------------------------------------------------
# Anthropic / Claude
# ---------------------------------------------------------------------------
def get_anthropic_api_key() -> str:
    return _get(ANTHROPIC_API_KEY)


def set_anthropic_api_key(value: str) -> None:
    _set(ANTHROPIC_API_KEY, value)


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------
def get_elevenlabs_api_key() -> str:
    return _get(ELEVENLABS_API_KEY)


def set_elevenlabs_api_key(value: str) -> None:
    _set(ELEVENLABS_API_KEY, value)


def get_elevenlabs_voice_id() -> str:
    return _get(ELEVENLABS_VOICE_ID)


def set_elevenlabs_voice_id(value: str) -> None:
    _set(ELEVENLABS_VOICE_ID, value)


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------
def get_slack_bot_token() -> str:
    return _get(SLACK_BOT_TOKEN)


def set_slack_bot_token(value: str) -> None:
    _set(SLACK_BOT_TOKEN, value)


def get_slack_app_token() -> str:
    return _get(SLACK_APP_TOKEN)


def set_slack_app_token(value: str) -> None:
    _set(SLACK_APP_TOKEN, value)


def get_slack_signing_secret() -> str:
    return _get(SLACK_SIGNING_SECRET)


def set_slack_signing_secret(value: str) -> None:
    _set(SLACK_SIGNING_SECRET, value)


# ---------------------------------------------------------------------------
# Gmail (OAuth 2.0)
# ---------------------------------------------------------------------------
def get_gmail_client_id() -> str:
    return _get(GMAIL_CLIENT_ID)


def set_gmail_client_id(value: str) -> None:
    _set(GMAIL_CLIENT_ID, value)


def get_gmail_client_secret() -> str:
    return _get(GMAIL_CLIENT_SECRET)


def set_gmail_client_secret(value: str) -> None:
    _set(GMAIL_CLIENT_SECRET, value)


def get_gmail_redirect_uri() -> str:
    return _get(GMAIL_REDIRECT_URI)


def set_gmail_redirect_uri(value: str) -> None:
    _set(GMAIL_REDIRECT_URI, value)


def get_gmail_refresh_token() -> str:
    return _get(GMAIL_REFRESH_TOKEN)


def set_gmail_refresh_token(value: str) -> None:
    _set(GMAIL_REFRESH_TOKEN, value)
