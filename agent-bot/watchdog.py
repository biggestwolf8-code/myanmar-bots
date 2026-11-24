"""Watchdog + activity log for the agent bot (2026-11-24).

The Nov 2026 outage: the agent loop went silent for 15+ hours with zero
log lines — no crash, no error, nothing to read. Two fixes in one place:
1. Every part of the loop reports what it is doing (polling, lock, steps).
2. A heartbeat thread prints one status line a minute, and a loud
   WATCHDOG line if the handling lock is held too long or polling stalls.
No secrets are ever printed here — only ages, counts and short labels.
"""
import threading
import time

_state_lock = threading.Lock()
_state = {
    "last_poll_ts": 0.0,        # last successful getUpdates
    "lock_holder": None,        # label of whoever holds _HANDLE_LOCK
    "lock_since_ts": 0.0,
    "step": None,               # current agent step label
    "step_since_ts": 0.0,
    "inbox_active": 0,          # inbox handler threads running
    "handled": 0,               # messages handled (done or abandoned)
}


def _set(**kw):
    with _state_lock:
        _state.update(kw)


def note_poll():
    _set(last_poll_ts=time.time())


def lock_acquired(holder):
    _set(lock_holder=holder, lock_since_ts=time.time())


def lock_released():
    _set(lock_holder=None, lock_since_ts=0.0)


def note_step(desc):
    _set(step=desc, step_since_ts=time.time())


def step_done():
    _set(step=None, step_since_ts=0.0)


def note_inbox_start():
    with _state_lock:
        _state["inbox_active"] += 1


def note_inbox_done():
    with _state_lock:
        _state["inbox_active"] = max(0, _state["inbox_active"] - 1)


def note_handled():
    with _state_lock:
        _state["handled"] += 1


def status_line():
    now = time.time()
    with _state_lock:
        s = dict(_state)
    poll_age = int(now - s["last_poll_ts"]) if s["last_poll_ts"] else -1
    if s["lock_holder"]:
        lock = f"held {int(now - s['lock_since_ts'])}s by {s['lock_holder']}"
    else:
        lock = "free"
    step = s["step"] or "-"
    return (f"heartbeat: poll_age={poll_age}s lock={lock} step={step} "
            f"inbox_active={s['inbox_active']} handled={s['handled']}")


def heartbeat_loop(interval_s, lock_timeout_s):
    """Print a status line every interval_s; shout if the loop stalls."""
    warned_poll = False
    warned_lock = False
    while True:
        time.sleep(interval_s)
        now = time.time()
        with _state_lock:
            s = dict(_state)
        print(status_line(), flush=True)
        # Polling stalled: no successful getUpdates for 3 intervals.
        poll_age = now - s["last_poll_ts"] if s["last_poll_ts"] else 1e9
        if poll_age > 3 * interval_s:
            if not warned_poll:
                print(f"WATCHDOG: polling loop silent for {int(poll_age)}s "
                      f"— loop may be stuck", flush=True)
                warned_poll = True
        else:
            warned_poll = False
        # Lock held far too long: whoever holds it is stuck.
        if s["lock_holder"] and (now - s["lock_since_ts"]) > lock_timeout_s:
            if not warned_lock:
                print(f"WATCHDOG: lock held {int(now - s['lock_since_ts'])}s by "
                      f"{s['lock_holder']} — handler exceeded "
                      f"{lock_timeout_s}s", flush=True)
                warned_lock = True
        else:
            warned_lock = False


def start(interval_s, lock_timeout_s):
    th = threading.Thread(target=heartbeat_loop,
                          args=(interval_s, lock_timeout_s), daemon=True)
    th.start()
    return th
