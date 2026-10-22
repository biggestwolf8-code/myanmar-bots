#!/usr/bin/env python3
"""
MasterClass Articulation — lecturer voiceover builder for demo videos.

1. Computes exact per-segment timings from make_demos.py builders.
2. Builds ENGLISH-ONLY lecturer narration scripts per segment
   (Arkar 2026-10-22: no Myanmar voice — English lecturer only).
3. Synthesizes via the PRODUCTION app's /api/admin/narrate endpoint
   (admin session; password from env ADMIN_PW; voice onyx = male lecturer).
4. Measures each MP3; flags overruns (shorten script, never stretch video).
5. Assembles one narration track per video and muxes (AAC) into the MP4.

Usage:
  ADMIN_PW=... python3 tools/narrate.py --calibrate   # 4 sample TTS, print durations
  ADMIN_PW=... python3 tools/narrate.py --plan        # print all scripts + budgets
  ADMIN_PW=... python3 tools/narrate.py --tts         # synthesize every segment -> /tmp/narr/
  ADMIN_PW=... python3 tools/narrate.py --mux         # assemble tracks + mux into static/demos/*.mp4
  ADMIN_PW=... python3 tools/narrate.py --strings     # new Burmese strings needing verification
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_demos as m

BASE = "https://speak-web-production.up.railway.app"
NARR_DIR = "/tmp/narr"
FPS = 24

# ------------------------------------------------------- new-string registry
NEW_NARR = []
def NY(s):
    if s not in NEW_NARR:
        NEW_NARR.append(s)
    m.MY(s)  # also visible via make_demos --strings
    return s

# ------------------------------------------------------- timing maps
def slot_n(slot, move_n, hold_n):
    keys = slot if isinstance(slot, list) else [slot]
    n = 12 + 12
    mn = 14 if len(keys) > 1 else move_n
    for key in keys:
        n += mn + hold_n
        if m.ARTS[key]['air'] == 'stop':
            n += 10
    return n

def drill_map(lesson):
    cfg = m.DRILLS[lesson['id']]
    segs, f = [], 0
    segs.append(('title', f, 48)); f += 48
    for i, demo in enumerate(cfg['demos']):
        n = slot_n(demo, 22, 30)
        segs.append((f'demo{i}', f, n, demo)); f += n
    segs.append(('tip', f, 84)); f += 84
    return segs

def topic_map(lesson):
    segs, f = [('title', 0, 72)], 72
    for pi, p in enumerate(lesson.get('phrases', [])):
        segs.append((f'p{pi}_card', f, 53)); f += 53
        for si, slot in enumerate(m.parse_focus(p.get('focus'))):
            n = slot_n(slot, 19, 24)
            segs.append((f'p{pi}_demo{si}', f, n, slot)); f += n
        segs.append((f'p{pi}_turn', f, 53)); f += 53
    segs.append(('outro', f, 48))
    return segs

def all_maps():
    lessons = m.load_lessons()
    out = {}
    for lid in m.DRILLS:
        out[f'lesson-{lid}'] = ('drill', lessons[lid], drill_map(lessons[lid]))
    for lid, L in lessons.items():
        if not lid.startswith('s-'):
            out[f'lesson-{lid}'] = ('topic', L, topic_map(L))
    return out

# ------------------------------------------------------- scripts (ENGLISH ONLY)
# Lecturer-style English narration. Tips are kept <= 42 chars so they fit
# the 2.5s topic-demo budget at ~17 chars/sec (onyx voice, speed 1.0).
DRILL_TITLES_EN = {
    's-th': "The 'th' sounds.",
    's-vw': "V versus W.",
    's-zs': "Z versus S.",
    's-rl': "R versus L.",
    's-final': "Final consonants.",
    's-clusters': "Consonant clusters.",
}
TURN_EN = "Your turn. Repeat after me."
OUTRO_EN = "Keep practicing!"

EN_TIPS = {
    'th':  "Tongue between the teeth. Blow air out.",
    'thd': "Same position. Now add your voice.",
    'f':   "Top teeth on the lower lip. Blow air.",
    'v':   "Teeth on the lower lip. Now buzz.",
    'w':   "Round your lips. Tongue rises at back.",
    's':   "Tongue near the ridge. Hiss the air.",
    'z':   "Same tongue spot. Turn voice on.",
    'sh':  "Middle of tongue rises. Say shhh.",
    'zh':  "Same as sh. Now add your voice.",
    'r':   "Curl the tongue back. Touch nothing.",
    'l':   "Tip on the ridge. Air flows sideways.",
    't':   "Tip seals the ridge. Then release.",
    'd':   "Same seal. Now add your voice.",
    'k':   "Back of tongue seals. Then release.",
    'g':   "Same back seal. Add your voice.",
    'p':   "Lips press shut. Then pop open.",
    'b':   "Same lip seal. Add your voice.",
    'm':   "Lips shut. Hum through your nose.",
    'n':   "Tip on the ridge. Hum through nose.",
    'h':   "Mouth open. Breathe out with voice.",
    'ii':  "Tongue high and forward. Say eee.",
    'uu':  "Tongue high at back. Round the lips.",
}

def en_tip(slot):
    keys = slot if isinstance(slot, list) else [slot]
    return " ".join(EN_TIPS[k] for k in keys)

def drill_scripts(lid, lesson, segs):
    pairs = [p['en'].replace(' — ', ', ') for p in lesson.get('phrases', [])[:2]]
    scr = {}
    for label, f, n, *rest in segs:
        if label == 'title':
            scr[label] = (DRILL_TITLES_EN[lid], 1.0)
        elif label.startswith('demo'):
            scr[label] = (en_tip(rest[0]), 1.0)
        elif label == 'tip':
            scr[label] = ("Your turn. Say: " + ". ".join(pairs) + ".", 1.0)
    return scr

def topic_scripts(lid, lesson, segs):
    scr = {}
    for label, f, n, *rest in segs:
        if label == 'title':
            scr[label] = (lesson['title'], 1.0)
        elif label.endswith('_card'):
            pi = int(label[1:].split('_')[0])
            scr[label] = (lesson['phrases'][pi]['en'], 1.0)
        elif '_demo' in label:
            scr[label] = (en_tip(rest[0]), 1.0)
        elif label.endswith('_turn'):
            scr[label] = (TURN_EN, 1.0)
        elif label == 'outro':
            scr[label] = (OUTRO_EN, 1.0)
    return scr

def build_scripts():
    out = {}
    for vid, (kind, lesson, segs) in all_maps().items():
        lid = lesson['id']
        scr = drill_scripts(lid, lesson, segs) if kind == 'drill' else topic_scripts(lid, lesson, segs)
        out[vid] = (segs, scr)
    return out

# ------------------------------------------------------- TTS
import requests
_sess = None
def sess():
    global _sess
    if _sess is None:
        pw = os.environ.get('ADMIN_PW', '')
        _sess = requests.Session()
        r = _sess.post(f"{BASE}/api/admin/login", json={"password": pw}, timeout=30)
        assert r.json().get('ok'), "admin login failed"
    return _sess

def tts_mp3(text, voice='onyx', speed=1.0):
    r = sess().post(f"{BASE}/api/admin/narrate",
                    json={"text": text, "voice": voice, "speed": speed},
                    timeout=120)
    r.raise_for_status()
    return r.content

def mp3_dur(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                          'format=duration', '-of', 'csv=p=0', path],
                         capture_output=True, text=True)
    return float(out.stdout.strip())

# ------------------------------------------------------- commands
def cmd_calibrate():
    samples = [
        ("The 'th' sounds.", 1.0),
        ("Tongue between the teeth. Blow air out.", 1.0),
        ("Hi, my name is Arkar. What's yours?", 1.0),
        ("Your turn. Repeat after me.", 1.0),
    ]
    os.makedirs('/tmp/narr_cal', exist_ok=True)
    for i, (t, sp) in enumerate(samples):
        p = f'/tmp/narr_cal/s{i}.mp3'
        open(p, 'wb').write(tts_mp3(t, speed=sp))
        print(f"{len(t):3d} chars -> {mp3_dur(p):.2f}s  {t[:40]}")

def cmd_plan():
    for vid, (segs, scr) in build_scripts().items():
        print(f"== {vid}")
        for label, f, n, *rest in segs:
            txt, sp = scr[label]
            print(f"  {label:14s} {f/24:6.2f}s +{n/24:5.2f}s  [{len(txt)}ch] {txt[:60]}")

def cmd_tts():
    total_ch = 0
    for vid, (segs, scr) in build_scripts().items():
        d = os.path.join(NARR_DIR, vid)
        os.makedirs(d, exist_ok=True)
        for label, f, n, *rest in segs:
            txt, sp = scr[label]
            p = os.path.join(d, f"{label}.mp3")
            if os.path.exists(p):
                continue
            open(p, 'wb').write(tts_mp3(txt, speed=sp))
            total_ch += len(txt)
            print(f"TTS {vid}/{label}: {len(txt)}ch", flush=True)
    print(f"TOTAL chars: {total_ch}")

def check_fit():
    bad = []
    for vid, (segs, scr) in build_scripts().items():
        d = os.path.join(NARR_DIR, vid)
        for label, f, n, *rest in segs:
            p = os.path.join(d, f"{label}.mp3")
            if not os.path.exists(p):
                bad.append((vid, label, 'missing', 0, n / 24))
                continue
            dur, budget = mp3_dur(p), n / 24 - 0.30
            if dur > budget:
                bad.append((vid, label, f'{dur:.2f}s', budget, f'{dur-budget:.2f}s over'))
    return bad

def cmd_mux():
    for vid, (segs, scr) in build_scripts().items():
        vpath = os.path.join(m.OUT_DIR, f'{vid}.mp4')
        if not os.path.exists(vpath):
            print(f"SKIP {vid}: video missing"); continue
        d = os.path.join(NARR_DIR, vid)
        # build concat list: silence pads + segments at exact start times
        parts, t = [], 0.0
        for label, f, n, *rest in segs:
            start = f / 24 + 0.25
            mp = os.path.join(d, f"{label}.mp3")
            dur = mp3_dur(mp)
            pad = max(0.0, start - t)
            if pad > 0.01:
                parts.append(('sil', pad))
                t += pad
            parts.append(('mp3', mp, dur))
            t += dur
        # concat via filter
        inputs, fc, idx = [], [], 0
        for kind, *a in parts:
            if kind == 'sil':
                inputs += ['-f', 'lavfi', '-i', f"anullsrc=r=44100:cl=stereo:d={a[0]:.3f}"]
            else:
                inputs += ['-i', a[0]]
            fc.append(f"[{idx}:a]aresample=44100,apad=whole_dur=0[a{idx}]")
            idx += 1
        join = "".join(f"[a{i}]" for i in range(idx))
        fc.append(f"{join}concat=n={idx}:v=0:a=1,apad,atrim=0:{t:.3f}[mix]")
        track = os.path.join(d, 'track.m4a')
        cmd = ['ffmpeg', '-y', '-v', 'error'] + inputs + \
              ['-filter_complex', ";".join(fc), '-map', '[mix]',
               '-c:a', 'aac', '-b:a', '96k', track]
        subprocess.run(cmd, check=True)
        tmp = vpath + '.muxed.mp4'
        # explicit maps: video from the original, audio ONLY from the new
        # narration track (the old file may already carry a previous voiceover).
        # Pad (never cut): if the narration is shorter than the video, extend
        # the audio with silence to the full video duration.
        vdur = float(subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', vpath],
            capture_output=True, text=True).stdout.strip())
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', vpath, '-i', track,
                        '-map', '0:v:0', '-map', '1:a:0',
                        '-c:v', 'copy', '-af', 'apad', '-c:a', 'aac', '-b:a', '96k',
                        '-movflags', '+faststart', '-t', f'{vdur:.3f}', tmp],
                       check=True)
        os.replace(tmp, vpath)
        print(f"MUXED {vid}: {os.path.getsize(vpath)/1e6:.1f}MB", flush=True)

def cmd_strings():
    for s in NEW_NARR:
        print(s)

if __name__ == '__main__':
    c = sys.argv[1] if len(sys.argv) > 1 else '--plan'
    {'--calibrate': cmd_calibrate, '--plan': cmd_plan, '--tts': cmd_tts,
     '--mux': cmd_mux, '--strings': cmd_strings}[c]()
