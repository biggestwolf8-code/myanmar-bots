"""Automated targeted sweeps for the Zoom license monitor bot.

Runs inside the bot (on Railway). Uses Playwright to log into Zoom accounts
and check their license status. Only checks at-risk accounts to avoid
triggering Zoom's rate limits.

Credentials come from the ZOOM_CREDS env var (JSON: {email: password}).
"""
import json
import logging
import os
import time

log = logging.getLogger("sweeper")


def load_credentials():
    raw = os.environ.get("ZOOM_CREDS", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        log.exception("Failed to parse ZOOM_CREDS")
        return {}


def check_account_playwright(email, password):
    """Returns (status, detail). Status: Licensed|Basic|ERROR|BLOCKED."""
    from playwright.sync_api import sync_playwright
    import subprocess

    # Use persistent volume for browsers so they survive restarts
    data_dir = os.environ.get("DATA_DIR", "./data")
    browser_path = os.path.join(data_dir, "ms-playwright")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browser_path

    def _launch(p):
        # Try system chromium first (from nixpacks), fall back to playwright's
        import shutil
        sys_chrome = shutil.which("chromium") or shutil.which("chromium-browser") \
            or shutil.which("google-chrome")
        if sys_chrome:
            return p.chromium.launch(headless=True, executable_path=sys_chrome,
                                     args=["--no-sandbox", "--disable-dev-shm-usage",
                                           "--disable-gpu"])
        return p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
        ])

    with sync_playwright() as p:
        try:
            browser = _launch(p)
        except Exception as e:
            if "Executable doesn't exist" in str(e):
                log.info("Installing Playwright Chromium...")
                subprocess.run(
                    ["python", "-m", "playwright", "install", "--with-deps", "chromium"],
                    timeout=600, check=False)
                browser = _launch(p)  # retry after install
            else:
                raise
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = ctx.new_page()
        try:
            page.goto("https://zoom.us/signin", timeout=30000)
            page.wait_for_timeout(2000)

            page.fill('input[name="email"]', email)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_timeout(4000)

            content = page.content()
            lower = content.lower()

            if "verification" in lower and "code" in lower:
                return "BLOCKED", "2FA/verification code required"

            # Go to profile to check plan
            page.goto("https://zoom.us/profile", timeout=30000)
            page.wait_for_timeout(3000)
            lower = page.content().lower()

            if "licensed" in lower:
                return "Licensed", "auto-sweep"
            elif "basic" in lower:
                return "Basic", "auto-sweep"
            else:
                return "ERROR", "plan type not determined"

        except Exception as e:
            return "ERROR", str(e)[:200]
        finally:
            browser.close()


def get_at_risk_accounts(store, fleet_emails_fn, short_email_fn):
    """Return accounts marked Basic — they may have been renewed since the
    last sweep. Expiring Licensed accounts are NOT re-checked: their expiry
    dates are already known from the last sweep.
    """
    at_risk = []
    for email in fleet_emails_fn(store):
        acc = store["accounts"].get(email, {})
        if acc.get("last_type") == "Basic":
            at_risk.append(email)
    return at_risk


def run_targeted_sweep(store, save_store_fn, fleet_emails_fn, short_email_fn,
                       max_accounts=15):
    """Run a targeted sweep of at-risk accounts. Returns (checked, changes, errors)."""
    creds = load_credentials()
    if not creds:
        log.warning("No ZOOM_CREDS configured, skipping sweep")
        return 0, [], ["No ZOOM_CREDS configured"]

    targets = get_at_risk_accounts(store, fleet_emails_fn, short_email_fn)
    # Filter to accounts we have credentials for, cap the count
    targets = [e for e in targets if e.lower() in creds][:max_accounts]

    if not targets:
        log.info("No at-risk accounts to sweep")
        return 0, [], []

    log.info(f"Targeted sweep: checking {len(targets)} accounts")
    changes = []
    errors = []
    checked = 0

    for email in targets:
        password = creds.get(email.lower())
        if not password:
            continue
        try:
            status, detail = check_account_playwright(email, password)
            checked += 1
        except Exception as e:
            log.exception(f"Sweep failed for {email}")
            status, detail = "ERROR", str(e)[:200]
            errors.append(f"{email}: {str(e)[:200]}")

        acc = store["accounts"].setdefault(email, {})
        prev = acc.get("last_type")
        if status in ("Licensed", "Basic") and status != prev:
            changes.append((email, prev, status))
            log.info(f"License change: {email} {prev} -> {status}")
        if status in ("Licensed", "Basic"):
            acc["last_type"] = status
            acc["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        elif status == "BLOCKED":
            acc["last_type"] = "BLOCKED"
            acc["block_reason"] = detail

        # Be nice to Zoom: small delay between accounts
        time.sleep(5)

    if checked:
        save_store_fn(store)
    return checked, changes, errors
