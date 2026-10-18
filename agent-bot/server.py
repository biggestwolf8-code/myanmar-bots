"""Tiny HTTP server: endpoints for the laptop companion worker + Muse inbox.

GET  /laptop/poll?secret=...    -> pending tasks (worker long-polls this)
POST /laptop/result              -> {secret, id, ok, output}
POST /inbox                      -> {secret, text}  (private channel from Muse;
                                    Arkar reads it with /inbox)
POST /report                     -> {secret, task, result}  (agent posts completion
                                    reports here; Muse polls GET /reports)
GET  /reports                    -> {secret}  (recent completion reports for Muse)
GET  /health                     -> ok
"""
import json
import os
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, request

import config
import remote

app = Flask(__name__)

# Set by bot.py at startup: called in a background thread per inbox message.
inbox_handler = None


def _auth():
    secret = request.args.get("secret") or (request.get_json(silent=True) or {}).get("secret")
    return secret == config.WORKER_SECRET


def _inbox_auth(data):
    if not config.INBOX_SECRET:
        return False
    secret = (data or {}).get("secret") or request.args.get("secret")
    return secret == config.INBOX_SECRET


def log_inbox(text):
    path = os.path.join(config.DATA_DIR, "inbox.jsonl")
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "text": text[:2000],
            }) + "\n")
    except Exception as e:
        print("inbox log failed:", e)


def read_inbox(n=8):
    path = os.path.join(config.DATA_DIR, "inbox.jsonl")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as fh:
            lines = fh.read().strip().split("\n")
        items = [json.loads(l) for l in lines if l.strip()]
        return items[-n:]
    except Exception:
        return []


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/laptop/poll")
def laptop_poll():
    if not _auth():
        return jsonify({"ok": False}), 403
    return jsonify({"ok": True, "tasks": remote.worker_poll()})


@app.route("/laptop/result", methods=["POST"])
def laptop_result():
    if not _auth():
        return jsonify({"ok": False}), 403
    data = request.get_json(force=True)
    remote.worker_result(data.get("id"), data.get("ok"), data.get("output", ""))
    return jsonify({"ok": True})


@app.route("/inbox", methods=["POST"])
def inbox():
    data = request.get_json(silent=True) or {}
    if not _inbox_auth(data):
        return jsonify({"ok": False}), 403
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty text"}), 400
    if inbox_handler is None:
        return jsonify({"ok": False, "error": "inbox not ready"}), 503
    log_inbox(text)
    threading.Thread(target=inbox_handler, args=(text,), daemon=True).start()
    return jsonify({"ok": True})


def _reports_path():
    return os.path.join(config.DATA_DIR, "reports.jsonl")


@app.route("/report", methods=["POST"])
def report():
    """Agent posts a completion report here after finishing an inbox task.
    Muse polls GET /reports to pick them up automatically."""
    data = request.get_json(silent=True) or {}
    if not _inbox_auth(data):
        return jsonify({"ok": False}), 403
    task = (data.get("task") or "").strip()[:500]
    result = (data.get("result") or "").strip()[:4000]
    if not task or not result:
        return jsonify({"ok": False, "error": "task and result required"}), 400
    try:
        with open(_reports_path(), "a") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "task": task,
                "result": result,
                "seen": False,
            }) + "\n")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/reports", methods=["GET", "POST"])
def reports():
    """Muse polls this to collect the agent's completion reports.
    Marks returned reports as seen."""
    data = request.get_json(silent=True) or {}
    secret = data.get("secret") or request.args.get("secret")
    if not secret or secret != config.INBOX_SECRET:
        return jsonify({"ok": False}), 403
    path = _reports_path()
    items = []
    if os.path.exists(path):
        try:
            with open(path) as fh:
                items = [json.loads(l) for l in fh.read().strip().split("\n") if l.strip()]
        except Exception:
            pass
    new = [it for it in items if not it.get("seen")]
    for it in items:
        it["seen"] = True
    try:
        with open(path, "w") as fh:
            for it in items[-50:]:
                fh.write(json.dumps(it) + "\n")
    except Exception:
        pass
    return jsonify({"ok": True, "reports": new})


def run():
    app.run(host="0.0.0.0", port=config.HTTP_PORT)
