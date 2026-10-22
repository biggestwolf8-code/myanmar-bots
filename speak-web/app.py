"""MasterClass Articulation — Bitesy-style English ARTICULATION practice for Myanmar learners.

Bite-sized lessons (A1/A2/B1 + Sounds drills) with tap-to-speak practice:
browser-recorded audio -> Whisper -> gpt-4o-mini articulation feedback
(per-SOUND notes with mouth/tongue/lip placement tips, bilingual EN+MM),
plus a Free Talk voice conversation mode. Invite-code access only; progress,
streaks and XP per invite code; per-code daily voice-turn caps.

Env vars:
  OPENAI_API_KEY   OpenAI API key (required for voice features)
  APP_NAME         Display name (default: "MasterClass Speak") — rename here
  ADMIN_PASSWORD   Password for the /admin panel (required)
  DATA_DIR         Storage dir (default "."; use "/data" with a Railway
                   volume so codes/progress/audio survive redeploys)
  DAILY_LIMIT      Max voice turns per invite code per day (default: 100)
  DAILY_COST_LIMIT Max $ per invite code per day (default: 2.0)
  MODEL            Chat model (default: gpt-4o-mini)
  PORT             Listen port (default: 5000)

Invite links: https://<host>/i/<CODE>  (single use; link is the credential)
Admin panel:  https://<host>/admin
"""
import datetime
import json
import os
import re
import secrets
import sqlite3
import time

from flask import Flask, jsonify, redirect, request, send_file, session, url_for

import brain

# ---------------------------------------------------------------- config ---
APP_NAME = os.environ.get("APP_NAME", "MasterClass Articulation")
DATA_DIR = os.environ.get("DATA_DIR", ".")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "100"))
DAILY_COST_LIMIT = float(os.environ.get("DAILY_COST_LIMIT", "2.0"))
PORT = int(os.environ.get("PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LESSONS_FILE = os.path.join(BASE_DIR, "lessons.json")
MAX_AUDIO_BYTES = 5 * 1024 * 1024
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LESSON_ID_RE = re.compile(r"^[a-z0-9-]{1,40}$")

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))


def get_secret_key():
    path = os.path.join(DATA_DIR, "secret.key")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = secrets.token_hex(32)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
        return key


app.secret_key = get_secret_key()
# Invite codes are single-use, so logins persist 90 days across restarts.
app.permanent_session_lifetime = datetime.timedelta(days=90)


# ---------------------------------------------------------------- SQLite ---
def db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(os.path.join(DATA_DIR, "speak.db"))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS codes(
      code TEXT PRIMARY KEY, used_by TEXT, used_at TEXT, created TEXT,
      label TEXT, day TEXT, day_count INTEGER DEFAULT 0, day_cost REAL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS sessions(
      sid TEXT PRIMARY KEY, code TEXT, created TEXT);
    CREATE TABLE IF NOT EXISTS progress(
      code TEXT, lesson_id TEXT, phrase_idx INTEGER, done_at TEXT, score INTEGER,
      PRIMARY KEY(code, lesson_id, phrase_idx));
    CREATE TABLE IF NOT EXISTS streaks(
      code TEXT PRIMARY KEY, last_day TEXT, streak INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS xp(
      code TEXT PRIMARY KEY, total INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS freetalk(
      id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, created TEXT,
      said TEXT, reply_en TEXT, reply_my TEXT);
    CREATE TABLE IF NOT EXISTS lesson_overrides(
      id TEXT PRIMARY KEY, data TEXT);
    CREATE TABLE IF NOT EXISTS usage(
      code TEXT, day TEXT, whisper_cost REAL DEFAULT 0, tts_cost REAL DEFAULT 0,
      in_tok INTEGER DEFAULT 0, out_tok INTEGER DEFAULT 0, chat_cost REAL DEFAULT 0,
      PRIMARY KEY(code, day));
    """)
    con.commit()
    con.close()


init_db()


# ---------------------------------------------------------------- lessons ---
def load_lessons():
    """Repo seed file, with admin overrides from the DB applied on top."""
    try:
        with open(LESSONS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"lessons": []}
    lessons = data.get("lessons", [])
    con = db()
    try:
        rows = con.execute("SELECT id, data FROM lesson_overrides").fetchall()
    finally:
        con.close()
    overrides = {}
    for r in rows:
        try:
            overrides[r["id"]] = json.loads(r["data"])
        except (ValueError, TypeError):
            pass
    out = []
    for l in lessons:
        if l.get("id") in overrides:
            out.append(overrides[l["id"]])
        else:
            out.append(l)
    # allow admin-added lessons that aren't in the seed file
    seed_ids = {l.get("id") for l in lessons}
    for lid, l in overrides.items():
        if lid not in seed_ids:
            out.append(l)
    return [l for l in out if l.get("id") and l.get("phrases")]


def get_lesson(lesson_id):
    for l in load_lessons():
        if l.get("id") == lesson_id:
            return l
    return None


# ------------------------------------------------------------------ auth ---
def current_sid():
    sid = session.get("sid")
    if not sid:
        return None
    con = db()
    try:
        row = con.execute("SELECT sid FROM sessions WHERE sid=?", (sid,)).fetchone()
    finally:
        con.close()
    return sid if row else None


def code_for_sid(sid):
    con = db()
    try:
        row = con.execute("SELECT code FROM sessions WHERE sid=?", (sid,)).fetchone()
    finally:
        con.close()
    return row["code"] if row else None


def make_code():
    con = db()
    try:
        while True:
            c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
            if not con.execute("SELECT 1 FROM codes WHERE code=?", (c,)).fetchone():
                return c
    finally:
        con.close()


def invite_link(code):
    return request.host_url.rstrip("/") + "/i/" + code


def redeem_code(code):
    """Mark a single-use code as used and create a session. Returns sid or None."""
    code = (code or "").strip().upper()
    con = db()
    try:
        row = con.execute("SELECT used_by FROM codes WHERE code=?", (code,)).fetchone()
        if not row or row["used_by"]:
            return None
        sid = secrets.token_hex(16)
        now = datetime.datetime.now().isoformat(timespec="seconds")
        con.execute("UPDATE codes SET used_by=?, used_at=? WHERE code=?",
                    (sid, now, code))
        con.execute("INSERT INTO sessions(sid, code, created) VALUES(?,?,?)",
                    (sid, code, now))
        con.commit()
        return sid
    finally:
        con.close()


def today():
    return datetime.date.today().isoformat()


def _day_row(con, code):
    row = con.execute("SELECT day, day_count, day_cost FROM codes WHERE code=?",
                      (code,)).fetchone()
    if not row:
        return {"day": today(), "count": 0, "cost": 0.0}
    if row["day"] != today():
        return {"day": today(), "count": 0, "cost": 0.0}
    return {"day": row["day"], "count": row["day_count"] or 0,
            "cost": row["day_cost"] or 0.0}


def check_limits(code):
    d = _day_row(db(), code)
    if d["count"] >= DAILY_LIMIT:
        return "daily"
    if d["cost"] >= DAILY_COST_LIMIT:
        return "cost"
    return None


def bump_voice_turn(code):
    con = db()
    try:
        d = _day_row(con, code)
        if d["day"] != today():
            con.execute("UPDATE codes SET day=?, day_count=1 WHERE code=?",
                        (today(), code))
        else:
            con.execute("UPDATE codes SET day_count=day_count+1 WHERE code=?",
                        (code,))
        con.commit()
    finally:
        con.close()


def record_cost(code, whisper=0.0, tts=0.0, in_tok=0, out_tok=0, chat=0.0):
    con = db()
    try:
        con.execute(
            """INSERT INTO usage(code, day, whisper_cost, tts_cost, in_tok, out_tok, chat_cost)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(code, day) DO UPDATE SET
                 whisper_cost=whisper_cost+excluded.whisper_cost,
                 tts_cost=tts_cost+excluded.tts_cost,
                 in_tok=in_tok+excluded.in_tok, out_tok=out_tok+excluded.out_tok,
                 chat_cost=chat_cost+excluded.chat_cost""",
            (code, today(), whisper, tts, in_tok, out_tok, chat))
        con.execute(
            "UPDATE codes SET day_cost=COALESCE(day_cost,0)+?, day=? WHERE code=?",
            (whisper + tts + chat, today(), code))
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------- progress ---
def touch_streak(code):
    """Count today toward the streak. Returns current streak length."""
    con = db()
    try:
        row = con.execute("SELECT last_day, streak FROM streaks WHERE code=?",
                          (code,)).fetchone()
        t = today()
        if row and row["last_day"] == t:
            return row["streak"]
        yesterday = (datetime.date.today() -
                     datetime.timedelta(days=1)).isoformat()
        streak = (row["streak"] + 1) if (row and row["last_day"] == yesterday) else 1
        con.execute(
            "INSERT INTO streaks(code, last_day, streak) VALUES(?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET last_day=excluded.last_day, streak=excluded.streak",
            (code, t, streak))
        con.commit()
        return streak
    finally:
        con.close()


def add_xp(code, n):
    con = db()
    try:
        con.execute(
            "INSERT INTO xp(code, total) VALUES(?,?) "
            "ON CONFLICT(code) DO UPDATE SET total=total+excluded.total",
            (code, n))
        row = con.execute("SELECT total FROM xp WHERE code=?", (code,)).fetchone()
        con.commit()
        return row["total"]
    finally:
        con.close()


def get_stats(code):
    con = db()
    try:
        s = con.execute("SELECT streak FROM streaks WHERE code=?", (code,)).fetchone()
        x = con.execute("SELECT total FROM xp WHERE code=?", (code,)).fetchone()
        return {"streak": s["streak"] if s else 0,
                "xp": x["total"] if x else 0}
    finally:
        con.close()


def mark_phrase_done(code, lesson_id, idx, score):
    con = db()
    try:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        old = con.execute(
            "SELECT score FROM progress WHERE code=? AND lesson_id=? AND phrase_idx=?",
            (code, lesson_id, idx)).fetchone()
        con.execute(
            """INSERT INTO progress(code, lesson_id, phrase_idx, done_at, score)
               VALUES(?,?,?,?,?)
               ON CONFLICT(code, lesson_id, phrase_idx) DO UPDATE SET
                 score=MAX(score, excluded.score), done_at=excluded.done_at""",
            (code, lesson_id, idx, now, score))
        con.commit()
        return (old["score"] if old else 0)
    finally:
        con.close()


def lesson_progress(code, lesson):
    con = db()
    try:
        rows = con.execute(
            "SELECT phrase_idx FROM progress WHERE code=? AND lesson_id=?",
            (code, lesson["id"])).fetchall()
        return {r["phrase_idx"] for r in rows}
    finally:
        con.close()


# ------------------------------------------------------------------ pages ---
@app.route("/health")
def health():
    return jsonify(ok=True, service="speak-web", app=APP_NAME,
                   key_configured=bool(brain.OPENAI_API_KEY))


@app.route("/")
def index():
    from flask import render_template
    sid = current_sid()
    if not sid:
        return render_template("index.html", logged_in=False, app_name=APP_NAME, nav="home")
    code = code_for_sid(sid)
    stats = get_stats(code)
    lessons = load_lessons()
    cards = []
    for l in lessons:
        done = lesson_progress(code, l)
        cards.append({"id": l["id"], "level": l.get("level", ""),
                      "title": l.get("title", ""), "title_my": l.get("title_my", ""),
                      "topic": l.get("topic", ""),
                      "n": len(l["phrases"]), "done": len(done),
                      "completed": len(done) >= len(l["phrases"])})
    cards.sort(key=lambda c: (c["level"], c["title"]))
    levels = sorted({c["level"] for c in cards})
    return render_template("index.html", logged_in=True, app_name=APP_NAME, nav="home",
                           stats=stats, cards=cards, levels=levels)


@app.route("/i/<code>")
def redeem_link(code):
    from flask import render_template
    sid = redeem_code(code)
    if not sid:
        return render_template("index.html", logged_in=False, app_name=APP_NAME, nav="home",
                               error="This invite link is invalid or already used."), 410
    session["sid"] = sid
    session.permanent = True
    return redirect(url_for("index"))


@app.route("/lesson/<lesson_id>")
def lesson_page(lesson_id):
    from flask import render_template
    sid = current_sid()
    if not sid:
        return redirect(url_for("index"))
    if not LESSON_ID_RE.match(lesson_id or ""):
        return "Not found", 404
    lesson = get_lesson(lesson_id)
    if not lesson:
        return "Not found", 404
    code = code_for_sid(sid)
    done = lesson_progress(code, lesson)
    return render_template("lesson.html", app_name=APP_NAME, nav="home", lesson=lesson,
                           done=sorted(done), stats=get_stats(code))


@app.route("/freetalk")
def freetalk_page():
    from flask import render_template
    sid = current_sid()
    if not sid:
        return redirect(url_for("index"))
    code = code_for_sid(sid)
    con = db()
    try:
        rows = con.execute(
            "SELECT said, reply_en, reply_my FROM freetalk WHERE code=? "
            "ORDER BY id DESC LIMIT 10", (code,)).fetchall()
    finally:
        con.close()
    thread = [{"said": r["said"], "reply_en": r["reply_en"],
               "reply_my": r["reply_my"]} for r in reversed(rows)]
    return render_template("freetalk.html", app_name=APP_NAME, nav="talk", thread=thread,
                           stats=get_stats(code))


@app.route("/admin")
def admin_page():
    from flask import render_template
    return render_template("admin.html", app_name=APP_NAME, admin=True,
                           logged_in=is_admin(), configured=bool(ADMIN_PASSWORD))


# -------------------------------------------------------------------- API ---
@app.route("/api/redeem", methods=["POST"])
def api_redeem():
    data = request.get_json(force=True, silent=True) or {}
    sid = redeem_code(data.get("code"))
    if not sid:
        return jsonify({"ok": False,
                        "error": "Invalid invite code, or it was already used."}), 404
    session["sid"] = sid
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    code = code_for_sid(sid)
    return jsonify({"ok": True, "app": APP_NAME, "code": code,
                    **get_stats(code)})


@app.route("/api/lessons")
def api_lessons():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    code = code_for_sid(sid)
    out = []
    for l in load_lessons():
        done = lesson_progress(code, l)
        out.append({"id": l["id"], "level": l.get("level", ""),
                    "title": l.get("title", ""), "title_my": l.get("title_my", ""),
                    "topic": l.get("topic", ""), "n_phrases": len(l["phrases"]),
                    "done": len(done),
                    "completed": len(done) >= len(l["phrases"])})
    return jsonify({"ok": True, "lessons": out})


@app.route("/api/lesson/<lesson_id>")
def api_lesson(lesson_id):
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    if not LESSON_ID_RE.match(lesson_id or ""):
        return jsonify({"ok": False, "error": "Not found."}), 404
    lesson = get_lesson(lesson_id)
    if not lesson:
        return jsonify({"ok": False, "error": "Not found."}), 404
    code = code_for_sid(sid)
    return jsonify({"ok": True, "lesson": lesson,
                    "done": sorted(lesson_progress(code, lesson))})


def _audio_path(lesson_id, idx):
    d = os.path.join(DATA_DIR, "audio")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{lesson_id}_{idx}.mp3")


@app.route("/api/audio/<lesson_id>/<int:idx>")
def api_audio(lesson_id, idx):
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False}), 401
    if not LESSON_ID_RE.match(lesson_id or ""):
        return jsonify({"ok": False, "error": "Not found."}), 404
    lesson = get_lesson(lesson_id)
    if not lesson or idx < 0 or idx >= len(lesson["phrases"]):
        return jsonify({"ok": False, "error": "Not found."}), 404
    path = _audio_path(lesson_id, idx)
    if not os.path.exists(path):
        if not brain.OPENAI_API_KEY:
            return jsonify({"ok": False,
                            "error": "Voice not configured on server."}), 503
        try:
            mp3 = brain.tts(lesson["phrases"][idx]["en"])
        except Exception as e:
            print("TTS failed:", type(e).__name__)
            return jsonify({"ok": False,
                            "error": "Couldn't generate audio — try again."}), 502
        with open(path, "wb") as f:
            f.write(mp3)
        code = code_for_sid(sid)
        record_cost(code, tts=brain.tts_cost(len(lesson["phrases"][idx]["en"])))
    return send_file(path, mimetype="audio/mpeg")


def _read_audio():
    f = request.files.get("audio")
    if f is None:
        return None, "No audio."
    data = f.read()
    if not data or len(data) > MAX_AUDIO_BYTES:
        return None, "Audio missing or too big (5MB max)."
    return data, None


def _guard_voice(code):
    if not brain.OPENAI_API_KEY:
        return jsonify({"ok": False,
                        "error": "Voice features aren't configured on this server."}), 503
    limited = check_limits(code)
    if limited == "daily":
        return jsonify({"ok": False,
                        "error": f"You've used all {DAILY_LIMIT} voice turns for today — come back tomorrow!"}), 429
    if limited == "cost":
        return jsonify({"ok": False,
                        "error": "You've reached today's usage limit — come back tomorrow!"}), 429
    return None


@app.route("/api/practice", methods=["POST"])
def api_practice():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    err = _guard_voice(code)
    if err:
        return err
    lesson_id = (request.form.get("lesson_id") or "").strip()
    try:
        idx = int(request.form.get("phrase_idx", -1))
    except (TypeError, ValueError):
        idx = -1
    lesson = get_lesson(lesson_id) if LESSON_ID_RE.match(lesson_id or "") else None
    if not lesson or idx < 0 or idx >= len(lesson["phrases"]):
        return jsonify({"ok": False, "error": "Unknown lesson or phrase."}), 400
    audio, aerr = _read_audio()
    if aerr:
        return jsonify({"ok": False, "error": aerr}), 400
    target = lesson["phrases"][idx]["en"]
    phrase = lesson["phrases"][idx]
    try:
        said = brain.transcribe(audio, "practice.webm")
    except Exception as e:
        print("Whisper failed:", type(e).__name__)
        return jsonify({"ok": False,
                        "error": "Couldn't understand the audio — try again."}), 502
    record_cost(code, whisper=brain.whisper_cost(len(audio) / 16000))
    if not said:
        return jsonify({"ok": True, "said": "", "score": 1, "sound_notes": [],
                        "feedback_en": "I couldn't hear anything — check your mic and try again.",
                        "feedback_my": "အသံကိုမကြားရပါ — မိုက်ကိုစစ်ပြီး ထပ်ကြိုးစားကြည့်ပါ။",
                        "tip_en": "Hold the phone a little closer and speak a bit louder.",
                        "tip_my": "ဖုန်းကိုအနည်းငယ်နီးကပ်ထားပြီး အသံကျယ်ကျယ်ပြောကြည့်ပါ။",
                        "xp": 0, "total_xp": get_stats(code)["xp"],
                        "streak": touch_streak(code)})
    try:
        fb, usage = brain.phrase_feedback(
            target, said,
            target_sounds=lesson.get("target_sounds"),
            phrase_focus=phrase.get("focus", ""))
    except Exception as e:
        print("Feedback failed:", type(e).__name__)
        return jsonify({"ok": False,
                        "error": "Couldn't grade that attempt — try again."}), 502
    record_cost(code, in_tok=usage["input_tokens"], out_tok=usage["output_tokens"],
                chat=usage["cost"])
    bump_voice_turn(code)
    score = fb["score"]
    gained = 10 if score >= 3 else 2
    total_xp = add_xp(code, gained)
    streak = touch_streak(code)
    mark_phrase_done(code, lesson_id, idx, score)
    done = lesson_progress(code, lesson)
    return jsonify({"ok": True, "said": fb["said"], "score": score,
                    "sound_notes": fb["sound_notes"],
                    "feedback_en": fb["corrections_en"],
                    "feedback_my": fb["corrections_my"],
                    "tip_en": fb["tip_en"], "tip_my": fb["tip_my"],
                    "xp": gained, "total_xp": total_xp, "streak": streak,
                    "done": sorted(done),
                    "lesson_completed": len(done) >= len(lesson["phrases"])})


@app.route("/api/freetalk", methods=["POST"])
def api_freetalk():
    sid = current_sid()
    if not sid:
        return jsonify({"ok": False, "error": "Not signed in."}), 401
    code = code_for_sid(sid)
    err = _guard_voice(code)
    if err:
        return err
    audio, aerr = _read_audio()
    if aerr:
        return jsonify({"ok": False, "error": aerr}), 400
    try:
        said = brain.transcribe(audio, "freetalk.webm")
    except Exception as e:
        print("Whisper failed:", type(e).__name__)
        return jsonify({"ok": False,
                        "error": "Couldn't understand the audio — try again."}), 502
    record_cost(code, whisper=brain.whisper_cost(len(audio) / 16000))
    if not said:
        return jsonify({"ok": True, "said": "",
                        "reply_en": "Sorry, I didn't catch that — could you say it again?",
                        "reply_my": "စိတ်မကောင်းပါဘူး၊ မကြားလိုက်ရဘူး — ထပ်ပြောပေးနိုင်မလား?"})
    con = db()
    try:
        rows = con.execute(
            "SELECT said, reply_en FROM freetalk WHERE code=? ORDER BY id DESC LIMIT 8",
            (code,)).fetchall()
        history = [(r["said"], r["reply_en"]) for r in reversed(rows)]
    finally:
        con.close()
    try:
        rep, usage = brain.freetalk_reply(history, said)
    except Exception as e:
        print("Free talk failed:", type(e).__name__)
        return jsonify({"ok": False,
                        "error": "The tutor didn't respond — try again."}), 502
    record_cost(code, in_tok=usage["input_tokens"], out_tok=usage["output_tokens"],
                chat=usage["cost"])
    bump_voice_turn(code)
    con = db()
    try:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        con.execute("INSERT INTO freetalk(code, created, said, reply_en, reply_my)"
                    " VALUES(?,?,?,?,?)",
                    (code, now, said, rep["reply_en"], rep["reply_my"]))
        con.execute("DELETE FROM freetalk WHERE code=? AND id NOT IN "
                    "(SELECT id FROM freetalk WHERE code=? ORDER BY id DESC LIMIT 30)",
                    (code, code))
        con.commit()
    finally:
        con.close()
    add_xp(code, 5)
    streak = touch_streak(code)
    return jsonify({"ok": True, "said": said, "reply_en": rep["reply_en"],
                    "reply_my": rep["reply_my"],
                    "pronunciation": rep["pronunciation"],
                    "streak": streak,
                    "total_xp": get_stats(code)["xp"]})


# ------------------------------------------------------------------ admin ---
def is_admin():
    return session.get("admin") is True and ADMIN_PASSWORD


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(force=True, silent=True) or {}
    if ADMIN_PASSWORD and data.get("password") == ADMIN_PASSWORD:
        session["admin"] = True
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Wrong password."}), 403


@app.route("/api/admin/data")
def api_admin_data():
    if not is_admin():
        return jsonify({"ok": False}), 403
    con = db()
    try:
        codes = []
        for r in con.execute("SELECT * FROM codes ORDER BY created DESC").fetchall():
            u = con.execute(
                "SELECT COALESCE(SUM(whisper_cost+tts_cost+chat_cost),0) AS c, "
                "COALESCE(SUM(in_tok),0) AS i, COALESCE(SUM(out_tok),0) AS o "
                "FROM usage WHERE code=?", (r["code"],)).fetchone()
            p = con.execute("SELECT COUNT(*) AS n FROM progress WHERE code=?",
                            (r["code"],)).fetchone()
            s = con.execute("SELECT streak FROM streaks WHERE code=?",
                            (r["code"],)).fetchone()
            codes.append({"code": r["code"], "link": invite_link(r["code"]),
                          "used": bool(r["used_by"]), "label": r["label"] or "",
                          "created": r["created"] or "",
                          "today": r["day_count"] if r["day"] == today() else 0,
                          "phrases_done": p["n"], "streak": s["streak"] if s else 0,
                          "cost": round(u["c"], 4),
                          "in_tok": u["i"], "out_tok": u["o"]})
        t = con.execute(
            "SELECT COALESCE(SUM(whisper_cost+tts_cost+chat_cost),0) AS c, "
            "COALESCE(SUM(in_tok),0) AS i, COALESCE(SUM(out_tok),0) AS o FROM usage"
        ).fetchone()
        lessons = [{"id": l["id"], "level": l.get("level", ""),
                    "title": l.get("title", ""), "n_phrases": len(l["phrases"]),
                    "overridden": bool(con.execute(
                        "SELECT 1 FROM lesson_overrides WHERE id=?",
                        (l["id"],)).fetchone())}
                   for l in load_lessons()]
    finally:
        con.close()
    return jsonify({"ok": True, "codes": codes,
                    "totals": {"cost": round(t["c"], 4), "in": t["i"], "out": t["o"],
                               "n_codes": len(codes)},
                    "lessons": lessons, "app": APP_NAME,
                    "daily_limit": DAILY_LIMIT,
                    "daily_cost_limit": DAILY_COST_LIMIT})


@app.route("/api/admin/newcodes", methods=["POST"])
def api_admin_newcodes():
    if not is_admin():
        return jsonify({"ok": False}), 403
    data = request.get_json(force=True, silent=True) or {}
    try:
        n = int(data.get("n", 10))
    except (TypeError, ValueError):
        n = 10
    n = max(1, min(n, 50))
    label = (data.get("label") or "")[:50]
    now = datetime.datetime.now().isoformat(timespec="seconds")
    con = db()
    try:
        fresh = []
        for _ in range(n):
            c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
            while con.execute("SELECT 1 FROM codes WHERE code=?", (c,)).fetchone():
                c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
            con.execute("INSERT INTO codes(code, created, label) VALUES(?,?,?)",
                        (c, now, label))
            fresh.append({"code": c, "link": invite_link(c)})
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True, "codes": fresh})


@app.route("/api/admin/revoke", methods=["POST"])
def api_admin_revoke():
    if not is_admin():
        return jsonify({"ok": False}), 403
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    con = db()
    try:
        if not con.execute("SELECT 1 FROM codes WHERE code=?", (code,)).fetchone():
            return jsonify({"ok": False, "error": "Code not found."}), 404
        con.execute("DELETE FROM sessions WHERE code=?", (code,))
        con.execute("DELETE FROM codes WHERE code=?", (code,))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@app.route("/api/admin/lesson/<lesson_id>")
def api_admin_lesson(lesson_id):
    if not is_admin():
        return jsonify({"ok": False}), 403
    lesson = get_lesson(lesson_id)
    if not lesson:
        return jsonify({"ok": False, "error": "Not found."}), 404
    return jsonify({"ok": True, "lesson": lesson})


@app.route("/api/admin/lesson", methods=["POST"])
def api_admin_lesson_save():
    """Save an admin-edited lesson (stored as an override in the DB)."""
    if not is_admin():
        return jsonify({"ok": False}), 403
    data = request.get_json(force=True, silent=True) or {}
    lesson = data.get("lesson") or {}
    lid = lesson.get("id", "")
    if not LESSON_ID_RE.match(lid):
        return jsonify({"ok": False, "error": "Bad lesson id."}), 400
    phrases = lesson.get("phrases") or []
    if not (1 <= len(phrases) <= 20) or not all(
            p.get("en") and p.get("my") for p in phrases):
        return jsonify({"ok": False,
                        "error": "Give 1–20 phrases, each with English and Myanmar."}), 400
    clean = {"id": lid, "level": (lesson.get("level") or "A1")[:3],
             "title": (lesson.get("title") or "")[:80],
             "title_my": (lesson.get("title_my") or "")[:80],
             "topic": (lesson.get("topic") or "")[:40],
             "phrases": [{"en": p["en"][:200], "my": p["my"][:200]}
                         for p in phrases]}
    con = db()
    try:
        con.execute("INSERT INTO lesson_overrides(id, data) VALUES(?,?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                    (lid, json.dumps(clean, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@app.route("/api/admin/lesson_reset", methods=["POST"])
def api_admin_lesson_reset():
    if not is_admin():
        return jsonify({"ok": False}), 403
    data = request.get_json(force=True, silent=True) or {}
    con = db()
    try:
        con.execute("DELETE FROM lesson_overrides WHERE id=?",
                    ((data.get("id") or "").strip(),))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not brain.OPENAI_API_KEY:
        print("Set the OPENAI_API_KEY env var (voice features will 503 without it).")
    app.run(host="0.0.0.0", port=PORT)
