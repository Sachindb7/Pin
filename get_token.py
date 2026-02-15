from google_auth_oauthlib.flow import InstalledAppFlow

# Permissions hume kya chahiye
SCOPES = ['https://www.googleapis.com/auth/blogger']

def get_token():
    # Ye wahi file hai jo tune abhi download ki Google Cloud se
    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json', SCOPES)
    
    # Ye browser open karega login ke liye
    creds = flow.run_local_server(port=0)
    
    print("\n\n--- INKO COPY KARKE RAKH LE ---")
    print(f"REFRESH_TOKEN: {creds.refresh_token}")
    print(f"CLIENT_ID: {creds.client_id}")
    print(f"CLIENT_SECRET: {creds.client_secret}")

if __name__ == '__main__':
    get_token()
