"""CHODBAK - chodi mat kar! A pixel-art drill guard that barks when you leave your focus apps.

usage:  python chodbak.py                    # or double-click Chodbak.exe; first run asks everything
        python chodbak.py "Visual Studio Code" "Notion"   # override the saved targets
        python chodbak.py --test 3          # preview one warning level
        python chodbak.py --setup           # redo the first-run questions
        python chodbak.py --lang tamil      # override the saved language once
        python chodbak.py --make-taunts     # re-record the taunt bank (all languages)

Targets match (case-insensitive substring) against the window title or the exe name,
so "YouTube" allows one browser tab and "chrome.exe" allows the whole browser.
The Sarvam key comes from SARVAM_API_KEY in .env next to the script/exe (asked for on first run).

First run asks for a Sarvam key, the language you speak at home, the apps to stay in,
and a photo (it doesn't say why).
Every taunt is spoken out loud in your language, after a meme sound from sfx/.
Level 1  SAAVDHAN    pixel warning + FAAAA!
Level 2  NALAYAK     nastier taunt + cat laugh + your photo, framed and disappointed in you,
                     while the family WhatsApp group gossips ("ye le")
Level 3  KHATRA      metal pipe, yanks you back, cooker siti, flying chappal, threatens your
                     coding agent, then the last taunt: "should I call your mummy?" in your
                     language. It only stops when you say "sorry mummy" into the mic.
Stay focused 25 min straight and you earn a chai break.
"""
import argparse
import array
import base64
import io
import ctypes
import json
import math
import os
import queue
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import wave
import winsound
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog

from sarvamai import SarvamAI

# Built with PyInstaller, user files (.env, prefs, photo) sit next to the exe and the bundled
# sounds/taunts are unpacked to sys._MEIPASS. From source, both are this folder.
HERE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
ASSETS = Path(getattr(sys, "_MEIPASS", HERE / "web"))  # web/ serves the same sounds + taunts to the website
ENV = HERE / ".env"
FACE = HERE / "chodbak_face.png"  # the "registration" photo, git-ignored
PREFS = HERE / "chodbak_prefs.json"
SFX = ASSETS / "sfx"  # meme mp3s; drop extra ones in here and nags pick them at random
SFX_MAX_MS = 2500  # clips are padded with silence; cut them so the guard's voice follows fast
TAUNTS = ASSETS / "taunts"  # pre-recorded bank: taunts/<lang>/NN.mp3 + taunts.json, made by --make-taunts

# name -> (how the model should write it, Sarvam language code, button label)
LANGS = {
    "hinglish": ("Hinglish (Hindi-English mix, Roman script)", "hi-IN", "Hinglish"),
    "hindi": ("Hindi in Devanagari script", "hi-IN", "हिन्दी"),
    "english": ("Indian English", "en-IN", "English"),
    "bengali": ("Bengali in Bengali script", "bn-IN", "বাংলা"),
    "gujarati": ("Gujarati in Gujarati script", "gu-IN", "ગુજરાતી"),
    "kannada": ("Kannada in Kannada script", "kn-IN", "ಕನ್ನಡ"),
    "malayalam": ("Malayalam in Malayalam script", "ml-IN", "മലയാളം"),
    "marathi": ("Marathi in Devanagari script", "mr-IN", "मराठी"),
    "odia": ("Odia in Odia script", "od-IN", "ଓଡ଼ିଆ"),
    "punjabi": ("Punjabi in Gurmukhi script", "pa-IN", "ਪੰਜਾਬੀ"),
    "tamil": ("Tamil in Tamil script", "ta-IN", "தமிழ்"),
    "telugu": ("Telugu in Telugu script", "te-IN", "తెలుగు"),
}
# a Bulbul v3 voice per language, so the guard sounds a bit more local
VOICES = {"hinglish": "shubh", "hindi": "aditya", "english": "rahul", "bengali": "soham", "gujarati": "manan",
          "kannada": "gokul", "malayalam": "mani", "marathi": "rupali", "odia": "advait", "punjabi": "kabir",
          "tamil": "vijay", "telugu": "kavitha"}
GRACE = 1.0  # seconds away before a strike, so alt-tab flicker doesn't count
NAG_EVERY = 8  # level 3: seconds between re-yanks while you're still away
RESET_AFTER = 600  # seconds of unbroken focus that wipe your strikes
CHAI_EVERY = 25 * 60  # unbroken focus that earns a chai break
LISTEN_SECS = 3
MOM_LINE = "Should I call your mummy right now?"
MOM_HINGLISH = "Mummy ko abhi phone lagaun kya?"
IGNORE_TITLES = {"", "Task Switching", "Task View", "Start", "Search"}
LEVEL_SFX = {1: "faaa", 2: "cat_laugh", 3: "metal_pipe"}
# coding agents the guard can take hostage (exe -> name). Threats only: nothing is ever killed.
AGENTS = {"claude.exe": "Claude", "codex.exe": "Codex", "cursor.exe": "Cursor", "windsurf.exe": "Windsurf",
          "antigravity.exe": "Antigravity", "zed.exe": "Zed", "code.exe": "VS Code Copilot"}
HOSTAGE_STATES = ["zinda (for now)", "ghabraya hua", "ro raha hai", "last rites chal rahe hain", "kalma padh raha hai"]
FAMILY = [
    ("Pinky Aunty", "beta {app} pe kya kar rahe ho?? 🙄"),
    ("Bade Papa", "Sharma ji ka beta toh aaj 14 ghante padha"),
    ("Mummy", "Seen ✓✓"),
    ("Chachi", "maine toh pehle hi bola tha ye haath se nikal gaya"),
    ("Nani", "🙏🙏 bhagwan sadbuddhi de"),
    ("Fufaji", "hamare zamane mein {app} nahi hota tha"),
    ("Cousin Rinku", "😂😂😂 pakde gaye"),
    ("Mausi", "forwarded: 10 SIGNS YOUR CHILD IS ADDICTED TO {app}"),
]

MOODS = {
    1: "a stern, firm first warning",
    2: "deeply disappointed and guilt-tripping, like a parent who expected better: start with a heavy sigh "
       "(Haaye..., Hmm...), use slow trailing pauses (...), mention someone they love watching right now",
    3: "maximum fury, SHOUTING: short punchy bursts, lots of exclamation marks, a few words in CAPS, "
       "stretched words like Kyaaaa?! and Nalaaayak!",
}
# how the voice delivers each level: Bulbul v3 pace + temperature (expressiveness, max 1.0), then a volume boost
EMOTION = {1: dict(pace=1.15, temperature=0.6), 2: dict(pace=0.9, temperature=0.9), 3: dict(pace=1.35, temperature=1.0)}
GAIN = {1: 1.0, 2: 1.0, 3: 2.5}  # >1 compresses + soft-clips: sounds like yelling into a megaphone
FALLBACK = {
    1: "Saavdhan! Back to work right now. Chodi mat kar!",
    2: "Oye nalayak! Sharma ji ka beta never opens other tabs. Dekh, sab disappointed hain.",
    3: "NIKAL us window se, nikamme! Chappal ready hai. WAPAS KAAM PE!",
}
HEADERS = {1: ("SAAVDHAN!", "#f5d742"), 2: ("RUK JA, NALAYAK!", "#f59342"), 3: ("KHATRA! KHATRA!", "#e83b3b")}
BG = "#14141c"
PIX = ("Terminal", 12)  # Windows' built-in bitmap font: free pixel look
INDIC = ("Nirmala UI", 14, "bold")  # renders every Indic script
BTN = dict(font=PIX, relief="flat", bd=0, padx=12, pady=6, activebackground="#ffffff")

# 16x16 drill guard: helmet, angry brows, mustache, shouting mouth, uniform collar
GUARD = [
    ".....HHHHHH.....",
    "...HHhhhhhhHH...",
    "..HhhhhhhhhhhH..",
    "..HHHHHHHHHHHH..",
    ".HHHHHHHHHHHHHH.",
    "...SSSSSSSSSS...",
    "...SBBSSSSBBS...",
    "...SSKSSSSKSS...",
    "...SSSSssSSSS...",
    "...SMMMMMMMMS...",
    "...SSSRRRRSSS...",
    "....SSRRRRSS....",
    ".....SSSSSS.....",
    "...GGGGGGGGGG...",
    "..GGGgGGGGgGGG..",
    "..GGGGGGGGGGGG..",
]
CHAPPAL = [
    "....bb.........",
    "...b..b........",
    "..b....b.......",
    "WWWWWWWWWWWWWW.",
    "WwwwwwwwwwwwwWW",
    "WWWWWWWWWWWWWW.",
]
CHAI = [
    "..s.s...",
    ".s.s....",
    "CCCCCC..",
    "CttttCCC",
    "CttttC.C",
    "CttttCCC",
    ".CCCC...",
]
PHONE = [
    ".KKKKKK.",
    ".KggggK.",
    ".KggggK.",
    ".KggggK.",
    ".KKKKKK.",
    ".KCKCKK.",
    ".KKCKCK.",
    ".KKKKKK.",
]
PALETTE = {"H": "#4b5341", "h": "#6e7860", "S": "#e0ac69", "s": "#b8834a", "B": "#2b1d0e", "K": "#111111",
           "M": "#3b2a1a", "R": "#7a1010", "G": "#55603f", "g": "#d4af37",
           "b": "#2a6fdb", "W": "#8b5a2b", "w": "#a87444", "C": "#e8e8e8", "t": "#c68642"}
CHAI_PAL = {**PALETTE, "s": "#aaaaaa"}
PHONE_PAL = {**PALETTE, "K": "#333344", "g": "#7ee081"}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
mci = ctypes.windll.winmm.mciSendStringW
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]


def load_key():
    """SARVAM_API_KEY from .env next to the script/exe, else the environment, else None."""
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8-sig").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "SARVAM_API_KEY" and value.strip():
                return value.strip().strip("\"'")
    return os.environ.get("SARVAM_API_KEY", "").strip() or None


def load_prefs():
    try:
        return json.loads(PREFS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_prefs(**changes):
    PREFS.write_text(json.dumps({**load_prefs(), **changes}, ensure_ascii=False), encoding="utf-8")


def foreground():
    """(hwnd, title, exe name, pid) of the window you're looking at."""
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        path, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, path, ctypes.byref(size)):
            exe = os.path.basename(path.value)
        kernel32.CloseHandle(h)
    return hwnd, buf.value, exe, pid.value


def matches(title, exe, targets):
    hay = f"{title} {exe}".lower()
    return any(t.lower() in hay for t in targets)


def yank_back(bad, good):
    """Minimize the distraction and drag your focus app to the front."""
    if not good or bad == good:  # another tab in the same window: nothing to minimize
        return
    user32.ShowWindow(bad, 6)  # SW_MINIMIZE
    user32.keybd_event(0x12, 0, 0, 0)  # tap Alt so Windows lets us steal focus
    user32.keybd_event(0x12, 0, 2, 0)
    user32.ShowWindow(good, 9 if user32.IsIconic(good) else 5)  # restore if minimized, else just show
    user32.SetForegroundWindow(good)


def save_face(src):
    """Any photo -> small upright PNG that Tk can show. Uses Windows' own System.Drawing, no Pillow."""
    ps = (
        "Add-Type -AssemblyName System.Drawing; $i=[Drawing.Image]::FromFile($env:SRC);"
        "if($i.PropertyIdList -contains 274){$r=@{3='Rotate180FlipNone';6='Rotate90FlipNone';8='Rotate270FlipNone'}"
        "[[int]$i.GetPropertyItem(274).Value[0]]; if($r){$i.RotateFlip($r)}};"
        "$s=[Math]::Min(220/$i.Width,220/$i.Height);"
        "$b=[Drawing.Bitmap]::new($i,[int]($i.Width*$s),[int]($i.Height*$s));"
        "$b.Save($env:DST,[Drawing.Imaging.ImageFormat]::Png)"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True,
                   env={**os.environ, "SRC": src, "DST": str(FACE)}, creationflags=subprocess.CREATE_NO_WINDOW)


def record(path, secs=LISTEN_SECS):
    """Record the default mic to a WAV with Windows' built-in MCI. False if there's no mic."""
    q = lambda cmd: mci(cmd, None, 0, None) == 0
    if not q("open new type waveaudio alias chodrec"):
        return False
    try:
        q("set chodrec bitspersample 16 samplespersec 16000 channels 1")
        if not q("record chodrec"):
            return False
        time.sleep(secs)
        q("stop chodrec")
        return q(f'save chodrec "{path}"')
    finally:
        q("close chodrec")


_sfx_ids = iter(range(10**9))


def play_mp3(path, max_ms=None):
    """Play an mp3 via Windows MCI, optionally cut short. Blocks, so call it off the UI thread."""
    alias = f"sfx{next(_sfx_ids)}"
    if mci(f'open "{path}" type mpegvideo alias {alias}', None, 0, None) == 0:
        mci(f"set {alias} time format milliseconds", None, 0, None)
        mci(f"play {alias} from 0" + (f" to {max_ms}" if max_ms else "") + " wait", None, 0, None)
        mci(f"close {alias}", None, 0, None)


def sfx(name=None):
    """Play sfx/<name>.mp3, or a random one."""
    files = [SFX / f"{name}.mp3"] if name else list(SFX.glob("*.mp3"))
    files = [f for f in files if f.exists()]
    if files:
        play_mp3(random.choice(files), SFX_MAX_MS)


def bank_taunt(lang):
    """A random pre-recorded (text, mp3 path) from taunts/<lang>/, or None if that bank isn't made yet."""
    index = TAUNTS / lang / "taunts.json"
    if not index.exists():
        return None
    texts = json.loads(index.read_text(encoding="utf-8"))
    i = random.randrange(len(texts))
    return texts[i], TAUNTS / lang / f"{i:02}.mp3"


def make_taunts(client, lang, n=8):
    """Have Sarvam write n region-flavoured taunts and record each in the regional voice."""
    r = client.chat.completions(
        model="sarvam-105b-conversations",
        max_tokens=3000,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": (
            "You write lines for CHODBAK, a furious old-school desi army havaldar and PT sir in a consensual "
            "productivity game, who scolds a student for getting distracted from work. Catchphrase: \"Chodi mat kar!\". "
            "Swearing is fine; no slurs, no threats of real violence against people, no foreign words other than English."
        )}, {"role": "user", "content": (
            f'Return JSON {{"taunts": [...]}} with {n} different taunts in {LANGS[lang][0]}. '
            + ("Write them in that script, not romanized: Latin letters only for English words. "
               if lang not in ("hinglish", "english") else "") +
            "Each one or two short sentences, written to be SHOUTED aloud in fury: exclamation marks, a few words "
            "in CAPS, stretched words. Make them regional: idioms, family words for mum and dad, foods, "
            "films, festivals and exam pressure typical of that language's region. Mix in phone/reels distraction, "
            "the student's AI coding agent being held hostage, and mummy finding out."
        )}],
    )
    texts = [t.strip() for t in json.loads(r.choices[0].message.content)["taunts"] if t.strip()][:n]
    out = TAUNTS / lang
    out.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(texts):
        (out / f"{i:02}.mp3").write_bytes(speak(client, lang, text, level=3, codec="mp3"))  # nags are angry
    (out / "taunts.json").write_text(json.dumps(texts, ensure_ascii=False, indent=1), encoding="utf-8")
    mom = mom_line(client, lang)  # the last taunt too, so the web app can say it without a key
    (out / "mom.mp3").write_bytes(speak(client, lang, mom, level=2, codec="mp3"))
    (out / "mom.txt").write_text(mom, encoding="utf-8")
    return texts


def said_sorry_mummy(text):
    """Accept 'sorry' plus any desi word for mum, as romanized by speech-to-text."""
    t = text.lower()
    return bool(re.search(r"s[oa]+r+[yie]+", t)) and bool(
        re.search(r"mumm|mumy|mommy|\bmom\b|mamma|\bmaa?\b|amma|\baai\b|\bbebe\b|\bammi\b", t))


def find_hostage():
    """Name of a coding agent the user has running, or None."""
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.lower()
    except OSError:
        return None
    return next((name for exe, name in AGENTS.items() if f'"{exe}"' in out), None)


def taunt(client, lang, level, fled_to, hostage=None):
    threat = (
        f'You are holding their AI coding agent "{hostage}" hostage. Threaten that if they stay distracted, '
        f"you will kill {hostage} or force it to write spaghetti code and push to main. " if hostage and level >= 2 else ""
    )
    system = (
        "You are CHODBAK, a furious old-school desi army havaldar and PT sir overseeing a desi student who must stay focused. "
        'Your catchphrase is "Chodi mat kar!". '
        f'The student just sneaked away from their work to "{fled_to}". '
        f"This is warning {level} of 3: be {MOODS[level]}. "
        f"Bark at them in {LANGS[lang][0]} (keep that script, don't romanize), sprinkled with desi drill-ground shouts "
        "(Saavdhan!, Oye!, Nalayak, Nikamma, Chal bhaag) and desi references "
        "(Sharma ji ka beta, chappal, log kya kahenge, board exams, mummy). Swearing is fine. "
        + threat +
        "Use only English and that Indian language: no German or any other foreign words. "
        "No slurs, no threats of real violence against people, no references to real wars. "
        "It will be read aloud by a voice actor, so let punctuation carry the emotion (... for sighs, ! for shouting). "
        "At most 2 short sentences. Output only the line itself."
    )
    try:
        r = client.chat.completions(
            model="sarvam-105b-conversations",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": "Taunt me."}],
        )
        return (r.choices[0].message.content or "").strip().strip('"') or FALLBACK[level]
    except Exception:  # ponytail: no network shouldn't kill the watchdog
        return FALLBACK[level]


def mom_line(client, lang):
    """The last taunt, in the language they speak at home."""
    if lang in ("hinglish", "english"):
        return MOM_HINGLISH if lang == "hinglish" else MOM_LINE
    try:
        r = client.text.translate(input=MOM_LINE, source_language_code="en-IN",
                                  target_language_code=LANGS[lang][1], model="mayura:v1", mode="modern-colloquial")
        return r.translated_text or MOM_HINGLISH
    except Exception:
        return MOM_HINGLISH


def speak(client, lang, text, level=1, codec="wav"):
    """Text -> audio bytes in the guard's regional voice, delivered in that level's emotion (None if offline)."""
    try:
        r = client.text_to_speech.convert(
            text=text[:2500], language_code=LANGS[lang][1], speaker=VOICES[lang], model="bulbul:v3",
            output_audio_codec=codec, **EMOTION[level],
        )
        audio = base64.b64decode("".join(r.audios))
    except Exception:
        return None
    return louder(audio, GAIN[level]) if codec == "wav" else audio


def louder(wav, gain):
    """Boost a 16-bit WAV with tanh soft-clipping: quiet parts come up, peaks squash instead of crackling."""
    if gain == 1:
        return wav
    with wave.open(io.BytesIO(wav)) as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    samples = array.array("h", frames)
    samples = array.array("h", (int(32000 * math.tanh(gain * s / 32768)) for s in samples))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(samples.tobytes())
    return out.getvalue()


def play(wav):
    if wav:
        winsound.PlaySound(wav, winsound.SND_MEMORY)  # blocks; always called off the UI thread


def cooker_siti(whistles=3):
    """Pressure cooker whistle: rising hiss, then the scream."""
    for _ in range(whistles):
        for f in range(1400, 3000, 160):
            winsound.Beep(f, 25)
        winsound.Beep(3000, 500)
        time.sleep(0.25)


def bg(fn, *args):
    t = threading.Thread(target=fn, args=args, daemon=True)
    t.start()
    return t


def draw_pixels(canvas, rows, px, palette, ox=0, oy=0, flip=False):
    for y, row in enumerate(reversed(rows) if flip else rows):
        for x, ch in enumerate(row):
            if ch in palette:
                canvas.create_rectangle(ox + x * px, oy + y * px, ox + (x + 1) * px, oy + (y + 1) * px,
                                        fill=palette[ch], width=0)


def draw_desi_frame(canvas, img):
    """Gold photo frame with a marigold toran across the top, all chunky pixels."""
    b, top = 20, 26  # border width, toran height
    w, h = img.width() + 2 * b, img.height() + 2 * b
    canvas.config(width=w, height=h + top)
    canvas.create_rectangle(0, top, w, top + h, fill="#5a2d0c", width=0)  # wood
    canvas.create_rectangle(6, top + 6, w - 6, top + h - 6, fill="#d4af37", width=0)  # gold
    canvas.create_rectangle(14, top + 14, w - 14, top + h - 14, fill="#7a1010", width=0)  # maroon mount
    for x in range(10, w - 10, 16):  # gold studs
        for y in (top + 8, top + h - 12):
            canvas.create_rectangle(x, y, x + 4, y + 4, fill="#fff1a8", width=0)
    canvas.create_image(b, top + b, image=img, anchor="nw")
    for i, x in enumerate(range(0, w, 12)):  # marigold toran
        canvas.create_rectangle(x, 8, x + 12, 20, fill="#ff8c00" if i % 2 else "#ffc300", width=0)
        if i % 3 == 1:
            canvas.create_rectangle(x + 3, 20, x + 9, 32, fill="#2e8b3a", width=0)  # mango leaf


class Chodbak:
    def __init__(self, targets, lang, test=False):
        self.targets, self.lang, self.test = targets, lang, test
        key = load_key()
        self.client = SarvamAI(api_subscription_key=key) if key else None  # None until ask_key()
        self.root = tk.Tk()
        self.root.withdraw()
        self.q = queue.Queue()  # callables from worker threads, run on the UI thread
        self.strikes, self.struck, self.today = 0, False, 0
        self.last_good = self.bad = None
        self.bad_title, self.last_taunt, self.last_wav, self.mom = "", FALLBACK[3], None, MOM_HINGLISH
        now = time.time()
        self.away_since, self.good_since, self.last_nag, self.next_chai = None, now, 0, now + CHAI_EVERY
        self.popup, self.popup_id, self.level, self.listening = None, 0, 0, False
        self.hostage, self.hostage_hp = None, 0  # hp counts up as the hostage's situation gets worse

    # --- watching -------------------------------------------------------
    def pump(self):
        while not self.q.empty():
            self.q.get()()
        self.root.after(150, self.pump)

    def tick(self):
        hwnd, title, exe, pid = foreground()
        now = time.time()
        if pid != os.getpid() and title not in IGNORE_TITLES:
            if matches(title, exe, self.targets):
                if self.struck:
                    self.good_since, self.next_chai = now, now + CHAI_EVERY
                    if self.level < 3:  # level 3 only ends with "sorry mummy"
                        self.close_popup()
                self.away_since, self.struck, self.last_good = None, False, hwnd
                if now - self.good_since > RESET_AFTER:
                    self.strikes = 0
                if now >= self.next_chai:
                    self.next_chai = now + CHAI_EVERY
                    self.chai_toast()
            elif self.last_good is None:
                pass  # haven't started working yet, nothing to leave
            elif self.away_since is None:
                self.away_since, self.bad, self.bad_title = now, hwnd, title or exe
            elif not self.struck and now - self.away_since >= GRACE:
                self.strike()
            elif self.struck and self.strikes == 3 and now - self.last_nag >= NAG_EVERY:
                self.nag()
        self.root.after(400, self.tick)

    def strike(self):
        self.struck, self.last_nag = True, time.time()
        self.strikes = level = min(self.strikes + 1, 3)
        self.today += 1
        meme = bg(sfx, LEVEL_SFX[level])
        if level == 2:
            self.family_gossip()
        if level == 3:
            yank_back(self.bad, self.last_good)
            bg(cooker_siti)
            self.throw_chappal()
        self.show_popup(level)
        pid = self.popup_id

        def work():
            text = taunt(self.client, self.lang, level, self.bad_title, self.hostage)
            wav = speak(self.client, self.lang, text, level) if text != FALLBACK[level] else None
            banked = None if wav else bank_taunt(self.lang)  # API down: use a pre-recorded line
            if banked:
                text = banked[0]
            self.q.put(lambda: self.set_body(pid, text))
            meme.join()  # let the meme land before the guard starts talking
            play_mp3(banked[1]) if banked else play(wav)
            self.last_taunt, self.last_wav = text, wav
            if level == 3:  # the last taunt
                self.q.put(lambda: (self.set_body(pid, f"{text}\n\n{self.mom}"), self.calling_toast()))
                play(speak(self.client, self.lang, self.mom, level=2))  # cold, disappointed, after all the shouting

        bg(work)

    def nag(self):
        # a fresh pre-recorded taunt each nag (no API calls); without a bank, replay the last one
        self.last_nag = time.time()
        self.hostage_hp = min(self.hostage_hp + 1, len(HOSTAGE_STATES) - 1)
        yank_back(self.bad, self.last_good)
        bg(cooker_siti, 1)
        banked = bank_taunt(self.lang)
        if banked:
            self.last_taunt = banked[0]
        bg(lambda: (sfx(), play_mp3(banked[1]) if banked else play(self.last_wav)))  # meme, then the guard
        self.throw_chappal()
        if not self.popup:
            self.show_popup(3)
        self.set_body(self.popup_id, f"{self.last_taunt}\n\n{self.mom}")
        self.refresh_hostage()
        self.popup.lift()
        self.shake()

    def set_body(self, pid, text):
        if pid == self.popup_id and self.popup:
            self.body.config(text=text)

    def refresh_hostage(self):
        if self.popup and self.hostage:
            self.hostage_lbl.config(text=f"HOSTAGE: {self.hostage}  >  {HOSTAGE_STATES[self.hostage_hp]}")

    # --- pixel windows --------------------------------------------------
    def window(self, color):
        """Borderless, always-on-top window with a chunky pixel border. Returns (window, inner frame)."""
        w = tk.Toplevel(self.root, bg=color)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        inner = tk.Frame(w, bg=BG)
        inner.pack(padx=8, pady=8)
        return w, inner

    def place(self, w, where="center"):
        w.update_idletasks()
        sw, sh, ww, wh = w.winfo_screenwidth(), w.winfo_screenheight(), w.winfo_width(), w.winfo_height()
        pos = ((sw - ww) // 2, (sh - wh) // 3) if where == "center" else (sw - ww - 24, sh - wh - 72)
        w.geometry("+%d+%d" % pos)
        return pos

    def guard_dialog(self, color, header):
        """Guard sprite on the left, returns the right-hand column to fill."""
        w, inner = self.window(color)
        c = tk.Canvas(inner, width=160, height=160, bg=BG, highlightthickness=0)
        draw_pixels(c, GUARD, 10, PALETTE)
        c.pack(side="left", padx=20, pady=20)
        col = tk.Frame(inner, bg=BG)
        col.pack(side="left", padx=(0, 24), pady=20)
        tk.Label(col, text="C H O D B A K", font=("Terminal", 10), fg="#777", bg=BG).pack(anchor="w")
        tk.Label(col, text=header, font=("Terminal", 28), fg=color, bg=BG).pack(anchor="w")
        return w, col

    def show_popup(self, level):
        self.close_popup()
        self.popup_id += 1
        self.level = level
        header, color = HEADERS[level]
        w, inner = self.window(color)
        self.popup = w

        left = tk.Frame(inner, bg=BG)
        left.pack(side="left", padx=20, pady=20)
        if level == 2 and FACE.exists():
            self.face_img = tk.PhotoImage(file=FACE)  # keep a reference or Tk drops it
            c = tk.Canvas(left, bg=BG, highlightthickness=0)
            draw_desi_frame(c, self.face_img)
            c.pack()
            tk.Label(left, text="DISAPPOINTED HAIN\nTUJHSE.", font=("Terminal", 14), fg="#ffc300", bg=BG).pack(pady=(8, 0))
        else:
            c = tk.Canvas(left, width=160, height=160, bg=BG, highlightthickness=0)
            draw_pixels(c, GUARD, 10, PALETTE)
            c.pack()

        col = tk.Frame(inner, bg=BG)
        col.pack(side="left", padx=(0, 24), pady=20)
        lbl = lambda text, font, fg, **kw: tk.Label(col, text=text, font=font, fg=fg, bg=BG, justify="left", **kw)
        lbl("C H O D B A K", ("Terminal", 10), "#777").pack(anchor="w")
        lbl(header, ("Terminal", 28), color).pack(anchor="w")
        lbl(f"WARNING {level}/3  >  {self.bad_title[:45]}", ("Terminal", 10), "#aaa").pack(anchor="w")
        lbl(f"LOG KYA KAHENGE? aaj {self.today} baar bhaage.", ("Terminal", 10), "#aaa").pack(anchor="w")
        self.hostage_lbl = lbl("", ("Terminal", 10), "#e83b3b")
        if self.hostage and level >= 2:
            self.hostage_lbl.pack(anchor="w")
            self.refresh_hostage()
        tk.Frame(col, bg=BG, height=10).pack()
        self.body = lbl("...", INDIC, "#ffffff", wraplength=420)
        self.body.pack(anchor="w")
        lbl("CHODI MAT KAR!", ("Terminal", 18), color).pack(anchor="w", pady=(10, 0))

        btns = tk.Frame(col, bg=BG)
        btns.pack(anchor="w", pady=(14, 0))
        if level < 3:
            tk.Button(btns, text="JI SIR! WAPAS JAATA HOON", bg=color, fg="#000", command=self.go_back, **BTN).pack(side="left")
            tk.Button(btns, text="MAIN KAMZOR HOON (stay)", bg="#3a3a46", fg="#ddd", command=self.close_popup,
                      **BTN).pack(side="left", padx=10)
        else:  # the only way out: say sorry to mummy
            self.status = lbl('Mic pe bol: "SORRY MUMMY"', PIX, "#aaa")
            self.status.pack(anchor="w", pady=(10, 4), before=btns)
            self.mic_btn = tk.Button(btns, text=f"BOLO ({LISTEN_SECS} SEC)", bg=color, fg="#000",
                                     command=lambda: self.listen(btns), **BTN)
            self.mic_btn.pack(side="left")

        self.pos = self.place(w)
        if level == 3:
            self.shake()

    def listen(self, btns):
        if self.listening:
            return
        self.listening = True
        pid = self.popup_id
        self.status.config(text="SUN RAHA HOON... bol!", fg="#7ee081")

        def work():
            path = os.path.join(tempfile.gettempdir(), "chodbak_sorry.wav")
            heard = None
            if record(path):
                try:
                    with open(path, "rb") as f:
                        heard = self.client.speech_to_text.transcribe(
                            file=f, model="saaras:v3", mode="translit", language_code="unknown").transcript
                except Exception:
                    heard = ""
            self.q.put(lambda: self.heard(pid, heard, btns))

        bg(work)

    def heard(self, pid, text, btns):
        self.listening = False
        if pid != self.popup_id or not self.popup:
            return
        if text is None:  # no mic: fall back to typing it
            self.status.config(text='Mic nahi mila. Type kar: "sorry mummy"', fg="#f59342")
            self.mic_btn.pack_forget()
            entry = tk.Entry(btns, font=PIX, width=22, bg="#22222c", fg="#fff", insertbackground="#fff", relief="flat")
            entry.pack(side="left", ipady=6)
            entry.bind("<Return>", lambda e: said_sorry_mummy(entry.get()) and self.forgiven())
            entry.focus_force()
        elif said_sorry_mummy(text):
            self.forgiven()
        else:
            self.status.config(text=f'Suna: "{text[:40]}". ZOR SE! "SORRY MUMMY"', fg="#e83b3b")
            bg(sfx, "cat_laugh")
            self.shake()

    def forgiven(self):
        self.strikes = self.hostage_hp = 0  # mummy forgives, the guard resets, the hostage breathes
        self.go_back()

    def shake(self, n=16):
        if not self.popup:
            return
        dx, dy = (random.randint(-16, 16), random.randint(-16, 16)) if n else (0, 0)
        self.popup.geometry(f"+{self.pos[0] + dx}+{self.pos[1] + dy}")
        if n:
            self.root.after(35, self.shake, n - 1)

    def throw_chappal(self):
        """A spinning pixel chappal arcs across the whole screen."""
        key = "#ff00ff"  # this colour becomes see-through
        w = tk.Toplevel(self.root, bg=key)
        w.overrideredirect(True)
        w.attributes("-topmost", True, "-transparentcolor", key)
        c = tk.Canvas(w, width=135, height=60, bg=key, highlightthickness=0)
        c.pack()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        right = random.random() < 0.5

        def frame(i, steps=45):
            if i > steps:
                return w.destroy()
            c.delete("all")
            draw_pixels(c, CHAPPAL, 9, PALETTE, flip=(i // 3) % 2)
            t = i / steps
            x = -150 + (sw + 300) * (1 - t if right else t)
            y = sh * 0.65 - math.sin(t * math.pi) * sh * 0.45
            w.geometry(f"+{int(x)}+{int(y)}")
            self.root.after(22, frame, i + 1)

        frame(0)

    def toast(self, color, sprite, palette, title, text, secs):
        w, inner = self.window(color)
        c = tk.Canvas(inner, width=64, height=64, bg=BG, highlightthickness=0)
        draw_pixels(c, sprite, 8, palette)
        c.pack(side="left", padx=14, pady=14)
        txt = tk.Frame(inner, bg=BG)
        txt.pack(side="left", padx=(0, 18))
        head = tk.Label(txt, text=title, font=("Terminal", 18), fg=color, bg=BG)
        head.pack(anchor="w")
        tk.Label(txt, text=text, font=PIX, fg="#ddd", bg=BG).pack(anchor="w")
        self.place(w, "corner")
        self.root.after(secs * 1000, w.destroy)
        return head

    def family_gossip(self, n=4):
        """Rishtedaar alert: fake family WhatsApp group lights up about where you went."""
        app = (self.bad_title.split(" - ")[0] or "phone")[:25]
        msgs = random.sample(FAMILY, n)
        w, inner = self.window("#25d366")
        tk.Label(inner, text="FAMILY GROUP (47)  muted? nahi.", font=PIX, fg="#25d366", bg=BG).pack(anchor="w", padx=12, pady=(10, 4))
        box = tk.Frame(inner, bg=BG)
        box.pack(anchor="w", padx=12, pady=(0, 10))
        self.place(w, "corner")

        def add(i):
            if i == n or not w.winfo_exists():
                return self.root.after(6000, lambda: w.winfo_exists() and w.destroy())
            who, msg = msgs[i]
            tk.Label(box, text=who, font=("Nirmala UI", 9, "bold"), fg="#ffc300", bg=BG).pack(anchor="w")
            tk.Label(box, text=msg.format(app=app), font=("Segoe UI Emoji", 10), fg="#ddd", bg=BG,
                     wraplength=300, justify="left").pack(anchor="w", pady=(0, 4))
            self.place(w, "corner")
            bg(sfx, "ye_le") if i == 0 else bg(winsound.MessageBeep)
            self.root.after(1400, add, i + 1)

        self.root.after(2500, add, 0)  # after the cat has finished laughing

    def chai_toast(self):
        self.toast("#2e8b3a", CHAI, CHAI_PAL, "SHABAASH!", "25 min focus. Chai break kamaya.", 9)
        bg(winsound.MessageBeep)

    def calling_toast(self):
        """Fake call. Mummy is never actually called. Probably."""
        head = self.toast("#e83b3b", PHONE, PHONE_PAL, "CALLING MUMMY...", "tring tring...", 10)

        def ring():
            for _ in range(3):
                for _ in range(2):
                    winsound.Beep(440, 350)
                    winsound.Beep(480, 350)
                time.sleep(0.6)
            self.q.put(lambda: head.winfo_exists() and head.config(text="LINE BUSY. Agli baar pakka."))

        bg(ring)

    # --- first run ------------------------------------------------------
    def text_step(self, header, prompt, button, save, secret=False, initial=""):
        """Pixel dialog with one text box. save(text) returns True to close, False to keep asking."""
        def ask(then):
            w, col = self.guard_dialog("#d4af37", header)
            tk.Label(col, text=prompt, font=PIX, fg="#ddd", bg=BG, justify="left").pack(anchor="w", pady=10)
            row = tk.Frame(col, bg=BG)
            row.pack(anchor="w")
            entry = tk.Entry(row, font=PIX, width=42, bg="#22222c", fg="#fff", insertbackground="#fff",
                             relief="flat", show="*" if secret else "")
            entry.insert(0, initial)
            entry.pack(side="left", ipady=6)

            def done(_=None):
                if save(entry.get().strip()):
                    w.destroy()
                    then()
                else:
                    entry.config(bg="#5a1e1e")

            entry.bind("<Return>", done)
            tk.Button(row, text=button, bg="#d4af37", fg="#000", command=done, **BTN).pack(side="left", padx=10)
            self.place(w)
            entry.focus_force()
        return ask

    def ask_key(self, then):
        def save(key):
            if not key:
                return False
            lines = [l for l in (ENV.read_text(encoding="utf-8-sig").splitlines() if ENV.exists() else [])
                     if not l.startswith("SARVAM_API_KEY=")]
            ENV.write_text("\n".join(lines + [f"SARVAM_API_KEY={key}"]) + "\n", encoding="utf-8")
            self.client = SarvamAI(api_subscription_key=key)
            return True
        self.text_step("SARVAM KEY", "CHODBAK ki awaaz Sarvam AI se aati hai.\n\nFree key: dashboard.sarvam.ai > API Keys.\n"
                       f"Paste it here. It is saved only in:\n{ENV}", "SAVE", save, secret=True)(then)

    def ask_targets(self, then):
        def save(text):
            targets = [t.strip() for t in text.split(",") if t.strip()]
            if targets:
                self.targets = targets
                save_prefs(targets=targets)
            return bool(targets)
        self.text_step("DUTY POST", "Kaunse apps / tabs mein rehna hai? Comma separated.\n\n"
                       "Window title or exe name, e.g.  Visual Studio Code, Notion, chrome.exe",
                       "LOCK IN", save, initial=", ".join(self.targets))(then)

    def pick_language(self, then):
        """Asks innocently. The answer decides which language mummy gets 'called' in."""
        w, col = self.guard_dialog("#d4af37", "NAYI BHARTI")
        tk.Label(col, text="Recruit registration.\n\nGhar pe kaunsi bhasha bolte ho?",
                 font=PIX, fg="#ddd", bg=BG, justify="left").pack(anchor="w", pady=10)
        grid = tk.Frame(col, bg=BG)
        grid.pack(anchor="w")

        def choose(name):
            self.lang = name
            save_prefs(lang=name)
            w.destroy()
            then()

        for i, (name, (_, _, label)) in enumerate(LANGS.items()):
            tk.Button(grid, text=label, font=("Nirmala UI", 12, "bold"), width=10, relief="flat", bd=0,
                      bg="#3a3a46", fg="#fff", activebackground="#d4af37",
                      command=lambda n=name: choose(n)).grid(row=i // 4, column=i % 4, padx=4, pady=4)
        self.place(w)

    def register(self, then):
        """Asks for a photo and doesn't say why. It comes back at level 2."""
        w, col = self.guard_dialog("#d4af37", "NAYI BHARTI")
        tk.Label(col, text="Recruit registration, last step.\n\nUpload a photo of someone whose opinion\n"
                           "matters to you.\n\nKyun? Classified. Bas upload kar.",
                 font=PIX, fg="#ddd", bg=BG, justify="left").pack(anchor="w", pady=10)
        btns = tk.Frame(col, bg=BG)
        btns.pack(anchor="w")

        def pick():
            w.attributes("-topmost", False)
            src = filedialog.askopenfilename(parent=w, title="Choose the photo",
                                             filetypes=[("Photos", "*.jpg *.jpeg *.png *.bmp *.gif")])
            if src:
                try:
                    save_face(src)
                except subprocess.CalledProcessError:
                    pass  # unreadable image: level 2 falls back to the guard
            w.destroy()
            then()

        tk.Button(btns, text="PHOTO CHUNO", bg="#d4af37", fg="#000", command=pick, **BTN).pack(side="left")
        tk.Button(btns, text="BAAD MEIN", bg="#3a3a46", fg="#ddd", command=lambda: (w.destroy(), then()),
                  **BTN).pack(side="left", padx=10)
        self.place(w)

    # --- lifecycle ------------------------------------------------------
    def go_back(self):
        self.close_popup()
        yank_back(self.bad, self.last_good)  # works best here: our click makes us the foreground app

    def close_popup(self):
        if self.popup:
            self.popup.destroy()
            self.popup, self.level = None, 0
            if self.test:
                self.root.quit()

    def prepare(self):
        """Translate the last taunt and pick a hostage once, up front, so strikes aren't waiting on it."""
        bg(lambda: setattr(self, "mom", mom_line(self.client, self.lang)))
        bg(lambda: setattr(self, "hostage", find_hostage()))

    def start(self):
        self.prepare()
        print(f"CHODBAK on duty ({self.lang}). Stay in: {', '.join(self.targets)}")
        print("Close this window (or Ctrl+C) to desert.")
        self.tick()

    def test_drill(self, level):
        self.prepare()
        self.bad_title, self.strikes = "test drill", level - 1
        self.root.after(300, self.strike)

    def run(self, test_level=None, setup=False):
        self.pump()
        steps = [self.ask_key] if not self.client else []
        if not test_level:
            steps += [s for s, needed in ((self.pick_language, setup or not self.lang),
                                          (self.ask_targets, setup or not self.targets),
                                          (self.register, setup or not FACE.exists())) if needed]
        finish = (lambda: self.test_drill(test_level)) if test_level else self.start

        def next_step():
            steps.pop(0)(next_step) if steps else finish()

        next_step()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="CHODBAK - chodi mat kar!")
    p.add_argument("targets", nargs="*", help="window title or exe substrings you must stay in (default: saved)")
    p.add_argument("--lang", choices=LANGS, help="override the language picked on first run")
    p.add_argument("--test", type=int, choices=[1, 2, 3], help="show one warning level and exit")
    p.add_argument("--setup", action="store_true", help="redo the first-run questions")
    p.add_argument("--make-taunts", nargs="*", metavar="LANG", choices=LANGS,
                   help="(re)generate the pre-recorded taunt bank for these languages, or all of them")
    a = p.parse_args()
    if a.make_taunts is not None:
        client = SarvamAI(api_subscription_key=load_key())
        for name in a.make_taunts or LANGS:
            print(name, len(make_taunts(client, name)), "taunts", flush=True)
        raise SystemExit
    prefs = load_prefs()
    lang = a.lang or prefs.get("lang") or ("hinglish" if a.test else None)
    Chodbak(a.targets or prefs.get("targets", []), lang, test=bool(a.test)).run(a.test, a.setup)
