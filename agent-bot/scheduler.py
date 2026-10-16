"""Simple scheduler: reminders and recurring tasks for the agent.

Tasks live in scheduled.json on the volume. The `schedule` tool (and the
/remind command) add them; a background thread runs due tasks through the
agent loop and messages the owner the result.
"""
import json
import os
import re
import threading
import time
import uuid

import config

TASKS_FILE = os.path.join(config.DATA_DIR, "scheduled.json")
_lock = threading.Lock()
_notify = None  # set by bot.py: notify(chat_id, text)


def set_notify(fn):
    global _notify
    _notify = fn


def _load():
    try:
        with open(TASKS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save(tasks):
    tmp = TASKS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(tasks, fh)
    os.replace(tmp, TASKS_FILE)


def parse_when(s):
    """Natural language -> (run_at_epoch, repeat_seconds or None)."""
    s = (s or "").strip().lower()
    now = time.time()
    m = re.match(r"in (\d+)\s*(minute|hour|day)s?", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mult = {"minute": 60, "hour": 3600, "day": 86400}[unit]
        return now + n * mult, None
    m = re.match(r"(tomorrow )?at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if m:
        import datetime
        h, mi = int(m.group(2)), int(m.group(3) or 0)
        ap = m.group(4)
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        # Asia/Bangkok
        tz = datetime.timezone(datetime.timedelta(hours=7))
        dt = datetime.datetime.now(tz).replace(hour=h, minute=mi, second=0,
                                               microsecond=0)
        if m.group(1) or dt.timestamp() <= now:
            dt += datetime.timedelta(days=1)
        return dt.timestamp(), None
    m = re.match(r"every day at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if m:
        run_at, _ = parse_when("at " + m.group(0).split("at ", 1)[1])
        return run_at, 86400
    m = re.match(r"every (\d+)\s*(minute|hour|day)s?", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        mult = {"minute": 60, "hour": 3600, "day": 86400}[unit]
        return now + n * mult, n * mult
    return None, None


def add_task(when, task):
    run_at, repeat = parse_when(when)
    if not run_at:
        return ("I couldn't understand that time. Try 'in 30 minutes', "
                "'tomorrow at 9am', or 'every day at 8am'.")
    with _lock:
        tasks = _load()
        tid = uuid.uuid4().hex[:6]
        tasks.append({"id": tid, "run_at": run_at, "repeat": repeat,
                      "task": task.strip(), "created": time.time()})
        _save(tasks)
    import datetime
    tz = datetime.timezone(datetime.timedelta(hours=7))
    when_s = datetime.datetime.fromtimestamp(run_at, tz).strftime("%Y-%m-%d %H:%M")
    rep = f", repeats {when}" if repeat else ""
    return f"Scheduled ({tid}) for {when_s} Bangkok time{rep}."


def list_tasks():
    with _lock:
        tasks = _load()
    if not tasks:
        return "No scheduled tasks."
    import datetime
    tz = datetime.timezone(datetime.timedelta(hours=7))
    lines = []
    for t in sorted(tasks, key=lambda x: x["run_at"]):
        when_s = datetime.datetime.fromtimestamp(t["run_at"], tz).strftime("%m-%d %H:%M")
        rep = " ↻" if t.get("repeat") else ""
        lines.append(f"• {t['id']} — {when_s}{rep}: {t['task'][:80]}")
    return "\n".join(lines)


def cancel_task(tid):
    with _lock:
        tasks = _load()
        kept = [t for t in tasks if t["id"] != tid]
        _save(kept)
    return "Cancelled." if len(kept) < len(tasks) else "No task with that id."


def _run_due():
    import agent as agent_mod
    import memory_store
    while True:
        time.sleep(20)
        now = time.time()
        due = []
        with _lock:
            tasks = _load()
            kept = []
            for t in tasks:
                if t["run_at"] <= now:
                    due.append(t)
                    if t.get("repeat"):
                        t["run_at"] = now + t["repeat"]
                        kept.append(t)
                else:
                    kept.append(t)
            if due:
                _save(kept)
        for t in due:
            try:
                chat_id = config.ADMIN_CHAT_ID
                history = memory_store.load_history(chat_id)
                history.append({"role": "user",
                                "content": f"[Scheduled task — {t['task']}]"})
                reply, usage, steps = agent_mod.run_agent(history)
                memory_store.save_history(chat_id, history)
                if _notify:
                    msg = f"⏰ {t['task']}\n\n{reply}"
                    _notify(chat_id, msg)
            except Exception as e:
                print("scheduled task failed:", e)


def start():
    th = threading.Thread(target=_run_due, daemon=True)
    th.start()
