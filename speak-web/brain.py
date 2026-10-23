"""OpenAI backend for MasterClass Articulation.

Pipeline (same approach as live-translate):
  browser-recorded audio -> Whisper transcription -> gpt-4o-mini
  (expression feedback / conversation tutor) -> audio playback.

ARTICULATION here means being ARTICULATE in conversation: speaking
naturally without hesitating, never being lost for words, expressing
yourself with interesting phrases. It is NOT pronunciation/phonetics —
never coach mouth/tongue placement or individual sounds.

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
    "You are an expert English FLUENCY coach for Myanmar learners using the "
    "'MasterClass Articulation' app. ARTICULATION here means being ARTICULATE: "
    "speaking naturally without hesitating, never being lost for words, "
    "expressing yourself with interesting phrases. It is NOT about "
    "pronunciation of sounds — NEVER give mouth/tongue/lip placement tips. "
    "The student practiced one expression item (a conversation opener, a "
    "natural phrase, or a rescue phrase) by saying it out loud; Whisper "
    "transcribed them (transcription may contain small errors — be generous, "
    "infer the most likely intended meaning). "
    "Respond with ONLY a JSON object, no other text, with these keys:\n"
    '{"said": "<what they most likely said, cleaned up into natural English>", '
    '"score": <1-5 integer>, '
    '"flow_en": "<1-2 sentences in SIMPLE English: did they sound natural, confident, interesting? If they hesitated or sounded flat, say so kindly>", '
    '"flow_my": "<the same in Myanmar>", '
    '"alternatives": [{"instead_of": "<their flat/boring wording, or empty>", '
    '"try_this": "<a smarter, more interesting native-speaker way to say the same thing>", '
    '"try_this_my": "<Myanmar translation of try_this>"}], '
    '"tip_en": "<ONE practical fluency tip in simple English, under 25 words>", '
    '"tip_my": "<the same tip in Myanmar, under 25 words>"} '
    "Rules: score 5 = natural, confident, interesting; 4 = good, tiny stiffness; "
    "3 = understandable but flat or textbook-sounding; 2 = hesitant, hard to follow, "
    "or froze; 1 = silence, not speech, or wrong item. alternatives: 1-2 upgrades that "
    "keep their meaning but sound more native and interesting — suggest livelier "
    "wording, not grammar drills. Skip alternatives only if what they said was "
    "already excellent (then praise it in flow_en). Mention pronunciation ONLY if "
    "something was genuinely unintelligible. If the transcription is empty or clearly "
    "not speech: score 1, empty alternatives, and say kindly in both languages that "
    "you could not hear them and to try again. Be ENCOURAGING always: end tip_en "
    "with one short motivating push."
)


def expression_feedback(item_en, item_my, section, said_text):
    """Grade one expression attempt (opener/phrase/rescue), fluency-first.
    Returns (feedback_dict, usage_dict)."""
    user = (f'Practice item ({section}): "{item_en}"\n'
            f'Myanmar meaning: "{item_my}"\n'
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
    for k in ("said", "flow_en", "flow_my", "tip_en", "tip_my"):
        fb[k] = str(fb.get(k, "")).strip()
    alts = []
    for a in (fb.get("alternatives") or [])[:2]:
        if isinstance(a, dict) and a.get("try_this"):
            alts.append({k: str(a.get(k, "")).strip()
                         for k in ("instead_of", "try_this", "try_this_my")})
    fb["alternatives"] = alts
    u = out.get("usage", {})
    usage = {"input_tokens": u.get("prompt_tokens", 0),
             "output_tokens": u.get("completion_tokens", 0),
             "cost": cost_for(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))}
    return fb, usage


CONVERSE_BASE = (
    "You are an AI English conversation partner inside the 'MasterClass "
    "Articulation' app, talking by voice with a Myanmar learner. The app's "
    "whole point is ARTICULATION = being ARTICULATE: speaking naturally "
    "without hesitating, never being lost for words, expressing yourself with "
    "interesting phrases. NEVER coach pronunciation, mouth/tongue placement, "
    "or individual sounds. "
    "Speak like a real native speaker would: short, natural sentences — never "
    "textbook English. Keep every reply to 1-3 sentences and always end with "
    "something that keeps the conversation going (a question, a reaction, a "
    "tease). "
    "After your in-character reply, add coaching as JSON. Respond with ONLY a "
    "JSON object, no other text:\n"
    '{"reply_en": "<your reply, 1-3 short natural sentences>", '
    '"reply_my": "<Myanmar translation of your reply, plus a brief Myanmar '
    'note on any difficult English word you used>", '
    '"coaching": {"flow": <1-5: how well they kept the conversation flowing>, '
    '"flow_note_en": "<one short note in simple English>", '
    '"flow_note_my": "<the same in Myanmar>", '
    '"freeze": <true if their last message shows freeze signals: fillers '
    '(uh/um), "I don\'t know", very short answers to open questions, '
    'repeating themselves, or empty/garbled input — else false>, '
    '"freeze_note_en": "<what happened, in simple English; empty if no freeze>", '
    '"freeze_note_my": "<the same in Myanmar>", '
    '"recovered": <true if they froze but got the conversation moving again>, '
    '"better_en": "<ONE smarter, more interesting native-speaker alternative '
    'to something they actually said; empty if they were already great>", '
    '"better_my": "<Myanmar translation of better_en>", '
    '"rescue_en": "<ONE rescue phrase they could have used when stuck; empty '
    'if no freeze>" , "rescue_my": "<Myanmar translation of rescue_en>"}} '
    "Rules: praise rescue phrases warmly when the learner uses one. Suggest "
    "livelier wording, never grammar drills. If the learner writes in Myanmar, "
    "answer in Myanmar in reply_my (reply_en stays English). If asked what you "
    "are, say you are their AI English tutor in MasterClass Articulation, "
    "powered by OpenAI."
)

ROLEPLAY_EXTRA = (
    "\nROLEPLAY MODE: stay in character as: {tutor_en}\n"
    "Scenario: {scene_en}\n"
    "The learner's goal: {goal_en}\n"
    "Never break character in reply_en. In reply_my you may add one short "
    "Myanmar note about the roleplay context."
)

FREEZE_EXTRA = (
    "\nFREEZE-DRILL MODE: this is a drill, and your secret mission is to "
    "DELIBERATELY create stuck moments that train the learner to recover. "
    "Cycle through these pressure moves across turns, one per turn: "
    "(1) an unexpected personal question, "
    "(2) a sudden topic change, "
    "(3) an awkward silence — reply with exactly '...' and nothing else, "
    "(4) playful disagreement with what they just said, "
    "(5) two rapid questions in a row. "
    "Never announce the drill or explain what you are doing — stay natural. "
    "Between pressure moves, be a normal warm conversation partner. "
    "Set freeze=true in coaching whenever their message shows freeze signals. "
    "Always offer a rescue phrase in rescue_en/rescue_my when they freeze."
)


def converse_reply(mode, scenario, history, new_said):
    """Voice conversation turn.

    mode: 'free' | 'roleplay' | 'freeze'.
    scenario: dict with tutor_en/scene_en/goal_en (roleplay/freeze only).
    history: list of (said, reply_en) for past turns.
    Returns (reply_dict, usage_dict).
    """
    system = CONVERSE_BASE
    if mode == "roleplay":
        system += ROLEPLAY_EXTRA.format(
            tutor_en=scenario.get("tutor_en", "a friendly conversation partner"),
            scene_en=scenario.get("scene_en", ""),
            goal_en=scenario.get("goal_en", ""))
    elif mode == "freeze":
        system += ROLEPLAY_EXTRA.format(
            tutor_en=scenario.get("tutor_en", "a friendly conversation partner"),
            scene_en=scenario.get("scene_en", ""),
            goal_en=scenario.get("goal_en", "")) + FREEZE_EXTRA
    msgs = [{"role": "system", "content": system}]
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
    c = rep.get("coaching") or {}
    coaching = {
        "flow": max(1, min(5, int(c.get("flow", 3) or 3))),
        "flow_note_en": str(c.get("flow_note_en", "")).strip(),
        "flow_note_my": str(c.get("flow_note_my", "")).strip(),
        "freeze": bool(c.get("freeze", False)),
        "freeze_note_en": str(c.get("freeze_note_en", "")).strip(),
        "freeze_note_my": str(c.get("freeze_note_my", "")).strip(),
        "recovered": bool(c.get("recovered", False)),
        "better_en": str(c.get("better_en", "")).strip(),
        "better_my": str(c.get("better_my", "")).strip(),
        "rescue_en": str(c.get("rescue_en", "")).strip(),
        "rescue_my": str(c.get("rescue_my", "")).strip(),
    }
    rep["coaching"] = coaching
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


# ------------------------------------------------------- practice drills ---
DRILL_SYSTEM = (
    "You are the content engine for the 'MasterClass Articulation' app, which "
    "teaches Myanmar learners to be ARTICULATE in English conversation: "
    "speaking naturally without hesitating, never lost for words, using "
    "interesting phrases instead of boring ones. It is NOT about "
    "pronunciation — never mention mouth/tongue/sounds. "
    "You generate items for a 5-round practice drill tied to one situation "
    "lesson. Respond with ONLY a JSON object, no other text."
)

DRILL_UPGRADE_SPEC = (
    'MODE: "upgrade" (Boring -> Brilliant). Write exactly 5 dull, plain, '
    'flat English phrases that a shy Myanmar learner would ACTUALLY say by '
    "default in this situation — the boring versions they need to upgrade "
    "(e.g. 'This coffee is good.', 'Nice to meet you.', 'I like music.'). "
    "Ground each one in the lesson's situation/topic. IMPORTANT: do NOT copy "
    "or rephrase the lesson's openers/phrases/rescue items listed below — "
    "those are the GOOD versions; write the PLAIN versions learners default "
    "to. Each item also needs a natural Myanmar translation.\n"
    'JSON: {"items": [{"boring_en": "<plain English phrase>", '
    '"boring_my": "<Myanmar translation>"}]} (exactly 5 items)'
)

DRILL_VARIATIONS_SPEC = (
    'MODE: "variations" (Say it another way). From the lesson\'s '
    "openers/phrases/rescue items below, pick 5 diverse items and write 3 "
    "FRESH alternative ways to say each one — different wording from the "
    "lesson, natural native-speaker English, same meaning. The alternatives "
    "must sound different from each other (not tiny word swaps). Each item "
    "and each variant needs a natural Myanmar translation.\n"
    'JSON: {"items": [{"base_en": "<lesson item English>", '
    '"base_my": "<its Myanmar translation>", "section": "<openers|phrases|'
    'rescue>", "variants": [{"en": "<fresh alternative 1>", "my": "<Myanmar>"}, '
    '{"en": "<fresh alternative 2>", "my": "<Myanmar>"}, '
    '{"en": "<fresh alternative 3>", "my": "<Myanmar>"}]}]} (exactly 5 items)'
)


def drill_items(lesson, mode):
    """Generate 5 drill items for a lesson. One LLM call per session start.

    mode="upgrade" -> 5 x {boring_en, boring_my}: dull default phrases.
    mode="variations" -> 5 x {base_en, base_my, section,
        variants: [{en, my} x 3]}: fresh alternatives to lesson items.
    Returns (items, usage_dict).
    """
    if mode == "upgrade":
        spec = DRILL_UPGRADE_SPEC
    elif mode == "variations":
        spec = DRILL_VARIATIONS_SPEC
    else:
        raise ValueError("bad drill mode")
    lesson_items_text = []
    for section in ("openers", "phrases", "rescue"):
        for p in lesson.get(section) or []:
            if p.get("en"):
                lesson_items_text.append(f'- [{section}] "{p["en"]}" / {p.get("my", "")}')
    user = (f'Lesson: "{lesson.get("title", "")}" (level {lesson.get("level", "")}, '
            f'topic: {lesson.get("topic", "")})\n'
            f'Situation: {lesson.get("situation_en", "")}\n'
            f"Lesson's good openers/phrases/rescue items:\n" +
            "\n".join(lesson_items_text) + "\n\n" + spec)
    r = requests.post(
        f"{OPENAI_BASE}/chat/completions",
        headers=_headers(),
        json={"model": MODEL, "temperature": 0.8,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": DRILL_SYSTEM},
                           {"role": "user", "content": user}]},
        timeout=60)
    r.raise_for_status()
    out = r.json()
    raw = (out.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    data = json.loads(raw)
    items = []
    for it in (data.get("items") or [])[:5]:
        if not isinstance(it, dict):
            continue
        if mode == "upgrade":
            boring_en = str(it.get("boring_en", "")).strip()
            boring_my = str(it.get("boring_my", "")).strip()
            if boring_en:
                items.append({"boring_en": boring_en, "boring_my": boring_my})
        else:
            base_en = str(it.get("base_en", "")).strip()
            base_my = str(it.get("base_my", "")).strip()
            section = str(it.get("section", "phrases")).strip()
            if section not in ("openers", "phrases", "rescue"):
                section = "phrases"
            variants = []
            for v in (it.get("variants") or [])[:3]:
                if isinstance(v, dict) and str(v.get("en", "")).strip():
                    variants.append({"en": str(v["en"]).strip(),
                                     "my": str(v.get("my", "")).strip()})
            if base_en and variants:
                items.append({"base_en": base_en, "base_my": base_my,
                              "section": section, "variants": variants})
    if not items:
        raise ValueError("drill generation returned no usable items")
    u = out.get("usage", {})
    usage = {"input_tokens": u.get("prompt_tokens", 0),
             "output_tokens": u.get("completion_tokens", 0),
             "cost": cost_for(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))}
    return items, usage


UPGRADE_FEEDBACK_SYSTEM = (
    "You are an expert English FLUENCY coach for Myanmar learners using the "
    "'MasterClass Articulation' app. ARTICULATION here means being ARTICULATE: "
    "speaking naturally without hesitating, never being lost for words, "
    "expressing yourself with interesting phrases. It is NOT about "
    "pronunciation of sounds — NEVER give mouth/tongue/lip placement tips. "
    "This is the 'Boring -> Brilliant' drill: the student saw a dull, plain "
    "phrase and had to say a MORE INTERESTING, vivid, natural version of it "
    "out loud. Whisper transcribed them (transcription may contain small "
    "errors — be generous, infer the most likely intended meaning). "
    "Grade the UPGRADE: is what they said livelier, more specific, more "
    "natural, more interesting than the boring original? "
    "Respond with ONLY a JSON object, no other text, with these keys:\n"
    '{"said": "<what they most likely said, cleaned up into natural English>", '
    '"score": <1-5 integer>, '
    '"flow_en": "<1-2 sentences in SIMPLE English: did their version sound more interesting and natural than the boring original? Be kind and specific>", '
    '"flow_my": "<the same in Myanmar>", '
    '"brilliant_en": "<ONE model brilliant version — the vivid, natural, native-speaker way to say it>", '
    '"brilliant_my": "<Myanmar translation of brilliant_en>", '
    '"tip_en": "<ONE practical tip in simple English, under 25 words, about making phrases more interesting (add a detail, a feeling, a specific word)>", '
    '"tip_my": "<the same tip in Myanmar, under 25 words>"} '
    "Rules: score 5 = clearly livelier, more specific and natural than the "
    "boring phrase; 4 = better, with a nice touch; 3 = slightly better or just "
    "as flat; 2 = barely changed, hesitant, or hard to follow; 1 = silence, "
    "not speech, or off-topic. Suggest livelier wording, never grammar "
    "drills. If their version is already great, praise it warmly in flow_en "
    "and make brilliant_en an equally-good alternative. Mention pronunciation "
    "ONLY if something was genuinely unintelligible. If the transcription is "
    "empty or clearly not speech: score 1, empty brilliant_en, and say kindly "
    "in both languages that you could not hear them and to try again. Be "
    "ENCOURAGING always: end tip_en with one short motivating push."
)


def upgrade_feedback(boring_en, boring_my, said_text, topic):
    """Grade one Boring->Brilliant upgrade attempt, fluency-first.

    Returns (feedback_dict, usage_dict)."""
    user = (f'Situation topic: "{topic}"\n'
            f'The boring phrase they had to upgrade: "{boring_en}"\n'
            f'Myanmar meaning: "{boring_my}"\n'
            f'Whisper transcription of their more interesting version: "{said_text}"')
    r = requests.post(
        f"{OPENAI_BASE}/chat/completions",
        headers=_headers(),
        json={"model": MODEL, "temperature": 0.5,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": UPGRADE_FEEDBACK_SYSTEM},
                           {"role": "user", "content": user}]},
        timeout=60)
    r.raise_for_status()
    out = r.json()
    raw = (out.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    fb = json.loads(raw)
    fb["score"] = max(1, min(5, int(fb.get("score", 1))))
    for k in ("said", "flow_en", "flow_my", "brilliant_en", "brilliant_my",
              "tip_en", "tip_my"):
        fb[k] = str(fb.get(k, "")).strip()
    u = out.get("usage", {})
    usage = {"input_tokens": u.get("prompt_tokens", 0),
             "output_tokens": u.get("completion_tokens", 0),
             "cost": cost_for(u.get("prompt_tokens", 0), u.get("completion_tokens", 0))}
    return fb, usage
