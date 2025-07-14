"""Utility script to fetch OAuth2 tokens for Finastra APIs."""

import os

from bankersbank.finastra import fetch_token

if __name__ == "__main__":
    client_id = os.getenv("FFDC_CLIENT_ID")
    client_secret = os.getenv("FFDC_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("Set FFDC_CLIENT_ID and FFDC_CLIENT_SECRET env vars")
    token = fetch_token(client_id, client_secret)
    print(token)
