# services/svc_qbo/client.py
import os, urllib.parse, requests
from .token_refresher import access_token, refresh

REALM = os.getenv("QBO_REALM")
BASE  = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{REALM}"

def _headers(tok: str):
    return {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

def _get(url: str):
    tok = access_token()
    r = requests.get(url, headers=_headers(tok), timeout=20)
    if r.status_code == 401:  # token expired: refresh once
        tok = refresh()
        r = requests.get(url, headers=_headers(tok), timeout=20)
    r.raise_for_status()
    return r.json()

def company_info():
    return _get(f"{BASE}/companyinfo/{REALM}?minorversion=70")

def query(sql: str):
    q = urllib.parse.quote(sql, safe=" ")
    return _get(f"{BASE}/query?minorversion=70&query={q}")
