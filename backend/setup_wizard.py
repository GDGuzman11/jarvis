"""First-run setup wizard API (Phase 10).

A tiny FastAPI router the frontend's first-run wizard calls to discover which
credentials Helix still needs and to store them — straight into the Windows
Credential Manager via :mod:`backend.security.keystore`, never a file (Security
Rule 1). Three endpoints::

    GET  /setup/status      -> {missing: [...], required: [...], complete: bool}
    POST /setup/credential  -> {name, value}  stores one credential
    GET  /setup/complete    -> {complete: bool}

Security
--------
* These endpoints are served by the same Uvicorn app that binds to
  ``127.0.0.1`` only (Security Rule 2 in :mod:`backend.main`), so they are never
  reachable off-box.
* ``POST /setup/credential`` validates the credential ``name`` against
  :data:`REQUIRED_CREDENTIALS` and rejects anything else with ``400`` — a
  caller can't write an arbitrary keyring entry through this surface.
* The stored value is never echoed back. Responses only ever report *which*
  credentials are present/missing by name, never their values.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.logging_config import get_logger
from backend.security import keystore

log = get_logger(__name__)

# The credentials the first-run wizard collects, in the order the UI should
# prompt for them. This is a deliberate subset of keystore.ALL_CREDENTIALS:
# the optional Slack app/signing and Gmail redirect values are not required to
# get Helix talking, so the wizard does not block on them. Names are the
# lower-case form the wizard sends; they map 1:1 to the keystore username
# constants below.
REQUIRED_CREDENTIALS: tuple[str, ...] = (
    "anthropic_api_key",
    "elevenlabs_api_key",
    "elevenlabs_voice_id",
    "slack_bot_token",
    "gmail_client_id",
    "gmail_client_secret",
    "gmail_refresh_token",
)

# Map each wizard credential name to its keystore username constant. Using the
# keystore constants (rather than re-deriving the string) keeps this in lockstep
# with the keystore if a username ever changes.
_NAME_TO_KEYSTORE: dict[str, str] = {
    "anthropic_api_key": keystore.ANTHROPIC_API_KEY,
    "elevenlabs_api_key": keystore.ELEVENLABS_API_KEY,
    "elevenlabs_voice_id": keystore.ELEVENLABS_VOICE_ID,
    "slack_bot_token": keystore.SLACK_BOT_TOKEN,
    "gmail_client_id": keystore.GMAIL_CLIENT_ID,
    "gmail_client_secret": keystore.GMAIL_CLIENT_SECRET,
    "gmail_refresh_token": keystore.GMAIL_REFRESH_TOKEN,
}


router = APIRouter(prefix="/setup", tags=["setup"])


class CredentialIn(BaseModel):
    """Body for ``POST /setup/credential``."""

    name: str = Field(..., description="Credential name (see REQUIRED_CREDENTIALS).")
    value: str = Field(..., min_length=1, description="The secret value to store.")


def _missing_required() -> list[str]:
    """Return the required credential names not yet present in the keyring.

    Reported in the wizard's lower-case naming, in the canonical prompt order.
    """
    return [
        name
        for name in REQUIRED_CREDENTIALS
        if not keystore.has_credential(_NAME_TO_KEYSTORE[name])
    ]


@router.get("/status")
async def setup_status() -> dict[str, object]:
    """Report which required credentials are still missing from the keyring.

    Returns the ``missing`` list (what the wizard must still collect), the full
    ``required`` list (for the UI to render every field), and a ``complete``
    flag that is ``True`` once nothing is missing. No values are ever returned.
    """
    missing = _missing_required()
    return {
        "missing": missing,
        "required": list(REQUIRED_CREDENTIALS),
        "complete": not missing,
    }


@router.post("/credential")
async def set_credential(body: CredentialIn) -> dict[str, object]:
    """Store one credential in the Windows Credential Manager.

    Validates ``name`` against :data:`REQUIRED_CREDENTIALS` — an unknown name is
    rejected with ``400`` so this surface can't write arbitrary keyring entries.
    The value is stored via the keystore and never echoed back; the response
    reports only the name stored and the updated completion state.
    """
    name = body.name.strip().lower()
    keystore_username = _NAME_TO_KEYSTORE.get(name)
    if keystore_username is None:
        log.warning("setup_credential_rejected_unknown_name", name=body.name)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown credential '{body.name}'. Allowed: "
                f"{', '.join(REQUIRED_CREDENTIALS)}."
            ),
        )

    try:
        keystore._set(keystore_username, body.value)
    except ValueError as exc:
        # Empty value — keystore refuses to store it.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # Metadata only — never the value (Security Rule 6 / audit-log spirit).
    log.info("setup_credential_stored", name=name)
    missing = _missing_required()
    return {"stored": name, "complete": not missing, "missing": missing}


@router.get("/complete")
async def setup_complete() -> dict[str, bool]:
    """Return ``{complete: true}`` once every required credential is present."""
    return {"complete": not _missing_required()}


__all__ = ["router", "REQUIRED_CREDENTIALS"]
