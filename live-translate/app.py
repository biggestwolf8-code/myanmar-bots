"""Live Translate - real-time speech translation for classes.

A teacher (or guest speaker) talks; students open this page on their phones
and hear/read the translation a few seconds later.

Pipeline per ~4s audio chunk:
  OpenAI Whisper transcription -> gpt-4o-mini translation -> JSON back to the
  page, which speaks it aloud with the phone's own speech synthesis and shows
  it in large text. The page also accumulates a downloadable transcript.

Env:
  OPENAI_API_KEY  (required - same key the other apps use, set on Railway)
  ACCESS_CODE     (shared class code; if unset the app is open - dev only)
  PORT            (Railway provides)
"""
import os

import requests
from flask import Flask, jsonify, render_template, request

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")
OPENAI_BASE = "https://api.openai.com/v1"

LANG_NAME = {"en": "English", "my": "Myanmar (Burmese)", "th": "Thai"}

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(ok=True, service="live-translate",
                   key_configured=bool(OPENAI_API_KEY))


@app.get("/")
def index():
    return render_template("index.html")


def _code_ok():
    if not ACCESS_CODE:
        return True
    return (request.form.get("code") == ACCESS_CODE
            or request.headers.get("X-Access-Code") == ACCESS_CODE)


def _transcribe(audio_bytes, filename, src):
    files = {"file": (filename, audio_bytes)}
    data = {"model": "whisper-1", "language": src}
    r = requests.post(f"{OPENAI_BASE}/audio/transcriptions",
                      headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                      files=files, data=data, timeout=60)
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


def _translate(text, src, tgt):
    system = (
        "You are a live classroom interpreter. Translate the speaker's words "
        f"from {LANG_NAME[src]} to {LANG_NAME[tgt]}. Output ONLY the "
        "translation, in natural spoken style, keeping names and numbers "
        "accurate. The setting is an English-teaching class for Myanmar "
        "students, so translate teaching terms precisely: grammar = သဒ္ဒါ "
        "(never သင်္ချာ/mathematics), vocabulary = ဝေါဟာရ, pronunciation = "
        "အသံထွက်, sentence = ဝါကျ. If the input is not real speech (noise, "
        "music, a fragment with no meaning), output nothing at all."
    )
    r = requests.post(
        f"{OPENAI_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": "gpt-4o-mini", "temperature": 0.2,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": text}]},
        timeout=60)
    r.raise_for_status()
    return (r.json()["choices"][0]["message"]["content"] or "").strip()


@app.post("/api/chunk")
def chunk():
    if not _code_ok():
        return jsonify(ok=False, error="Invalid access code."), 403
    if not OPENAI_API_KEY:
        return jsonify(ok=False,
                       error="OPENAI_API_KEY not configured on server."), 503
    src = (request.form.get("src") or "en").strip()
    tgt = (request.form.get("tgt") or "my").strip()
    if src not in LANG_NAME or tgt not in LANG_NAME or src == tgt:
        return jsonify(ok=False, error="Bad language pair."), 400
    f = request.files.get("audio")
    if f is None:
        return jsonify(ok=False, error="No audio."), 400
    audio = f.read()
    if len(audio) < 1000:
        return jsonify(ok=True, original="", translation="")
    try:
        original = _transcribe(audio, f.filename or "chunk.webm", src)
        if not original:
            return jsonify(ok=True, original="", translation="")
        translation = _translate(original, src, tgt)
    except requests.RequestException as e:
        return jsonify(ok=False, error=f"Upstream error: {e}"), 502
    return jsonify(ok=True, original=original, translation=translation)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
