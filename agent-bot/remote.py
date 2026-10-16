"""Remote execution: Vultr VM over SSH, and the Windows laptop via a task queue.

Vultr: direct SSH from this service (Railway has normal internet egress).
Laptop: nothing can reach into the laptop from outside, so a small companion
program on the laptop polls this service for tasks and posts back results.
"""
import json
import os
import threading
import time
import uuid

import config

QUEUE_FILE = os.path.join(config.DATA_DIR, "laptop_queue.json")
_lock = threading.Lock()


# ---------------- Vultr SSH ----------------

def vultr_configured():
    return bool(config.VULTR_PASSWORD)


def vultr_exec(command, timeout=60):
    """Run a shell command on the Vultr VM over SSH. Returns (ok, output)."""
    if not vultr_configured():
        return False, "Vultr SSH is not configured (VULTR_PASSWORD missing)."
    try:
        import paramiko
    except ImportError:
        return False, "SSH library not installed on the agent."
    command = command.strip()
    if not command:
        return False, "Empty command."
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(config.VULTR_HOST, username=config.VULTR_USER,
                       password=config.VULTR_PASSWORD, timeout=15,
                       banner_timeout=15, auth_timeout=15)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        try:
            exit_code = stdout.channel.recv_exit_status()
        except Exception:
            exit_code = -1
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        text = out
        if err.strip():
            text += ("\n" if text else "") + "[stderr]\n" + err
        text += f"\n[exit code: {exit_code}]"
        return True, text.strip()
    except Exception as e:
        return False, f"SSH failed: {e}"
    finally:
        try:
            client.close()
        except Exception:
            pass


# ---------------- Laptop task queue ----------------

def _load_queue():
    try:
        with open(QUEUE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"pending": [], "results": {}}


def _save_queue(q):
    tmp = QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(q, fh)
    os.replace(tmp, QUEUE_FILE)


def laptop_online():
    """True if the laptop worker has polled recently (within 60s)."""
    q = _load_queue()
    last = q.get("worker_last_seen", 0)
    return (time.time() - last) < 60


def laptop_task(action, payload, timeout=120):
    """Queue a task for the laptop worker and wait for its result.

    action: shell | read | write | list
    payload: {"command": ...} | {"path": ...} | {"path": ..., "content": ...}
    Returns (ok, output).
    """
    task_id = uuid.uuid4().hex[:12]
    timeout = min(max(timeout, 10), 600)
    task = {"id": task_id, "action": action, "payload": payload,
            "created": time.time(), "expires": time.time() + timeout + 30}
    with _lock:
        q = _load_queue()
        q["pending"].append(task)
        _save_queue(q)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        with _lock:
            q = _load_queue()
            if task_id in q.get("results", {}):
                res = q["results"].pop(task_id)
                _save_queue(q)
                out = res.get("output", "")
                return bool(res.get("ok")), out or "(no output)"
    # timed out: withdraw the task so a late worker doesn't run it blind
    with _lock:
        q = _load_queue()
        q["pending"] = [t for t in q.get("pending", []) if t.get("id") != task_id]
        _save_queue(q)
    return False, (f"Timed out after {timeout}s waiting for the laptop. "
                   "The companion program may not be running on the laptop.")


def worker_poll():
    """Called by the laptop worker: fetch pending tasks, mark worker seen."""
    now = time.time()
    with _lock:
        q = _load_queue()
        pending = [t for t in q.get("pending", [])
                   if t.get("expires", now + 1) > now]
        q["pending"] = []
        q["worker_last_seen"] = now
        _save_queue(q)
    return pending


def worker_result(task_id, ok, output):
    """Called by the laptop worker: store a task result."""
    with _lock:
        q = _load_queue()
        q["results"][task_id] = {"ok": bool(ok), "output": output or "",
                                "at": time.time()}
        # prune old results
        ids = list(q["results"])
        if len(ids) > 50:
            for rid in ids[:-50]:
                q["results"].pop(rid, None)
        _save_queue(q)
    return True
