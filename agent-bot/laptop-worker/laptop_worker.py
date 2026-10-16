"""Laptop companion worker for Arkar's personal agent (Windows).

Runs on the Windows laptop and gives the Telegram agent the ability to run
commands and work with files there. Uses only the Python standard library.

HOW IT WORKS: every few seconds it asks the agent "any tasks for the laptop?",
runs them, and posts back the results. It only makes OUTGOING connections, so
it works behind any router/firewall with no network setup.

SETUP (one time):
  1. Install Python 3 from https://www.python.org/downloads/
     (tick "Add python.exe to PATH" during install)
  2. Edit AGENT_URL and WORKER_SECRET below (ask the agent bot for them:
     send it "laptop setup info")
  3. Double-click this file (or run: python laptop_worker.py)
Keep this window open while you want the agent to reach the laptop.
"""
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

# ----------------- EDIT THESE -----------------
AGENT_URL = "https://YOUR-AGENT-APP.up.railway.app"  # no trailing slash
WORKER_SECRET = "PASTE-SECRET-HERE"
# ----------------------------------------------

POLL_INTERVAL = 5


def api(path, data=None):
    url = AGENT_URL + path
    if data is not None:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
    else:
        sep = "&" if "?" in url else "?"
        req = urllib.request.Request(
            url + sep + urllib.parse.urlencode({"secret": WORKER_SECRET}))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def run_task(task):
    action = task.get("action")
    p = task.get("payload", {}) or {}
    try:
        if action == "shell":
            cmd = p.get("command", "")
            proc = subprocess.run(cmd, shell=True, capture_output=True,
                                  text=True, timeout=120)
            out = proc.stdout
            if proc.stderr.strip():
                out += "\n[stderr]\n" + proc.stderr
            return True, (out.strip() or f"(exit {proc.returncode})")
        if action == "read":
            with open(os.path.expandvars(p.get("path", "")), encoding="utf-8",
                      errors="replace") as fh:
                data = fh.read()
            if len(data) > 8000:
                data = data[:8000] + "\n...[truncated]"
            return True, data
        if action == "write":
            path = os.path.expandvars(p.get("path", ""))
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(p.get("content", ""))
            return True, f"Wrote {path}."
        if action == "list":
            path = os.path.expandvars(p.get("path", "") or ".")
            items = []
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                items.append(name + ("\\" if os.path.isdir(full) else ""))
            return True, "\n".join(items) or "(empty)"
        return False, f"Unknown action: {action}"
    except Exception as e:
        return False, f"Failed: {e}"


def main():
    print("Laptop worker starting. Agent:", AGENT_URL)
    print("Keep this window open. Press Ctrl+C to stop.\n")
    while True:
        try:
            resp = api("/laptop/poll")
            for task in resp.get("tasks", []):
                tid = task.get("id")
                print(f"[{time.strftime('%H:%M:%S')}] task {tid}: "
                      f"{task.get('action')}")
                ok, output = run_task(task)
                api("/laptop/result", {"secret": WORKER_SECRET, "id": tid,
                                       "ok": ok, "output": output})
                print(f"  -> {'ok' if ok else 'FAILED'} ({len(output)} chars)")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
