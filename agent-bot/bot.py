"""Arkar's personal agent — Telegram bot, owner-only.

Runs the Claude agent loop (agent.py) for every message from the owner.
Also hosts the laptop-worker HTTP endpoints (server.py) and the scheduler.
"""
import html
import json
import os
import threading
import time

import requests

import config
import memory_store
import scheduler
import server
from agent import run_agent

API = config.API

# Serializes message handling: the Telegram polling loop and the inbox
# endpoint both run handle_message for the same owner chat_id in different
# threads, and they share one history file.
_HANDLE_LOCK = threading.Lock()
USAGE_FILE = os.path.join(config.DATA_DIR, "usage.json")


def tg(method, **params):
    try:
        r = requests.post(f"{API}/{method}", json=params, timeout=30)
        return r.json()
    except Exception as e:
        print("telegram error:", e)
        return {}


def send(chat_id, text, parse_html=True):
    if not text:
        return
    # split long messages
    while len(text) > 4000:
        cut = text.rfind("\n", 0, 4000)
        if cut < 1000:
            cut = 4000
        tg("sendMessage", chat_id=chat_id, text=text[:cut],
           parse_mode="HTML" if parse_html else None)
        text = text[cut:]
    tg("sendMessage", chat_id=chat_id, text=text,
       parse_mode="HTML" if parse_html else None)


def esc(s):
    return html.escape(s or "")


def load_usage():
    try:
        with open(USAGE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"input": 0, "output": 0}


def record_usage(u):
    d = load_usage()
    d["input"] += u.get("input_tokens", 0)
    d["output"] += u.get("output_tokens", 0)
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except OSError:
        pass
    return d


def usage_text():
    d = load_usage()
    r_in, r_out = config.MODEL_RATES.get(config.MODEL, (2.0, 10.0))
    cost = d["input"] / 1e6 * r_in + d["output"] / 1e6 * r_out
    return (f"Model: {esc(config.MODEL)}\n"
            f"Tokens in/out: {d['input']:,}/{d['output']:,}\n"
            f"Estimated cost: ${cost:.2f}")


def handle_command(chat_id, text):
    cmd = text.split()[0].split("@")[0].lower()
    arg = text[len(text.split()[0]):].strip()
    if cmd == "/start":
        send(chat_id,
             "👋 I'm your personal agent.\n\n"
             "I can chat, run code, work with files, fetch web pages, "
             "run commands on your <b>Vultr server</b>, and on your <b>laptop</b> "
             "(while the companion program is running there).\n\n"
             "I remember things across conversations. "
             "Ask me to remind you of things — e.g. <i>remind me in 30 minutes to call the supplier</i>.\n\n"
             "Commands: /usage /tasks /cancel <id> /memory /forget /inbox")
    elif cmd == "/usage":
        send(chat_id, "📊 " + usage_text())
    elif cmd == "/tasks":
        send(chat_id, "🗓 " + esc(scheduler.list_tasks()))
    elif cmd == "/cancel":
        send(chat_id, esc(scheduler.cancel_task(arg)))
    elif cmd == "/memory":
        send(chat_id, "<b>What I remember:</b>\n" + esc(memory_store.read_memory()))
    elif cmd == "/forget":
        memory_store.clear_history(chat_id)
        send(chat_id, "Conversation history cleared. Long-term memory kept — tell me what to remove specifically if needed.")
    elif cmd == "/remind":
        parts = arg.split(" to ", 1)
        if len(parts) == 2:
            send(chat_id, "⏰ " + esc(scheduler.add_task(parts[0], parts[1])))
        else:
            send(chat_id, "Use: /remind <when> to <what> — e.g. /remind in 30 minutes to check the oven")
    elif cmd == "/inbox":
        items = server.read_inbox()
        if not items:
            send(chat_id, "📥 Inbox is empty — nothing from Muse yet.")
        else:
            lines = []
            for it in items:
                ts = it.get("ts", "")[:16].replace("T", " ")
                lines.append(f"• <i>{esc(ts)}</i>\n{esc(it.get('text', '')[:300])}")
            send(chat_id, "📥 <b>Recent inbox messages from Muse:</b>\n\n" + "\n\n".join(lines))
    else:
        send(chat_id, "Unknown command. Try /start.")
    return True


def typing_loop(chat_id, stop):
    while not stop.is_set():
        tg("sendChatAction", chat_id=chat_id, action="typing")
        stop.wait(4)


def handle_message(chat_id, text):
    # Serialize with inbox handling: both threads use the same chat_id and
    # share the history file, so load -> run -> save must be atomic.
    with _HANDLE_LOCK:
        _handle_message_inner(chat_id, text)


def _handle_message_inner(chat_id, text):
    history = memory_store.load_history(chat_id)
    history.append({"role": "user", "content": text})
    stop = threading.Event()
    th = threading.Thread(target=typing_loop, args=(chat_id, stop), daemon=True)
    th.start()
    try:
        reply, usage, steps = run_agent(history)
    except Exception as e:
        print("agent failed:", e)
        reply, usage, steps = "Something went wrong on my end — try again in a moment.", {"input_tokens": 0, "output_tokens": 0}, []
    finally:
        stop.set()
    memory_store.save_history(chat_id, history)
    record_usage(usage)
    if steps:
        step_txt = "⚙️ " + f"{len(steps)} step{'s' if len(steps) != 1 else ''}\n" + "\n".join(steps[:12])
        send(chat_id, esc(step_txt))
    send(chat_id, esc(reply))


def process_inbox(text):
    """Handle a message arriving via the private Muse inbox endpoint.

    Processed silently through the normal agent loop — no Telegram echo
    (owner disabled the inbox preview 2026-10-17 to reduce noise).
    The raw text is still logged to inbox.jsonl and readable via /inbox.
    """
    chat_id = str(config.ADMIN_CHAT_ID)
    handle_message(chat_id, "[Inbox from Muse] " + text)


def main():
    if not config.BOT_TOKEN or not config.ANTHROPIC_API_KEY:
        raise SystemExit("Set BOT_TOKEN and ANTHROPIC_API_KEY env vars.")
    memory_store.ensure_seed()
    scheduler.set_notify(lambda cid, msg: send(cid, esc(msg)))
    scheduler.start()
    server.inbox_handler = process_inbox
    threading.Thread(target=server.run, daemon=True).start()
    print("agent bot starting...", flush=True)
    offset = 0
    while True:
        try:
            r = requests.get(f"{API}/getUpdates",
                             params={"offset": offset, "timeout": 50}).json()
        except Exception as e:
            print("poll error:", e)
            time.sleep(5)
            continue
        for upd in r.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            text = (msg.get("text") or "").strip()
            if not chat_id or not text:
                continue
            if chat_id != str(config.ADMIN_CHAT_ID):
                tg("sendMessage", chat_id=chat_id,
                   text="This is a private agent. Please ask Arkar for access.")
                continue
            if text.startswith("/"):
                handle_command(chat_id, text)
            else:
                handle_message(chat_id, text)


if __name__ == "__main__":
    main()
