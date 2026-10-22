#!/usr/bin/env python3
"""
MasterClass Articulation — tongue-movement demonstration video generator.

Deterministic animated midsagittal (side-view cross-section) diagrams.
NOT AI-generated: every tongue position is parametric and anatomically exact.

Output: 1080x1920 portrait MP4s (h264, yuv420p), phone-first.
  - 6 sound-drill videos : static/demos/lesson-s-<id>.mp4   (~14s each)
  - 15 topic-lesson videos: static/demos/lesson-<id>.mp4    (~45-75s each)
  - 1 neutral loop        : static/demos/rest-loop.mp4      (5s, for s-stress/s-intonation)

Text rendering: English = DejaVu Sans(+Bold); Myanmar = Padauk + RAQM layout
(AGENTS.md: Noto Sans Myanmar renders U+1031 as tofu under RAQM; Padauk+RAQM verified).
Never mix scripts on one line — EN and MY always on separate lines.

NARRATION (v1: none — no OpenAI key in sandbox). Timestamps for future voiceover mux:
  - drill videos : title 0.0-2.0s | demo A 2.0-6.5s | demo B 6.5-11.0s | tip card 11.0-14.5s
  - topic videos : title 0.0-3.0s | per phrase: phrase card 2.2s, each sound demo ~2.8s,
                   your-turn card 2.2s | outro 2.0s
  A narration MP3 can be muxed later with: ffmpeg -i video.mp4 -i narration.mp3 -c:v copy -c:a aac -shortest out.mp4

Usage:
  python3 tools/make_demos.py --test s-th        # render one drill, frames to /tmp for inspection
  python3 tools/make_demos.py --all              # render everything (parallel workers)
  python3 tools/make_demos.py --strings          # print new Burmese strings needing verification
"""
import math, json, os, re, subprocess, sys, argparse
from concurrent.futures import ProcessPoolExecutor
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- config
W, H = 1080, 1920
SS = 1.5                      # supersample factor (render big, downscale in ffmpeg)
FW, FH = int(W * SS), int(H * SS)
FPS = 24

ACCENT = (91, 91, 214)
ACCENT_D = (70, 70, 184)
INK = (28, 30, 42)
MUTED = (107, 114, 128)
BG = (244, 245, 251)
CARD = (255, 255, 255)
GREEN = (22, 163, 74)
GRAY = (148, 163, 184)
SKIN = (242, 201, 164)
SKIN_D = (232, 178, 148)
TONGUE = (232, 110, 130)
TONGUE_D = (176, 58, 90)
AIR = (90, 150, 255)
CAVITY = (96, 52, 60)

PADUK = '/home/hatch/workspace/myanmar-bots/gpt-web/fonts/Padauk-Regular.ttf'
DEJA = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
DEJAB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
RAQM = ImageFont.Layout.RAQM

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LESSONS_JSON = os.path.join(BASE, 'lessons.json')
OUT_DIR = os.path.join(BASE, 'static', 'demos')

# ------------------------------------------------- new Burmese string registry
# Every NEW customer-facing Myanmar string must go through MY() so it can be
# listed for the native speaker's verification (standing rule).
NEW_MY_STRINGS = []
def MY(s):
    if s not in NEW_MY_STRINGS:
        NEW_MY_STRINGS.append(s)
    return s

# Reused (already verified by Arkar): lesson title_my, phrase my, tip_my.
# New strings needing verification:
S_PRACTICE_SESSION = MY("အသံထွက် လေ့ကျင့်ခန်း")          # "Practice Session"
S_YOUR_TURN_MY = MY("သင့်အလှည့် — မော်ဒယ်အတိုင်း လိုက်ဆိုပါ")  # "Your turn — repeat after the model"
S_LISTEN_MY = MY("နားထောင်ပါ")                              # "Listen"
S_REST_MY = MY("အနားယူ")                                    # "Rest"
S_MOVE_MY = MY("ရွှေ့ပါ")                                    # "Move"
S_HOLD_MY = MY("ထိန်းထားပါ")                                # "Hold"
S_RELAX_MY = MY("ဖြေလျှော့ပါ")                               # "Relax"
S_VOICED_MY = MY("အသံပါဝင်သည်")                             # "voiced"
S_VOICELESS_MY = MY("အသံမပါဝင်ပါ")                          # "voiceless"
S_TONGUE_MY = MY("လျှာ")                                     # "tongue"
S_TEETH_MY = MY("သွား")                                      # "teeth"
S_LIPS_MY = MY("နှုတ်ခမ်း")                                  # "lips"
S_TRY_MY = MY("လေ့ကျင့်ကြည့်ပါ")                            # "Practice (these)"
S_KEEP_MY = MY("ဆက်လက်လေ့ကျင့်ပါ")                          # "Keep practicing"
S_RELAXED_MOUTH_MY = MY("ပါးစပ်ကို ဖြေလျှော့ထားပါ")          # "Keep your mouth relaxed"

# ---------------------------------------------------------------- fonts
_font_cache = {}
def fen(size, bold=False):
    k = ('en', size, bold)
    f = _font_cache.get(k)
    if f is None:
        f = ImageFont.truetype(DEJAB if bold else DEJA, int(size * SS))
        _font_cache[k] = f
    return f
def fmy(size):
    k = ('my', size)
    f = _font_cache.get(k)
    if f is None:
        f = ImageFont.truetype(PADUK, int(size * SS), layout_engine=RAQM)
        _font_cache[k] = f
    return f

def tw(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]

def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(' '), [], ''
    for w_ in words:
        t = (cur + ' ' + w_).strip()
        if tw(draw, t, font)[0] <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w_
    if cur:
        lines.append(cur)
    return lines

def center_text(draw, cx, y, text, font, fill):
    w_, h_ = tw(draw, text, font)
    draw.text((cx - w_ / 2, y), text, font=font, fill=fill)
    return h_

def left_text(draw, x, y, text, font, fill):
    w_, h_ = tw(draw, text, font)
    draw.text((x, y), text, font=font, fill=fill)
    return h_

def block_centered(draw, cx, y, lines, line_gap=1.35):
    """lines = [(text, font, fill)], returns bottom y."""
    for text, font, fill in lines:
        for ln in wrap(draw, text, font, W * SS - 160 * SS):
            h_ = center_text(draw, cx, y, ln, font, fill)
            y += h_ * line_gap
    return y

def rr(draw, box, r, fill, outline=None, width=1):
    draw.rounded_rectangle([v * SS for v in box], radius=int(r * SS), fill=fill,
                           outline=outline, width=int(width * SS))

# ================================================================ ANATOMY
# Midsagittal view, facing RIGHT. Units = final video pixels (scaled by SS at draw time).
# Landmarks shared by every frame.

# Schematic vocal tract (flat design, no head silhouette). Facing right.
# Panel: x 36-1044, y 420-1560. Content lives x ~300-960, y ~460-1420.
TEETH_UP = [(682, 648), (742, 648), (742, 752), (682, 752)]
TEETH_UP_LONG = [(682, 648), (742, 648), (742, 800), (682, 800)]  # for v/f: teeth on lip
TEETH_LOW = [(682, 895), (742, 895), (742, 999), (682, 999)]
RIDGE = (695, 640)                       # alveolar ridge bump center
# Roof = hard palate + velum, one filled shape. Two variants (velum up/down).
ROOF_UP = [(700, 600), (620, 562), (520, 556), (455, 575), (425, 660), (418, 740),
           (425, 762), (445, 762), (448, 730), (460, 660), (485, 600),
           (560, 596), (650, 622), (700, 648)]
ROOF_DOWN = [(700, 600), (620, 562), (520, 556), (460, 580), (445, 680), (450, 760),
             (470, 758), (466, 700), (485, 610), (560, 596), (650, 622), (700, 648)]
NASAL_BOX = (500, 465, 700, 560)         # nasal cavity (light wash above palate)
PHARYNX_BOX = (315, 600, 375, 1300)      # back wall of throat (peach band)
AIRWAY_BOX = (375, 650, 435, 1290)       # dark airway slot
FOLDS = (402, 1200)                      # vocal folds (ticks across airway)
ROOT_TOP, ROOT_BOT = (450, 980), (420, 1250)
MOUTH = (812, 930)                       # mouth opening center
MOUTH_OUT = (965, 930)                   # where exhaled air exits the frame

def chaikin(pts, iters=3):
    for _ in range(iters):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append((a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25))
            out.append((a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75))
        out.append(pts[-1])
        pts = out
    return pts

def bez(p0, p1, p2, n=24):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        pts.append((x, y))
    return pts

def tongue_top_points(tip, blade, dorsum):
    """Smoothed tongue TOP surface: root -> dorsum -> blade -> tip."""
    return chaikin([ROOT_TOP, dorsum, blade, tip])

def tongue_poly(tip, blade, dorsum, thick=64):
    """Tongue as a capsule of ~uniform thickness following the top curve,
    tapering toward the tip."""
    top = tongue_top_points(tip, blade, dorsum)
    n = len(top)
    tx, ty = tip
    # round the tip with a small arc before heading back along the bottom
    tip_arc = [(tx + 10, ty + 6), (tx + 8, ty + 22), (tx - 2, ty + 36), (tx - 16, ty + 44)]
    bot = []
    for i, (x, y) in enumerate(reversed(top)):
        f = i / max(n - 1, 1)          # 0 at tip, 1 at root
        t = thick * (0.32 + 0.68 * f)  # thinner near the tip
        bot.append((x - 10 * (1 - f), y + t))
    return top + tip_arc + bot[1:]


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

def smooth(t):
    return t * t * (3 - 2 * t)

# ================================================================ ARTICULATIONS
# tip/blade/dorsum = tongue control points; lips: neutral|rounded|rounded_slight|
#   closed|open|teeth_on_lip ; velum: up|down ; air: fric|stop|lateral|open|nasal|gentle
def A(tip, blade, dorsum, lips='neutral', velum='up', voice=False, air='open',
      constrict=None, symbol='', cap_en='', cap_my=''):
    return dict(tip=tip, blade=blade, dorsum=dorsum, lips=lips, velum=velum,
                voice=voice, air=air, constrict=constrict, symbol=symbol,
                cap_en=cap_en, cap_my=cap_my)

REST = A((720, 1010), (670, 940), (580, 975), air='gentle')

ARTS = {
 'rest': REST,
 'th': A((800, 930), (700, 900), (590, 930), air='fric', constrict=(788, 930),
         symbol='/θ/', cap_en='Tongue tip between the teeth — blow air out',
         cap_my=MY('လျှာဖျားကို သွားကြားထားပြီး လေမှုတ်ထုတ်ပါ')),
 'thd': A((800, 930), (700, 900), (590, 930), voice=True, air='fric', constrict=(788, 930),
          symbol='/ð/', cap_en='Same position — add your voice',
          cap_my=MY('နေရာတူတူပဲ — အသံထည့်ပါ')),
 'f': A((680, 1030), (640, 990), (580, 970), lips='teeth_on_lip', air='fric', constrict=(735, 1078),
        symbol='/f/', cap_en='Top teeth rest on the lower lip — blow air',
        cap_my=MY('အပေါ်သွားကို အောက်နှုတ်ခမ်းပေါ်တင်ပြီး လေမှုတ်ပါ')),
 'v': A((680, 1030), (640, 990), (580, 970), lips='teeth_on_lip', voice=True, air='fric', constrict=(735, 1078),
        symbol='/v/', cap_en='Top teeth on the lower lip — buzz',
        cap_my=MY('အပေါ်သွားကို အောက်နှုတ်ခမ်းပေါ်တင်ပြီး ညည်းပါ')),
 'w': A((680, 1030), (640, 960), (560, 860), lips='rounded', voice=True, air='open',
        symbol='/w/', cap_en='Round the lips — the back of the tongue rises',
        cap_my=MY('နှုတ်ခမ်းဝိုင်းပါ — လျှာနောက်ပိုင်း မြင့်တက်လာတယ်')),
 's': A((702, 685), (680, 670), (590, 900), air='fric', constrict=(700, 672),
        symbol='/s/', cap_en='Tongue close to the ridge — hiss the air out',
        cap_my=MY('လျှာကို အဖုနားကပ်ပြီး ရှူးရှဲမြည်အောင် လေမှုတ်ပါ')),
 'z': A((702, 685), (680, 670), (590, 900), voice=True, air='fric', constrict=(700, 672),
        symbol='/z/', cap_en='Same tongue spot — turn the voice on',
        cap_my=MY('လျှာနေရာ အတူတူပဲ — အသံထည့်ပါ')),
 'sh': A((680, 880), (640, 630), (580, 890), lips='rounded_slight', air='fric', constrict=(640, 615),
         symbol='/ʃ/', cap_en='The middle of the tongue rises — “shhh”',
         cap_my=MY('လျှာအလယ်ကို မြှင့်ပြီး “ရှူး” လို့ မှုတ်ပါ')),
 'zh': A((680, 880), (640, 630), (580, 890), lips='rounded_slight', voice=True, air='fric', constrict=(640, 615),
         symbol='/ʒ/', cap_en='Like “sh” — with the voice on',
         cap_my=MY('“ရှူး” သံနဲ့တူတူပဲ — အသံပါဝင်သည်')),
 'r': A((610, 860), (655, 840), (590, 890), voice=True, air='open',
        symbol='/r/', cap_en='Curl the tongue back — it touches nothing',
        cap_my=MY('လျှာဖျားကို နောက်ကို ကွေးပါ — ဘာနဲ့မှ မထိစေနဲ့')),
 'l': A((700, 662), (665, 700), (590, 920), voice=True, air='lateral', constrict=(700, 662),
        symbol='/l/', cap_en='The tip presses the ridge — air flows around the sides',
        cap_my=MY('လျှာဖျားကို အဖုမှာ ဖိထားပါ — လေက ဘေးနှစ်ဖက်က ထွက်တယ်')),
 't': A((700, 660), (663, 698), (588, 918), air='stop', constrict=(700, 662),
        symbol='/t/', cap_en='The tip seals the ridge — then release!',
        cap_my=MY('လျှာဖျားနဲ့ အဖုကို လုံအောင်ပိတ်ပြီး လွှတ်ပါ')),
 'd': A((700, 660), (663, 698), (588, 918), voice=True, air='stop', constrict=(700, 662),
        symbol='/d/', cap_en='Same seal — with the voice on',
        cap_my=MY('လျှာနေရာ အတူတူပဲ — အသံပါဝင်သည်')),
 'k': A((680, 1030), (640, 990), (465, 615), air='stop', constrict=(465, 605),
        symbol='/k/', cap_en='The back of the tongue seals — then release!',
        cap_my=MY('လျှာနောက်ပိုင်းနဲ့ လုံအောင်ပိတ်ပြီး လွှတ်ပါ')),
 'g': A((680, 1030), (640, 990), (465, 615), voice=True, air='stop', constrict=(465, 605),
        symbol='/g/', cap_en='Same back seal — with the voice on',
        cap_my=MY('လျှာနေရာ အတူတူပဲ — အသံပါဝင်သည်')),
 'p': A((680, 1030), (640, 990), (580, 970), lips='closed', air='stop', constrict=(808, 930),
        symbol='/p/', cap_en='The lips press shut — pop them open!',
        cap_my=MY('နှုတ်ခမ်းကို လုံအောင်ပိတ်ပြီး ပေါက်ထွက်အောင် ဖွင့်ပါ')),
 'b': A((680, 1030), (640, 990), (580, 970), lips='closed', voice=True, air='stop', constrict=(808, 930),
        symbol='/b/', cap_en='Same lip seal — with the voice on',
        cap_my=MY('နှုတ်ခမ်းအနေအထား အတူတူပဲ — အသံပါဝင်သည်')),
 'm': A((680, 1030), (640, 990), (580, 970), lips='closed', velum='down', voice=True, air='nasal',
        symbol='/m/', cap_en='Lips shut — hum through the nose',
        cap_my=MY('နှုတ်ခမ်းပိတ်ပြီး နှာခေါင်းထဲက ညည်းပါ')),
 'n': A((700, 662), (665, 700), (590, 920), velum='down', voice=True, air='nasal', constrict=(700, 662),
        symbol='/n/', cap_en='The tip holds the ridge — hum through the nose',
        cap_my=MY('လျှာဖျားကို အဖုမှာကပ်ပြီး နှာခေါင်းထဲက ညည်းပါ')),
 'h': A((680, 1040), (640, 1000), (580, 990), lips='open', voice=True, air='open',
        symbol='/h/', cap_en='Mouth open — breathe out with the voice on',
        cap_my=MY('ပါးစပ်ဟပြီး အသံပါတဲ့ လေကို မှုတ်ထုတ်ပါ')),
 'ii': A((690, 990), (640, 640), (600, 880), voice=True, air='open',
         symbol='/i:/', cap_en='The tongue is high and forward — “eee”',
         cap_my=MY('လျှာကို အပေါ်ရှေ့ မြှင့်ထားပြီး “အီး” လို့ ဆိုပါ')),
 'uu': A((690, 1020), (640, 900), (555, 640), lips='rounded', voice=True, air='open',
         symbol='/u:/', cap_en='The tongue is high at the back — lips round',
         cap_my=MY('လျှာကို အပေါ်နောက် မြှင့်ထားပြီး နှုတ်ခမ်းဝိုင်းပါ')),
}

# ================================================================ FOCUS PARSER
# phrase focus string -> list of demo slots; a slot is an art key or a list (cluster chain)
CHAINS = {
 'str': ['s', 't', 'r'], 'spr': ['s', 'p', 'r'], 'spl': ['s', 'p', 'l'], 'scr': ['s', 'k', 'r'],
 'sps': ['s', 'p', 's'], 'sts': ['s', 't', 's'], 'skt': ['s', 'k', 't'], 'tcht': ['t', 'ch'],
 'kst': ['k', 's', 't'], 'sp': ['s', 'p'], 'st': ['s', 't'], 'sk': ['s', 'k'],
 'sl': ['s', 'l'], 'fl': ['f', 'l'], 'fr': ['f', 'r'], 'tr': ['t', 'r'],
 'gr': ['g', 'r'], 'pr': ['p', 'r'], 'kw': ['k', 'w'], 'ks': ['k', 's'],
 'pt': ['p', 't'], 'kt': ['k', 't'], 'rd': ['r', 'd'],
}
CHAIN_RE = re.compile(r'\b(str|spl|spr|scr|sps|sts|skt|tcht|kst|sp|st|sk|sl|fl|fr|tr|gr|pr|kw|ks|pt|kt|rd)\b')

def parse_focus(focus):
    """Return <=2 demo slots for a phrase focus string."""
    if not focus:
        return []
    f = focus.lower()
    slots = []
    def add(slot):
        flat = [x for s in slots for x in (s if isinstance(s, list) else [s])]
        xs = slot if isinstance(slot, list) else [slot]
        if any(x in flat for x in xs):
            return
        if len(slots) < 2:
            slots.append(slot)
    if 'th /θ/ and /ð/' in f:
        return ['th', 'thd']
    if 'th /θ/' in f:
        add('th')
    elif 'th /ð/' in f:
        add('thd')
    elif re.search(r'\bth\b', f):
        add('thd')  # bare "th" (e.g. in 'this') -> voiced default
    m = CHAIN_RE.search(f)
    if m:
        add(CHAINS[m.group(1)])
    if re.search(r'\bf\b', f):
        add('f')
    if re.search(r'\bv\b', f):
        add('v')
    if re.search(r'\bw\b', f):
        add('w')
    if 'z vs s' in f or 's vs z' in f:
        add('s'); add('z')
    elif re.search(r'\bz\b', f):
        add('z')
    elif re.search(r"(?<!')\bs\b", f) and 'vs' not in f:
        add('s')
    if 'r vs l' in f or 'l vs r' in f:
        add('l'); add('r')
    elif re.search(r'\br\b', f):
        add('r')
    elif re.search(r'\bl\b', f):
        add('l')
    if re.search(r'\bsh\b', f):
        add('zh' if '/ʒ/' in f else 'sh')
    if re.search(r'\bch\b', f):
        add(['t', 'sh'])
    if '/t/' in f:
        add('t')
    if re.search(r'\bj\b', f):
        add(['d', 'zh'])
    if re.search(r'\bd\b', f):
        add('d')
    if re.search(r'\bb\b', f):
        add('b')
    if re.search(r'\bh\b', f):
        add('h')
    if 'i:/' in f:
        add('ii')
    if 'u:/' in f:
        add('uu')
    if 'final -k' in f:
        add('k')
    return slots[:2]

# ================================================================ DIAGRAM RENDERER
PANEL = (36, 420, 1044, 1560)          # diagram card
CAP_Y = 1590                            # caption band top

def _s(v):
    return v * SS

def _pts(pts):
    return [(p[0] * SS, p[1] * SS) for p in pts]

_bg_cache = {}

def draw_teeth(d, on_lip=False):
    up = TEETH_UP_LONG if on_lip else TEETH_UP
    for rect in (up, TEETH_LOW):
        d.rounded_rectangle([_s(rect[0][0]), _s(rect[0][1]), _s(rect[2][0]), _s(rect[2][1])],
                            radius=int(8 * SS), fill=(255, 255, 255),
                            outline=(160, 170, 190), width=int(3 * SS))

def draw_roof(d, velum):
    # nasal cavity wash (behind/above palate)
    x0, y0, x1, y1 = NASAL_BOX
    d.ellipse([_s(x0), _s(y0), _s(x1), _s(y1)], fill=(232, 238, 248))
    # hard palate: smooth dome from the ridge
    d.line(_pts(bez((702, 648), (600, 548), (498, 566))),
           fill=SKIN_D, width=int(30 * SS), joint='curve')
    # alveolar ridge bump behind the upper teeth
    d.ellipse([_s(RIDGE[0] - 22), _s(RIDGE[1] - 22), _s(RIDGE[0] + 22), _s(RIDGE[1] + 22)],
              fill=SKIN_D, outline=(205, 150, 125), width=int(2 * SS))
    # velum: soft palate curving down (lowered for nasals)
    if velum == 'down':
        d.line(_pts(bez((498, 566), (448, 660), (456, 778))),
               fill=SKIN_D, width=int(34 * SS), joint='curve')
        d.ellipse([_s(456 - 15), _s(778 - 15), _s(456 + 15), _s(778 + 15)], fill=SKIN_D)
    else:
        d.line(_pts(bez((498, 566), (444, 645), (428, 758))),
               fill=SKIN_D, width=int(34 * SS), joint='curve')
        d.ellipse([_s(428 - 15), _s(758 - 15), _s(428 + 15), _s(758 + 15)], fill=SKIN_D)


def draw_throat(d):
    x0, y0, x1, y1 = PHARYNX_BOX
    d.rounded_rectangle([_s(x0), _s(y0), _s(x1), _s(y1)], radius=int(24 * SS), fill=SKIN)
    x0, y0, x1, y1 = AIRWAY_BOX
    d.rounded_rectangle([_s(x0), _s(y0), _s(x1), _s(y1)], radius=int(20 * SS), fill=CAVITY)

def draw_lips(d, mode):
    # mode: neutral | open | rounded | rounded_slight | closed | teeth_on_lip
    if mode == 'teeth_on_lip':
        # long upper teeth already drawn; lips meet them top and bottom
        d.ellipse([_s(742), _s(700), _s(852), _s(780)], fill=SKIN, outline=SKIN_D,
                  width=int(3 * SS))
        d.ellipse([_s(740), _s(790), _s(850), _s(870)], fill=SKIN, outline=SKIN_D,
                  width=int(3 * SS))
        return
    if mode == 'closed':
        d.rounded_rectangle([_s(748), _s(900), _s(864), _s(960)], radius=int(20 * SS),
                            fill=SKIN, outline=SKIN_D, width=int(3 * SS))
        d.line([_s(758), _s(930), _s(854), _s(930)], fill=SKIN_D, width=int(3 * SS))
        return
    if mode in ('rounded', 'rounded_slight'):
        r = 48 if mode == 'rounded' else 36
        cx, cy = 792, 930
        d.ellipse([_s(cx - r - 12), _s(cy - r - 10), _s(cx + r), _s(cy + r + 10)],
                  fill=SKIN, outline=SKIN_D, width=int(3 * SS))
        d.ellipse([_s(cx - r + 12), _s(cy - r + 10), _s(cx + r - 22), _s(cy + r - 10)],
                  fill=CAVITY)
        return
    # neutral / open: dark mouth slot + lip shapes
    d.rounded_rectangle([_s(772), _s(850), _s(814), _s(1010)], radius=int(18 * SS), fill=CAVITY)
    if mode == 'open':
        d.rounded_rectangle([_s(764), _s(836), _s(822), _s(1024)], radius=int(24 * SS),
                            outline=CAVITY, width=int(4 * SS))
    d.ellipse([_s(748), _s(792), _s(860), _s(872)], fill=SKIN, outline=SKIN_D,
              width=int(3 * SS))
    d.ellipse([_s(748), _s(988), _s(860), _s(1068)], fill=SKIN, outline=SKIN_D,
              width=int(3 * SS))


def render_bg(lips_mode):
    """Static schematic vocal tract for a lip configuration. Cached."""
    if lips_mode in _bg_cache:
        return _bg_cache[lips_mode]
    img = Image.new('RGB', (FW, FH), BG)
    d = ImageDraw.Draw(img)
    rr(d, PANEL, 28, CARD, outline=(229, 231, 240), width=2)
    draw_throat(d)
    draw_roof(d, 'up')
    draw_teeth(d, on_lip=(lips_mode == 'teeth_on_lip'))
    draw_lips(d, lips_mode)
    _bg_cache[lips_mode] = img
    return img

LABELS = [
    # (text_en, text_my_or_None, anchor_xy, label_xy)
    ('tongue', S_TONGUE_MY, (580, 1060), (110, 1340)),
    ('teeth', S_TEETH_MY, (712, 700), (858, 640)),
    ('lips', S_LIPS_MY, (800, 930), (858, 930)),
    ('alveolar ridge', None, (695, 640), (858, 470)),
    ('hard palate', None, (585, 575), (110, 470)),
    ('vocal folds', None, FOLDS, (300, 1462)),
]


def draw_labels(d):
    fe = fen(27, bold=True)
    fm = fmy(27)
    for en, my, anchor, lab in LABELS:
        ax, ay = lab
        d.line([_s(anchor[0]), _s(anchor[1]), _s(ax + 60), _s(ay + 20)],
               fill=(150, 156, 175), width=int(2 * SS))
        d.ellipse([_s(anchor[0] - 5), _s(anchor[1] - 5), _s(anchor[0] + 5), _s(anchor[1] + 5)],
                  fill=ACCENT)
        left_text(d, _s(ax), _s(ay), en, fe, MUTED)
        if my:
            left_text(d, _s(ax), _s(ay + 34), my, fm, MUTED)

def draw_voicing_badge(d, voiced, frame_i):
    x0, y0, x1, y1 = 64, 1442, 252, 1522
    col = GREEN if voiced else GRAY
    rr(d, (x0, y0, x1, y1), 14, (255, 255, 255), outline=col, width=3)
    center_text(d, _s((x0 + x1) / 2), _s(y0 + 12), 'VOICED' if voiced else 'VOICELESS',
                fen(26, bold=True), col)
    center_text(d, _s((x0 + x1) / 2), _s(y0 + 44), S_VOICED_MY if voiced else S_VOICELESS_MY,
                fmy(24), col)
    if voiced:
        # animated ripple at the vocal folds
        fx, fy = FOLDS
        for k in range(3):
            r = 14 + ((frame_i * 2 + k * 12) % 36)
            alpha = 1 - ((frame_i * 2 + k * 12) % 36) / 36
            d.arc([_s(fx - r), _s(fy - r), _s(fx + r), _s(fy + r)], start=200, end=340,
                  fill=GREEN, width=max(2, int(4 * SS * alpha)))

def draw_folds(d, voiced, frame_i):
    fx, fy = FOLDS
    if voiced:
        wob = math.sin(frame_i * 0.9) * 4
        d.line([_s(fx - 16), _s(fy - 8 + wob), _s(fx + 16), _s(fy - 8 - wob)],
               fill=(255, 255, 255), width=int(5 * SS))
        d.line([_s(fx - 16), _s(fy + 8 - wob), _s(fx + 16), _s(fy + 8 + wob)],
               fill=(255, 255, 255), width=int(5 * SS))
    else:
        d.line([_s(fx - 16), _s(fy - 6), _s(fx + 16), _s(fy - 6)], fill=(200, 200, 210),
               width=int(4 * SS))
        d.line([_s(fx - 16), _s(fy + 6), _s(fx + 16), _s(fy + 6)], fill=(200, 200, 210),
               width=int(4 * SS))

# ------------------------------------------------- airflow particles
def top_y_at(top_pts, x):
    """Interpolate tongue-top y for a given x (top_pts ordered root->tip)."""
    for (x0, y0), (x1, y1) in zip(top_pts, top_pts[1:]):
        if (x0 <= x <= x1) or (x1 <= x <= x0):
            if x1 == x0:
                return y0
            f = (x - x0) / (x1 - x0)
            return y0 + (y1 - y0) * f
    return None

def airflow_waypoints(art, top_pts):
    air = art.get('air')
    if air == 'nasal':
        return [(402, 1150), (430, 950), (440, 800), (470, 680),
                (520, 580), (600, 520), (700, 500)]
    # follow the tongue's top surface, 30px above it, then out the mouth
    surf = []
    for x in range(470, 700, 36):
        y = top_y_at(top_pts, x)
        if y is not None:
            surf.append((x, y - 30))
    if art.get('lips') == 'rounded':
        mouth, out = [(792, 930)], (965, 930)
    elif art.get('lips') == 'closed':
        mouth, out = [(808, 930)], (965, 930)
    elif art.get('lips') == 'teeth_on_lip':
        mouth, out = [(800, 830)], (965, 830)
    else:
        mouth, out = [(812, 930)], (965, 930)
    return [(402, 1150), (445, 1030)] + surf + mouth + [out]


def path_pos(waypoints, t):
    t = max(0.0, min(1.0, t))
    segs = len(waypoints) - 1
    x = t * segs
    i = min(int(x), segs - 1)
    f = x - i
    a, b = waypoints[i], waypoints[i + 1]
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)

def draw_particles(d, art, top_pts, frame_i, intensity=1.0, dammed=False, burst_t=None):
    """intensity 0..1 scales count/speed. dammed=True: pile up before constriction (stops).
    burst_t 0..1: release burst progress (stops)."""
    if intensity <= 0:
        return
    wp = airflow_waypoints(art, top_pts)
    n = int(34 * intensity)
    for k in range(n):
        if dammed:
            t = 0.60 + 0.05 * math.sin(frame_i * 0.5 + k * 1.7) + (k % 5) * 0.010
        elif burst_t is not None:
            t = 0.62 + burst_t * 0.38 * ((k % 7) / 6 + 0.2)
            t = min(t, 1.0)
        else:
            t = ((frame_i * 0.014 * intensity) + k / n) % 1.0
        x, y = path_pos(wp, t)
        r = 6 + (3 if burst_t is not None else 0)
        d.ellipse([_s(x - r), _s(y - r), _s(x + r), _s(y + r)], fill=AIR)

# ------------------------------------------------- frame compositor
def draw_diagram(art_from, art_to, t, lips_mode, velum, voiced, frame_i,
                 particle_mode='flow', burst_t=None, intensity=1.0,
                 caption_lines=None, show_labels=True):
    """particle_mode: 'flow' | 'dammed' | 'burst' | 'none'"""
    img = render_bg(lips_mode).copy()
    d = ImageDraw.Draw(img)
    a = ARTS[art_from]; b = ARTS[art_to]
    tip = lerp(a['tip'], b['tip'], t)
    blade = lerp(a['blade'], b['blade'], t)
    dorsum = lerp(a['dorsum'], b['dorsum'], t)
    draw_roof(d, velum)
    top = tongue_top_points(tip, blade, dorsum)
    poly = top + chaikin([(tip[0] - 18, tip[1] + 44), (640, 1262), (520, 1288), ROOT_BOT])
    d.polygon(_pts(poly), fill=TONGUE, outline=TONGUE_D, width=int(3 * SS))
    draw_folds(d, voiced, frame_i)
    if particle_mode == 'flow':
        draw_particles(d, b, top, frame_i, intensity)
    elif particle_mode == 'dammed':
        draw_particles(d, b, top, frame_i, intensity, dammed=True)
    elif particle_mode == 'burst':
        draw_particles(d, b, top, frame_i, intensity, burst_t=burst_t)
    if show_labels:
        draw_labels(d)
    draw_voicing_badge(d, voiced, frame_i)
    if caption_lines:
        y = _s(CAP_Y)
        for text, font, fill in caption_lines:
            h_ = center_text(d, _s(W / 2), y, text, font, fill)
            y += h_ * 1.25
    return img

# ================================================================ CARDS
def blank():
    img = Image.new('RGB', (FW, FH), BG)
    return img, ImageDraw.Draw(img)

def brand_header(d, y=150):
    center_text(d, _s(W / 2), _s(y), 'MasterClass Articulation', fen(44, True), ACCENT)

def title_card_drill(symbol, title_en, title_my):
    img, d = blank()
    brand_header(d)
    block_centered(d, _s(W / 2), _s(620), [
        (symbol, fen(150, True), INK),
        (title_en, fen(62, True), INK),
        (title_my, fmy(58), MUTED),
    ], line_gap=1.5)
    return img

def title_card_topic(lesson):
    img, d = blank()
    brand_header(d)
    lvl = lesson.get('level', '')
    bw, bh = tw(d, lvl, fen(44, True))
    rr(d, (W / 2 - bw / SS / 2 - 30, 296, W / 2 + bw / SS / 2 + 30, 296 + bh / SS + 34),
       16, ACCENT)
    center_text(d, _s(W / 2), _s(306), lvl, fen(44, True), (255, 255, 255))
    block_centered(d, _s(W / 2), _s(560), [
        (lesson.get('title', ''), fen(64, True), INK),
        (lesson.get('title_my', ''), fmy(60), MUTED),
    ], line_gap=1.5)
    block_centered(d, _s(W / 2), _s(1180), [
        ('Practice Session', fen(56, True), ACCENT),
        (S_PRACTICE_SESSION, fmy(54), ACCENT),
    ], line_gap=1.4)
    return img

def phrase_card(en, my):
    img, d = blank()
    block_centered(d, _s(W / 2), _s(430), [
        ('LISTEN', fen(40, True), ACCENT),
        (S_LISTEN_MY, fmy(40), ACCENT),
    ], line_gap=1.3)
    y = block_centered(d, _s(W / 2), _s(680), [
        (en, fen(62, True), INK),
    ], line_gap=1.45)
    block_centered(d, _s(W / 2), y + _s(50), [
        (my, fmy(54), MUTED),
    ], line_gap=1.6)
    return img

def your_turn_card():
    img, d = blank()
    block_centered(d, _s(W / 2), _s(660), [
        ('Your turn', fen(78, True), ACCENT),
        ('repeat after the model', fen(44), MUTED),
        (S_YOUR_TURN_MY, fmy(50), INK),
    ], line_gap=1.5)
    return img

def word_card(header, lines):
    img, d = blank()
    center_text(d, _s(W / 2), _s(210), header, fen(46, True), ACCENT)
    y = _s(540)
    for w in lines:
        h_ = center_text(d, _s(W / 2), y, w, fen(78, True), INK)
        y += h_ * 2.1
    return img

def tip_card(tip_my, pairs):
    img, d = blank()
    center_text(d, _s(W / 2), _s(230), 'Tip', fen(58, True), ACCENT)
    y = block_centered(d, _s(W / 2), _s(360), [(tip_my, fmy(46), INK)], line_gap=1.7)
    y += _s(60)
    center_text(d, _s(W / 2), y, S_TRY_MY, fmy(44), ACCENT)
    y += _s(80)
    for pr in pairs:
        h_ = center_text(d, _s(W / 2), y, pr, fen(48), INK)
        y += h_ * 1.6
    return img

def outro_card():
    img, d = blank()
    block_centered(d, _s(W / 2), _s(720), [
        ('Well done!', fen(78, True), ACCENT),
        (S_KEEP_MY, fmy(54), INK),
        ('Practice with feedback in the app', fen(40), MUTED),
    ], line_gap=1.5)
    return img

# ================================================================ SEGMENTS
def phase_cap(en, my):
    return [(en, fen(44, True), INK), (my, fmy(44), MUTED)]

def move_cap(art):
    return [(('Move into position  ' + art['symbol']) if art['symbol'] else 'Move into position',
             fen(40, True), INK),
            (S_MOVE_MY, fmy(40), MUTED)]

def sound_cap(art):
    lines = []
    if art['symbol']:
        lines.append((art['symbol'], fen(56, True), ACCENT))
    lines.append((art['cap_en'], fen(38, True), INK))
    lines.append((art['cap_my'], fmy(38), MUTED))
    return lines

def repeat_img(img, n):
    for _ in range(n):
        yield img

def demo_slot_frames(slot, move_n=19, hold_n=24):
    """One demo slot (art key or chain list) -> frames: rest/move/hold/[burst]/relax."""
    keys = slot if isinstance(slot, list) else [slot]
    R, X = 12, 12
    fi = 0
    for i in range(R):
        yield draw_diagram('rest', 'rest', 0, 'neutral', 'up', False, fi,
                           particle_mode='flow', intensity=0.35,
                           caption_lines=phase_cap('Rest', S_REST_MY))
        fi += 1
    prev = 'rest'
    for key in keys:
        art = ARTS[key]
        is_stop = art['air'] == 'stop'
        mn = 14 if len(keys) > 1 else move_n
        for i in range(mn):
            t = smooth((i + 1) / mn)
            lips = art['lips'] if t > 0.5 else ARTS[prev]['lips']
            vel = art['velum'] if t > 0.5 else ARTS[prev]['velum']
            yield draw_diagram(prev, key, t, lips, vel, False, fi,
                               particle_mode='none', caption_lines=move_cap(art))
            fi += 1
        pm = 'dammed' if is_stop else 'flow'
        for i in range(hold_n):
            yield draw_diagram(key, key, 1, art['lips'], art['velum'], art['voice'], fi,
                               particle_mode=pm, intensity=1.0,
                               caption_lines=sound_cap(art))
            fi += 1
        if is_stop:
            for i in range(10):
                bt = (i + 1) / 10
                lips_b = 'neutral' if art['lips'] == 'closed' else art['lips']
                yield draw_diagram(key, 'rest', bt * 0.6, lips_b, art['velum'],
                                   art['voice'], fi, particle_mode='burst', burst_t=bt,
                                   intensity=1.0, caption_lines=sound_cap(art))
                fi += 1
        prev = key
    for i in range(X):
        t = smooth((i + 1) / X)
        yield draw_diagram(keys[-1], 'rest', t, 'neutral', 'up', False, fi,
                           particle_mode='flow', intensity=0.35 * (1 - t),
                           caption_lines=phase_cap('Relax', S_RELAX_MY))
        fi += 1

# ================================================================ VIDEO BUILDERS
DRILLS = {
    's-th': dict(symbol='/θ/ /ð/', demos=['th', 'thd'], words=[
        ('/θ/ · no voice', ['thin', 'think', 'thank']),
        ('/θ/ · no voice', ['three', 'teeth', 'bath']),
        ('/θ/ · no voice', ['month', 'through', 'birthday']),
        ('/ð/ · with voice', ['this', 'that', 'these']),
        ('/ð/ · with voice', ['those', 'they', 'them']),
        ('/ð/ · with voice', ['their', 'with', 'breathe']),
    ]),
    's-vw': dict(symbol='/v/ /w/', demos=['v', 'w'], words=[
        ('/v/ vs /w/', ['very — wary', 'vine — wine']),
        ('/v/ vs /w/', ['vest — west', 'vet — wet']),
        ('/v/ vs /w/', ['verse — worse', 'van — one']),
    ]),
    's-zs': dict(symbol='/s/ /z/', demos=['s', 'z'], words=[
        ('/s/ vs /z/', ['sip — zip', 'Sue — zoo']),
        ('/s/ vs /z/', ['bus — buzz', 'ice — eyes']),
        ('/s/ vs /z/', ['face — phase', 'rice — rise']),
        ('/s/ vs /z/', ['price — prize', 'loose — lose']),
    ]),
    's-rl': dict(symbol='/l/ /r/', demos=['l', 'r'], words=[
        ('/r/ vs /l/', ['red — led', 'right — light']),
        ('/r/ vs /l/', ['read — lead', 'road — load']),
        ('/r/ vs /l/', ['fry — fly', 'grass — glass']),
    ]),
    's-final': dict(symbol='/t/ · /k/', demos=['t', 'k'], words=[
        ('Final consonants', ['worked', 'liked', 'stopped']),
        ('Final consonants', ['jumped', 'asked', 'watched']),
        ('Final consonants', ['missed', 'walked', 'talked']),
        ('Final consonants', ['fixed', 'laughed', 'helped']),
    ]),
    's-clusters': dict(symbol='s → t → r', demos=[['s', 't'], ['p', 'l']], words=[
        ('Consonant clusters', ['street', 'strong', 'spring']),
        ('Consonant clusters', ['splash', 'smile', 'spoon']),
        ('Consonant clusters', ['flower', 'fly', 'clean']),
        ('Consonant clusters', ['clock', 'price', 'pray']),
    ]),
}
# frames per example-word card
WORD_N = 108

def drill_frames(lesson):
    lid = lesson['id']
    cfg = DRILLS[lid]
    yield from repeat_img(title_card_drill(cfg['symbol'], lesson['title'], lesson['title_my']), 48)
    for demo in cfg['demos']:
        yield from demo_slot_frames(demo, move_n=22, hold_n=30)
    for header, lines in cfg.get('words', []):
        yield from repeat_img(word_card(header, lines), WORD_N)
    pairs = [p['en'] for p in lesson.get('phrases', [])[:2]]
    yield from repeat_img(tip_card(lesson.get('tip_my', ''), pairs), 84)

def topic_frames(lesson):
    yield from repeat_img(title_card_topic(lesson), 72)
    for p in lesson.get('phrases', []):
        yield from repeat_img(phrase_card(p['en'], p['my']), 53)
        for slot in parse_focus(p.get('focus')):
            yield from demo_slot_frames(slot)
        yield from repeat_img(your_turn_card(), 53)
    yield from repeat_img(outro_card(), 48)

def rest_loop_frames():
    for i in range(60):
        yield draw_diagram('rest', 'rest', 0, 'neutral', 'up', False, i,
                           particle_mode='flow', intensity=0.35,
                           caption_lines=phase_cap('Relaxed mouth', S_RELAXED_MOUTH_MY))
    for i in range(60):
        yield draw_diagram('rest', 'rest', 0, 'neutral', 'up', True, i,
                           particle_mode='flow', intensity=0.35,
                           caption_lines=phase_cap('Relaxed mouth', S_RELAXED_MOUTH_MY))

def encode(frames, outfile):
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    cmd = ['ffmpeg', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', f'{FW}x{FH}', '-r', str(FPS), '-i', '-',
           '-vf', f'scale={W}:{H}:flags=lanczos',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '23',
           '-preset', 'medium', '-movflags', '+faststart', outfile]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = 0
    for im in frames:
        p.stdin.write(im.convert('RGB').tobytes())
        n += 1
    p.stdin.close()
    p.wait()
    return n

def load_lessons():
    d = json.load(open(LESSONS_JSON))
    return {L['id']: L for L in d['lessons']}

def render_one(job):
    """job = (kind, lesson_id). kind: drill|topic|loop"""
    kind, lid = job
    lessons = load_lessons()
    if kind == 'drill':
        frames = drill_frames(lessons[lid])
        out = os.path.join(OUT_DIR, f'lesson-{lid}.mp4')
    elif kind == 'topic':
        frames = topic_frames(lessons[lid])
        out = os.path.join(OUT_DIR, f'lesson-{lid}.mp4')
    else:
        frames = rest_loop_frames()
        out = os.path.join(OUT_DIR, 'rest-loop.mp4')
    n = encode(frames, out)
    size = os.path.getsize(out)
    return (lid if kind != 'loop' else 'rest-loop', n, size, out)

def all_jobs():
    lessons = load_lessons()
    jobs = []
    for lid in DRILLS:
        jobs.append(('drill', lid))
    for lid, L in lessons.items():
        if not lid.startswith('s-'):
            jobs.append(('topic', lid))
    jobs.append(('loop', 'rest-loop'))
    return jobs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--test', help='render one video (drill/topic id or rest-loop) to /tmp')
    ap.add_argument('--all', action='store_true', help='render everything into static/demos/')
    ap.add_argument('--strings', action='store_true', help='list new Burmese strings')
    ap.add_argument('--parse', action='store_true', help='dump focus->demos mapping for all phrases')
    args = ap.parse_args()

    if args.strings:
        for s_ in NEW_MY_STRINGS:
            print(s_)
        return

    if args.parse:
        lessons = load_lessons()
        for lid, L in lessons.items():
            if lid.startswith('s-'):
                continue
            print(f'== {lid}')
            for p in L.get('phrases', []):
                print(f"  {p.get('focus')!r:55} -> {parse_focus(p.get('focus'))}")
        return

    if args.test:
        lid = args.test
        lessons = load_lessons()
        if lid == 'rest-loop':
            frames, out = rest_loop_frames(), '/tmp/test_rest-loop.mp4'
        elif lid in DRILLS:
            frames, out = drill_frames(lessons[lid]), f'/tmp/test_{lid}.mp4'
        else:
            frames, out = topic_frames(lessons[lid]), f'/tmp/test_{lid}.mp4'
        n = encode(frames, out)
        print(f'rendered {n} frames -> {out} ({os.path.getsize(out)} bytes)')
        # save 3 sample frames as PNG for inspection
        return

    if args.all:
        jobs = all_jobs()
        print(f'{len(jobs)} videos, {os.cpu_count()} workers')
        with ProcessPoolExecutor(max_workers=2) as ex:
            for lid, n, size, out in ex.map(render_one, jobs):
                print(f'OK {lid}: {n} frames, {size/1e6:.1f}MB -> {out}', flush=True)

if __name__ == '__main__':
    main()
