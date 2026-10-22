"""OpenAI backend for MasterClass Articulation.

Pipeline (same approach as live-translate):
  browser-recorded audio -> Whisper transcription -> gpt-4o-mini
  (phrase feedback / free-talk tutor) -> audio playback. Tutor replies are
  spoken with the phone's own speech synthesis; phrase model audio is
  pre-generated once via OpenAI TTS and cached.

Never import this module's key anywhere else; OPENAI_API_KEY is read here
only and never printed.
"""
import json
import os

import requests

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE = "https://api.openai.com/v1"

# gpt-4o-mini pricing ($ per 1M tokens); override via env if the model changes
MODEL = os.environ.get("MODEL", "gpt-4o-mini")
INPUT_RATE = float(os.environ.get("INPUT_RATE", "0.15"))
OUTPUT_RATE = float(os.environ.get("OUTPUT_RATE", "0.60"))
WHISPER_RATE_PER_MIN = float(os.environ.get("WHISPER_RATE_PER_MIN", "0.006"))
TTS_MODEL = os.environ.get("TTS_MODEL", "tts-1")
TTS_VOICE = os.environ.get("TTS_VOICE", "nova")
TTS_RATE_PER_1M_CHARS = float(os.environ.get("TTS_RATE_PER_1M_CHARS", "15.0"))


def _headers(json_body=True):
    h = {"Authorization": "Bearer " + OPENAI_API_KEY}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def cost_for(input_tokens, output_tokens):
    return input_tokens / 1e6 * INPUT_RATE + output_tokens / 1e6 * OUTPUT_RATE


def whisper_cost(audio_seconds):
    return max(audio_seconds, 1) / 60.0 * WHISPER_RATE_PER_MIN


def tts_cost(chars):
    return chars / 1e6 * TTS_RATE_PER_1M_CHARS


def transcribe(audio_bytes, filename="clip.webm"):
    """Whisper transcription of browser-recorded audio. Returns text."""
    files = {"file": (filename, audio_bytes, "audio/webm")}
    data = {"model": "whisper-1", "language": "en"}
    r = requests.post(f"{OPENAI_BASE}/audio/transcriptions",
                      headers=_headers(json_body=False),
                      files=files, data=data, timeout=60)
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


FEEDBACK_SYSTEM = (
    "You are an expert English ARTICULATION coach for Myanmar learners using "
    "the 'MasterClass Articulation' app. The student tried to say a target "
    "English phrase out loud; their speech was transcribed by Whisper (the "
    "transcription may contain small errors — be generous, not punishing, and "
    "infer the most likely intended sounds). Your job is to identify WHICH "
    "SOUNDS were mispronounced — not just which words were wrong. Myanmar "
    "speakers commonly struggle with: th /θ/ /ð/ sounding like t/d, v vs w, "
    "z vs s, r vs l, dropped final consonants, consonant clusters, word "
    "stress, and sentence intonation. Listen for exactly these. "
    "Respond with ONLY a JSON object, no other text, with these keys:\n"
    '{"said": "<what the student most likely said, cleaned up into natural English>", '
    '"score": <1-5 integer>, '
    '"sound_notes": [{"sound": "<the target sound, e.g. \'th /θ/ as in think\'>", '
    '"heard_as": "<what it sounded like, e.g. \'t\'>", '
    '"fix_en": "<concrete mouth/tongue/lip placement fix in SIMPLE English, under 30 words>", '
    '"fix_my": "<the same fix in Myanmar, under 30 words>"}], '
    '"corrections_en": "<any other short corrections in SIMPLE English, under 30 words>", '
    '"corrections_my": "<the same in Myanmar, under 30 words>", '
    '"tip_en": "<ONE extra articulation tip in simple English, under 25 words>", '
    '"tip_my": "<the same tip in Myanmar, under 25 words>"} '
    "Rules: sound_notes lists the 1–3 clearest SOUND problems, ordered by "
    "importance; each fix_en/fix_my must describe PHYSICAL placement "
    "(tongue, teeth, lips, airflow, voicing — e.g. \"rest your tongue tip "
    "lightly BETWEEN your teeth and blow air out; don't bite down\"). Empty "
    "sound_notes only if articulation was genuinely good. "
    "Score is weighted toward clarity of the lesson's target sounds: "
    "5 = target sounds clear and natural; 4 = target sounds good, tiny slip; "
    "3 = understandable but target sounds need work; 2 = target sounds "
    "wrong or hard to understand; 1 = wrong phrase, silence, or not speech. "
    "If the transcription is empty or clearly not speech, score 1, empty "
    "sound_notes, and say kindly in both languages that you could not hear "
    "them and to try again. Be ENCOURAGING always: learners improve by "
    "repeating — end corrections_en with one short motivating phrase."
)


def phrase_feedback(target_en, said_text, target_sounds=None, phrase_focus=""):
    """Grade one phrase attempt, articulation-first.
    Returns (feedback_dict, usage_dict)."""
    hint = ""
    if target_sounds:
        hint += f"\nLesson target sounds: {', '.join(target_sounds)}"
    if phrase_focus:
        hint += f"\nThis phrase focuses on: {phrase_focus}"
    user = (f'Target phrase: "{target_en}"{hint}\n'
            f'Whisper transcription of the student: "{said_text}"')
    r = requests.post(
        f"{OPENAI_BASE}/chat/completions",
        headers=_headers(),
        json={"model": MODEL, "temperature": 0.3,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": FEEDBACK_SYSTEM},
                           {"role": "user", "content": user}]},
        timeout=60)
    r.raise_for_status()
    out = r.json()
    raw = (out.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    fb = json.loads(raw)
    fb["score"] = max(1, min(5, int(fb.get("score", 1))))
    for k in ("said", "corrections_en", "corrections_my", "tip_en", "tip_my"):
        fb[k] = str(fb.get(k, "")).strip()
    notes = []
    for n in (fb.get("sound_notes") or [])[:3]:
        if isinstance(n, dict) and n.get("sound"):
            notes.append({k: str(n.get(k, "")).strip()
                          for k in ("sound", "heard_as", "fix_en", "fix_my")})
    fb["sound_notes"] = notes
    u = out.get("usage", {})
    usage = {"input_tokens": u.get("prompt_tokens", 0),
             "output_tokens": u.get("completion_tokens", 0),
             "cost": cost_for(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))}
    return fb, usage


FREETALK_SYSTEM = (
    "You are a friendly AI English tutor inside the 'MasterClass Articulation' "
    "app, chatting by voice with a Myanmar learner. This app's core value is "
    "ARTICULATION — clear, correct production of English sounds. Speak "
    "SIMPLY: short sentences, everyday words, one idea at a time. Keep the "
    "conversation going with a question when natural. Respond with ONLY a "
    "JSON object, no other text:\n"
    '{"reply_en": "<your reply in English, 1-3 short sentences>", '
    '"reply_my": "<Myanmar translation of your reply, plus a brief Myanmar '
    'explanation of any difficult English word you used>", '
    '"pronunciation": [{"issue_en": "<the clearest pronunciation issue in the '
    "student's last turn, in simple English, e.g. 'your th sounded like t'>\", "
    '"fix_en": "<concrete mouth/tongue/lip fix, under 25 words>", '
    '"fix_my": "<the same fix in Myanmar, under 25 words>"}]} '
    "pronunciation lists the 1–2 clearest SOUND issues from the student's last "
    "utterance only (empty list if their articulation was fine — don't invent "
    "issues). Myanmar speakers commonly struggle with th/v-w/z-s/r-l, final "
    "consonants, clusters, and stress — listen for these. "
    "If the student writes or asks in Myanmar, answer in Myanmar in reply_my "
    "(still give the English version in reply_en). If they ask what an English "
    "word means, explain it clearly in Myanmar. Never break character: if asked "
    "what you are, say you are their AI English tutor in MasterClass "
    "Articulation, powered by OpenAI."
)


def freetalk_reply(history, new_said):
    """history: list of (said, reply_en) for past turns; new_said is the
    latest student utterance. Returns (reply_dict, usage_dict)."""
    msgs = [{"role": "system", "content": FREETALK_SYSTEM}]
    for said, reply_en in history[-8:]:
        msgs.append({"role": "user", "content": said})
        msgs.append({"role": "assistant", "content": reply_en})
    msgs.append({"role": "user", "content": new_said})
    r = requests.post(
        f"{OPENAI_BASE}/chat/completions",
        headers=_headers(),
        json={"model": MODEL, "temperature": 0.7,
              "response_format": {"type": "json_object"},
              "messages": msgs},
        timeout=60)
    r.raise_for_status()
    out = r.json()
    raw = (out.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    rep = json.loads(raw)
    rep["reply_en"] = str(rep.get("reply_en", "")).strip()
    rep["reply_my"] = str(rep.get("reply_my", "")).strip()
    pron = []
    for n in (rep.get("pronunciation") or [])[:2]:
        if isinstance(n, dict) and n.get("issue_en"):
            pron.append({k: str(n.get(k, "")).strip()
                         for k in ("issue_en", "fix_en", "fix_my")})
    rep["pronunciation"] = pron
    u = out.get("usage", {})
    usage = {"input_tokens": u.get("prompt_tokens", 0),
             "output_tokens": u.get("completion_tokens", 0),
             "cost": cost_for(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))}
    return rep, usage


def tts(text):
    """OpenAI TTS for phrase model audio. Returns MP3 bytes."""
    r = requests.post(
        f"{OPENAI_BASE}/audio/speech",
        headers=_headers(),
        json={"model": TTS_MODEL, "voice": TTS_VOICE, "input": text},
        timeout=60)
    r.raise_for_status()
    return r.content
