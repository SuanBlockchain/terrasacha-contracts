import secrets

def generate_api_key():
    # Generate a random 32-character string using secrets.token_urlsafe()
    return secrets.token_urlsafe(32)