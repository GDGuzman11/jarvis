from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

flow = InstalledAppFlow.from_client_secrets_file(
    r"C:\Users\User\Desktop\Jarvis\client_secret_1057050494684-9nhus4frc8k62tejsofqug6qo3mipdha.apps.googleusercontent.com.json",
    SCOPES,
)
creds = flow.run_local_server(port=0)
print("REFRESH TOKEN:", creds.refresh_token)
