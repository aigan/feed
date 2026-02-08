import os

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
ROOT = os.environ["PROJECT_ROOT"]
TOKEN_FILE = ROOT + "/var/token.json"
def get_youtube_client():
    """Builds an authenticated YouTube API client."""
    import google_auth_oauthlib.flow
    import googleapiclient.discovery
    import googleapiclient.errors
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = os.environ["GOOGLE_OAUTH_FILE"]

    credentials = None

    # Load credentials if the token file exists
    if os.path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # If credentials are missing or expired, run auth flow
    if not credentials or not credentials.valid:
        try:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                raise RefreshError("Invalid or missing credentials")
        except RefreshError:
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)

            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, SCOPES
            )
            credentials = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(TOKEN_FILE, "w") as token:
                token.write(credentials.to_json())

    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)
    return youtube
