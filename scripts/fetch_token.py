"""Utility script to fetch OAuth2 tokens for Finastra APIs."""

from bankersbank.finastra import fetch_token
from common.secrets import get_secret

if __name__ == "__main__":
    client_id = get_secret("FFDC_CLIENT_ID")
    client_secret = get_secret("FFDC_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("Set FFDC_CLIENT_ID and FFDC_CLIENT_SECRET in secrets")
    token = fetch_token(client_id, client_secret)
    print(token)
