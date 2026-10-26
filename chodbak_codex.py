"""Windows focus watchdog. Run with Python; uses only sarvamai and the standard library."""

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import io
import json
import math
import os
from pathlib import Path
import queue
import random
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
import wave
import winsound

import httpx
from sarvamai import SarvamAI
from chat import get_api_key

PHRASE = "sorry mummy"
LANGUAGES = {
    "Hinglish": "hi-IN", "Hindi": "hi-IN", "Bengali": "bn-IN",
    "Gujarati": "gu-IN", "Kannada": "kn-IN", "Malayalam": "ml-IN",
    "Marathi": "mr-IN", "Odia": "od-IN", "Punjabi": "pa-IN",
    "Tamil": "ta-IN", "Telugu": "te-IN", "English": "en-IN",
}
BG, PANEL, INK, MUTED = "#121a1c", "#1d292b", "#f2e8cf", "#a0afaa"
GREEN, RED, GOLD = "#b9d781", "#f4846d", "#f0bf61"
MONO, BODY = ("Consolas", 11), ("Nirmala UI", 11)
SFX_DIR = Path(__file__).with_name("New folder")
SFX = (
    "metal pipe falling sound effect.mp3",
    "Cat Laughing Meme Sound Effect.mp3",
    "FAAAA! [Funny Trending Meme Sound Effect].mp3",
    "Ye le meme notification sound ringtone #memes#funny#viralvideo#soundeffect#ringtone#shortvideo.mp3",
)


def terms(text):
    return tuple(part.strip().casefold() for part in text.split(",") if part.strip())


def matches(process, title, apps, titles):
    process = process.casefold().removesuffix(".exe")
    return (any(process == app.removesuffix(".exe") for app in apps)
            or any(term in title.casefold() for term in titles))


def apologised(text):
    return " ".join(text.casefold().split()) == PHRASE


@dataclass
class Patrol:
    armed: bool = False
    strikes: int = 0

    def observe(self, allowed):
        departed = self.armed and not allowed
        self.armed = allowed
        if departed:
            self.strikes = min(3, self.strikes + 1)
            return self.strikes
        return 0


class Desktop:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        # Explicit handle types prevent pointer truncation on 64-bit Windows.
        signatures = [
            (self.user.GetForegroundWindow, [], wintypes.HWND),
            (self.user.GetWindowTextW, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user.GetWindowThreadProcessId, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            (self.kernel.OpenProcess, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            (self.kernel.QueryFullProcessImageNameW, [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.kernel.CloseHandle, [wintypes.HANDLE], wintypes.BOOL),
        ]
        for function, args, result in signatures:
            function.argtypes, function.restype = args, result

    def foreground(self):
        window = self.user.GetForegroundWindow()
        if not window:
            return None
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return None
        title = ctypes.create_unicode_buffer(4096)
        self.user.GetWindowTextW(window, title, len(title))
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        # Unreadable processes are unknown, not distractions.
        if not handle:
            return None
        try:
            image = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(image))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
                return None
            return Path(image.value).name, title.value
        finally:
            self.kernel.CloseHandle(handle)


def parse_lines(content):
    data = json.loads(content)
    names = ("warning", "taunt", "last", "caption", "hostage")
    if not isinstance(data, dict) or any(
        not isinstance(data.get(name), str) or not 1 <= len(data[name].strip()) <= 240
        for name in names
    ):
        raise ValueError("Unusable warning text")
    return {name: data[name].strip() for name in names}


def decode_audio(encoded):
    data = base64.b64decode(encoded, validate=True)
    with wave.open(io.BytesIO(data), "rb") as audio:
        if not 0 < audio.getnframes() / audio.getframerate() <= 90:
            raise ValueError("Unusable speech duration")
    return data


def preparation_error(error):
    code = getattr(error, "status_code", None)
    if code:
        return f"Sarvam returned HTTP {code}. Check API access, key and credits; then retry."
    if isinstance(error, httpx.TimeoutException):
        return "Sarvam timed out. Check your connection and retry."
    if isinstance(error, (httpx.RequestError, OSError)):
        return "Cannot connect to Sarvam. Run this app outside a restricted sandbox and check your connection."
    if isinstance(error, (ValueError, wave.Error, EOFError)):
        return "Sarvam returned unusable text or audio. Please retry."
    return f"Preparation failed ({type(error).__name__}). Please retry."


class AudioPlayer:
    """Windows' native MP3 player handles two-second stings; WAV handles speech."""

    def __init__(self, root, on_error):
        self.root, self.on_error, self.after_id = root, on_error, None
        self.alias = f"chodbak_sfx_{os.getpid()}"
        self.mci = ctypes.WinDLL("winmm").mciSendStringW
        self.mci.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HWND]
        self.mci.restype = wintypes.DWORD

    def stop(self):
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.mci(f"close {self.alias}", None, 0, None)
        winsound.PlaySound(None, 0)

    def play(self, speech, sting):
        self.stop()
        if sting.exists() and self.mci(f'open "{sting}" type mpegvideo alias {self.alias}', None, 0, None) == 0:
            self.mci(f"set {self.alias} time format milliseconds", None, 0, None)
            length = ctypes.create_unicode_buffer(32)
            code = self.mci(f"status {self.alias} length", length, len(length), None)
            duration = min(2000, int(length.value)) if code == 0 and length.value.isdigit() else 2000
            if self.mci(f"play {self.alias} from 0 to {duration}", None, 0, None) == 0:
                self.after_id = self.root.after(duration + 40, lambda: self.speak(speech))
                return
        self.speak(speech)

    def speak(self, path):
        self.after_id = None
        self.mci(f"close {self.alias}", None, 0, None)
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except RuntimeError:
            self.on_error("Audio playback failed. Visual warnings remain active.")


def prepare_session(key, language, cancelled):
    if cancelled.is_set():
        return None
    client = SarvamAI(api_subscription_key=key, timeout=30)
    response = client.chat.completions(
        model="sarvam-105b-conversations",
        reasoning_effort=None,
        max_tokens=1400,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": (
                "Write dialogue for CHODBAK, a fictional pixel-art desi army drill havaldar "
                "in a consensual adult productivity game. Gruff, funny parade-ground commands. "
                "Adult swearing is wanted; target procrastination, not identity or human worth. "
                "No real violence or threats to real people. Reply only with a JSON object."
            )},
            {"role": "user", "content": (
                f"Preferred language: {language}. Use its native script; Hinglish uses Roman Hindi. "
                "Return five strings, each under 180 characters, with exactly these keys: "
                "warning: a simple first warning to return to work, no swearing; "
                "taunt: a sharper, sweary second warning about getting distracted; "
                "caption: a funny photo-frame caption meaning 'I am not angry, just disappointed'; "
                "hostage: a cartoon threat to delete fictional PIXEL Agent 404 if distraction continues; "
                "last: ONLY the natural translation of 'Should I call your mom?' in the preferred language. "
                "Do not include English translations alongside the chosen language."
            )},
        ],
        request_options={"max_retries": 0},
    )
    lines = parse_lines(response.choices[0].message.content)
    spoken = [lines["warning"], lines["taunt"],
              f'{lines["caption"]} {lines["hostage"]} {lines["last"]}']
    sounds = []
    for text in spoken:
        if cancelled.is_set():
            return None
        speech = client.text_to_speech.convert(
            text=text, language_code=LANGUAGES[language], model="bulbul:v3",
            speaker="shubh", output_audio_codec="wav", speech_sample_rate=22050,
            request_options={"max_retries": 0},
        )
        if not speech.audios:
            raise ValueError("Speech response was empty")
        sounds.append(decode_audio(speech.audios[0]))
    return lines, sounds


def guard(parent, scale=4, captive=False, deleted=False):
    sprite = [
        "....OOOOOOOO....", "...OHHHHHHHHO...", "...OHHHHHHHHO...",
        "..OOOOOOOOOOOO..", "...OSSSSSSSSO...", "...OSKSSSKSSO...",
        "...OSSSSSSSSO...", "....OSKKKSO.....", ".....OSSSO......",
        "...OOBBBBBOO....", "..OBBBBBBBBBO...", "..OBBOBBBOBBO...",
        "..OSSOBBBO SSO..".replace(" ", ""), "...OOBBGBBOO....",
        "....OBBBBO......", "....OB OBO......".replace(" ", "."),
        "....OK.OKO......", "...OOK.OOKO.....",
    ]
    canvas = tk.Canvas(parent, width=16 * scale, height=19 * scale,
                       bg=PANEL, highlightthickness=0)
    palette = {"O": "#080e11", "H": "#66784a", "S": "#dba579",
               "K": "#28332c", "B": "#718452", "G": GOLD}
    if deleted:
        canvas.create_text(32, 30, text="404", fill=RED, font=("Consolas", 14, "bold"))
        canvas.create_text(32, 60, text="RIP", fill=MUTED, font=MONO)
    else:
        for y, row in enumerate(sprite):
            for x, pixel in enumerate(row):
                if pixel in palette:
                    canvas.create_rectangle(x * scale, y * scale, (x + 1) * scale,
                                            (y + 1) * scale, fill=palette[pixel], width=0)
    if captive:
        for x in (1, 5, 10, 14):
            canvas.create_rectangle(x * scale, 0, (x + 1) * scale, 19 * scale,
                                    fill="#87918b", width=0)
    return canvas


class Chodbak:
    def __init__(self, root):
        self.root, self.desktop = root, Desktop()
        self.patrol, self.alerts = Patrol(), []
        self.photo = None
        self.running = self.pending = self.locked = False
        self.session, self.results = 0, queue.Queue()
        self.cancelled = threading.Event()
        self.audio_dir = tempfile.TemporaryDirectory(prefix="chodbak-")
        self.sounds = []
        self.repeat_interval = 25
        root.title("CHODBAK // Chodi mat kar")
        root.configure(bg=BG)
        root.geometry("650x790")
        root.minsize(650, 790)
        root.bind_all("<Escape>", lambda event: self.stop())
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=INK, arrowcolor=GREEN, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", INK)])

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=22)
        header = tk.Frame(body, bg=PANEL, highlightbackground=GREEN, highlightthickness=2)
        header.pack(fill="x", pady=(0, 18))
        guard(header, 5).pack(side="left", padx=16, pady=12)
        words = tk.Frame(header, bg=PANEL)
        words.pack(side="left", fill="x", expand=True)
        self.label(words, "CHODBAK", ("Consolas", 32, "bold"), GREEN, PANEL).pack(anchor="w")
        self.label(words, "CHODI MAT KAR", MONO, GOLD, PANEL).pack(anchor="w")
        self.label(words, "FOCUS PATROL / AGENT 404 IN CUSTODY", ("Consolas", 9), MUTED, PANEL).pack(anchor="w", pady=(8, 0))

        self.label(body, "01 / FIRST, CHOOSE YOUR LANGUAGE", MONO, GREEN).pack(anchor="w")
        self.language = ttk.Combobox(body, values=list(LANGUAGES), state="readonly", font=BODY)
        self.language.pack(fill="x", pady=(6, 12))
        self.label(body, "02 / CHOOSE A PHOTO FOR FOCUS REMINDERS", MONO, GREEN).pack(anchor="w")
        self.photo_button = self.button(body, "CHOOSE PHOTO  [ PNG / GIF ]", self.choose_photo, PANEL, INK)
        self.photo_button.pack(fill="x", pady=(6, 3))
        self.photo_label = self.label(body, "Stays on this computer. Never sent to Sarvam.", ("Nirmala UI", 9), MUTED)
        self.photo_label.pack(anchor="w", pady=(0, 12))
        self.label(body, "03 / APPS TO STAY IN", MONO, GREEN).pack(anchor="w")
        self.apps = self.entry(body)
        self.apps.pack(fill="x", pady=(6, 3))
        self.label(body, "Process names, comma separated: notepad.exe, figma.exe", ("Nirmala UI", 9), MUTED).pack(anchor="w")
        self.label(body, "OR WINDOW / TAB TITLE CONTAINS", MONO, GREEN).pack(anchor="w", pady=(10, 0))
        self.titles = self.entry(body)
        self.titles.pack(fill="x", pady=(6, 3))
        self.label(body, "Title fragments, comma separated. Any app OR title match is allowed.", ("Nirmala UI", 9), MUTED).pack(anchor="w")
        self.label(body, "01 WARNING  >  02 ROAST  >  03 COURT-MARTIAL", MONO, GOLD).pack(anchor="w", pady=(16, 2))
        self.label(body, f'Three popups + voice. Type "{PHRASE}" to end the session.', ("Nirmala UI", 10), INK).pack(anchor="w")
        self.status = tk.StringVar(value="OFF DUTY. Choose a language, photo and focus target.")
        self.audio = AudioPlayer(root, self.status.set)
        tk.Label(body, textvariable=self.status, bg=PANEL, fg=GOLD, font=BODY,
                 wraplength=555, justify="left", anchor="w", padx=12, pady=10).pack(fill="x", pady=14)
        controls = tk.Frame(body, bg=BG)
        controls.pack(fill="x")
        self.start_button = self.button(controls, "REPORT FOR DUTY", self.start, GREEN, BG)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(controls, "EMERGENCY STOP / ESC", self.stop, RED, BG).pack(side="left", fill="x", expand=True)
        self.label(body, "Sarvam prepares text + voice once per start. Local checks every 350 ms.", ("Nirmala UI", 9), MUTED).pack(anchor="w", pady=(10, 0))
        root.after(100, self.poll)

    @staticmethod
    def label(parent, text, font=BODY, color=INK, bg=BG):
        return tk.Label(parent, text=text, bg=bg, fg=color, font=font, justify="left",
                        wraplength=330 if bg == PANEL else 580)

    @staticmethod
    def entry(parent):
        return tk.Entry(parent, bg=PANEL, fg=INK, insertbackground=GREEN, font=BODY,
                        relief="flat", highlightthickness=1, highlightbackground=MUTED,
                        highlightcolor=GREEN)

    @staticmethod
    def button(parent, text, command, bg, fg):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground=GOLD, activeforeground=BG, font=("Consolas", 10, "bold"),
                         relief="flat", padx=10, pady=9, cursor="hand2")

    def choose_photo(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose your focus photo (local only)",
                                          filetypes=[("Photo", "*.png *.gif")])
        if not path:
            return
        try:
            photo = tk.PhotoImage(file=path, master=self.root)
            factor = max(1, math.ceil(photo.width() / 280), math.ceil(photo.height() / 170))
            self.photo = photo.subsample(factor)
            self.photo_label.configure(text=f"{Path(path).name} / local only")
        except tk.TclError:
            self.status.set("That image could not be opened. Choose a PNG or GIF.")

    def start(self):
        language = self.language.get()
        if language not in LANGUAGES:
            self.status.set("Choose your preferred language first.")
            self.language.focus_set()
            return
        if self.photo is None:
            self.status.set("Choose a photo for your focus reminders first.")
            self.choose_photo()
            if self.photo is None:
                return
        self.app_rules, self.title_rules = terms(self.apps.get()), terms(self.titles.get())
        if not self.app_rules and not self.title_rules:
            self.status.set("Enter at least one app name or window-title fragment.")
            return
        try:
            key = get_api_key()
        except (RuntimeError, OSError):
            self.status.set("Save your Sarvam key in .env before starting.")
            return
        self.session += 1
        session = self.session
        self.cancelled = cancelled = threading.Event()
        self.pending = True
        self.set_controls(False)
        self.status.set("Preparing your patrol: one chat request + three speech requests...")

        def work():
            try:
                result = prepare_session(key, language, cancelled)
                self.results.put((session, result, None))
            except Exception as error:
                # Never display request bodies, headers or the API key in UI errors.
                self.results.put((session, None, preparation_error(error)))

        threading.Thread(target=work, daemon=True).start()

    def set_controls(self, enabled):
        for widget in (self.apps, self.titles, self.photo_button, self.start_button):
            widget.configure(state="normal" if enabled else "disabled")
        self.language.configure(state="readonly" if enabled else "disabled")

    def poll(self):
        while not self.results.empty():
            session, result, error = self.results.get_nowait()
            if session != self.session:
                continue
            self.pending = False
            if error or result is None:
                self.set_controls(True)
                self.status.set(error or "Preparation cancelled.")
                continue
            self.lines, audio = result
            self.sounds = []
            try:
                for index, data in enumerate(audio):
                    path = Path(self.audio_dir.name) / f"{session}-{index}.wav"
                    path.write_bytes(data)
                    self.sounds.append(path)
                with wave.open(io.BytesIO(audio[-1]), "rb") as clip:
                    self.repeat_interval = max(25, clip.getnframes() / clip.getframerate() + 3)
            except OSError:
                self.status.set("Could not prepare local audio files. Check temporary-folder access.")
                self.set_controls(True)
                continue
            self.running, self.patrol = True, Patrol()
            self.status.set("ON DUTY. Open a watched app or title to arm the patrol.")
        if self.running and not self.locked:
            foreground = self.desktop.foreground()
            if foreground:
                allowed = matches(*foreground, self.app_rules, self.title_rules)
                stage = self.patrol.observe(allowed)
                if stage:
                    self.show_warning(stage)
                elif allowed:
                    self.clear_alerts()
                    self.status.set(f"ON TARGET / departures: {self.patrol.strikes}. Hold your position.")
        if self.running and self.locked:
            elapsed = time.monotonic() - self.locked_at
            if elapsed >= 30 and not self.executed:
                self.executed = True
                self.agent_sprite.destroy()
                self.agent_sprite = guard(self.agent_frame, captive=True, deleted=True)
                self.agent_sprite.pack()
                self.agent_status.set("AGENT 404: 'DELETED'\nOnly pixels. Apologise to restore.")
            elif not self.executed:
                self.agent_status.set(f"FICTIONAL HOSTAGE / {max(0, 30 - int(elapsed)):02}s\nAgent 404 is on the chopping block.")
            if time.monotonic() >= self.repeat_at:
                self.play(3)
                self.repeat_at = time.monotonic() + self.repeat_interval
        self.root.after(350, self.poll)

    def play(self, stage):
        sting = SFX[stage - 1] if stage < 3 else random.choice(SFX[2:])
        self.audio.play(self.sounds[stage - 1], SFX_DIR / sting)

    def clear_alerts(self):
        for popup in self.alerts:
            if popup.winfo_exists():
                popup.destroy()
        self.alerts.clear()

    def show_warning(self, stage):
        self.clear_alerts()
        self.locked = stage == 3
        if self.locked:
            self.locked_at = time.monotonic()
            self.repeat_at, self.executed = self.locked_at + self.repeat_interval, False
        self.status.set(f"DEPARTURE {stage} / {'COURT-MARTIAL' if self.locked else 'RETURN TO YOUR POST'}")
        headings = ("WARNING / STAY ON TASK", "SECOND STRIKE / REALLY?", "COURT-MARTIAL / THREE STRIKES")
        message = self.lines[("warning", "taunt", "last")[stage - 1]]
        count = 3 if self.locked else 1
        for index in range(count):
            popup = tk.Toplevel(self.root, bg=BG)
            popup.title(f"CHODBAK // {headings[stage - 1]} // {index + 1}")
            popup.attributes("-topmost", True)
            popup.resizable(False, False)
            width = 390
            screen_w, screen_h = popup.winfo_screenwidth(), popup.winfo_screenheight()
            x = max(0, min(screen_w - width - 20, (screen_w - width) // 2 + (index - 1) * 120))
            y = max(0, min(screen_h - 580, (screen_h - 580) // 2 + index * 70))
            popup.geometry(f"+{x}+{y}")
            popup.protocol("WM_DELETE_WINDOW", self.closed_locked_popup if self.locked else self.clear_alerts)
            self.alerts.append(popup)
            box = tk.Frame(popup, bg=PANEL, highlightthickness=3, highlightbackground=RED if self.locked else GOLD)
            box.pack(fill="both", expand=True, padx=10, pady=10)
            self.label(box, headings[stage - 1], ("Consolas", 11, "bold"), RED if self.locked else GOLD, PANEL).pack(padx=16, pady=14)
            if self.locked and index == 0:
                tk.Label(box, image=self.photo, bg="#c7ae70", padx=10, pady=10).pack(padx=15)
                self.label(box, self.lines["caption"], BODY, GOLD, PANEL).pack(padx=16, pady=8)
            elif self.locked and index == 1:
                self.agent_frame = tk.Frame(box, bg=PANEL)
                self.agent_frame.pack()
                self.agent_sprite = guard(self.agent_frame, captive=True)
                self.agent_sprite.pack()
                self.agent_status = tk.StringVar(value="FICTIONAL HOSTAGE / 30s")
                tk.Label(box, textvariable=self.agent_status, bg=PANEL, fg=GOLD, font=MONO).pack(padx=12, pady=10)
                self.label(box, self.lines["hostage"], BODY, INK, PANEL).pack(padx=16, pady=4)
            else:
                guard(box, 5).pack()
            tk.Label(box, text=message, wraplength=330, justify="center", bg=PANEL,
                     fg=INK, font=("Nirmala UI", 13, "bold")).pack(padx=18, pady=14)
            if self.locked:
                self.label(box, f'Type "{PHRASE}" to end the session.', ("Nirmala UI", 10), GOLD, PANEL).pack(padx=12)
                entry = self.entry(box)
                entry.pack(fill="x", padx=20, pady=10)
                entry.bind("<Return>", lambda event, field=entry: self.apologise(field.get()))
                self.button(box, "APOLOGISE + END SESSION", lambda field=entry: self.apologise(field.get()), GREEN, BG).pack(fill="x", padx=20, pady=(0, 8))
                if index == count - 1:
                    popup.after(100, entry.focus_force)
            else:
                self.button(box, "DISMISS", self.clear_alerts, GREEN, BG).pack(fill="x", padx=20, pady=(0, 12))
            self.button(box, "EMERGENCY STOP / ESC", self.stop, PANEL, MUTED).pack(padx=12, pady=(0, 10))
        self.play(stage)

    def closed_locked_popup(self):
        self.status.set(f'Type "{PHRASE}" in any popup, or use Emergency Stop.')

    def apologise(self, text):
        if apologised(text):
            self.stop("APOLOGY ACCEPTED. Agent 404 restored. Session ended.")
        else:
            self.status.set(f'Enter exactly "{PHRASE}" and press Enter.')

    def stop(self, message="OFF DUTY. Patrol and audio stopped."):
        self.cancelled.set()
        self.session += 1
        self.running = self.pending = self.locked = False
        self.audio.stop()
        self.clear_alerts()
        self.patrol = Patrol()
        self.set_controls(True)
        self.status.set(message)

    def close(self):
        self.stop()
        self.audio_dir.cleanup()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Chodbak(root)
    root.mainloop()
