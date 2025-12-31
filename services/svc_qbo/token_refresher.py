import os, json, time, base64, requests
from pathlib import Path

# ----- Load env from repo root -----
REPO_ROOT = Path(__file__).resolve().parents[2]
for f in (REPO_ROOT / ".env.local", REPO_ROOT / ".env"):
    if f.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=f, override=False)
            print(f"🔎 token_refresher: loaded env file {f}")
        except Exception as e:
            print(f"⚠️ token_refresher: failed to load {f}: {e}")
        break

TOKEN_FILE = REPO_ROOT / "secrets" / "qbo_token.json"
CLIENT_ID  = os.getenv("QBO_CLIENT_ID")
CLIENT_SEC = os.getenv("QBO_CLIENT_SECRET")
TOKEN_URL  = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

def _require_env():
    missing = [k for k in ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"❌ Missing env vars: {', '.join(missing)}. "
                           "Export them or put them in .env.local at repo root.")

def _auth_basic():
    _require_env()
    creds = f"{CLIENT_ID}:{CLIENT_SEC}".encode()
    return base64.b64encode(creds).decode()

def load_tokens() -> dict:
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(f"❌ Token file not found: {TOKEN_FILE}. Run qbo_auth_test.py first.")
    return json.loads(TOKEN_FILE.read_text())

def save_tokens(data: dict) -> dict:
    TOKEN_FILE.parent.mkdir(exist_ok=True, parents=True)
    data["refreshed_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    return data

def access_token() -> str:
    return load_tokens()["access_token"]

def refresh() -> str:
    """
    Refresh access token; Intuit rotates the refresh_token on every refresh.
    On failure, prints the exact response so you can see invalid_client/invalid_grant/etc.
    """
    _require_env()
    data = load_tokens()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("❌ No refresh_token present. Re-run qbo_auth_test.py to re-authorize.")

    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {_auth_basic()}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=20,
    )

    if resp.status_code != 200:
        # Show full error body (do NOT raise before printing it)
        print(f"❌ Refresh failed HTTP {resp.status_code}: {resp.text}")
        # Common causes:
        # - invalid_client: CLIENT_ID/SECRET don't match the app that minted the original tokens
        # - invalid_grant: refresh_token expired or already rotated/used; re-run qbo_auth_test.py
        # - unsupported_grant_type / invalid_request: header/body mismatch
        raise RuntimeError("Refresh failed; see error above.")

    payload = resp.json()
    # Persist NEW refresh_token (old becomes invalid)
    save_tokens(payload)
    return payload["access_token"]

# (Optional) small helper to confirm env presence without printing secrets
def debug_env_redacted():
    def red(s): 
        return (s[:4] + "…" + s[-4:]) if s and len(s) > 12 else s
    print("ENV QBO_CLIENT_ID =", red(CLIENT_ID))
    print("ENV QBO_CLIENT_SECRET =", red(CLIENT_SEC))
    print("Token file exists =", TOKEN_FILE.exists(), "size =", TOKEN_FILE.stat().st_size if TOKEN_FILE.exists() else 0)
