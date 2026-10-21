#!/usr/bin/env python3
"""Seed Telegram file_ids for the English video course.

Uploads each set's video + worksheet PDF to the admin's chat via the bot,
records the returned file_ids in course_file_ids.json, then deletes the
messages (silent upload, no spam left behind).

After this runs, the bot serves media by file_id — no media hosting needed.

Env: BOT_TOKEN, ADMIN_CHAT_ID
Looks for media in ~/workspace/your_files/english-video-set{N}.mp4 and
~/workspace/your_files/english-worksheets/set{N}-worksheets.pdf
"""
import json
import os
import sys

import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
if not BOT_TOKEN or not ADMIN_CHAT_ID:
    print("Set BOT_TOKEN and ADMIN_CHAT_ID env vars.")
    sys.exit(1)

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
MEDIA_DIR = os.path.expanduser("~/workspace/your_files")
SHEETS_DIR = os.path.join(MEDIA_DIR, "english-worksheets")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "course_file_ids.json")


def api(method, **params):
    r = requests.post(f"{API}/{method}", data=params, timeout=120)
    r.raise_for_status()
    out = r.json()
    if not out.get("ok"):
        raise RuntimeError(f"{method} failed: {out}")
    return out["result"]


def upload(kind, n, path):
    if kind == "video":
        method, field = "sendVideo", "video"
    else:
        method, field = "sendDocument", "document"
    with open(path, "rb") as f:
        r = requests.post(
            f"{API}/{method}",
            data={"chat_id": ADMIN_CHAT_ID,
                  "caption": f"course seed {kind} set {n}",
                  "disable_notification": "true"},
            files={field: (os.path.basename(path), f,
                           "video/mp4" if kind == "video" else "application/pdf")},
            timeout=300,
        )
    r.raise_for_status()
    out = r.json()
    if not out.get("ok"):
        raise RuntimeError(f"{method} set {n} failed: {out}")
    msg = out["result"]
    file_id = msg[field]["file_id"]
    try:
        api("deleteMessage", chat_id=ADMIN_CHAT_ID, message_id=msg["message_id"])
    except Exception as e:
        print(f"  (couldn't delete seed message for set {n} {kind}: {e})")
    return file_id


def main():
    ids = {"video": {}, "pdf": {}}
    if os.path.exists(OUT):
        ids = json.load(open(OUT, encoding="utf-8"))
    for n in range(1, 101):
        for kind in ("video", "pdf"):
            if str(n) in ids[kind]:
                continue
            path = (os.path.join(MEDIA_DIR, f"english-video-set{n}.mp4")
                    if kind == "video"
                    else os.path.join(SHEETS_DIR, f"set{n}-worksheets.pdf"))
            if not os.path.exists(path):
                print(f"set {n} {kind}: MISSING {path}, skipping")
                continue
            try:
                fid = upload(kind, n, path)
            except Exception as e:
                print(f"set {n} {kind}: FAILED {e}")
                continue
            ids[kind][str(n)] = fid
            json.dump(ids, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
            print(f"set {n} {kind}: ok", flush=True)
    nv, np = len(ids["video"]), len(ids["pdf"])
    print(f"done: {nv}/100 videos, {np}/100 pdfs -> {OUT}")


if __name__ == "__main__":
    main()
