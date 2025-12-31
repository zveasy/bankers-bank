#!/usr/bin/env python3
# qbo_auth_test.py — OAuth sanity check for QuickBooks Online (Sandbox/Prod)
# Requirements: requests, python-dotenv  (install via: poetry add requests python-dotenv)

import os
import base64
import json
from pathlib import Path
import requests
from dotenv import load_dotenv

# ---------- Load env (.env.local preferred; fallback to .env) ----------
REPO_ROOT = Path(__file__).resolve().parent.parent
for f in (REPO_ROOT / ".env.local", REPO_ROOT / ".env"):
    if f.exists():
        load_dotenv(dotenv_path=f, override=False)
        print(f"🔎 Loaded env file: {f}")
        break
else:
    print("⚠️ No .env.local/.env found; relying on process env only.")

def show(name: str) -> str:
    val = os.getenv(name)
    print(f"ENV {name} = {'∅' if not val else (val[:4] + '…' + val[-4:] if len(val)>12 else val)}")
    return val

print("🔍 Checking QuickBooks OAuth configuration...")
client_id     = show("QBO_CLIENT_ID")
client_secret = show("QBO_CLIENT_SECRET")
redirect_uri  = show("QBO_REDIRECT_URI")
realm         = show("QBO_REALM")
scope         = os.getenv(
    "QBO_SCOPE",
    "com.intuit.quickbooks.accounting com.intuit.quickbooks.payment openid profile email",
)

if not (client_id and client_secret and redirect_uri):
    raise SystemExit("❌ Missing required env: QBO_CLIENT_ID / QBO_CLIENT_SECRET / QBO_REDIRECT_URI")

# ---------- Build authorization URL ----------
auth_url = (
    "https://appcenter.intuit.com/connect/oauth2?"
    f"client_id={client_id}&response_type=code&scope={scope.replace(' ', '%20')}&"
    f"redirect_uri={redirect_uri}&state=1234"
)

print("✅ Env loaded successfully. Next step: open this URL in your browser manually:")
print(auth_url)

# ---------- Prompt for code ----------
print("\nOnce you log in, paste the 'code=' value from the redirect URL below.")
code = input("Authorization code: ").strip()
if not code:
    raise SystemExit("❌ No code provided; restart and try again.")

# ---------- Exchange code for tokens ----------
token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

resp = requests.post(
    token_url,
    headers={
        "Authorization": f"Basic {basic}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    },
    timeout=20,
)

if resp.status_code != 200:
    print(f"❌ Token exchange failed (HTTP {resp.status_code}):\n{resp.text}")
    raise SystemExit(1)

data = resp.json()
print("🎉 Success! Access token (truncated):", data.get("access_token", "")[:20], "…")

# ---------- Persist tokens ----------
OUT_DIR = REPO_ROOT / "secrets"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "qbo_token.json"
OUT_FILE.write_text(json.dumps(data, indent=2))
print(f"💾 Saved tokens to {OUT_FILE} (add 'secrets/' to .gitignore)")

# ---------- Quick sanity check ----------
try:
    access_token = data["access_token"]
    if realm:
        url = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{realm}/companyinfo/{realm}?minorversion=70"
        r = requests.get(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, timeout=20)
        print(f"🔗 CompanyInfo probe -> HTTP {r.status_code}")
        print("✅ CompanyInfo reachable." if r.ok else r.text[:400])
    else:
        print("ℹ️ Skipping CompanyInfo probe (no QBO_REALM set).")
except Exception as e:
    print(f"⚠️ CompanyInfo probe failed: {e}")
