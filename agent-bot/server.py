"""Tiny HTTP server: endpoints for the laptop companion worker.

GET  /laptop/poll?secret=...    -> pending tasks (worker long-polls this)
POST /laptop/result              -> {secret, id, ok, output}
GET  /health                     -> ok
"""
from flask import Flask, jsonify, request

import config
import remote

app = Flask(__name__)


def _auth():
    secret = request.args.get("secret") or (request.get_json(silent=True) or {}).get("secret")
    return secret == config.WORKER_SECRET


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


def run():
    app.run(host="0.0.0.0", port=config.HTTP_PORT)
