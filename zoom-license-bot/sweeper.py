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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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
    """Return emails that need re-checking:
    - Licensed accounts expiring within 2 days
    - Accounts marked Basic (may have been renewed)
    - Accounts with unknown/BLOCKED status
    """
    import datetime
    at_risk = []
    now = datetime.datetime.now(datetime.timezone.utc).date()
    for email in fleet_emails_fn(store):
        acc = store["accounts"].get(email, {})
        st = acc.get("last_type", "unknown")
        if st == "Licensed":
            exp = acc.get("license_expires_at")
            if exp:
                try:
                    exp_date = datetime.date.fromisoformat(exp[:10])
                    if (exp_date - now).days <= 2:
                        at_risk.append(email)
                except Exception:
                    at_risk.append(email)
            else:
                # No expiry date — check it
                at_risk.append(email)
        elif st in ("Basic", "unknown", "BLOCKED"):
            at_risk.append(email)
    return at_risk


def run_targeted_sweep(store, save_store_fn, fleet_emails_fn, short_email_fn,
                       max_accounts=15):
    """Run a targeted sweep of at-risk accounts. Returns (checked, changes)."""
    creds = load_credentials()
    if not creds:
        log.warning("No ZOOM_CREDS configured, skipping sweep")
        return 0, []

    targets = get_at_risk_accounts(store, fleet_emails_fn, short_email_fn)
    # Filter to accounts we have credentials for, cap the count
    targets = [e for e in targets if e.lower() in creds][:max_accounts]

    if not targets:
        log.info("No at-risk accounts to sweep")
        return 0, []

    log.info(f"Targeted sweep: checking {len(targets)} accounts")
    changes = []
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
    return checked, changes
