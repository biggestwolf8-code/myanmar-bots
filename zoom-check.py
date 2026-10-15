#!/usr/bin/env python3
"""
Zoom license checker for Vultr VM.
Uses persistent Playwright sessions for fast checks.
Posts results to the Telegram bot's ingest endpoint.
"""
import os, json, sys, time, logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("zoom-check")

BASE = "/opt/zoom-monitor"
STATES_DIR = os.path.join(BASE, "states")
CREDS_FILE = os.path.join(BASE, "creds.json")

INGEST_URL = os.environ.get("INGEST_URL", "https://zoom-license-bot-production.up.railway.app/ingest")
INGEST_SECRET = os.environ.get("INGEST_SECRET", "")

def load_creds():
    with open(CREDS_FILE) as f:
        return json.load(f)

def state_path(email):
    safe = email.lower().replace("@", "_at_").replace("+", "_plus_").replace(".", "_")
    return os.path.join(STATES_DIR, f"{safe}.json")

def check_account(email, password):
    """Check license status using Playwright. Returns (status, detail)."""
    from playwright.sync_api import sync_playwright
    sp = state_path(email)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        try:
            # Try saved session first
            if os.path.exists(sp):
                ctx = browser.new_context(storage_state=sp)
                page = ctx.new_page()
                page.goto("https://zoom.us/profile", timeout=30000)
                page.wait_for_timeout(3000)
                if "signin" not in page.url.lower():
                    # Session valid, check license
                    body = page.inner_text("body", timeout=10000)
                    lic = parse_license(body)
                    # Refresh session
                    ctx.storage_state(path=sp)
                    return lic, "session"
                ctx.close()
            # Need fresh login
            ctx = browser.new_context()
            page = ctx.new_page()
            page.goto("https://zoom.us/signin", timeout=30000)
            # Email step
            page.fill('input[type="email"]', email, timeout=10000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(3000)
            # Password step (if present)
            try:
                pw_field = page.wait_for_selector('input[type="password"]', timeout=8000)
                pw_field.fill(password)
                page.keyboard.press("Enter")
                page.wait_for_timeout(5000)
            except Exception:
                pass
            # Check for blocks
            body = page.inner_text("body", timeout=8000).lower()
            if "recaptcha" in body and "error" in body:
                return "BLOCKED", "reCAPTCHA"
            if "allow on other devices" in body:
                return "BLOCKED", "device approval"
            if "verification code" in body or "enter the code" in body:
                return "BLOCKED", "2FA/SMS"
            # Try profile
            page.goto("https://zoom.us/profile", timeout=30000)
            page.wait_for_timeout(3000)
            if "signin" in page.url.lower():
                return "BLOCKED", "login failed"
            body = page.inner_text("body", timeout=10000)
            lic = parse_license(body)
            # Save session for next time
            ctx.storage_state(path=sp)
            return lic, "fresh login"
        except Exception as e:
            return "ERROR", str(e)[:100]
        finally:
            browser.close()

def parse_license(body):
    bl = body.lower()
    if "30 hours" in bl or ("100 participants" in bl and "40 minute" not in bl):
        return "Licensed"
    if "40 minutes" in bl or "basic" in bl:
        return "Basic"
    return "UNKNOWN"

def main():
    creds = load_creds()
    # Filter to specific accounts if given as args
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(creds.keys())
    results = {}
    for email in targets:
        email = email.lower()
        pwd = creds.get(email)
        if not pwd:
            log.warning(f"No password for {email}, skipping")
            continue
        log.info(f"Checking {email}...")
        status, detail = check_account(email, pwd)
        log.info(f"  -> {status} ({detail})")
        if status in ("Licensed", "Basic"):
            results[email] = {"status": status, "detail": detail}
        # Pace to avoid rate limiting
        time.sleep(5)
    # Post to bot
    if results and INGEST_SECRET:
        import requests
        payload = {
            "results": results,
            "swept_at": datetime.now(timezone.utc).isoformat()
        }
        try:
            r = requests.post(INGEST_URL, json=payload,
                            headers={"X-Ingest-Secret": INGEST_SECRET},
                            timeout=30)
            log.info(f"Ingested: {r.status_code} {r.text[:200]}")
        except Exception as e:
            log.error(f"Ingest failed: {e}")
    else:
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
