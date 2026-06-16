"""One-time bootstrap helper: mint a Gmail OAuth refresh token.

NOT imported at runtime. Run manually once to obtain a refresh token, then
store that token in Windows Credential Manager (keyring) — never in a file.

Usage:
    python get_gmail_token.py path\\to\\client_secret_*.json

Or set the GMAIL_CLIENT_SECRET_FILE environment variable to the path of the
downloaded Google OAuth client_secret JSON file:
    set GMAIL_CLIENT_SECRET_FILE=C:\\path\\to\\client_secret.json
    python get_gmail_token.py

The client_secret JSON is downloaded from the Google Cloud Console and must be
kept out of the repo (it contains the OAuth client id and secret).
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def main() -> None:
    client_secret_file = (
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GMAIL_CLIENT_SECRET_FILE")
    )
    if not client_secret_file:
        sys.exit(
            "Provide the OAuth client_secret JSON path as an argument or via the "
            "GMAIL_CLIENT_SECRET_FILE environment variable."
        )

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    creds = flow.run_local_server(port=0)
    print("REFRESH TOKEN:", creds.refresh_token)


if __name__ == "__main__":
    main()
