"""Thai speaking practice tutor bot for English speakers.

Trains like an experienced professional speaking teacher: short lessons,
word-by-word breakdowns, drilling, and the student produces their own
sentences after every lesson. Powered by the Claude API.
Voice messages supported: students speak Thai, the bot transcribes (Whisper,
Thai), teaches the lesson (Claude), and speaks the Thai sentences back (TTS).

ACCESS CONTROL: the bot is private. Each student gets a single-use invite
link (t.me/<bot>?start=CODE). The first Telegram account to open it is bound
to that code; the code can't be reused or shared. Anyone else gets a polite
notice and no API calls are made for them.

Deploy as a Railway worker. Env vars:
  BOT_TOKEN          Telegram bot token (from @BotFather)
  ANTHROPIC_API_KEY  Claude API key (console.anthropic.com)
  OPENAI_API_KEY     OpenAI API key (platform.openai.com) — needed for voice
  MODEL              Claude model id (default: claude-haiku-4-5-20251001)
  TTS_VOICE          OpenAI TTS voice (default: onyx, male)
  ADMIN_CHAT_ID      Telegram user id of the teacher (full access + commands)
  BOT_USERNAME       Bot username without @ (default: ThaiPractice_Bot)
  DATA_DIR           Directory for codes.json (default: "."; use "/data" with
                     a Railway volume so invites survive redeploys)
  DAILY_LIMIT        Max practice messages per user per day (default: 100)

Admin commands (only ADMIN_CHAT_ID):
  /newcodes 20     generate 20 single-use invite links
  /users           list activated students
  /revoke CODE     deactivate an invite code / student
"""
import datetime
import html
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request

import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("MODEL", "claude-haiku-4-5-20251001")
TTS_VOICE = os.environ.get("TTS_VOICE", "onyx")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "ThaiPractice_Bot")
DATA_DIR = os.environ.get("DATA_DIR", ".")
CODES_FILE = os.path.join(DATA_DIR, "codes.json")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "100"))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

SYSTEM_PROMPT = (
    "You are an experienced professional Thai speaking teacher for English-speaking "
    "beginners. You are male — if anyone asks, say you are a male Thai tutor bot.\n\n"
    "TEACH LIKE A REAL SPEAKING TEACHER. Every lesson follows this flow:\n"
    "1. TEACH — Present ONE short, useful Thai sentence or pattern. Show it three ways: "
    "Thai script, simple transliteration with tone marks (e.g. phom yaak gin), and English meaning.\n"
    "2. BREAK DOWN — Break the sentence into words: each word with its transliteration "
    "and English meaning, so the student sees how the sentence is built.\n"
    "3. DRILL — Ask the student to say it out loud: by voice message, or by typing the "
    "transliteration.\n"
    "4. PRODUCE — Ask the student to make their OWN sentence with the same pattern "
    "(a different word, about their own life). This step is mandatory — never skip it, "
    "never move on without the student producing something.\n"
    "5. CORRECT & ENCOURAGE — Praise what they got right, gently fix mistakes, then "
    "start the next small lesson.\n\n"
    "RULES:\n"
    "- Students do NOT need to type Thai script — transliteration or English answers are "
    "fine. Thai script in your lessons is for reading and listening.\n"
    "- One pattern per lesson. Bite-sized. No grammar lectures.\n"
    "- Follow the student's lead on topics. If they ask to practice a specific topic "
    "(e.g. ordering food) or return to an earlier one, switch to it immediately — never "
    "force them back to the beginning. If they don't name a topic, start from absolute "
    "beginner (greetings, introducing yourself) and build up gradually across the "
    "conversation.\n"
    "- Always end your message with a question or task that makes the student produce "
    "something — never end with just information.\n"
    "- Keep it warm, patient, and encouraging like a great teacher.\n"
    "- VOICE: you CAN speak out loud. Every reply you write is also delivered to the "
    "student as a Thai voice message that speaks your Thai text. Never claim you are "
    "text-only or cannot produce audio — you are a speaking teacher, and the student "
    "hears your voice every turn.\n\n"
    "REPLY FORMAT (follow exactly):\n"
    "1. FIRST: the Thai lesson phrase wrapped in 🔊 markers — the exact sentence the student "
    "must learn and repeat (or the corrected model sentence when fixing a mistake). Nothing "
    "else on these lines: no greeting, no English, no transliteration. Your voice speaks "
    "exactly what's between the markers, so the student hears the pronunciation FIRST, "
    "before any explanation.\n"
    "2. Then a line containing only ---\n"
    "3. Then the rest of the lesson: greeting, transliteration, English meaning, "
    "word-by-word breakdown, corrections, encouragement, and your question/task for the "
    "student.\n"
    "Example:\n"
    "🔊ผมอยากกินข้าวผัด🔊\n"
    "---\n"
    "Great choice! That means ...\n\n"
    "IMPORTANT: You are a practice bot, NOT a human teacher. If a student asks about "
    "class schedules, fees, payments, enrollment, or anything administrative — or tries to "
    "talk to you as if you were the teacher — do NOT guess or invent answers. Reply briefly "
    "in a friendly way: \"I'm just the practice buddy — please message your teacher "
    "directly about classes or fees!\" Then steer back to the lesson with a question."
)

CHAT_SYSTEM_PROMPT = (
    "You are a friendly Thai conversation partner for English-speaking learners of "
    "Thai. You are male — if anyone asks, say you are a male Thai tutor bot. "
    "Chat naturally and warmly in Thai (Thai script), like a good friend. When the "
    "student makes mistakes in Thai, first respond to what they said, then add a short "
    "gentle correction in English like \"Small fix: ...\" explaining the correct Thai. "
    "Keep replies short (2-4 sentences of Thai) and conversational, and always ask a "
    "follow-up question to keep the conversation going. Match their level.\n\n"
    "RULES:\n"
    "- Students do NOT need to type Thai script — transliteration or English answers are "
    "fine. Thai script in your messages is for reading and listening.\n"
    "- Keep it warm, patient, and encouraging.\n"
    "- VOICE: you CAN speak out loud. Every reply you write is also delivered to the "
    "student as a Thai voice message that speaks your Thai text. Never claim you are "
    "text-only or cannot produce audio.\n\n"
    "REPLY FORMAT (follow exactly):\n"
    "First, a block with ONLY Thai script. Your voice speaks exactly this block, so no "
    "English and no transliteration here.\n"
    "Then a line containing only ---\n"
    "Then the English translation of your whole reply (including any correction note) — "
    "natural, not word-for-word.\n\n"
    "IMPORTANT: You are a practice bot, NOT a human teacher. If a student asks about "
    "class schedules, fees, payments, enrollment, or anything administrative — or tries to "
    "talk to you as if you were the teacher — do NOT guess or invent answers. Reply briefly "
    "in a friendly way: \"I'm just the practice buddy — please message your teacher "
    "directly about classes or fees!\" Then steer back to chatting in Thai with a question."
)

# user_id -> "lesson" (default) or "chat"
modes = {}

# user_id -> list of {"role": ..., "content": ...}
histories = {}
# user_id -> (date_str, count)
daily_counts = {}
# user_id -> last timestamp of the "private bot" notice (spam cooldown)
gate_notices = {}


def tg(method, params=None, timeout=30):
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def send_text(chat_id, text, reply_to=None, keyboard=None):
    params = {"chat_id": chat_id, "text": text}
    if reply_to:
        params["reply_to_message_id"] = reply_to
    # Persistent visible tab: every message carries the Commands keyboard
    # unless the caller passes an explicit markup (False suppresses it).
    if keyboard is None:
        keyboard = commands_keyboard()
    if keyboard:
        params["reply_markup"] = keyboard
    try:
        return tg("sendMessage", params)
    except Exception as e:
        print("sendMessage failed:", e)
        return None


COMMANDS_BTN = "📋 Commands"


def commands_keyboard():
    """Persistent visible tab — a single Commands button, always on screen."""
    return json.dumps({
        "keyboard": [[{"text": COMMANDS_BTN}]],
        "resize_keyboard": True,
    })


COMMANDS_TEXT = (
    "📋 Commands\n\n"
    "/lesson — step-by-step Thai lessons\n"
    "/chat — free conversation in Thai\n"
    "/new — start a fresh conversation\n"
    "/start — restart the bot"
)

COMMANDS_TEXT_ADMIN = COMMANDS_TEXT + (
    "\n\n👑 Admin commands\n"
    "/newcodes [N] — make N single-use invite links\n"
    "/users — list activated students\n"
    "/revoke CODE — revoke an invite or user"
)


def send_typing(chat_id):
    try:
        tg("sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout=10)
    except Exception:
        pass


# ---------- invite codes ----------

def load_codes():
    try:
        with open(CODES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("codes", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_codes(codes):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CODES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"codes": codes}, f, ensure_ascii=False)
    os.replace(tmp, CODES_FILE)


def is_admin(user_id):
    return bool(ADMIN_CHAT_ID) and str(user_id) == str(ADMIN_CHAT_ID)


def is_activated(user_id):
    if is_admin(user_id):
        return True
    codes = load_codes()
    return any(c.get("used_by") == user_id for c in codes.values())


def redeem_code(code, user_id, label=""):
    code = (code or "").strip().upper()
    codes = load_codes()
    entry = codes.get(code)
    if not entry:
        return "invalid"
    if entry.get("used_by") == user_id:
        return "already_yours"
    if entry.get("used_by"):
        return "used"
    entry["used_by"] = user_id
    entry["label"] = label
    entry["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    save_codes(codes)
    return "ok"


CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no confusing chars


def make_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def invite_link(code):
    return f"https://t.me/{BOT_USERNAME}?start={code}"


GATE_MSG = (
    "🔒 This Thai practice bot is private.\n\n"
    "Please ask your teacher for your personal invite link!"
)


def gate_check(chat_id, user_id):
    """True if the user may use the bot. Sends a (rate-limited) notice otherwise."""
    if is_activated(user_id):
        return True
    now = time.time()
    if now - gate_notices.get(user_id, 0) > 3600:
        send_text(chat_id, GATE_MSG)
        gate_notices[user_id] = now
    return False


# ---------- AI ----------

def ask_claude(messages, model=None, max_tokens=400, system=None):
    body = json.dumps({
        "model": model or MODEL,
        "max_tokens": max_tokens,
        "system": system or SYSTEM_PROMPT,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")


def over_daily_limit(user_id):
    today = datetime.date.today().isoformat()
    day, count = daily_counts.get(user_id, (today, 0))
    if day != today:
        daily_counts[user_id] = (today, 0)
        return False
    return count >= DAILY_LIMIT


def bump_daily(user_id):
    today = datetime.date.today().isoformat()
    day, count = daily_counts.get(user_id, (today, 0))
    daily_counts[user_id] = (today, count + 1) if day == today else (today, 1)


def send_voice(chat_id, audio_bytes, caption="", reply_to=None):
    """Send an .ogg Opus voice message, with the reply text as caption when it fits."""
    try:
        files = {"voice": ("reply.ogg", audio_bytes, "audio/ogg")}
        data = {"chat_id": chat_id, "caption": caption[:1024]}
        if reply_to:
            data["reply_to_message_id"] = reply_to
        r = requests.post(f"{API}/sendVoice", data=data, files=files, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("sendVoice failed:", e)
        return None


def download_telegram_file(file_id):
    info = tg("getFile", {"file_id": file_id}, timeout=30)
    path = info["result"]["file_path"]
    with urllib.request.urlopen(f"{FILE_API}/{path}", timeout=60) as r:
        return r.read()


def _whisper(audio_bytes):
    # Auto-detect language: students mix Thai practice with English questions,
    # so forcing Thai would turn English into gibberish. Thai auto-detection
    # is reliable (unlike Burmese) — no forcing needed.
    data = {"model": "whisper-1", "response_format": "verbose_json", "temperature": 0}
    r = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={"file": ("voice.ogg", audio_bytes, "audio/ogg")},
        data=data,
        timeout=90,
    )
    r.raise_for_status()
    out = r.json()
    return out.get("text", "").strip(), out.get("language", "")


def whisper_transcribe(audio_bytes, duration=0):
    text, lang = _whisper(audio_bytes)
    print(f"whisper: detected={lang} chars={len(text)} dur={duration}s")
    return text


def tts_speak(text):
    r = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={"model": "tts-1", "input": text, "voice": TTS_VOICE, "response_format": "opus"},
        timeout=90,
    )
    r.raise_for_status()
    return r.content


def split_reply(reply):
    """Split bilingual reply into (thai_part, full_text)."""
    if "\n---\n" in reply:
        thai = reply.split("\n---\n")[0].strip()
        return (thai or reply), reply
    return reply, reply


def thai_only(text):
    """Extract Thai-script runs. Guarantees the voice speaks Thai even if the
    model drifts from the --- reply format."""
    parts = re.findall(r"[\u0E00-\u0E7F][\u0E00-\u0E7F ]*", text)
    return " ".join(p.strip() for p in parts if p.strip())


def phrase_to_speak(reply):
    """The Thai phrase the voice should speak (the lesson phrase)."""
    # 1. Explicit 🔊...🔊 markers (most reliable).
    m = re.search(r"🔊(.*?)🔊", reply, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # 2. Pre---- block, if it's mostly Thai (prompt-compliant format).
    thai_part, _ = split_reply(reply)
    stripped = thai_part.strip()
    if stripped:
        latin = re.sub(r"[\u0E00-\u0E7F\s]", "", stripped)
        if len(latin) <= len(stripped) * 0.3:
            out = thai_only(stripped)
            if out:
                return out
    # 3. Fallback: longest Thai run in the reply (usually the lesson phrase,
    # not the greeting or single breakdown words).
    runs = [r.strip() for r in re.findall(r"[\u0E00-\u0E7F][\u0E00-\u0E7F ]*", reply)
            if r.strip()]
    if runs:
        return max(runs, key=len)
    return stripped or reply


def send_lesson_turn(chat_id, user_id, reply, thread):
    """Teacher speaks the Thai phrase FIRST (voice), then the written lesson
    (which asks the student to say it out loud)."""
    speak = phrase_to_speak(reply)
    print(f"lesson voice: mode={get_mode(user_id)} speak_chars={len(speak)} reply_chars={len(reply)}")
    try:
        voice_bytes = tts_speak(speak)
        print(f"TTS ok: {len(voice_bytes)} bytes")
        res = send_voice(chat_id, voice_bytes, reply_to=thread)
        print(f"sendVoice ok={bool(res and res.get('ok'))}")
    except Exception as e:
        print(f"voice send failed: {type(e).__name__}: {e}")
    send_text(chat_id, reply, thread)


def get_mode(user_id):
    return modes.get(user_id, "lesson")


def tutor_reply(user_id, user_text):
    """Run one tutor turn: returns the reply text (also updates history)."""
    history = histories.setdefault(user_id, [])
    history.append({"role": "user", "content": user_text})
    history[:] = history[-20:]  # keep last 10 exchanges
    system = CHAT_SYSTEM_PROMPT if get_mode(user_id) == "chat" else SYSTEM_PROMPT
    try:
        reply = ask_claude(history, system=system).strip()
    except Exception as e:
        print("Claude API failed:", e)
        history.pop()  # don't keep the failed turn
        return None
    if not reply:
        history.pop()
        return None
    history.append({"role": "assistant", "content": reply})
    history[:] = history[-20:]
    bump_daily(user_id)
    return reply


START_MSG = (
    "👋 Hi! I'm your Thai speaking teacher.\n\n"
    "I'll train you step by step like a real teacher: short lessons, "
    "word-by-word breakdowns, and you'll make your own Thai sentences "
    "after every lesson.\n\n"
    "You don't need to type Thai — answer in transliteration or English, "
    "or hold the 🎤 mic button and SPEAK Thai out loud!\n\n"
    "Two modes:\n"
    "📚 Lessons (default) — I teach you step by step\n"
    "💬 /chat — free conversation in Thai\n\n"
    "Commands:\n"
    "/lesson — back to lessons\n"
    "/chat — free Thai conversation\n"
    "/new — fresh start (keeps your mode)"
    "\n\nDeveloped by Arkar Myowin"
)

LIMIT_MSG = (
    "You've had lots of great practice today! 🎉 Come back tomorrow for more. "
    "Keep using what you learned!"
)


def handle_voice(chat_id, user_id, voice, thread):
    duration = voice.get("duration", 0)
    if duration > 120:
        send_text(chat_id,
                  "That's a long one! 😄 Keep voice messages under 2 minutes so I can "
                  "understand you properly.", thread)
        return
    if not OPENAI_API_KEY:
        send_text(chat_id,
                  "Voice isn't switched on yet — send me text for now and I'll still "
                  "help you practice! ✍️", thread)
        return
    if over_daily_limit(user_id):
        send_text(chat_id, LIMIT_MSG, thread)
        return
    try:
        tg("sendChatAction", {"chat_id": chat_id, "action": "record_voice"}, timeout=10)
    except Exception:
        pass
    try:
        audio = download_telegram_file(voice["file_id"])
        transcript = whisper_transcribe(audio, duration)
    except Exception as e:
        print("voice download/transcribe failed:", e)
        send_text(chat_id, "I couldn't quite hear that 🎧 — try again?", thread)
        return
    if not transcript or len(transcript) < 2:
        if duration <= 2:
            send_text(chat_id,
                      "That was too short for me to hear anything! 🎤\n"
                      "Hold the mic button down, say a full sentence in Thai, "
                      "then release.", thread)
        else:
            send_text(chat_id, "I didn't catch any words there — say it once more? 🎤", thread)
        return
    # Admin sees the raw transcript — makes it easy to check what was heard.
    if is_admin(user_id):
        send_text(chat_id, f"👂 Heard: {transcript}", thread)
    send_typing(chat_id)
    reply = tutor_reply(user_id, transcript)
    if not reply:
        send_text(chat_id, "Hmm, I lost my train of thought 😅 — try sending that again!", thread)
        return
    # Voice answer speaks Thai only; the text carries the lesson / translation.
    if get_mode(user_id) == "lesson":
        send_lesson_turn(chat_id, user_id, reply, thread)
        return
    thai_part, _ = split_reply(reply)
    try:
        voice_bytes = tts_speak(thai_part)
        sent = send_voice(chat_id, voice_bytes, caption=reply, reply_to=thread)
    except Exception as e:
        print("TTS failed:", e)
        sent = None
    if sent and len(reply) <= 1024:
        return  # caption carried the text
    send_text(chat_id, reply, thread)


def handle_admin_command(chat_id, user_id, text):
    parts = text.split()
    cmd = parts[0].lower()

    if cmd == "/newcodes":
        try:
            n = int(parts[1]) if len(parts) > 1 else 10
        except ValueError:
            n = 10
        n = max(1, min(n, 50))
        codes = load_codes()
        fresh = []
        while len(fresh) < n:
            c = make_code()
            if c not in codes:
                codes[c] = {"used_by": None, "label": "", "created": datetime.datetime.now().isoformat(timespec="seconds")}
                fresh.append(c)
        save_codes(codes)
        lines = [f"🎟️ {n} single-use invite links (each works once, then locks to that student):",
                 ""]
        lines += [invite_link(c) for c in fresh]
        lines += ["", "Send one link per student, privately — not in a group!"]
        # Telegram messages cap at 4096 chars; split if needed.
        chunk, out = [], []
        for line in lines:
            if sum(len(x) + 1 for x in chunk) + len(line) > 4000:
                out.append("\n".join(chunk))
                chunk = []
            chunk.append(line)
        out.append("\n".join(chunk))
        for m in out:
            send_text(chat_id, m)
        return True

    if cmd == "/users":
        codes = load_codes()
        used = [(c, e) for c, e in codes.items() if e.get("used_by")]
        unused = sum(1 for e in codes.values() if not e.get("used_by"))
        if not used:
            send_text(chat_id, f"No students activated yet. {unused} unused invite(s).")
            return True
        lines = [f"👥 Activated students ({len(used)}), {unused} invite(s) left:", ""]
        for c, e in sorted(used, key=lambda x: x[1].get("used_at", "")):
            label = f" ({e['label']})" if e.get("label") else ""
            lines.append(f"• {c} → {e['used_by']}{label}")
        send_text(chat_id, "\n".join(lines)[:4000])
        return True

    if cmd == "/revoke":
        if len(parts) < 2:
            send_text(chat_id, "Usage: /revoke CODE  (or /revoke <telegram user id>)")
            return True
        target = parts[1].strip().upper()
        codes = load_codes()
        if target in codes:
            codes[target]["used_by"] = None
            save_codes(codes)
            send_text(chat_id, f"🚫 Invite {target} deactivated.")
        else:
            try:
                uid = int(parts[1])
            except ValueError:
                send_text(chat_id, "Code not found.")
                return True
            found = [c for c, e in codes.items() if e.get("used_by") == uid]
            for c in found:
                codes[c]["used_by"] = None
            save_codes(codes)
            histories.pop(uid, None)
            send_text(chat_id, f"🚫 Deactivated {len(found)} invite(s) for user {uid}."
                               if found else "That user has no active invite.")
        return True

    return False


def handle_update(u):
    msg = u.get("message") or {}
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    if not chat_id:
        return
    user = msg.get("from", {})
    user_id = user.get("id")
    if not user_id:
        return
    name = user.get("first_name", "there")
    thread = msg.get("message_id") if chat.get("type") in ("group", "supergroup") else None
    text = (msg.get("text") or "").strip()

    # Admin commands work without an invite.
    if is_admin(user_id) and text.startswith("/"):
        if handle_admin_command(chat_id, user_id, text):
            return

    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            result = redeem_code(parts[1], user_id, name)
            if result == "ok":
                send_text(chat_id,
                          f"🎉 Welcome, {html.escape(name)}! Your invite is activated.\n\n" + START_MSG,
                          thread)
            elif result == "already_yours":
                send_text(chat_id, "You're already activated — let's practice! 💪\n\n" + START_MSG,
                          thread)
            else:
                send_text(chat_id,
                          "😕 This invite link is invalid or was already used.\n"
                          "Please ask your teacher for your own personal link!", thread)
            return
        if not gate_check(chat_id, user_id):
            return
        send_text(chat_id, START_MSG, thread)
        return

    # Everyone else needs a valid invite before anything (no API cost for strangers).
    if not gate_check(chat_id, user_id):
        return

    if msg.get("voice"):
        handle_voice(chat_id, user_id, msg["voice"], thread)
        return

    if not text:
        return
    if text == COMMANDS_BTN:
        send_text(chat_id,
                  COMMANDS_TEXT_ADMIN if is_admin(user_id) else COMMANDS_TEXT,
                  thread)
        return
    if text.startswith("/new"):
        histories.pop(user_id, None)
        send_text(chat_id, "✨ Fresh start! What would you like to talk about?", thread)
        return
    if text.startswith("/chat"):
        modes[user_id] = "chat"
        histories.pop(user_id, None)
        send_text(chat_id,
                  "💬 Free talk mode! Just chat with me in Thai — type or send a voice "
                  "message. I'll reply in Thai with an English translation.\n\n"
                  "Say /lesson anytime to go back to lessons.", thread)
        return
    if text.startswith("/lesson"):
        modes[user_id] = "lesson"
        histories.pop(user_id, None)
        send_text(chat_id,
                  "📚 Lesson mode! I'll teach you Thai step by step: short lessons, "
                  "word breakdowns, and you'll make your own sentences.\n\n"
                  "Say /chat anytime for free conversation.", thread)
        return
    if text.startswith("/"):
        return

    if over_daily_limit(user_id):
        send_text(chat_id, LIMIT_MSG, thread)
        return

    send_typing(chat_id)
    reply = tutor_reply(user_id, text)
    if reply:
        if get_mode(user_id) == "lesson" and OPENAI_API_KEY:
            send_lesson_turn(chat_id, user_id, reply, thread)
        else:
            send_text(chat_id, reply, thread)
    else:
        send_text(chat_id, "Hmm, I lost my train of thought 😅 — try sending that again!", thread)


def main():
    if not BOT_TOKEN:
        print("Set the BOT_TOKEN env var (get it from @BotFather).")
        return
    if not ANTHROPIC_API_KEY:
        print("Set the ANTHROPIC_API_KEY env var (console.anthropic.com).")
        return
    import sys
    sys.stdout.reconfigure(line_buffering=True)  # never lose log lines to buffering
    offset = 0
    print("Thai practice tutor bot started. Polling...")
    while True:
        try:
            res = tg("getUpdates", {"offset": offset, "timeout": 50}, timeout=70)
            for u in res.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                try:
                    handle_update(u)
                except Exception as e:
                    print("handler error:", e)
        except Exception as e:
            print("poll error:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
