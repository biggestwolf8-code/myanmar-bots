"""Daddy3.0 — interactive game-board bot for Arkar's channel.

A board is a post: a text message with inline buttons. Each button is
tied to one photo. A user taps a button in the channel and the photo is
sent to their PRIVATE chat (never to the channel).

Admin (Arkar) designs boards from the bot's DM:
  /newboard          start a draft (bot asks for the board title)
  <title text>       sets the draft title
  <photo + caption>  adds a button; the caption IS the button label
                     (e.g. caption "Show his balls")
  /done              save the draft, show a preview
  /post <id>         post the board to the channel
  /setchannel <@ch>  set the target channel (bot must be admin there)
  /boards            list saved boards
  /delboard <id>     delete a board
  /cancel            discard the current draft
  /help              admin help

Users:
  /start             welcome (or /start board_<id> via deep link)
  tap a button       the photo lands in their private chat

Photos are stored as Telegram file_ids only — Telegram hosts the images.
Boards live in boards.json under DATA_DIR (Railway volume).
"""

import json
import os
import random
import string
import time

import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = {
    x.strip()
    for x in os.environ.get("ADMIN_CHAT_IDS", "7061620871,8028025915").split(",")
    if x.strip()
}
DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
BOARDS_PATH = os.path.join(DATA_DIR, "boards.json")
API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

FOOTER = "Developed by Arkar Myowin"


def load_boards():
    try:
        with open(BOARDS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"channel": "", "boards": {}, "draft": None, "seq": 0}


def save_boards(state):
    tmp = BOARDS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, BOARDS_PATH)


def new_board_id(state):
    state["seq"] = state.get("seq", 0) + 1
    return f"b{state['seq']}"


def api(method, payload=None, files=None, timeout=60):
    url = f"{API}/{method}"
    try:
        if files:
            r = requests.post(url, data=payload or {}, files=files, timeout=timeout)
        else:
            r = requests.post(url, json=payload or {}, timeout=timeout)
        return r.json()
    except Exception as e:
        print(f"api {method} error: {e}", flush=True)
        return {"ok": False}


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api("sendMessage", payload)


def send_photo(chat_id, file_id, caption=None):
    payload = {"chat_id": chat_id, "photo": file_id}
    if caption:
        payload["caption"] = caption
    return api("sendPhoto", payload)


def answer_callback(callback_id, text=None, show_alert=False, url=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    if url:
        payload["url"] = url
    return api("answerCallbackQuery", payload)


def bot_username():
    r = api("getMe")
    if r.get("ok"):
        return r["result"].get("username", "")
    return ""


def board_keyboard(board, include_open=True):
    rows = []
    for i, btn in enumerate(board["buttons"]):
        rows.append(
            [{"text": btn["label"], "callback_data": f"reveal:{board['id']}:{i}"}]
        )
    if include_open:
        uname = bot_username()
        if uname:
            rows.append(
                [
                    {
                        "text": "▶ Open in private chat",
                        "url": f"https://t.me/{uname}?start=board_{board['id']}",
                    }
                ]
            )
    return {"inline_keyboard": rows}


def board_text(board):
    lines = [board["title"], "", "Tap a button — the photo comes to your private chat."]
    return "\n".join(lines)


def is_admin(chat_id):
    return str(chat_id) in ADMIN_IDS


def handle_start(chat_id, text, state):
    parts = text.split()
    if len(parts) > 1 and parts[1].startswith("board_"):
        bid = parts[1][len("board_"):]
        board = state["boards"].get(bid)
        if board:
            send_message(
                chat_id,
                board_text(board),
                reply_markup=board_keyboard(board, include_open=False),
            )
            return
        send_message(chat_id, "That board is gone. Check the channel for the latest one.")
        return
    if is_admin(chat_id):
        send_message(
            chat_id,
            "Daddy3.0 admin.\n\n"
            "/newboard — design a new board\n"
            "/boards — list your boards\n"
            "/post <id> — post a board to the channel\n"
            "/setchannel <@channel> — where boards go\n"
            "/delboard <id> — delete a board\n"
            "/help — full help",
        )
        return
    send_message(
        chat_id,
        "Welcome to Daddy3.0.\n\n"
        "The game boards live in the channel — tap a button there and "
        "the photo comes straight to this private chat.",
    )


def handle_help(chat_id):
    send_message(
        chat_id,
        "Design a board:\n\n"
        "1. /newboard — I ask for a title, you send it.\n"
        "2. Send photos, one by one. The CAPTION on each photo "
        "becomes its button label — e.g. caption \"Show his balls\".\n"
        "3. /done — saves the board and shows a preview.\n"
        "4. /post <id> — posts it to the channel.\n\n"
        "Other commands:\n"
        "/boards — list boards\n"
        "/delboard <id> — delete one\n"
        "/setchannel <@channel> — where boards go\n"
        "/cancel — throw the draft away",
    )


def handle_message(msg, state):
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"].get("type", "private")
    text = (msg.get("text") or "").strip()
    user_id = msg.get("from", {}).get("id")

    if chat_type != "private":
        return

    if text.startswith("/start"):
        handle_start(chat_id, text, state)
        return

    if not is_admin(chat_id):
        if text.startswith("/"):
            send_message(
                chat_id,
                "Boards live in the channel — tap a button there and the "
                "photo comes to this private chat.",
            )
        return

    # ---- admin ----
    if text == "/help":
        handle_help(chat_id)
        return

    if text == "/cancel":
        state["draft"] = None
        save_boards(state)
        send_message(chat_id, "Draft discarded.")
        return

    if text == "/newboard":
        state["draft"] = {"title": None, "buttons": []}
        save_boards(state)
        send_message(chat_id, "New board. Send me the board title (the text on the post).")
        return

    if text == "/done":
        draft = state.get("draft")
        if not draft or not draft.get("title"):
            send_message(chat_id, "No draft yet — /newboard first, then send a title.")
            return
        if not draft["buttons"]:
            send_message(chat_id, "The board has no buttons yet — send at least one photo with a caption.")
            return
        bid = new_board_id(state)
        board = {"id": bid, "title": draft["title"], "buttons": draft["buttons"]}
        state["boards"][bid] = board
        state["draft"] = None
        save_boards(state)
        send_message(
            chat_id,
            f"Saved as {bid} — preview:\n\n{board_text(board)}",
            reply_markup=board_keyboard(board, include_open=False),
        )
        send_message(chat_id, f"Post it with: /post {bid}")
        return

    if text == "/boards":
        boards = state["boards"]
        if not boards:
            send_message(chat_id, "No boards yet. /newboard to make one.")
            return
        lines = ["Your boards:"]
        for bid, b in boards.items():
            lines.append(f"{bid} — {b['title']} ({len(b['buttons'])} buttons)")
        lines.append("\nPost one with /post <id>")
        send_message(chat_id, "\n".join(lines))
        return

    if text.startswith("/delboard"):
        parts = text.split()
        if len(parts) < 2 or parts[1] not in state["boards"]:
            send_message(chat_id, "Usage: /delboard <id> — see /boards for ids.")
            return
        title = state["boards"][parts[1]]["title"]
        del state["boards"][parts[1]]
        save_boards(state)
        send_message(chat_id, f"Deleted {parts[1]} ({title}).")
        return

    if text.startswith("/setchannel"):
        parts = text.split()
        if len(parts) < 2:
            cur = state.get("channel") or "(not set)"
            send_message(chat_id, f"Current channel: {cur}\nUsage: /setchannel <@channel>")
            return
        state["channel"] = parts[1]
        save_boards(state)
        send_message(
            chat_id,
            f"Channel set to {parts[1]}.\n"
            "Make sure the bot is an admin in that channel, or posting will fail.",
        )
        return

    if text.startswith("/post"):
        parts = text.split()
        channel = state.get("channel")
        if not channel:
            send_message(chat_id, "No channel set yet — /setchannel <@channel> first.")
            return
        bid = parts[1] if len(parts) > 1 else None
        if not bid or bid not in state["boards"]:
            send_message(chat_id, "Usage: /post <id> — see /boards for ids.")
            return
        board = state["boards"][bid]
        r = send_message(channel, board_text(board), reply_markup=board_keyboard(board))
        if r.get("ok"):
            send_message(chat_id, f"Posted {bid} to {channel}.")
        else:
            send_message(
                chat_id,
                "Posting failed — is the bot an admin in the channel? "
                f"Telegram said: {r.get('description', 'unknown error')}",
            )
        return

    # photo with caption -> add a button to the draft
    if msg.get("photo"):
        draft = state.get("draft")
        if not draft:
            send_message(chat_id, "No draft open — /newboard first.")
            return
        if draft.get("title") is None:
            send_message(chat_id, "Send the board title first (plain text), then the photos.")
            return
        label = (msg.get("caption") or "").strip()
        if not label:
            send_message(chat_id, "That photo has no caption — the caption becomes the button label. Send it again with a caption.")
            return
        file_id = msg["photo"][-1]["file_id"]
        draft["buttons"].append({"label": label, "file_id": file_id})
        save_boards(state)
        send_message(
            chat_id,
            f"Added button \"{label}\" ({len(draft['buttons'])} on this board). "
            "Send another photo, or /done to save.",
        )
        return

    # plain text while a draft is open and title not set -> title
    draft = state.get("draft")
    if draft is not None and draft.get("title") is None and text and not text.startswith("/"):
        draft["title"] = text
        save_boards(state)
        send_message(
            chat_id,
            f"Title set: {text}\n\nNow send the photos, one by one — "
            "caption each one with its button label.",
        )
        return

    if text.startswith("/"):
        send_message(chat_id, "Unknown command. /help for the list.")
    else:
        send_message(chat_id, "Nothing to do with that — /newboard to start a board, /help for the list.")


def handle_callback(query, state):
    data = query.get("data", "")
    user_id = query["from"]["id"]
    qid = query["id"]
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "reveal":
        answer_callback(qid, "Unknown button.")
        return
    _, bid, idx = parts
    board = state["boards"].get(bid)
    if not board:
        answer_callback(qid, "That board is gone.", show_alert=True)
        return
    try:
        i = int(idx)
        btn = board["buttons"][i]
    except (ValueError, IndexError):
        answer_callback(qid, "Unknown button.", show_alert=True)
        return
    r = send_photo(user_id, btn["file_id"])
    if r.get("ok"):
        answer_callback(qid, "Sent to your private chat.")
    else:
        uname = bot_username()
        url = f"https://t.me/{uname}?start=board_{bid}" if uname else None
        answer_callback(
            qid,
            "Tap START on the bot first, then tap the button again.",
            show_alert=True,
            url=url,
        )


def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN not set", flush=True)
        return
    print("Daddy3.0 started. Polling for updates...", flush=True)
    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset:
                params["offset"] = offset
            r = requests.get(f"{API}/getUpdates", params=params, timeout=60)
            data = r.json()
        except Exception as e:
            print(f"getUpdates error: {e}", flush=True)
            time.sleep(5)
            continue
        if not data.get("ok"):
            print(f"getUpdates not ok: {data}", flush=True)
            time.sleep(5)
            continue
        state = load_boards()
        dirty = False
        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            try:
                if "message" in upd:
                    before = json.dumps(state, sort_keys=True)
                    handle_message(upd["message"], state)
                    if json.dumps(state, sort_keys=True) != before:
                        dirty = True
                elif "callback_query" in upd:
                    handle_callback(upd["callback_query"], state)
            except Exception as e:
                print(f"update error: {e}", flush=True)
        if dirty:
            save_boards(state)


if __name__ == "__main__":
    main()
